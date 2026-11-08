// ============================================================================
// RaymarchedCloudShadow - ground shadow cast by the raymarched cloud layers.
//
// Written for this fork (there is no stock GLSL to port): EVE's stock ground
// shadow is the screen-space `EVE/ScreenSpaceCloudShadow`, driven by the 2D
// cloud maps, so the volumetric layers never darkened the ground at all.
//
// Pass 0 builds a low-resolution "how much sun reaches the ground here" mask by
// projecting each ground pixel along the sun onto the layer's mid shell and
// reading that layer's coverage map. It is a coverage approximation, not a
// density march: the shadow is soft and lines up with the visible cloud field
// (the same coverage map that shapes the render), but it cannot resolve
// individual puffs. Soft is what a 20 km deck casts anyway.
//
// Pass 1 multiplies the frame by that mask with an alpha blend, so the pass
// never reads the colour buffer (SrcAlpha/OneMinusSrcAlpha does the multiply on
// the blend unit) and there is no read-write hazard on the current target.
//
// Both passes run inside a command buffer, pass 0 into a quarter-resolution R8
// target and pass 1 full screen.
// ============================================================================

#include "UnityCG.cginc"

// ---------------------------------------------------------------------------
// Reconstruction. Same derivation as ReconstructRaymarchedClouds.hlsl (which is
// the ported stock code): ndc xy through the inverse projection to get a view
// ray, the linearised depth for the distance, then the ray through
// CameraToWorld. `CameraToWorld` is a material matrix, the rest are builtins.
// ---------------------------------------------------------------------------
float4x4 CameraToWorld;
float4 _ShadowSunDir;                       // world space, planet -> sun, unit
float4 _ShadowPlanetCenter;                 // world space planet centre (the layers' sphereCenter)

float _ShadowLayerCount;                    // 0..2

float4 _ShadowCenter0;
float4 _ShadowCenter1;
float _ShadowInnerRadius0;
float _ShadowInnerRadius1;
float _ShadowMidRadius0;                    // (inner + outer) * 0.5
float _ShadowMidRadius1;
float _ShadowCoverageScale0;                // coverage -> extinction, 0 disables the layer
float _ShadowCoverageScale1;
float4x4 _ShadowRotation0;
float4x4 _ShadowRotation1;

float _ShadowStrength;                      // 0..1, the "clouds on the ground" knob
float _ShadowSunUp;                         // saturate(dot(sun, up)): no shadow at night

// Explicit sampler states: the mask pass must read depth at exact texels (point) and the
// darken pass gets its smoothness from bilinear upsampling of the quarter-resolution mask.
SamplerState sampler_point_clamp;
SamplerState sampler_linear_clamp;

Texture2D _CameraDepthTexture : register(t0);
Texture2D _ShadowCov0xn : register(t1);
Texture2D _ShadowCov0xp : register(t2);
Texture2D _ShadowCov0yn : register(t3);
Texture2D _ShadowCov0yp : register(t4);
Texture2D _ShadowCov0zn : register(t5);
Texture2D _ShadowCov0zp : register(t6);
Texture2D _ShadowCov1xn : register(t7);
Texture2D _ShadowCov1xp : register(t8);
Texture2D _ShadowCov1yn : register(t9);
Texture2D _ShadowCov1yp : register(t10);
Texture2D _ShadowCov1zn : register(t11);
Texture2D _ShadowCov1zp : register(t12);

Texture2D _MainTex;                        // pass 1: the mask built by pass 0

// ---------------------------------------------------------------------------
// Cube-face lookup. This is the same lattice the ported raymarcher uses for its
// own coverage fetches (the `.yxyz` swizzle and the sign/selector dance), kept
// verbatim so the shadow samples the texels the renderer sampled. It is
// duplicated rather than shared because EVE/RaymarchCloud.hlsl is a generated
// file and pulls in nothing but UnityCG.
// ---------------------------------------------------------------------------
static float2 eve_face_uv(float3 localPosition, out float signValue, out float2 selector)
{
    float radius = length(localPosition);
    float4 cubeCoords = localPosition.yxyz / radius;

    float dirInvLen = dot(cubeCoords.yzw, cubeCoords.yzw);
    dirInvLen = rsqrt(dirInvLen);
    float3 faceDir = float3(dirInvLen, dirInvLen, dirInvLen) * cubeCoords.zyw;

    bool axisZ = abs(faceDir.z) >= abs(faceDir.y);
    float maxYZ = max(abs(faceDir.z), abs(faceDir.y));
    bool axisX = maxYZ >= abs(faceDir.x);
    float2 faceSel;
    faceSel.x = (axisZ) ? 1.0 : 0.0;
    faceSel.y = (axisX) ? 1.0 : 0.0;

    float faceCoord = cubeCoords.w * dirInvLen + (-faceDir.y);
    faceCoord = faceSel.x * faceCoord + faceDir.y;
    dirInvLen = (-cubeCoords.z) * dirInvLen + faceCoord;
    dirInvLen = faceSel.y * dirInvLen + faceDir.x;

    int signNeg = (0.0 < dirInvLen) ? int(0xFFFFFFFFu) : 0;
    int signPos = (dirInvLen < 0.0) ? int(0xFFFFFFFFu) : 0;
    signPos = (-signNeg) + signPos;

    float4 signVec;
    signVec.x = 1.0;
    signVec.z = -1.0;
    signVec.y = float(signPos);
    signVec.w = 0.0;

    float4 negSignVec;
    negSignVec.x = 1.0;
    negSignVec.z = -1.0;
    negSignVec.y = (-signVec.y);
    negSignVec.w = 0.0;

    float3 tangent0 = negSignVec.xyz * faceDir.yzx;
    float3 tangent1 = signVec.xyz * faceDir.zyx + (-tangent0);
    tangent0 = faceSel.xxx * tangent1 + tangent0;
    tangent1 = signVec.xxy * faceDir.xyz;
    faceDir = (-signVec.xxy) * faceDir.xyz + tangent0;
    faceDir = faceSel.yyy * faceDir + tangent1;

    float2 faceUV;
    faceUV.xy = faceDir.yz * float2(0.5, 0.5);
    faceUV.xy = faceUV.xy / abs(faceDir.xx);
    faceUV.xy = faceUV.xy + float2(0.5, 0.5);

    signValue = (signVec.y >= 0.0) ? 1.0 : 0.0;
    selector = faceSel;
    return faceUV;
}

static float eve_blend_faces(float4 xn, float4 xp, float4 yn, float4 yp, float4 zn, float4 zp,
                             float signValue, float2 selector)
{
    float4 faceSign = float4(signValue, signValue, signValue, signValue);

    float4 blendedX = (-xn) + xp;
    blendedX = faceSign * blendedX + xn;
    float4 blendedY = (-yn) + yp;
    blendedY = faceSign * blendedY + yn;
    float4 blendedZ = (-zn) + zp;
    blendedZ = faceSign * blendedZ + zn;

    blendedZ = (-blendedX) + blendedZ;
    blendedX = float4(selector.x, selector.x, selector.x, selector.x) * blendedZ + blendedX;
    blendedX = (-blendedY) + blendedX;
    blendedX = float4(selector.y, selector.y, selector.y, selector.y) * blendedX + blendedY;
    return blendedX;
}

/// Coverage (0..1) of one layer at a point in that layer's cloud space.
static float eve_layer_coverage(float3 localPosition, bool secondLayer)
{
    float signValue;
    float2 selector;
    float2 faceUV = eve_face_uv(localPosition, signValue, selector);
    float4 coverage;
    if (!secondLayer)
    {
        coverage = eve_blend_faces(
            _ShadowCov0xn.SampleLevel(sampler_point_clamp, faceUV, 0.0),
            _ShadowCov0xp.SampleLevel(sampler_point_clamp, faceUV, 0.0),
            _ShadowCov0yn.SampleLevel(sampler_point_clamp, faceUV, 0.0),
            _ShadowCov0yp.SampleLevel(sampler_point_clamp, faceUV, 0.0),
            _ShadowCov0zn.SampleLevel(sampler_point_clamp, faceUV, 0.0),
            _ShadowCov0zp.SampleLevel(sampler_point_clamp, faceUV, 0.0),
            signValue, selector);
    }
    else
    {
        coverage = eve_blend_faces(
            _ShadowCov1xn.SampleLevel(sampler_point_clamp, faceUV, 0.0),
            _ShadowCov1xp.SampleLevel(sampler_point_clamp, faceUV, 0.0),
            _ShadowCov1yn.SampleLevel(sampler_point_clamp, faceUV, 0.0),
            _ShadowCov1yp.SampleLevel(sampler_point_clamp, faceUV, 0.0),
            _ShadowCov1zn.SampleLevel(sampler_point_clamp, faceUV, 0.0),
            _ShadowCov1zp.SampleLevel(sampler_point_clamp, faceUV, 0.0),
            signValue, selector);
    }
    // Same lane the renderer reads (the coverage alpha channel is the density weight).
    return saturate(coverage.w);
}

/// World -> cloud space for one layer, using the same row convention as the
/// material's `cloudRotation` in the raymarcher.
static float3 eve_cloud_space(float3 worldPosition, float4x4 rotation, float4 center)
{
    float3 offset = worldPosition - center.xyz;
    float3 outPosition = rotation[1].xyz * offset.yyy;
    outPosition = rotation[0].xyz * offset.xxx + outPosition;
    outPosition = rotation[2].xyz * offset.zzz + outPosition;
    return outPosition + rotation[3].xyz;
}

/// Where the sun ray from `groundPosition` crosses the layer's mid shell, or a
/// miss when the ground is already inside the shell (or the ray goes away).
static bool eve_shell_hit(float3 groundPosition, float3 sunDir, float3 center, float midRadius, out float3 hitPosition)
{
    float3 toCenter = groundPosition - center;
    float along = dot(toCenter, sunDir);
    float outside = dot(toCenter, toCenter) - midRadius * midRadius;
    float discriminant = along * along - outside;
    hitPosition = groundPosition;
    if (discriminant <= 0.0)
    {
        return false;
    }
    float distance = -along + sqrt(discriminant);
    if (distance <= 0.0)
    {
        return false;
    }
    hitPosition = groundPosition + sunDir * distance;
    return true;
}

// ---------------------------------------------------------------------------
// Vertex stages. Both passes are drawn with Graphics.Blit, so the vertex
// stream is Unity's fullscreen quad and UnityObjectToClipPos maps it to the
// viewport.
// ---------------------------------------------------------------------------
struct v2f_shadow
{
    float4 position : SV_POSITION;
    float2 uv : TEXCOORD0;
};

/// Pass 0 vertex.
v2f_shadow VS_ShadowMask(appdata_img input)
{
    v2f_shadow output;
    output.position = UnityObjectToClipPos(input.vertex);
    output.uv = input.texcoord;
    return output;
}

/// Pass 1 vertex (same geometry, separate entry so both passes can share this file).
v2f_shadow VS_ShadowDarken(appdata_img input)
{
    v2f_shadow output;
    output.position = UnityObjectToClipPos(input.vertex);
    output.uv = input.texcoord;
    return output;
}

// ---------------------------------------------------------------------------
// Pass 0: how much sun reaches the ground, 1 = unshadowed.
// ---------------------------------------------------------------------------
float PS_ShadowMask(v2f_shadow input) : SV_Target
{
    float rawDepth = _CameraDepthTexture.SampleLevel(sampler_point_clamp, input.uv, 0.0).x;

    // The ported depth convention (`_ZBufferParams.x * d + _ZBufferParams.y`) yields a 0..1
    // fraction of the far plane, which the reconstruct pass then scales by `far`. Sky pixels sit
    // at 1.0 and carry no ground.
    float viewDistance01 = 1.0 / (_ZBufferParams.x * rawDepth + _ZBufferParams.y);
    if (viewDistance01 > 0.999)
    {
        return 1.0;
    }

    // Rebuild the world position exactly like the reconstruct pass does.
    float2 screenUV = input.uv;
    float2 ndc = screenUV * float2(2.0, 2.0) + float2(-1.0, -1.0);

    float4 sceneClip = ndc.yyyy * unity_CameraInvProjection[1];
    sceneClip = unity_CameraInvProjection[0] * ndc.xxxx + sceneClip;
    sceneClip = unity_CameraInvProjection[2] * rawDepth + sceneClip;
    sceneClip = sceneClip + unity_CameraInvProjection[3];

    float3 viewDir = sceneClip.xyz / sceneClip.www;
    viewDir = normalize(viewDir);
    float3 depthScaled = viewDistance01 * viewDir;
    float3 sceneRay = depthScaled / (-viewDir.zzz);
    sceneRay = sceneRay * _ProjectionParams.zzz;

    float4 sceneWorld = sceneRay.yyyy * CameraToWorld[1];
    sceneWorld = CameraToWorld[0] * sceneRay.xxxx + sceneWorld;
    sceneWorld = CameraToWorld[2] * sceneRay.zzzz + sceneWorld;
    sceneWorld = sceneWorld + CameraToWorld[3];
    float3 groundPosition = sceneWorld.xyz / sceneWorld.www;

    float3 sunDir = normalize(_ShadowSunDir.xyz);
    float transmittance = 1.0;

    // Layer 0.
    float3 hitPosition;
    if (_ShadowLayerCount > 0.5 && _ShadowCoverageScale0 > 0.0)
    {
        if (eve_shell_hit(groundPosition, sunDir, _ShadowCenter0.xyz, _ShadowMidRadius0, hitPosition))
        {
            float coverage = eve_layer_coverage(eve_cloud_space(hitPosition, _ShadowRotation0, _ShadowCenter0), false);
            transmittance *= exp(-coverage * _ShadowCoverageScale0);
        }
    }

    // Layer 1.
    if (_ShadowLayerCount > 1.5 && _ShadowCoverageScale1 > 0.0)
    {
        if (eve_shell_hit(groundPosition, sunDir, _ShadowCenter1.xyz, _ShadowMidRadius1, hitPosition))
        {
            float coverage = eve_layer_coverage(eve_cloud_space(hitPosition, _ShadowRotation1, _ShadowCenter1), true);
            transmittance *= exp(-coverage * _ShadowCoverageScale1);
        }
    }

    // `_ShadowSunUp` kills the effect at night (and near the terminator), `_ShadowStrength`
    // is the user's knob: 0 means "no shadow on the ground".
    float unshadowed = 1.0;
    float shadowed = lerp(transmittance, 1.0, 1.0 - saturate(_ShadowStrength) * saturate(_ShadowSunUp));
    return saturate(shadowed);
}

// ---------------------------------------------------------------------------
// Pass 1: darken the frame by (1 - mask), leaving the cloud pass untouched
// because this buffer runs before the cloud composite.
// ---------------------------------------------------------------------------
float4 PS_ShadowDarken(v2f_shadow input) : SV_Target
{
    float sunReach = _MainTex.SampleLevel(sampler_linear_clamp, input.uv, 0.0).r;
    return float4(0.0, 0.0, 0.0, saturate(1.0 - sunReach));
}
