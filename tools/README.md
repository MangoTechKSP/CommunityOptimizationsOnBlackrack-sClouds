# Tools

Build, inspection and auditing tools used by this project. All of them are standalone: they take a
file path and print what they found. None of them contain code from the mod.

| Tool | Purpose |
| --- | --- |
| `flatten_cbuffer.py` | Rewrites Unity `cbuffer { ... }` blocks into flat uniforms, and rewrites sampler declarations into the inline sampler states Unity requires. Unity binds material properties **by name**; a member of a constant buffer never binds. Also rebinds the GL-era matrix names to Unity's built-in matrices and provides the column accessors the ported GLSL expects. |
| `hlsl_check.py` | Compiles one shader stage in milliseconds through `d3dcompiler_47.dll` and prints **all** errors. Unity reports one error per 40-second build, which makes iteration on a 2000-line shader impractical. |
| `hlsl_check_unity.py` | Wrapper for shaders that `#include "UnityCG.cginc"`: stubs the include and the Unity-provided uniforms, then calls `hlsl_check.py`. Without this, a known-bad include failure hides every real error behind it. |
| `scope_scan.py` | Finds variables declared inside a nested block and read outside it — the most common error after porting GLSL, because GLSL and HLSL differ in how they scope declarations inside `if`/`while` bodies. |
| `dump_bundle.py` | Lists the objects inside a UnityFS bundle (shaders, compute shaders) and their platform payloads. |
| `unityfs_extract.py` | Extracts a UnityFS bundle by hand (header, block info, LZMA/LZ4 blocks), for bundles the usual tools refuse. |
| `shader_reflection.py` | For one shader in a bundle: lists its variants, keywords and uniforms, so "the keyword compiles to nothing" and "the C# sets a name no shader declares" become visible. |
| `audit_uniforms.py` | Cross-checks every name the managed code sets against every name the shaders declare, per shader. This turns an entire class of silent no-op into a list. |
| `rebuild.sh` | Runs the whole build: assemblies, flatten, offline checks, Unity bundle, package. Refuses to continue when an offline check fails. |
| `pack-buildout.sh` | Assembles the release archive from the build outputs, the shader sources, the docs, and the per-shader diff. |

## Requirements

* Python 3.8+, standard library for everything except bundle *inspection* (`lz4`, `UnityPy`), which
  is optional and only needed by `dump_bundle.py` / `shader_reflection.py`.
* `hlsl_check.py` needs `d3dcompiler_47.dll`, which ships with Windows and with every DirectX
  runtime since Vista. No SDK install.
* `rebuild.sh` / `pack-buildout.sh` are Bash (Git Bash / MSYS), because the rest of the toolchain is
  Windows-native and this is the one place where a shell is convenient.

## Exit codes

`hlsl_check.py` exits non-zero if any stage fails to compile; `audit_uniforms.py` exits non-zero if
any name is set but never declared. Both are used as gates in `rebuild.sh`, so a silent pass cannot
happen twice.

## Not included

`unpack_bundle.py` (an early, broken attempt) and the one-off scripts used to inventory the source
tree are not published: they were disposable, and the working versions are the ones above.
