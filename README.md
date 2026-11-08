# Community Optimizations on blackrack's Clouds

A community optimization and shading pass over **blackrack's volumetric clouds** — the
ray-marched volumetric cloud build of *Environmental Visual Enhancements* (EVE-Redux) for
Kerbal Space Program.

Current version: **1.2.4** · [Changelog](CHANGELOG.md) · [Future features](docs/FUTURE-FEATURES.md)

---

## This is not the mod

This repository is an optimization layer. It ships a replacement set of managed assemblies and
an overriding shader bundle that are applied **on top of a legally purchased copy** of the
original. It contains no code and no assets from the original, and it does not work without it.

> **You must own the original to use this.**
> Get it from the author: <https://www.patreon.com/blackrack>

If you do not own the original, nothing here will run — the assemblies expect the original
`eveshaders.bundle`, the original configs in `GameData/EnvironmentalVisualEnhancements/`, and
the original texture set.

Everything in this repository is our own work: the new source files under [`source/`](source/),
the Unity shader-override project under [`unity/`](unity/), the Python/Bash tooling under
[`tools/`](tools/), and the documentation under [`docs/`](docs/). See [`NOTICE.md`](NOTICE.md)
for exactly what is and is not included, and why.

---

## What it does

The goal is a simple one: **keep the clouds looking the same or better, and remove the work that
was being wasted.** No effect is traded away for speed — no resolution drops, no density cuts, no
step-count caps presented as "optimization". Where the picture does change, it is because a
shading model was added or fixed, and every such change has a knob that restores the previous
look.

| Area | Summary | Details |
| --- | --- | --- |
| Frame time | Per-frame LINQ and array allocations removed from the render path; sorting replaced with zero-allocation stable sorts; render-target identifier arrays cached | [ARCHITECTURE](docs/ARCHITECTURE.md) |
| GPU memory | Per-layer 128³ noise volumes are now shared through a cache: a 19-layer body drops from ~114 MB to ~12 MB of noise, and the resources are released when a layer is removed | [ARCHITECTURE](docs/ARCHITECTURE.md) |
| Startup robustness | Three shader references and one raw-file read that could fail *silently* on a modern install (no clouds at all, one log line, nothing else) now degrade loudly and keep running | [DIAGNOSTICS](docs/DIAGNOSTICS.md) |
| Correctness | Command-buffer attach/detach always paired; empty frames skip recording; cross-body contamination bounded to one body per camera by design | [MULTI-BODY](docs/MULTI-BODY.md) |
| Cloud lighting | Multiple scattering, ground bounce, sun-march dither, vertical light penetration, density-gradient sculpting, contour hardening, edge wisps | [LIGHTING](docs/LIGHTING.md) · [TUNING](docs/TUNING.md) |
| Cloud-on-cloud shadows | A shadow-caster path that the original C# configured but no shader ever implemented | [SHADOW-CASTER](docs/SHADOW-CASTER.md) |
| Cloud shadows on the ground | A quarter-resolution sun-visibility mask drawn into the cloud pass | [GROUND-SHADOW](docs/GROUND-SHADOW.md) |
| Sky optics | Ice halo at 22° and primary/secondary rainbows at 42°/51.5°, correct angles, drawn *before* the cloud composite so clouds occlude them | [SKY-OPTICS](docs/SKY-OPTICS.md) |
| Light volume | Baking-sweep fix (two slices were never refreshed), divide-by-zero under time warp, multi-slice pointer, missing-shader guard | [LIGHT-VOLUME](docs/LIGHT-VOLUME.md) |
| Texture binding | Sampler states corrected for the blue-noise and flow-map textures; the D3D11 per-program sampler budget audited and pinned | [SAMPLERS](docs/SAMPLERS.md) · [UNIFORMS](docs/UNIFORMS.md) |
| In-game settings | A volumetric-clouds button and window with live diagnostic readout | [PANEL](docs/PANEL.md) |
| Tooling | Offline HLSL compile checks, constant-buffer flattening, bundle inspection, a uniform audit that turns "the C# writes a name no shader declares" into a mechanical check | [UNIFORMS](docs/UNIFORMS.md) · [BUILDING](docs/BUILDING.md) |

---

## Requirements

* Windows x64, Direct3D 11.
* Kerbal Space Program **1.12.5**.
* A purchased install of **blackrack's volumetric clouds** (EVE-Redux ray-marched build).
* Optional: Scatterer. When present, the cloud layers and the godrays integrate as before.

The shader bundle is built against **Unity 2019.4.18f1c1** with the built-in render pipeline,
which is the Unity version the cloud build targets. Both the shipped bundle and the original are
D3D11 (`target 5.0`) shaders; OpenGL is not covered by this pass.

---

## Install

1. Back up `GameData/EnvironmentalVisualEnhancements/` and `GameData/Scatterer/`.
2. Copy the contents of the release `GameData/` over your KSP `GameData/`.
   * `EnvironmentalVisualEnhancements/Plugins/*.dll` — the optimized assemblies.
   * `EnvironmentalVisualEnhancements/eveshaders_tweak.bundle` — the shader overrides.
   * `Scatterer/Plugins/Scatterer.dll` — only if you use Scatterer.
3. Start KSP. In `KSP.log`, look for:

```
[EVE] ShaderLoader: override bundle loaded
[EVE] Shader EVE/RaymarchCloud overridden
[EVE] Shader EVE/ReconstructRaymarchedClouds overridden
[EVE] Shader EVE/RaymarchedCloudShadow overridden
[EVE] Shader EVE/SkyOptics overridden
```

4. In flight, click the **volumetric clouds** toolbar button (next to EVE's own) to confirm the pass
   is compiling. The panel shows which body's clouds are drawn, layer and interval counts,
   reprojection factor, light-volume state, culled shells and CPU/GPU cost. Preset-level settings
   remain in the EVE window (**Alt+0**).

Step-by-step acceptance checks, with what to look at and what a failure means, are in
[`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md).

### Rollback

* **Shaders only:** delete `GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle`.
  The optimized assemblies keep running and fall back to the original shaders.
* **Everything:** restore the backup from step 1.

---

## Build it yourself

The full pipeline — DLL build, constant-buffer flattening, offline D3DCompile checks, Unity
batch-mode bundle build, packaging — is documented in [`docs/BUILDING.md`](docs/BUILDING.md).
It requires the patched source tree, which is *not* in this repository (see
[`NOTICE.md`](NOTICE.md)), plus Unity 2019.4.18f1c1.

The tools under [`tools/`](tools/) are usable on their own: `flatten_cbuffer.py` turns Unity
`cbuffer` blocks into flat uniforms, `hlsl_check.py` compiles a shader in milliseconds through
`d3dcompiler_47.dll` and reports *all* errors at once instead of one per Unity build,
`dump_bundle.py` and `shader_reflection.py` read a UnityFS bundle, and `audit_uniforms.py`
compares the names the C# sets against the names the shaders declare.

---

## Verification status

Honest summary: **the offline loop is green, the in-game loop is not yet done.**

* `dotnet build` — 0 errors, 0 warnings.
* Offline D3DCompile of all four shader entry points — clean.
* Unity batch-mode bundle build — `shader errors: 0`, four shaders packed.
* In-game: **not verified**. The machine this pass was prepared on has no KSP install, so every
  item that needs a running game is written as a checklist item in
  [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) and as "verify this" notes in the changelog.

If you install this and something looks wrong, [`docs/DIAGNOSTICS.md`](docs/DIAGNOSTICS.md)
lists every log line the pass emits, and [`docs/TUNING.md`](docs/TUNING.md) lists every knob that
can put a look back to stock.

---

## Repository layout

```
docs/        Design notes, mechanisms, tuning reference, acceptance checklist
source/      New source files we wrote (C# classes and new shader passes)
unity/       Unity project assets that build the shader-override bundle
tools/       Build and inspection tooling (Python + Bash)
```

`source/` and `unity/` are provided for reference and for porting: they compile only inside a
licensed copy of the original source tree, because they reference its types and its constant
buffers.

---

## Documentation

| Document | What it is |
| --- | --- |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Rules that are not obvious from the code: layer skipping, load/unload distances, camera roles, shared state |
| [LIGHTING](docs/LIGHTING.md) | Multiple scattering, ground bounce, dither, vertical structure, contour and edge wisps |
| [TUNING](docs/TUNING.md) | Every knob: location, default, range, and what to look for when you turn it |
| [SHADOW-CASTER](docs/SHADOW-CASTER.md) | Cloud-on-cloud shadows |
| [GROUND-SHADOW](docs/GROUND-SHADOW.md) | Cloud shadows cast on the terrain |
| [SKY-OPTICS](docs/SKY-OPTICS.md) | Ice halo and rainbows |
| [LIGHT-VOLUME](docs/LIGHT-VOLUME.md) | The baked 3D light volume: sweep, time slicing, failure modes |
| [SAMPLERS](docs/SAMPLERS.md) | D3D11 sampler budget and which state each texture needs |
| [UNIFORMS](docs/UNIFORMS.md) | The uniform contract between C# and shaders, and how to audit it |
| [MULTI-BODY](docs/MULTI-BODY.md) | Why one camera draws one planet's clouds, and what a real fix needs |
| [PANEL](docs/PANEL.md) | The in-game volumetric-clouds window |
| [DIAGNOSTICS](docs/DIAGNOSTICS.md) | Every log line and what it means |
| [ACCEPTANCE](docs/ACCEPTANCE.md) | In-game checklist: install, look, diagnose |
| [BUILDING](docs/BUILDING.md) | Reproducing the build |
| [TWEAK-BUNDLE](docs/TWEAK-BUNDLE.md) | How the shader-override bundle works and how to extend it |
| [FUTURE-FEATURES](docs/FUTURE-FEATURES.md) | Roadmap: what is planned, why, and what it would cost |

---

## Contributing

Bug reports are most useful with the diagnostic block from the in-game panel plus the relevant
`KSP.log` lines — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License and credits

Our own code, shaders, tools and documentation are MIT licensed — see [`LICENSE`](LICENSE).
The mod being optimized is **not** MIT licensed and is not distributed here; see
[`NOTICE.md`](NOTICE.md).

Clouds by **blackrack**. Environmental Visual Enhancements by **rbray89** and contributors.
Scatterer by **blackrack**. Kerbal Space Program by Squad / Private Division. This pass is
community work and is not affiliated with, endorsed by, or supported by any of them.
