# Source files we wrote

These are the files this project added to the mod, published so the work can be read, reviewed and
ported. They are **not** a buildable project on their own: they reference the mod's own types,
constant buffers and pipeline, and they compile only inside a licensed copy of its source tree.

| File | What it is |
| --- | --- |
| `CameraRoles.cs` | Replaces nine string comparisons on camera `GameObject` names with explicit role flags, so a renamed camera object cannot silently disable a pass |
| `VolumetricCloudsWindow.cs` | The in-game volumetric-clouds panel: status block, structure and scattering sliders, apply-on-mouse-release |
| `RaymarchedCloudShadow.hlsl` | New pass: a quarter-resolution sun-visibility mask (cloud shadows on the ground), sampled by the terrain and the Scatterer reflection path |
| `SkyOptics.hlsl` | New pass: ice halo and rainbows, at physical scattering angles, drawn before the cloud composite so decks occlude them |

## Why only these

Everything else in the pass is a change to existing files — a corrected sampler state, a cached
render-target array, a reordered composite, a fixed index. Publishing those as files or as patches
would redistribute the original source, which this project does not do (see
[`../NOTICE.md`](../NOTICE.md)). Those changes are instead described in [`../docs/`](../docs): the
formula, the default, the failure mode, and how the fix was verified. That is enough to
re-implement them, which is the point of the documentation.

## How the two shader passes fit in

Both are standalone single-pass shaders. To use them you need:

1. A `.shader` wrapper with the same name the C# looks up, `Cull Off ZWrite Off ZTest Always`,
   `target 5.0`, and the `multi_compile` keywords the C# enables. The wrappers used for the release
   are in [`../unity/Assets/Shaders/`](../unity/Assets/Shaders).
2. A flattened version of the HLSL — Unity binds uniforms by name, not by constant-buffer layout —
   produced by [`../tools/flatten_cbuffer.py`](../tools/flatten_cbuffer.py).
3. Inline sampler states declared in the file, with the wrap mode each texture actually needs.
4. The dispatch/composite point wired into the frame at the right event; `RaymarchedCloudShadow`
   runs inside the cloud command buffer before the composite, `SkyOptics` immediately before it.

[`../docs/SKY-OPTICS.md`](../docs/SKY-OPTICS.md) and
[`../docs/GROUND-SHADOW.md`](../docs/GROUND-SHADOW.md) describe the algorithms; the variable names
and the maths in the files are the reference.
