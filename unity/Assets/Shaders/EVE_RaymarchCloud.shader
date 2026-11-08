Shader "EVE/RaymarchCloud"
{
    // Tweak build: identical code path to the recovered GLSL variant, plus two
    // early-outs in RaymarchCloud.hlsl. All state is opaque/no-depth so the
    // fullscreen quad always runs.
    SubShader
    {
        Cull Off
        ZWrite Off
        ZTest Always
        Blend Off

        Pass
        {
            Name "RaymarchCloud"

            HLSLPROGRAM
            #pragma vertex   VS_RaymarchCloud
            #pragma fragment PS_RaymarchCloud
            #pragma target 5.0

            // The recovered variant has no light-volume path; both keywords are
            // declared so the C# EnableKeyword calls stay harmless and the two
            // variants stay code-identical.
            #pragma multi_compile LIGHT_VOLUME_OFF LIGHT_VOLUME_ON
            #pragma multi_compile DISCRETE_LIGHT_SAMPLES_OFF DISCRETE_LIGHT_SAMPLES_ON

            #include "RaymarchCloud.hlsl"
            ENDHLSL
        }
    }
}
