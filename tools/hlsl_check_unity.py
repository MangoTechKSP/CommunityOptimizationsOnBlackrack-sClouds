"""Compile the flattened tweak shaders without Unity's CGIncludes.

tools/hlsl_check.py hands the source to D3DCompile with no include handler, so a
`#include "UnityCG.cginc"` line breaks it. This wrapper swaps that include for
hand-written stubs of exactly the Unity builtins the shaders use, so the rest of
the file (all of the ported math) is still compiled for real.

Usage: python tools/hlsl_check_unity.py <flat.hlsl> <vs_entry> <ps_entry>
"""
import ctypes
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hlsl_check  # noqa: E402

STUBS = """// [hlsl_check_unity] stubs for the UnityCG.cginc builtins
// Keep this list equal to the builtins the two shaders actually reference:
//   grep -oE "_ProjectionParams|_ScreenParams|_ZBufferParams|_WorldSpaceCameraPos|unity_MatrixVP|unity_CameraInvProjection" <flat.hlsl>
float4 _ProjectionParams;
float3 _WorldSpaceCameraPos;
float4 _ZBufferParams;
float4x4 unity_MatrixVP;
float4x4 unity_CameraInvProjection;

// The authored shaders (ground shadow, sky optics) use the blit vertex path and
// Unity's depth helper, which the ported files do not touch.
struct appdata_img
{
    float4 vertex : POSITION;
    float2 texcoord : TEXCOORD0;
};

float4 UnityObjectToClipPos(float4 position) { return position; }

float LinearEyeDepth(float depth) { return 1.0 / (_ZBufferParams.z * depth + _ZBufferParams.w); }
"""


def main():
    path, vs, ps = sys.argv[1], sys.argv[2], sys.argv[3]
    text = open(path, encoding="utf-8-sig").read()
    text, n = re.subn(r'^[ \t]*#include[ \t]+"UnityCG\.cginc"[ \t]*\n', "", text, flags=re.M)
    src = (STUBS + text).encode("utf-8")
    dll = ctypes.WinDLL("d3dcompiler_47.dll")
    dll.D3DCompile.restype = ctypes.c_long
    print("include lines stubbed: %d" % n)
    bad = 0
    for entry, target in ((vs, "vs_5_0"), (ps, "ps_5_0")):
        hr, err = hlsl_check.compile_stage(dll, src, entry, target)
        ok = hr == 0
        print("=== %s (%s): %s" % (entry, target, "OK" if ok else "FAIL hr=0x%08x" % (hr & 0xffffffff)))
        if not ok:
            bad += 1
            print(err.strip())
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
