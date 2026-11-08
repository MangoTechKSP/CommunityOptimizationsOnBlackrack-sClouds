# Volumetric Clouds Community Optimizations

A community-maintained optimization pass over **blackrack's volumetric clouds** — the
raymarched cloud build of *Environmental Visual Enhancements* (EVE-Redux). The goal is
simple: keep the clouds looking the same, while removing the crashes, the per-frame
garbage, the leaked GPU memory and the wasted draw work that the original build carries
around.

**Version 1.2.4** — the first public release was 1.0.0; 1.1.x was the queue of fixes and
knobs that came out of auditing it (sampler states, a light-volume sweep that never closed
its loop, four config knobs instead of hard-coded constants, camera-role identification,
per-frame allocations) plus a startup-hardening pass, because three shader constructions
and one raw-file read could throw on a stock install and take the whole mod down with one
log line. 1.1.x ships edge wisps on by default, adds a uniform-name audit that turns silent
`SetFloat("typo", …)` no-ops into a table (`docs/UNIFORMS.md`), stops paying for GPU timing
that stock KSP cannot report, ports **cloud-on-cloud shadows** (the config already asked for
them; the shader now reads the caster layer's coverage map — `docs/SHADOW-CASTER.md`), and
adds a **dedicated volumetric-clouds panel** on its own toolbar button, with a live status
block and every cloud knob (`docs/PANEL.md`).

1.2.0 is the round that goes after the two things a raymarcher gets wrong by default:
**lighting that flattens a complete deck** and **edges that cut instead of fading**.
Multiple scattering, ground bounce and sun-march dither give the cloud volume a lit
interior (`docs/LIGHTING.md`); a vertical light-penetration ramp, a large-scale coverage
breakup and density-gradient sculpted shading put relief back into a fully covered layer
(`docs/LIGHTING.md` §5); cloud shadows now land on the terrain and the sky grows an ice
halo and a rainbow (`docs/GROUND-SHADOW.md`, `docs/SKY-OPTICS.md`). The edge-wisp pass was
rebuilt: the old one multiplied a narrow band just above the visibility threshold, which is
a hard cut however it is dressed up; it now displaces at a lower frequency and modulates the
whole tail, so the silhouette frays sample by sample. See `CHANGELOG.md`; the checklist for the on-device pass is `docs/ACCEPTANCE.md`.

---

## 1. What is in the package

```
GameData/
  EnvironmentalVisualEnhancements/
    Plugins/                     redesigned EVE managed assemblies (11 DLLs)
    eveshaders_tweak.bundle      shader override bundle (RaymarchCloud + ReconstructRaymarchedClouds)
  Scatterer/
    Plugins/Scatterer.dll        rebuilt Scatterer assembly
README.md                        this file
CHANGELOG.md                     what changed, release by release
BUILD-NOTES.md                   how the bundle and the DLLs are produced
```

The shader bundle is **optional at load time**: `ShaderLoader` looks for
`GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle`, and if it is missing
the stock `eveshaders.bundle` is used unchanged. The DLLs, however, expect the EVE
volumetric build they were recovered from — they are not a drop-in for stock EVE-Redux.

## 2. Dropping in / rolling back

* Install: copy `GameData/` into the KSP root, overwriting the existing EVE and Scatterer
  plugin folders. Restart KSP.
* Roll back the shaders only: delete `eveshaders_tweak.bundle`. The stock bundle is then
  used and the DLLs keep working (they only lose the shader-side improvements).
* Roll back everything: restore the original `Plugins/` folders from your backup.

Log lines to confirm the override is alive:

```
[EVE] Shader EVE/RaymarchCloud overridden
[EVE] Shader EVE/ReconstructRaymarchedClouds overridden
```

## 3. What was optimized

### 3.1 CPU and frame time

| Area | Before | After |
| --- | --- | --- |
| Sorting of per-frame cloud intersections | three `LINQ OrderBy(...).ToList()` allocations per frame | zero-allocation stable insertion sort, comparers cached in statics |
| Render-target identifier arrays | 10 `new RenderTargetIdentifier[n]` arrays per frame | arrays cached on the renderer, contents refilled only when the targets are recreated |
| Per-layer uniform upload | `new Vector4[cloudTypes.Count]` every frame | one reusable buffer |
| Empty render passes | command buffer still recorded and drawn with zero volumes | early-out before any recording |

### 3.2 GPU memory

* **Shared noise volumes.** Each raymarched layer used to bake and hold its own pair of
  128³ noise textures (`baseNoise` R16, `curlNoise` RGB111110Float). A 19-layer config
  therefore held ~114 MB of noise data that was identical for layers sharing a noise
  configuration. `NoiseVolumeCache` now reference-counts the bakes and hands the same
  texture to every layer with the same settings: **~12 MB for the same 19 layers**, and
  the bake happens once instead of 19 times at scene load.
* **Released shader resources.** `Remove()` now frees the two noise render textures and
  the three materials it created. Previously, re-applying a cloud config (body reload,
  config edit, scene change) leaked a full layer's worth of GPU memory every time.

### 3.3 Correctness and robustness

* **Multi-body cameras no longer corrupt each other.** The composite, the temporal
  reconstruction and the light volume all read the `planetRadius`/`sphereCenter` of the
  *first* volume that happened to be submitted for the camera. With two clouded bodies in
  one view (Jool + Laythe, or a moon over a planet) the second body's clouds were
  composited with the first body's sphere. The renderer now collects one body per camera
  and, if a nearer body takes over, drops the stale volumes, rebases the motion vectors
  on the switch frame and re-collects. Switchable with `singleBodyPerCamera`.
* **Command buffer bookkeeping.** Attach happens only when the pass actually renders, and
  `RemoveCommandBuffer` no longer depends on the same flag that `OnPostRender` clears —
  the mismatch used to leave a buffer attached to the camera, re-adding it every frame.
* **`Sun.Instance` null guard** in the raymarched volume setup (main menu, scaled-space
  transitions).
* **`HistoryManager` indexer** clamped with `Math.Min(x, length)` instead of
  `length - 1`, so an index equal to the array length threw. Dead code today, correct now.
* **A missing noise dump no longer disables the mod.** `ShaderLoader` read `stbn.R8` and
  `stbn_unitvec3.ARGB32` with a bare `File.ReadAllBytes` before setting its `loaded` flag,
  and every EVE manager only initialises when that flag is set — so on the current EVE
  release, which ships only `stbn.R8`, the second read threw and the sky stayed empty with
  a single `FileNotFoundException` in the log. Both reads are validated and defensively
  loaded now: the scalar dump falls back to a constant, the unit-vector dump (which nothing
  in the bundle declares) is simply skipped.
* **Four shader constructions that could throw** (`EVE/LightVolumeShadow`,
  `EVE/InvisibleShadowCaster`, `EVE/BlendScreenSpaceShadows`,
  `EVE/WetSurfacesAccumulationMask`). None of the four is in the stock `eveshaders.bundle`,
  and `new Material(null)` throws — on the light-volume path that happened every frame, on
  the shadow path it left a half-initialised singleton behind. They now degrade one feature
  at a time with one log line each; 2D cloud shadows are unaffected.
* **One setup window that could be missed.** `GlobalEVEManager` set up a scene only if the
  shader bundle had finished loading at its `Awake`; if the loader's `Start` had not run
  yet, that scene never set up at all. It now retries once from `FixedUpdate`.

### 3.4 Shaders

The recovered HLSL has never been compiled before this release, so a number of GLSL-isms
had to be made legal first (scalar broadcasts, `lessThan`/`greaterThanEqual`, variables
declared inside a branch but read outside it). On top of that:

* **D3D clip-plane fix — the important one.** The fullscreen quad was emitted with
  `gl_Position.zw = (-1, 1)`, which is the *GL* near plane. Under D3D11, `z = -1` is
  outside `[0, 1]` and the whole quad is clipped, i.e. on a Windows/D3D11 build the
  raymarched pass could produce nothing at all. It is now `(0, 1)`.
* **Depth-aware upscale of the ray buffer.** The new-ray buffer is rendered at 1/3
  resolution and was resampled with a plain nearest-neighbour tap for every pixel that is
  not a lattice centre. The reconstruct pass now takes four taps of that buffer and
  rejects taps whose scene depth disagrees with the current pixel's depth, falling back to
  the single tap when the neighbourhood is not flat. Behind cloud edges and against
  terrain silhouettes this removes the blocky 3×3 shimmer that the nearest-neighbour
  upsample produced. Guarded by `EVE_DEPTH_AWARE_UPSAMPLE`.
* **A second shader is now overridable.** `EVE/ReconstructRaymarchedClouds` — the temporal
  reconstruct/composite stage — is included in the tweak bundle. Previously only
  `EVE/RaymarchCloud` was.
* **Matrix uniforms rebound.** Every matrix in the recovered source was declared as
  `hlslcc_mtx4x4…` — the name Unity's GLSL backend generates for a uniform, not the name
  the C# sets or the D3D backend binds. Nothing uploaded those, so on D3D the camera and
  volume matrices were zero and the pass could collapse to nothing. The tweak copy now
  uses Unity's real builtin names (declared by `UnityCG.cginc`) for the camera matrices,
  the plain material names (`cloudRotation`, `currentVP`, …) as `float4x4` for the rest,
  and `ev_col0..3` helpers that preserve the GLSL "index a column" convention the
  multiplies were written against.
* **Sampler states consolidated.** D3D11 gives a program 16 sampler slots; the recovered
  GLSL used GL texture units (31 for `RaymarchCloud`, 9 for the reconstruct pass) and
  would not run as-is. Sampling now goes through Unity inline sampler states
  (`sampler_trilinear_clamp`, `sampler_trilinear_repeat`, `sampler_point_clamp`,
  `sampler_linear_clamp`, `sampler_point_repeat`). Two of them were wrong in 1.0.0 and are
  fixed in 1.1.x: the STBN blue noise is a point/repeat lattice texture, not trilinear
  clamp, and the flow map is an equirectangular texture whose u axis wraps at ±180°, so
  clamping it smeared the last texel column across the seam. `docs/SAMPLERS.md` has the
  per-slot table.
* **Edge wisps, on by default.** Two extra curl octaves on the density sampling position
  (8×/16× the base tiling, amplitude following `curlNoiseStrength` and decaying with height
  in the shell) plus a thinning ramp over the low-density tail just above the marcher's own
  visibility threshold. The cloud core is multiplied by exactly 1.0, so the coverage of the
  image does not change — only the silhouette gets filaments instead of smooth blobs. It
  costs two extra curl fetches per marcher step; `edgeWisp = 0` in the preset restores the
  pixel-exact 1.0.0 edge. `docs/TUNING.md` §4.

## 4. Known limitations and what to verify in game

These are honest gaps, not marketing:

1. **The light volume is baked but nothing here draws it.** Both overridden shaders were
   checked for light-volume samplers and have none — neither pass of `RaymarchCloud`
   declares one (it samples exactly three 3D textures: curl noise, base noise, detail
   noise), and `LIGHT_VOLUME_ON`/`OFF` and `DISCRETE_LIGHT_SAMPLES_ON`/`OFF` appear zero
   times in the original bundle, so in the *original* build they are empty switches too.
   The only sampler of the global light volume is `EVE/LightVolumeShadow`, which is not in
   the stock bundle, so cloud shadows run on the 2D `EVE/ScreenSpaceCloudShadow` path. What
   actually gives the clouds their volume is the in-shell `lightMarchSteps`/`stepSizeLight`
   sun marching. See `docs/LIGHT-VOLUME.md` for the evidence and for what restoring
   light-volume shadows would take.
2. **`PAINTER_UNSTABLE_MASK_*` and `LIGHTNING_UNSTABLE_MASK_*`** keywords exist in C# but
   the recovered variant has no branch for them; the cloud-map painter's "don't paint
   where the clouds are unstable" behaviour and the lightning mask are therefore not
   implemented here.
3. **A few sampler slots remain judgement calls**, documented per slot in
   `docs/SAMPLERS.md` §4: `_DetailTex` (the C# decides its wrap from config), the depth
   texture (bilinear, per GL `texture2D` semantics), three slots no C# in this build binds
   (`BlueNoise`, `DetailNoiseTexture`, `PreviousLayerMotionVectors`) and the packed rays
   buffer, which is filtered the same way it was before because changing it changes
   reprojection aliasing and needs an A/B. Everything else is pinned to the state its
   texture was actually created with.
4. **The shell culling** only helps when the camera is *outside* the cloud shell looking
   away — space, map view, high altitude looking up. In low flight it never culls
   anything, by design (the test is conservative).
5. **Memory numbers** (114 MB → 12 MB) are for the 19-layer stock config; other planet
   packs scale with the number of distinct noise settings, not with the layer count.
6. **The y flip comes from `_ProjectionParams.x`.** The recovered source is the OpenGL
   variant of the shader, where Unity sets that to `-1` for a flipped view; on D3D it is
   normally `1`. If the clouds render vertically mirrored, remove the two
   `* _ProjectionParams.x` factors in the vertex stage of both shaders.

## 5. Building

See `BUILD-NOTES.md`. Short version — `bash tools/rebuild.sh` runs all five steps in order
and stops at the first problem:

```
dotnet build VolClouds.sln -c Release      # 11 assemblies, 0 errors
python tools/flatten_cbuffer.py            # HLSL -> Unity-ready includes
E:/unity/editor/2019.4.18f1/Editor/Unity.exe -batchmode -quit \
    -projectPath EVE-Tweak \
    -executeMethod TweakBundleBuilder.CIBuild \
    -logFile EVE-Tweak/build.log           # success = zero "Shader error" lines
bash tools/pack-buildout.sh                # BuildOut/ + dist/VolClouds-tweak.zip
```

## 6. Credits

* **blackrack** — the volumetric cloud renderer, the shaders and the original EVE code
  this package optimizes. Nothing here is a reimplementation of the algorithm; it is the
  same algorithm, made cheaper and safer.
* **EVE-Redux / Environmental Visual Enhancements** contributors for the base mod.
* The recovered source tree this work started from documents its own provenance in the
  repository README.
