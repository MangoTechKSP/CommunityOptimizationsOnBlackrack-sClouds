# Building

This document describes how the release is produced. It is written for someone who owns the
original mod **and** has a patched source tree of it; the source tree itself is not part of this
repository ([NOTICE](../NOTICE.md)).

Everything below is Windows, because the cloud build is D3D11 and the shader bundle is built by a
Windows Unity editor.

---

## 1. What you need

| Piece | Version used | Notes |
| --- | --- | --- |
| .NET SDK | 6.0 or newer | builds `net481` assemblies; `dotnet build` drives the SDK-style projects |
| KSP managed assemblies | KSP 1.12.5 | `KSP_x64_Data/Managed/*.dll`; the project files reference them by path |
| Unity | **2019.4.18f1c1** | must include *Windows Build Support (Mono)*; the bundle is built in batch mode |
| Python | 3.8+ | the tools; `lz4`, `UnityPy` optional, only for bundle inspection |
| git | any | for the per-shader diff snapshot in the package |

Unity 2019.4 is not a preference — it is the version the original shaders were compiled with, and
the bundle format and built-in shader includes must match it.

---

## 2. The pipeline

Five steps, in this order. Each has a pass/fail criterion that is not "it exited 0".

```
# 1. C# assemblies
dotnet build VolClouds.sln -c Release
#    pass: 0 errors, 0 warnings (warnings in the original tree are expected; yours must add none)

# 2. Flatten constant buffers into flat uniforms (Unity binds by name, not by cbuffer layout)
python tools/flatten_cbuffer.py
#    writes the flattened .hlsl into the Unity project next to the .shader wrapper

# 3. Offline compile check — milliseconds, reports every error at once
python tools/hlsl_check.py shaders/hlsl/RaymarchCloud.hlsl VS_RaymarchCloud PS_RaymarchCloud
python tools/hlsl_check_unity.py shaders/hlsl/ReconstructRaymarchedClouds.hlsl \
       VS_ReconstructRaymarchedClouds PS_ReconstructRaymarchedClouds
#    pass: no error lines. This is the check that saves you the 40-second Unity round trip.

# 4. Bundle
"D:/Program Files/2019.4.18f1c1/Editor/Unity.exe" -batchmode -quit \
  -projectPath ".../EVE-Tweak" -executeMethod TweakBundleBuilder.CIBuild \
  -logFile ".../EVE-Tweak/build.log"
#    pass: `grep -c "Shader error" build.log` == 0, and the bundle grew by one shader per change.
#    Look at the manifest inside the bundle, not at the file size.

# 5. Package
bash tools/rebuild.sh      # 1-4 in one go
bash tools/pack-buildout.sh
#    pass: unzip -l lists GameData + docs; the DLLs inside match bin/Release byte for byte
```

`tools/rebuild.sh` runs steps 1–4 and refuses to continue if the offline check fails. That is
deliberate: a Unity build that reports one error per run is the slowest possible feedback loop.

---

## 3. How the shader override works

The original bundle is loaded first; the tweak bundle is loaded second and overrides shaders by
name. Requirements for an override to take effect:

* The **shader name string** must be identical, e.g. `Shader "EVE/RaymarchCloud"`.
* The `.shader` file must be a single-pass surface-less shader: `Cull Off`, `ZWrite Off`,
  `ZTest Always`, `Blend Off`, with explicit `#pragma vertex` / `#pragma fragment` / `#pragma target 5.0`.
* Uniform names must match what the C# sets. Unity binds by name; a mismatch is silent — the
  shader just reads zero. `tools/audit_uniforms.py` checks this mechanically.
* `multi_compile` keywords must cover the keywords the C# enables. A missing keyword variant means
  the shader compiles, loads, and does nothing.
* Samplers must be declared as inline sampler states with the wrap mode the texture actually needs;
  a texture has no sampler of its own in a Unity HLSL file.

`docs/TWEAK-BUNDLE.md` has the details and the failure modes; `docs/SAMPLERS.md` has the D3D11
register budget.

---

## 4. Why the tools exist

Each tool exists because a specific mistake was made once and would otherwise be made again:

| Tool | The mistake it prevents |
| --- | --- |
| `hlsl_check.py` | Unity reports one shader error per 40-second build; this reports all of them in milliseconds |
| `hlsl_check_unity.py` | The offline check fails on `#include "UnityCG.cginc"` unless the include is stubbed; without it, real errors hide behind a known-bad one |
| `flatten_cbuffer.py` | Unity binds by name, so a `cbuffer` member never binds; the shader silently reads zero |
| `scope_scan.py` | A variable declared inside a nested block and read outside it — the single most common port error when porting GLSL back to HLSL |
| `dump_bundle.py` / `unityfs_extract.py` | "Which shaders are actually in the bundle, and which variants?" answered from the file instead of from memory |
| `shader_reflection.py` | The same question per variant, with the uniform list, so a keyword that compiles to nothing is visible |
| `audit_uniforms.py` | The C# sets a name no shader declares — no error, no warning, just a feature that does not work |

---

## 5. Common failures

| Symptom | Cause |
| --- | --- |
| Nothing renders, no errors, full-screen quad is invisible | clip-space `z` written as `-1` (D3D near plane is `z = 0`), or a matrix uniform left at its GL binding name |
| Shader loads, effect missing | a keyword variant not declared, or a cburniform the C# sets is missing in the shader |
| Clouds are there but black | depth texture not bound, or the colour is multiplied by a shadow/occlusion term that is 0 |
| `undeclared identifier 'sampler_...'` | inline sampler used but not declared in the file |
| Works in the editor, not in game | the bundle in `GameData` is the old one, or the KSP process was not restarted — KSP only reads bundles at startup |
| Bundle builds but the shader is missing | the `.shader` file has no `assetBundleName`, or the build script's asset scan missed the folder |

---

## 6. What "verified" means here

There are three levels, and they are not interchangeable:

1. **Offline compile** — the shader compiles for D3D11 `target 5.0`. Necessary, not sufficient.
2. **Bundle build** — Unity packed the shader with the expected variants. Also necessary.
3. **In game** — the pass runs in a real frame with real uniforms, at the right time in the frame,
   with the right state. This is the only level that proves anything about appearance, and it is
   the checklist in [`ACCEPTANCE.md`](ACCEPTANCE.md).

A release is prepared with levels 1 and 2 green. Level 3 is per-machine and per-GPU, and the
changelog says explicitly when it has not been done.
