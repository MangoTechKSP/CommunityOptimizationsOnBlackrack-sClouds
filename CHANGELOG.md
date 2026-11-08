# Changelog

All notable changes to **Community Optimizations on blackrack's Clouds** — the community
optimization pass over blackrack's ray-marched volumetric clouds for EVE.

Versions before 1.0.0 were internal iterations and were never packaged for anyone but the author;
they are summarized at the bottom so the history stays readable.

---

## [1.2.4] — 2026-11-08

### Fixed

- **A rainbow is drawn behind the clouds again.** The halo and the bow existed since 1.2.0 but were
  drawn *after* the cloud composite, so a bow was painted on top of every deck in front of it. The
  pass moved into the cloud renderer's command buffer, immediately before the composite blit, and
  now binds its depth as `_SkyDepthTexture` so it cannot disturb what the composite and the
  ground-shadow pass read from `_CameraDepthTexture`.

### Changed

- **Both optics are louder.** `skyHaloStrength` 0.3 → **0.4**, `skyRainbowStrength` 0.35 → **0.55**,
  primary bow band 0.95° → 1.2°, secondary 1.3° → 1.6°, plus a faint wide glow inside the primary
  bow — which a real bow has and a ring decal does not.

---

## [1.2.3] — 2026-11-08

### Fixed

- **The fringe is thrown away instead of steepened.** The silhouette was a power curve on coverage,
  which steepens a gradient but keeps all of it. New `contourThreshold` (0.35 shipped) drops
  everything the ray accumulated below it and `contourBand` (0.18) stretches only the remainder, so
  the edge is two or three pixels instead of tens. 0 / 1.0 reproduces 1.2.2 exactly.
- **The wisps are an order of magnitude finer.** Curl displacement 4/8 → 12/22, modulation fetch
  16 → 34, amplitude down to 0.28, so the fray reads as hair instead of blobs hanging off the edge.
- **Detail grain follows.** `detailFrequency` 1.8 → **3.0** (range to 8), `detailErosionScale`
  2.0 → **2.4**, `macroBreakup` 0.3 → **0.18**.

---

## [1.2.2] — 2026-11-08

### Changed

- **The outline is carved out of the box.** `contourHardness` 1.5 → **2.6**, knob range 1–6. A
  colour rescale keeps covered pixels at their brightness.
- **New `detailFrequency`** (default 1.8, range 0.5–8) scales the detail-noise tiling as a multiply
  on the sample position — no extra fetch — so erosion acts on puff-sized features instead of
  region-sized ones.
- Erosion depth `detailErosionScale` 1.45 → **2.0**, sculpt `sculptStrength` 0.7 → **0.85**, and the
  shading gradient is sampled at 0.0024 world scale instead of 0.0011, so a full deck breaks into
  towers rather than reading as one sheet.

---

## [1.2.1] — 2026-11-08

### Fixed

- **Cloud edges no longer go black.** Colour accumulators were weighted by density, so every place
  a layer thinned out lost brightness and the deck ended in a dark halo. The resolve now lifts a
  thinning fringe (silver lining) while the pixel still holds cloud. New knob `edgeGlow`
  (default 0.8); 0 restores the 1.2.0 look.
- **Wisps stopped looking like branches.** Displacement reached a third of the way into the shell;
  amplitude is down to 0.42 of the curl strength, the height fade is cubed so the warp only lives in
  the outer few percent of the layer, and the modulation is 0.85 instead of 0.55.
- **The silhouette is no longer haze.** A transfer curve on transmittance (`contourHardness`,
  default 1.5) steepens the cloud/sky gradient, with colour rescaled by the same ratio.
- `detailErosionScale` ships at 1.45 instead of 1.0 (same two fetches), `baseDarkness` 0.45 → 0.22,
  `sculptStrength` 0.5 → 0.7.
- Packaging: when the release archives are locked by another process, the packer now falls back to a
  timestamped name instead of failing.

### Added

- `docs/LIGHTING.md` §5.7–5.8, `docs/TUNING.md` §7, and three new sliders in the volumetric-clouds
  panel.

---

## [1.2.0] — 2026-11-08

The "make it look like the photographs" round, plus the T1–T11 queue and a startup-hardening pass.
1.1.0–1.1.2 were never published, so they ship here.

### Added

- **Multiple scattering.** `T + 0.6T + 0.28T(½τ) + 0.12T(¼τ)` — four evaluations of the transmittance
  the marcher already has, no extra fetch, no extra step.
- **Ground bounce.** Light reflected off the surface is added back into the cloud base, weighted by
  shell height `(1 − shellHeight)²` and by sun elevation, so a low sun does not light a deck from
  below in the wrong places.
- **Sun-march dither.** Each light-march step is offset by a per-step hash of 0.3 of a step; the
  original only dithered the first sample, which left visible banding in thick decks.
- **Vertical light penetration.** The march start is offset by a macro-noise field, the ambient term
  is damped with height, and a four-tap sculpt of the density gradient modulates direct and ambient
  light so a flat sheet reads as towers and canyons.
- **Large-scale coverage breakup** (`macroBreakup`), density-gradient sculpting (`sculptStrength`),
  contour hardening (`contourHardness`, `contourThreshold`, `contourBand`) and an edge-wisp pass
  (`edgeWisp`) that frays the silhouette.
- **Cloud-on-cloud shadows.** The C# had always written `shadowCaster*` uniforms that no shader
  declared, so the feature had never existed. Implemented as coverage along the sun direction:
  `occlusion = coverage · min(shadowCasterDensity, 1) · timeFade · strength · aboveRamp`, applied
  only to the direct term. `shadowCasterStrength` defaults to 0.5; 0 restores 1.1.1.
- **Cloud shadows on the ground.** New `EVE/RaymarchedCloudShadow` pass: a quarter-resolution sun
  visibility mask drawn into the cloud command buffer and composited before clouds.
- **Sky optics.** New `EVE/SkyOptics` additive pass with physically placed angles: ice halo at
  22° (three radii), primary bow at 42.4/41.4/40.4°, faint secondary at 50.4/51.4/52.4°, Alexander
  dark band at 46°.
- **In-game panel.** A volumetric-clouds button and window with live readout, apply-on-release, and
  the structure/scattering knobs exposed as sliders (`docs/PANEL.md`).
- **Uniform audit** (`tools/audit_uniforms.py`, `docs/UNIFORMS.md`) that makes the whole class of
  "the C# sets a name no shader declares and nothing complains" mechanical to find.

### Fixed

- **Silent startup failure.** `StbnBlueNoise` was loaded by a hard-coded filename that modern
  installs no longer ship; the resulting exception left `ShaderLoaderClass.loaded == false`, which
  silently skipped the entire cloud setup — no clouds, one log line. The loader now resolves the
  texture it actually finds and validates size.
- **Three shaders that are not in the stock bundle** (`EVE/LightVolumeShadow`,
  `EVE/BlendScreenSpaceShadows`, `EVE/DownscaleDepth`, `EVE/WetSurfacesAccumulationMask`) were
  dereferenced straight after construction, i.e. `new Material(null)` on a normal install. Material
  creation now returns null and every call site degrades with one log line instead of throwing.
- **Light-volume sweep never closed its loop.** `32 / 10` truncated to 3 slices per frame and visited
  only 30 of 32 slices, so two were refreshed from stale data forever; the remainder is now spread
  over the cycle. Divisions that divide evenly keep the old per-frame count.
- **`DivideByZeroException` at `directLightTimeSlicing = 1` under time warp** — the time-warp divisor
  could become 0; clamped to ≥ 1.
- **Multi-slice light-volume path skipped slices**: the pointer advanced by 16 unconditionally
  instead of by the slices the pass wrote.
- **`StbnBlueNoise` and `_FlowMap` sampled with the wrong sampler state**: point/repeat versus
  trilinear/clamp, which interpolates across STBN lattice cells and smears the flow map's ±180° seam.
- **`FrameTimingManager` never returned anything** because KSP disables frame statistics; now probed
  once per second and abandoned after 60 tries.
- **Per-frame allocations**: `RegisterCamera` rebuilt its dictionary every event, `WetSurfacesRenderer`
  allocated two `Camera.allCameras` arrays per frame, and `ResolveLayerOverlapIntervals` allocated a
  `HashSet` plus a `List` per frame — all pooled or reused.
- The offline shader checker no longer reports a false negative for `_ZBufferParams`.

### Changed

- The diagnostic line now reports culled volumes, direct-light slices, CPU ms and GPU ms, so a
  frame-time regression can be attributed without a profiler.

---

## [1.0.0] — first packaged release

### Added

- **Shader override bundle.** A second bundle (`eveshaders_tweak.bundle`) is loaded after the
  original and overrides shaders by name; loading now uses indexer assignment, because `Add` on a
  duplicate name throws — which is exactly what an override is. Deleting the file rolls the shaders
  back without touching the assemblies.
- **Depth-aware upsampling** in `EVE/ReconstructRaymarchedClouds`: the half-resolution ray buffer is
  upsampled with a 4-tap depth-aware filter instead of a single bilinear tap, so cloud edges stop
  bleeding into geometry silhouettes. Falls back to the old path when the depth tap is unusable.
- **Noise volume cache.** Every cloud layer used to bake its own 128³ base-noise and curl-noise
  volumes — a 19-layer body held ~114 MB of duplicate noise and never freed it. The cache brings that
  to ~12 MB and the volumes are released when a layer is removed.
- **Shell culling** when the camera is outside a shell entirely, plus an empty-volume early out so no
  command buffer is recorded for a frame with nothing to draw.
- **Diagnostics**: a five-second summary line (camera, body, volume count, bounds, intervals, light
  volume, reflection probe, resolution, reprojection) and an applied-config inventory.
- `singleBodyPerCamera` — one body per camera, chosen by nearest, so a second planet in frame cannot
  be drawn with the first planet's centre and radius.

### Changed

- **Per-frame garbage removed from the render path**: three `OrderBy(...).ToList()` sorts replaced
  with zero-allocation stable sorts (stable on purpose — `OrderBy` is stable and `List.Sort` is not,
  so equal keys would otherwise reorder), ten render-target-identifier arrays cached and refilled in
  place, and the per-layer `Vector4[]` reused.
- Noise formats widened where precision was the limit: base noise `R8` → `R16` (the erosion threshold
  is a comparison, and 8 bits quantized it into contour rings), curl noise `RGB565` → `RGB111110Float`,
  coverage curve `RG16` → `RGHalf`.

### Fixed

- **The full-screen quad was clipped away on D3D11.** The vertex stage wrote clip-space `z = -1`;
  D3D's near plane is `z = 0`, so the march could discard the entire screen. This is the fix that
  matters most and the one to re-test first.
- **Matrix uniforms rebound to Unity's own built-ins.** The ported shaders used the GL binding names
  Unity's cross-compiler generates; those are zero in a D3D build, which collapses the quad. All
  matrices now use `unity_MatrixVP`, `unity_CameraInvProjection`, `unity_CameraToWorld` and explicit
  material matrices.
- **Command-buffer attach/detach is always paired**, and detach no longer depends on the render flag
  that might already be false.
- **GPU resources are released**: per-layer materials and noise render targets, previously leaked on
  every config re-apply.
- `Sun.Instance` is null-checked on the cloud path; a history indexer clamped to the array length
  instead of `length - 1`.

### Known issues

- The light-volume variants of `EVE/RaymarchCloud` compile to the same code because neither ported
  GLSL variant samples the light volume; cloud-on-cloud shadowing therefore comes from the coverage
  path, not from the volume.
- Sampler wrap modes for a few textures are inferred, not proven; the visible symptom would be
  tiling seams.
- `_ProjectionParams.x` y-flip handling on D3D is inferred from UnityCG and not verified on device.

---

## Internal iterations (0.x, never packaged)

- 0.1 — depth-aware upsampling prototype; discovered the D3D clip-plane and matrix-name bugs.
- 0.2 — sampler budget: 31 samplers into two inline states (D3D11 gives 16 registers per program).
- 0.3 — override bundle pipeline: flatten constant buffers, build per shader, verify `Shader error`
  count is zero, pack.
- 0.4 — noise sharing and format widening; first memory measurement (114 MB → 12 MB).
- 0.5 — contour, edge wisps and the first attempt at cloud-on-cloud shadowing.
