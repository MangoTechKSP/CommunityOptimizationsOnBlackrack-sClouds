Shader "EVE/RaymarchedCloudShadow"
{
    // Ground shadow cast by the raymarched cloud layers. Two passes: build a
    // quarter-resolution sun-reachability mask, then multiply the frame by it.
    // Authored for this fork; there is no stock shader to port (the stock ground
    // shadow is the 2D screen-space one in EVE/ScreenSpaceCloudShadow).
    SubShader
    {
        Cull Off
        ZWrite Off
        ZTest Always

        Pass
        {
            Name "ShadowMask"

            Blend Off

            HLSLPROGRAM
            #pragma vertex   VS_ShadowMask
            #pragma fragment PS_ShadowMask
            #pragma target 5.0

            #include "RaymarchedCloudShadow.hlsl"
            ENDHLSL
        }

        Pass
        {
            Name "ShadowDarken"

            // Multiplies the destination by the mask without reading it:
            // dst * (1 - a) with a = 1 - sunReach.
            Blend SrcAlpha OneMinusSrcAlpha

            HLSLPROGRAM
            #pragma vertex   VS_ShadowDarken
            #pragma fragment PS_ShadowDarken
            #pragma target 5.0

            #include "RaymarchedCloudShadow.hlsl"
            ENDHLSL
        }
    }
}
