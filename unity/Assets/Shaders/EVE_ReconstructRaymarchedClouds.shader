Shader "EVE/ReconstructRaymarchedClouds"
{
    // Tweak build: the recovered GLSL variant (one pass) plus a depth-aware
    // upsample of the low-resolution ray buffer in the off-centre branch.
    // The C# renderer draws this with three different passes 0/1/2 on the
    // original; the recovered variant has a single pass, which is equivalent
    // because the original clamps the missing pass index back to pass 0.
    SubShader
    {
        Cull Off
        ZWrite Off
        ZTest Always
        Blend Off

        Pass
        {
            Name "ReconstructRaymarchedClouds"

            HLSLPROGRAM
            #pragma vertex   VS_ReconstructRaymarchedClouds
            #pragma fragment PS_ReconstructRaymarchedClouds
            #pragma target 5.0

            // Declared so the C# EnableKeyword calls stay harmless. The recovered
            // variant carries no painter/lightning unstable-mask code, so all
            // four variants compile to the same instructions.
            #pragma multi_compile PAINTER_UNSTABLE_MASK_OFF PAINTER_UNSTABLE_MASK_ON
            #pragma multi_compile LIGHTNING_UNSTABLE_MASK_OFF LIGHTNING_UNSTABLE_MASK_ON

            #include "ReconstructRaymarchedClouds.hlsl"
            ENDHLSL
        }
    }
}
