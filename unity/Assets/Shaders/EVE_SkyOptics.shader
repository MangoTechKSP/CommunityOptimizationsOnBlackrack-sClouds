Shader "EVE/SkyOptics"
{
    // 22 degree halo and the rainbow, drawn additively on top of the atmosphere.
    // Authored for this fork; the stock EVE bundle has neither effect.
    SubShader
    {
        Cull Off
        ZWrite Off
        ZTest Always

        Pass
        {
            Name "SkyOptics"

            Blend One One

            HLSLPROGRAM
            #pragma vertex   VS_SkyOptics
            #pragma fragment PS_SkyOptics
            #pragma target 5.0

            #include "SkyOptics.hlsl"
            ENDHLSL
        }
    }
}
