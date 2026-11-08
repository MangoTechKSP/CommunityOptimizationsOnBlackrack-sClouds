"""Prepare the recovered HLSL for Unity: flatten cbuffers, rewrite sampler states.

Usage:
    python tools/flatten_cbuffer.py                      # both known shaders
    python tools/flatten_cbuffer.py <src> <dst>
"""
import re, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Unity only accepts a SamplerState whose name is an inline sampler name
# (filter+wrap), or one bound to a texture property. The recovered GLSL used
# UNITY_LOCATION(n) units, so the port declares one SamplerState per texture.
# Rewrite them to the two inline states the shader actually needs, longest
# names first so "samplerNewRaysBufferBilinear" is not eaten by the shorter key.
SAMPLER_MAP = [
    ("samplerCameraDepthTexture", "sampler_point_clamp"),
    ("samplerNewRaysMotionVectors", "sampler_point_clamp"),
    ("samplerHistoryMotionVectors", "sampler_point_clamp"),
    ("samplerNewRaysSecondaryBufferBilinear", "sampler_linear_clamp"),
    ("samplerNewRaysSecondaryBuffer", "sampler_point_clamp"),
    ("samplerNewRaysBufferBilinear", "sampler_linear_clamp"),
    ("samplerNewRaysBuffer", "sampler_point_clamp"),
    ("samplerHistorySecondaryBuffer", "sampler_point_clamp"),
    ("samplerHistoryBuffer", "sampler_point_clamp"),
]

# hlslcc prefixes every matrix uniform with "hlslcc_mtx4x4" and declares it as a
# loose float4[4]. Neither survives the D3D path: Unity binds matrices as
# float4x4, and the builtin matrices only get their values when they are the
# real Unity names declared by UnityCG.cginc. So the tweak copy renames them,
# lets UnityCG provide the camera matrices, and converts the 5 material matrices
# to float4x4. The original array indexing (M[1] = second *column* in the GLSL)
# is preserved through the ev_col0..3 helpers below, so no multiply site changes.
MATRIX_RENAMES = [
    ("hlslcc_mtx4x4unity_CameraInvProjection", "unity_CameraInvProjection"),
    ("hlslcc_mtx4x4unity_MatrixVP", "unity_MatrixVP"),
    ("hlslcc_mtx4x4CameraToWorld", "CameraToWorld"),
    ("hlslcc_mtx4x4currentVP", "currentVP"),
    ("hlslcc_mtx4x4previousVP", "previousVP"),
    ("hlslcc_mtx4x4cloudDetailRotation", "cloudDetailRotation"),
    ("hlslcc_mtx4x4cloudRotation", "cloudRotation"),
    ("hlslcc_mtx4x4shadowCasterCloudRotation", "shadowCasterCloudRotation"),
]
BUILTIN_MATRICES = ["unity_CameraInvProjection", "unity_MatrixVP"]
MATERIAL_MATRICES = ["CameraToWorld", "currentVP", "previousVP", "cloudRotation", "cloudDetailRotation",
                     "shadowCasterCloudRotation"]
ALL_MATRICES = BUILTIN_MATRICES + MATERIAL_MATRICES
# UnityCG.cginc already declares these; a second declaration is an error.
BUILTIN_SCALARS = ["_ProjectionParams", "_WorldSpaceCameraPos", "_ZBufferParams"]

UNITY_PRELUDE = """// [tweak-build] Unity builtin uniforms (camera matrices, _ProjectionParams,
// _WorldSpaceCameraPos) come from UnityCG.cginc. Declaring them by hand does not
// bind them on D3D: Unity only routes the names it knows to UnityPerCamera*.
#include "UnityCG.cginc"

// [tweak-build] The recovered GLSL indexes mat4 columns (M[1] = column 1) because
// hlslcc flattened each matrix into a float4[4] of columns. Unity binds matrices
// as float4x4, whose [i] is a *row*, so the column view is rebuilt here and every
// `NAME[i]` use becomes `ev_coli(NAME)`.
static float4 ev_col0(float4x4 m) { return float4(m._m00, m._m10, m._m20, m._m30); }
static float4 ev_col1(float4x4 m) { return float4(m._m01, m._m11, m._m21, m._m31); }
static float4 ev_col2(float4x4 m) { return float4(m._m02, m._m12, m._m22, m._m32); }
static float4 ev_col3(float4x4 m) { return float4(m._m03, m._m13, m._m23, m._m33); }
"""

DEFAULT_PAIRS = [
    (os.path.join(ROOT, "shaders", "hlsl", "RaymarchCloud.hlsl"),
     os.path.join(ROOT, "EVE-Tweak", "Assets", "Shaders", "RaymarchCloud.hlsl")),
    (os.path.join(ROOT, "shaders", "hlsl", "ReconstructRaymarchedClouds.hlsl"),
     os.path.join(ROOT, "EVE-Tweak", "Assets", "Shaders", "ReconstructRaymarchedClouds.hlsl")),
]

# Shaders authored for the fork after the port (ground shadow, sky optics) need no
# rewriting: they are already HLSL with Unity's names. They are copied verbatim so the
# Unity project always builds the same bytes that live under version control.
COPY_PAIRS = [
    (os.path.join(ROOT, "shaders", "hlsl", "RaymarchedCloudShadow.hlsl"),
     os.path.join(ROOT, "EVE-Tweak", "Assets", "Shaders", "RaymarchedCloudShadow.hlsl")),
    (os.path.join(ROOT, "shaders", "hlsl", "SkyOptics.hlsl"),
     os.path.join(ROOT, "EVE-Tweak", "Assets", "Shaders", "SkyOptics.hlsl")),
]


def flatten(src, dst):
    text = open(src, encoding="utf-8-sig").read().split("\n")
    out = []
    i = 0
    flattened = 0
    while i < len(text):
        line = text[i]
        m = re.match(r"^cbuffer\s+\w+\s*(:\s*register\(b\d+\))?\s*$", line.strip())
        if m:
            j = i + 1
            while text[j].strip() == "":
                j += 1
            assert text[j].strip() == "{", (i, text[j])
            out.append("// [tweak-build] cbuffer wrapper removed so Unity binds members by name")
            i = j + 1
            flattened += 1
            while True:
                l = text[i]
                if l.strip() == "};":
                    i += 1
                    break
                out.append(l)
                i += 1
            continue
        out.append(line)
        i += 1

    out_text = "\n".join(out)

    # Rename every sample call to an inline sampler state, then drop the
    # per-texture SamplerState declarations that Unity rejects.
    rewritten = 0
    for src_name, inline_name in SAMPLER_MAP:
        out_text, n = re.subn(r"\b%s\b" % src_name, inline_name, out_text)
        rewritten += n
    out_text = re.sub(r"^[ \t]*SamplerState\s+\w+\s*:\s*register\(s\d+\);[ \t]*$",
                      "", out_text, flags=re.M)
    out_text = re.sub(r"[ \t]+:\s*register\(t\d+\)", "", out_text)

    if rewritten:
        # Unity recognises inline sampler names only when they are declared as
        # an explicit SamplerState; without the declaration the sample calls
        # fail with "undeclared identifier 'sampler_point_clamp'".
        decls = "SamplerState sampler_point_clamp;    // [tweak-build] Unity inline sampler state\n" \
                "SamplerState sampler_linear_clamp;   // [tweak-build] Unity inline sampler state\n"
        note = decls + "// [tweak-build] inline samplers: " + ", ".join(
            "%s->%s" % (a, b) for a, b in SAMPLER_MAP) + "\n"
        out_text = out_text.replace("struct VS_INPUT_", note + "\nstruct VS_INPUT_", 1)

    # ---- matrices ---------------------------------------------------------
    # 1. strip the hlslcc prefix / restore the binding name Unity expects.
    matrices = 0
    for old, new in MATRIX_RENAMES:
        out_text, n = re.subn(r"\b%s\b" % old, new, out_text)
        matrices += n
    # 2. the builtin camera matrices are declared by UnityCG.cginc.
    for name in BUILTIN_MATRICES:
        out_text = re.sub(r"^[ \t]*float4[ \t]+%s\[4\][^\n]*\n" % name, "", out_text, flags=re.M)
    # 3. material matrices become float4x4 so SetMatrix binds them.
    for name in MATERIAL_MATRICES:
        out_text = re.sub(r"^([ \t]*)float4([ \t]+)%s\[4\];" % name, r"\1float4x4\2%s;" % name,
                          out_text, flags=re.M)
    # 4. M[i] -> ev_coli(M), keeping the GLSL column semantics (and any swizzle).
    for name in ALL_MATRICES:
        for i in range(4):
            out_text = re.sub(r"\b%s\[%d\]" % (name, i), "ev_col%d(%s)" % (i, name), out_text)

    # ---- builtin scalars UnityCG.cginc already declares -------------------
    for name in BUILTIN_SCALARS:
        out_text = re.sub(r"^[ \t]*float[34][ \t]+%s[ \t]*;[^\n]*\n" % name, "", out_text, flags=re.M)

    # ---- UnityCG include + column helpers, before the first declaration ---
    marker = "// [tweak-build]"
    pos = out_text.find(marker)
    if pos < 0:
        out_text = UNITY_PRELUDE + out_text
    else:
        line_start = out_text.rfind("\n", 0, pos) + 1
        out_text = out_text[:line_start] + UNITY_PRELUDE + "\n" + out_text[line_start:]

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "w", encoding="utf-8-sig", newline="\n").write(out_text)
    print("%s -> %s  cbuffers=%d samplers=%d matrices=%d lines=%d"
          % (os.path.basename(src), os.path.basename(dst), flattened, rewritten,
             matrices, out_text.count("\n") + 1))


def copy_verbatim(src, dst):
    """Copies an authored (not ported) shader into the Unity project unchanged."""
    if not os.path.exists(src):
        print("%s -> %s  (missing, skipped)" % (os.path.basename(src), os.path.basename(dst)))
        return
    with open(src, encoding="utf-8") as handle:
        text = handle.read()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "w", encoding="utf-8-sig", newline="\n").write(text)
    print("%s -> %s  copied lines=%d" % (os.path.basename(src), os.path.basename(dst),
                                         text.count("\n") + 1))


if __name__ == "__main__":
    if len(sys.argv) == 3:
        flatten(sys.argv[1], sys.argv[2])
    else:
        for src, dst in DEFAULT_PAIRS:
            flatten(src, dst)
        for src, dst in COPY_PAIRS:
            copy_verbatim(src, dst)
