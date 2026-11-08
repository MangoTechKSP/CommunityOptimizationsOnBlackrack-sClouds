// ============================================================================
// SkyOptics - 22 degree ice halo and the primary/secondary rainbow.
//
// Authored for this fork: neither effect exists in the stock EVE shaders, and
// neither belongs inside the cloud shader (a rainbow has to be visible where
// there are no clouds, and it has to survive on top of Scatterer's atmosphere,
// which is drawn at BeforeForwardAlpha -- so this pass runs later than that).
//
// Both effects are pure geometry on the view ray:
//   * halo:   angle from the *sun*    ~ 22 degrees, red inside, blue outside
//   * bow:    angle from the *antisolar point*  ~ 42 degrees (primary, red
//             outside) and ~ 51 degrees (secondary, colour order reversed,
//             about 1/8 the brightness), with Alexander's dark band between
//             them falling out of the maths for free.
//
// Drawn as an additive fullscreen quad with a depth test against the scene, so
// terrain and the sun disc keep their pixels. Everything scales with two
// strengths; 0 on both makes the pass a no-op (the C# side then skips it).
// ============================================================================

#include "UnityCG.cginc"

float4x4 CameraToWorld;

float4 _SkySunDir;        // world space, planet -> sun, unit
float4 _SkyUpDir;         // world space "up" at the camera (camera position - planet centre)
float _SkyHaloStrength;   // 0 disables the halo
float _SkyRainbowStrength;// 0 disables the bow
float _SkySunElevation;   // degrees, negative below the horizon (set from C# so both
                          // shader and C# agree on the gate)

// Bound by the cloud renderer for this blit only; deliberately not _CameraDepthTexture, because
// overwriting that mid-frame would change what the composite and ground shadow read.
Texture2D _SkyDepthTexture : register(t0);

SamplerState sampler_point_clamp;

struct v2f_optics
{
    float4 position : SV_POSITION;
    float2 uv : TEXCOORD0;
};

v2f_optics VS_SkyOptics(appdata_img input)
{
    v2f_optics output;
    output.position = UnityObjectToClipPos(input.vertex);
    output.uv = input.texcoord;
    return output;
}

/// World-space direction of the ray through a screen uv.
static float3 eve_view_ray(float2 uv)
{
    float2 ndc = uv * float2(2.0, 2.0) + float2(-1.0, -1.0);
    float4 clipView = ndc.yyyy * unity_CameraInvProjection[1];
    clipView = unity_CameraInvProjection[0] * ndc.xxxx + clipView;
    clipView = clipView + unity_CameraInvProjection[2];
    clipView = clipView + unity_CameraInvProjection[3];

    float4 world = clipView.yyyy * CameraToWorld[1];
    world = CameraToWorld[0] * clipView.xxxx + world;
    world = CameraToWorld[2] * clipView.zzzz + world;
    clipView = CameraToWorld[3] * clipView.wwww + world;
    return normalize(clipView.xyz / clipView.www);
}

/// Gaussian ring of half-width `sigma` (degrees) centred on `radiusDegrees`.
static float eve_ring(float angle, float radiusDegrees, float sigma)
{
    float offset = (angle - radiusDegrees) / sigma;
    return exp(-offset * offset);
}

float4 PS_SkyOptics(v2f_optics input) : SV_Target
{
    // Only sky pixels: an additive pass over terrain or a hull would look painted on.
    float rawDepth = _SkyDepthTexture.SampleLevel(sampler_point_clamp, input.uv, 0.0).x;
    if (LinearEyeDepth(rawDepth) < _ProjectionParams.z * 0.999)
    {
        return float4(0.0, 0.0, 0.0, 1.0);
    }

    float3 viewDir = eve_view_ray(input.uv);
    float3 sunDir = normalize(_SkySunDir.xyz);
    float3 upDir = normalize(_SkyUpDir.xyz);

    float3 color = float3(0.0, 0.0, 0.0);

    //--------------------------------------------------------------------
    // 22 degree halo. Radii are the classic 21.8 (red, inside) to 22.4
    // (blue, outside) dispersion; the ring is narrow because ice crystals
    // are, and a broad faint glow around it keeps it from looking like a
    // decal.
    //--------------------------------------------------------------------
    float haloStrength = saturate(_SkyHaloStrength);
    if (haloStrength > 0.0)
    {
        float sunAngle = degrees(acos(clamp(dot(viewDir, sunDir), -1.0, 1.0)));

        float haloRed = eve_ring(sunAngle, 21.7000008, 0.449999988);
        float haloGreen = eve_ring(sunAngle, 22.1000004, 0.5);
        float haloBlue = eve_ring(sunAngle, 22.3999996, 0.550000012);
        float3 haloRing = float3(haloRed, haloGreen, haloBlue);

        // A wide, very faint glow inside the ring: sun dogs and the diffuse
        // scattering that makes a halo read as light rather than as a line.
        float haloGlow = eve_ring(sunAngle, 22.0, 4.5) * 0.150000006;

        // Halos need the sun above the horizon and fade as it climbs.
        float haloGate = saturate((_SkySunElevation + 1.0) / 4.0);
        haloGate = haloGate * (1.0 - saturate((_SkySunElevation - 55.0) / 20.0));

        color = color + (haloRing * 0.800000012 + haloGlow) * (haloStrength * haloGate);
    }

    //--------------------------------------------------------------------
    // Rainbow: angular distance from the antisolar point.
    //--------------------------------------------------------------------
    float bowStrength = saturate(_SkyRainbowStrength);
    if (bowStrength > 0.0)
    {
        float antiAngle = degrees(acos(clamp(dot(viewDir, -sunDir), -1.0, 1.0)));

        // Primary bow: red outside (42.4), blue inside (40.4).
        float primaryRed = eve_ring(antiAngle, 42.4000015, 1.20000005);
        float primaryGreen = eve_ring(antiAngle, 41.4000015, 1.20000005);
        float primaryBlue = eve_ring(antiAngle, 40.4000015, 1.20000005);

        // Secondary bow: colour order reversed, wider and much fainter.
        float secondaryRed = eve_ring(antiAngle, 50.4000015, 1.60000002);
        float secondaryGreen = eve_ring(antiAngle, 51.4000015, 1.60000002);
        float secondaryBlue = eve_ring(antiAngle, 52.4000015, 1.60000002);

        // A faint wide glow inside the primary bow: the inside of a real bow is brighter than the
        // sky around it, and without it the ring reads as a decal.
        float primaryGlow = eve_ring(antiAngle, 41.4000015, 3.20000005) * 0.100000001;

        float3 primary = float3(primaryRed, primaryGreen, primaryBlue) + primaryGlow;
        float3 secondary = float3(secondaryRed, secondaryGreen, secondaryBlue) * 0.119999997;

        // Alexander's dark band: a gentle dip between the two bows, which is
        // what the eye actually uses to tell a real rainbow from a gradient.
        float darkBand = 1.0 - eve_ring(antiAngle, 46.0, 2.6) * 0.550000012;

        // A bow needs the sun low and the antisolar point above the horizon.
        float bowGate = saturate((42.0 - _SkySunElevation) / 8.0);
        bowGate = bowGate * saturate((_SkySunElevation + 2.0) / 4.0);

        color = color + (primary + secondary) * (darkBand * bowStrength * bowGate);
    }

    // Additive: alpha is unused, but 1 keeps a future Lerp-blend variant sane.
    return float4(color, 1.0);
}
