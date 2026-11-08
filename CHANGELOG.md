# Changelog

All notable changes to **Volumetric Clouds Community Optimizations** — the community
optimization pass over blackrack's raymarched volumetric clouds for EVE.

Versions before 1.0.0 were internal iterations and were never packaged for anyone but the
author; they are summarized here so the history stays readable.

---

## [1.2.4] — 2026-11-08

The halo and the rainbow existed since 1.2.0 but were drawn *after* the cloud composite, so a
bow was painted on top of every deck in front of it, and both were quiet enough to miss.

### Fixed

- **A rainbow is behind the clouds again.** The pass moved out of its own component and into the
  cloud renderer's command buffer, immediately before the composite blit, so the clouds are drawn
  over the bow instead of under it. Same event, same one pass; nothing else about the ordering
  changed. It also binds its depth as `_SkyDepthTexture` now, so it cannot disturb what the
  composite and the ground-shadow pass read from `_CameraDepthTexture`.
- **Both effects are louder.** `skyHaloStrength` 0.3 -> **0.4**, `skyRainbowStrength` 0.35 ->
  **0.55**, the primary bow band widened from 0.95° to 1.2° (and the secondary from 1.3° to 1.6°),
  plus a faint wide glow inside the primary bow, which is what a real bow has and a ring decal
  does not.
- `src/Atmosphere/Atmosphere/SkyOpticsRenderer.cs` is gone; the logic lives in
  `DeferredRaymarchedVolumetricCloudsRenderer.UpdateSkyOpticsPass`.

## [1.2.3] — 2026-11-08

The 1.2.2 screenshots answered back: "现在的边缘更像是团块而不是发丝，发丝应当比现在的小很多
而且边缘仍然是明显的渐变的，渐变的长度太长，不够锐利". Two structural causes, two structural
fixes: the fraction of a ray that was still nearly empty was being drawn as cloud, and the wisps
were displaced at frequencies a puff wide.

### Fixed

- **The fringe is thrown away instead of steepened.** The silhouette used to be a power curve on
  coverage, which steepens a gradient but keeps all of it. New `contourThreshold` (0.35 shipped)
  drops everything the ray accumulated below that and `contourBand` (0.18) stretches only the
  remainder, so the edge is two or three pixels instead of tens. 0 / 1.0 restores 1.2.2 exactly.
- **The wisps are an order of magnitude finer.** Curl displacement frequencies 4/8 -> 12/22 and the
  modulation fetch 16 -> 34, with the amplitude down to 0.28, so the fray reads as hair rather
  than as blobs hanging off the edge.
- **Detail grain and erosion follow.** `detailFrequency` default 1.8 -> **3.0** (range to 8),
  `detailErosionScale` 2.0 -> **2.4**, `macroBreakup` 0.3 -> **0.18** (the large-scale breakup was
  itself one of the sources of the blob look).

## [1.2.2] — 2026-11-08

The 1.2.1 build still read soft in flight ("边缘仍然不够硬朗，细节应当作用于更小的范围"), so
this round moves the shipped defaults, not the code: the transfer curve and the detail scale are
where the answer to "how crisp" actually lives.

### Changed

- **The outline is carved out of the box.** `contourHardness` 1.5 -> **2.6**, knob range 1-6
  instead of 1-4. At 1.5 the cloud/sky transition was still a long haze; 2.6 closes it into an
  outline, and the colour rescale keeps covered pixels at their brightness.
- **The detail acts on a smaller neighbourhood.** New `detailFrequency` (default **1.8**, range
  0.5-6) scales the detail-noise tiling, so the erosion that used to carve country-sized puffs
  now carves puffs you can read from a cockpit. It is a multiply on the sample position: no
  extra fetch.
- **Erosion depth** `detailErosionScale` 1.45 -> **2.0** and **sculpt** `sculptStrength`
  0.7 -> **0.85**, with the gradient sampled at 0.0024 world scale instead of 0.0011, so a full
  deck breaks into towers instead of reading as one sheet.
- `detailFrequency` sits in the volumetric-clouds panel next to the other structure knobs.

## [1.2.1] — 2026-11-08

Still no on-device pass. This is the round that answers the 1.2.0 screenshots: the deck was still
flat, still too dark, its edge went black, and the wisps read as branches.

### Fixed

- **Cloud edges no longer go black.** The colour accumulators are weighted by density, so every
  place where a layer thins out simply lost brightness and the deck ended in a dark halo. The
  resolve now lifts a thinning fringe (silver lining) while the pixel still has cloud in it, so the
  outline is bright instead of sooty. Clear sky is untouched because `finalColor` is already zero
  there. New knob `edgeGlow`, default 0.8, 0 restores the 1.2.0 look.
- **Wisps stopped looking like branches.** The 1.2.0 displacement reached a third of the way into
  the shell at 4x/8x frequency, which is a tendril, not a fringe. Amplitude is down to 0.42 of the
  curl strength, the height fade is cubed so the warp only lives in the outer few percent of the
  layer, the modulation went from 0.55 to 0.85 (crisper filaments), and the second fetch moved from
  12x to 16x.
- **The silhouette is no longer haze.** The marcher accumulates a soft optical depth, so the
  cloud/sky transition was a long gradient. A transfer curve on the transmittance (`contourHardness`,
  default 1.5) steepens it, and the colour is rescaled by the same ratio so a covered pixel keeps its
  brightness.
- **The near field has detail again.** Stock erosion is smoothed away by the coarse step size, so
  `detailErosionScale` now ships at 1.45 instead of 1.0 (same two fetches, no extra cost).
- **The deck is less dark.** `baseDarkness` default 0.45 -> 0.22: the top-penetration term was
  intended to give depth, not to grey out the whole layer.
- **Sculpted shading is crisper.** `sculptStrength` default 0.5 -> 0.7, and the gradient taps moved
  from 0.0004 to 0.0011 world scale (bumps are now cloud-sized instead of continent-sized).
- Packaging: when both `dist/VolClouds-tweak.zip` and the versioned archive are locked (Explorer or
  a zip viewer holding them), the pack now falls back to a timestamped name instead of failing.

### Added

- `docs/LIGHTING.md` §5.7 (silver lining) and §5.8 (contour hardness), `docs/TUNING.md` §7 (the two
  new knobs), and three new sliders in the volumetric-clouds panel.

---

## [1.2.0] — 2026-11-08

Still no on-device pass: the machine this was prepared on has no Kerbal Space Program
install, so every item below is verified only as far as the offline loop goes
(`dotnet build` 0 errors, offline D3DCompile of all four shader entries, Unity batch
bundle build with `shader errors: 0`, repack). The acceptance steps that need a running
game are written next to each item, and `docs/ACCEPTANCE.md` is the checklist for them.

1.1.0, 1.1.1 and 1.1.2 were never published, so the T1–T11 queue and the 1.2.0 feature work ship
together. 1.2.0 itself is the "make it look like the photographs" round: multiple scattering,
ground bounce, sun-march dither, cloud shadows on the ground, an ice halo and a rainbow, a
vertical light-penetration model, large-scale coverage breakup, density-gradient sculpted
shading, and an edge-wisp pass rebuilt to fray the silhouette instead of cutting it. Every one
of those is a shading/algorithm change, not a coverage knob: the reference photographs of an
overcast deck are complete coverage with relief in the lighting, and adding relief to a
complete sheet is what this round does.

This release is the T1–T11 queue from `HANDOVER.md` plus a startup-hardening pass: three
shader constructions and one raw-file read that could throw on a normal install, and one
setup window that could be missed, all of which failed *silently* before (no clouds, no
shadows) rather than loudly. It also turns edge wisps on (§Changed), ports cloud-on-cloud
shadows (§Added), adds an in-panel settings button for the volumetric clouds, and adds a
uniform audit that makes the whole class of "the C# writes a name no shader declares, and
nothing complains" mechanical to find (`tools/audit_uniforms.py`, `docs/UNIFORMS.md`).

### Fixed

* **`StbnBlueNoise` was sampled with the wrong sampler state** (T7). The texture is
  created as `FilterMode.Point` + `TextureWrapMode.Repeat` (`ShaderLoaderClass.cs:78-92`);
  the port sampled it with `sampler_trilinear_clamp`, which interpolates across lattice
  cells (destroying the "one sample per pixel per frame, cycling over the tile" protocol
  STBN is built on) and stops the tile from wrapping at its last row/column. Two call
  sites now use `sampler_point_repeat`.
* **`_FlowMap` was clamped instead of repeating** (T7). The flow map is an equirectangular
  texture whose u axis wraps at ±180°; `TextureWrapper.cs:114` creates it with
  `Repeat` by default. Clamping smeared the last texel column across exactly the seam
  that the acceptance list asks about. Three call sites now use `sampler_trilinear_repeat`.
* **False-negative in the offline shader check** (T7). `tools/hlsl_check_unity.py` did not
  stub `_ZBufferParams`, so `ReconstructRaymarchedClouds` always failed in
  `tools/rebuild.sh` — which hid any real error behind a known-bad one.
* **The light-volume sweep never closed its loop on some slicing values** (T9).
  `volumeSlices / (int)directLightTimeSlicing` truncates, so `32/10` baked 3 slices per
  frame and only ever visited 30 of the 32 slices before wrapping — the last two were
  refreshed from stale data forever. The remainder is now spread over the first frames of
  the cycle (`4,4,3,3,...`, exactly 32 per sweep). Values that divide evenly (`8`, `32`,
  the defaults) produce the same per-frame count as before.
* **`DivideByZeroException` at `directLightTimeSlicing = 1` under timewarp** (T9). The
  timewarp divisor was `(int)(1 / TimeWarpRate)`; rates above 2 made the divisor 0 and the
  slicing formula divided by it. The divisor is clamped to ≥1 now.
* **Slices were skipped on the D3D multi-slice path** (T9). One draw call writes up to
  `maxSlicesInOnePass` (16) slices and cannot wrap past the end of the volume, but the
  pointer was advanced by 16 unconditionally. It now advances by the number of slices the
  pass actually wrote and stops at the volume end so the next frame continues the sweep.
* **A shader missing from the bundle could throw on the light-volume per-frame path** (T3).
  `LightVolume.Init()` built `new Material(LightVolumeShadowShader)`, but the stock
  `eveshaders.bundle` ships 37 `EVE/` shaders and `EVE/LightVolumeShadow` is not one of them,
  and `ShaderLoaderClass.FindShader` (`ShaderLoaderClass.cs:134-147`) has no `Shader.Find`
  fallback — so in a normal install the argument is null, on a call reached from
  `DeferredRaymarchedVolumetricCloudsRenderer.OnPreRender()`. The two reprojection shaders had
  the same shape: a missing compute kernel was dereferenced for its thread-group sizes
  immediately. All three now degrade with one log line each: missing compute kernel → raster
  reprojection; missing both → `bakeUnavailable`, `LightVolume.Update` becomes a no-op and
  `scattererCloudLightVolumeEnabled` stays 0; missing `LightVolumeShadow` → the ten skipped
  `Set*` calls are skipped and cloud shadows stay on the 2D path (which is what
  `ScreenSpaceShadowsManager`'s `blendBothShadowSources` test already assumed). With the
  shaders present the code path is unchanged line for line.
* **One missing noise file could disable the whole mod.** `ShaderLoaderClass.LoadShaders()`
  read `stbn.R8` and `stbn_unitvec3.ARGB32` with a bare `File.ReadAllBytes` *after* loading the
  bundles and *before* setting `loaded = true`. Current EVE installs ship only `stbn.R8`
  (checked in all three copies on this machine; `stbn_unitvec3.ARGB32` only exists in an old
  0.9 install), so the second read throws, `Start()` aborts, and `loaded` stays `false` for the
  session — and `GlobalEVEManager.Awake` (`GlobalEVEManager.cs:65`) only calls `Setup(false)`
  and schedules `Setup(true)` when that flag is set, so **no EVE manager would ever initialise**.
  Both dumps now go through `LoadRawNoise`, which validates the byte count, logs the file name
  and falls back to a 1x1 constant for `stbn.R8` (it is sampled: `StbnBlueNoise`) or skips
  `stbn_unitvec3.ARGB32` entirely (nothing in the bundle declares `StbnUnitVec3`; grep of the
  25 MB serialised bundle: 0 hits). Startup can no longer throw from this path, and the
  degradation is one line each in the log.
* **`GlobalEVEManager` could miss its own setup window.** `Awake` ran the immediate setups only
  if `ShaderLoaderClass.loaded` was already true, and nothing guaranteed the `Instantly` addon's
  `Start()` ran first; if it did not, that scene's managers were never set up at all (no
  `Setup(true)` was scheduled either). `FixedUpdate` now picks the scene up as soon as the flag
  turns true, once, through the same `RunEarlySetup()` the `Awake` path uses.
* **Three more shaders referenced by the C# are absent from the stock bundle**:
  `EVE/InvisibleShadowCaster`, `EVE/BlendScreenSpaceShadows` and
  `EVE/WetSurfacesAccumulationMask` (0 hits each in the serialised bundle, and no
  `Resources.FindObjectsOfTypeAll` supplier). `new Material(null)` throws, so
  `ScreenSpaceShadowsManager.SetupGameObject()` died halfway through `Init()` — leaving a
  half-initialised singleton behind that later ticks with null materials — and
  `ScreenSpaceShadowsRenderer.Init()` died on the per-camera registration path. New
  `ShaderLoaderClass.CreateMaterial(name)` returns null instead of throwing; the shadow manager
  disables the invisible caster quad and keeps the per-camera shadow renderers, the shadow
  renderer switches the screenspace pass off for that camera, and wet surfaces report and skip
  the volume. 2D cloud shadows and eclipses are unaffected in all three cases.

### Added

* **Multiple-scattering approximation** (`EVEMultipleScattering`, default 0.4). The ported shader
  fitted single-scattering transmittance, so a thick layer's interior went black. Four octaves of
  the same fit (weights 0.6/0.28/0.12 at 1x/0.5x/0.25x optical depth) approximate light that has
  bounced inside the cloud, which is what makes a deep layer glow instead of going flat dark.
  No extra fetches: the octaves reuse the already-accumulated light optical depth
  (`docs/LIGHTING.md` §2).
* **Ground bounce** (`EVEGroundBounce` 0.25, `EVEGroundBounceTint` warm). Light reflected off
  sunlit ground into the cloud base, weighted by how close the sample is to the bottom of the
  shell and by how much of the ground the sun actually lights. Warms a low deck and separates it
  from the terrain (`docs/LIGHTING.md` §3).
* **Sun-march dither** (`EVELightMarchJitter`, default 1.0). The light march now scales each step
  by `1 ± 0.15 * hash(step, STBN)`, so the shadow-ray banding that a 2-4 step march produces turns
  into noise that the temporal filter already averages. Expected value is unbiased; 0 restores
  the deterministic march exactly (`docs/LIGHTING.md` §4).
* **Cloud shadows on the ground** (`EVE/RaymarchedCloudShadow`, two passes, `cloudShadowStrength`
  default 0.6). A quarter-resolution sun-reachability mask is built from the lowest two layers'
  coverage maps (the same cubemaps the main pass samples), then multiplied over the scene colour
  at `AfterForwardOpaque`. It is a coverage prior, not a density march, so it is one texture fetch
  per shadowed pixel; `docs/GROUND-SHADOW.md` has the tradeoff.
* **Ice halo and rainbow** (`EVE/SkyOptics`, `skyHaloStrength` 0.3, `skyRainbowStrength` 0.35). A
  single additive full-screen pass at `AfterForwardAlpha` (after Scatterer's atmosphere and after
  the cloud composite): a 22° halo of 21.7° red / 22.4° blue with a wide falloff, a primary bow at
  42.4°/41.4°/40.4° and a reversed secondary at 50.4°/51.4°/52.4° at 12% strength, and the 46°
  Alexander dark band. Gated on sun elevation, applied to sky pixels only (`docs/SKY-OPTICS.md`).
* **Volumetric clouds panel** (`ApplicationLauncher` button, window id 33026). The stock EVE
  button opens the whole config editor; this one opens a dedicated window: a live status block fed
  by the renderer's diagnostics snapshot (body, layers, intervals, reprojection factor, culling
  counters, baked cloud slices, CPU ms), one slider per cloud knob, and Apply/Discard/Reload. It
  writes into the active preset object and re-applies through the same path as the cfg, so the
  preset file stays the source of truth (`docs/PANEL.md`).
* **Cloud-on-cloud shadows** (the "overcast comes from the layer below" item). A layer whose config
  says `receiveShadowsFromLayer = <another layer>` now actually loses direct sun light where that
  layer covers the sun: the shader walks from the mean cloud position along the sun to the caster's
  altitude and samples the caster's coverage map there (six cube faces for `AlphaCubeMap` configs
  such as RSSVE, one equirect sample for plain `AlphaMap` configs), then attenuates only the direct
  term so the upper deck reads flat grey instead of bright-topped. The C# had been writing
  `shadowCasterDensity`/`shadowCasterSphereRadius`/`ShadowCasterCloudCoverage` and the caster
  rotation into the void since 1.0.0 — they were *dead* names in the ported shader (see
  `docs/UNIFORMS.md` §3.1). New knob `shadowCasterStrength` (default `0.5`, `0` restores the 1.1.1
  look). Cost is one coverage lookup per pixel behind a uniform branch; there is no second march.
  Details: `docs/SHADOW-CASTER.md`, tuning: `docs/TUNING.md` §5.
* **An in-game panel for the volumetric clouds** (`docs/PANEL.md`). A second toolbar button —
  next to EVE's own, with its own cloud glyph so the two cannot be confused — opens a compact window:
  a live status block pulled from the same numbers the `[EVE] raymarched pass` log line prints
  (layers, intervals, culled, cloud slices baked, cpu/gpu), and live sliders for the three knobs this
  fork added (`edgeWisp`, `shadowCasterStrength`, `depthUpsampleThreshold`) that apply on release
  through the same path a preset switch takes. Reaching those three used to need Alt+0 plus three
  nested selectors, and a change was only re-read on the next preset switch. Deliberately **not** a
  second settings system: the preset file stays the source of truth, "Reload preset" discards live
  tweaks, and the raymarch-budget knobs stay on the EVE window's quality page.
* **`docs/SHADOW-CASTER.md`**: what the config links, which uniforms the C# feeds, the occlusion
  formula, why only the direct term is attenuated, what this approximation does *not* reproduce
  (small isolated caster clouds under-shadow because a coverage lookup only sees the silhouette),
  and the offline + on-device verification steps.
* `docs/ACCEPTANCE.md` (T1): the on-device checklist. Deployment and the three rollback levels,
  the three log lines that must appear and the two that appear but are not errors, then the six
  acceptance items with a fixed camera position, a pass criterion and a "look here first" entry
  for each — written so the person with the game does not have to reconstruct the reasoning.
* `docs/MULTI-BODY.md` (T5): why two clouded bodies in one frame still only render the nearer one —
  the four single-body assumptions with file:line anchors (the radial interval sweep, the single
  sphere the reconstruction solves against, the global light volume, the shared temporal history),
  the three things that are already per-body correct, a five-phase plan that keeps each phase
  independently shippable, and the memory arithmetic that decides the design. No behaviour change.
* **Vertical structure: base darkness, coverage breakup, detail erosion, sculpted shading**
  (`EVEBaseDarkness` 0.45, `EVEMacroBreakup` 0.3, `EVEDetailErosionScale` 1.0, `EVESculptStrength`
  0.5). A fully covered deck has no shading variation of its own — the sun term saturates and the
  ambient term is uniform — which is the "flat ceiling" read. Three changes put the relief back
  into the lighting: light penetration darkens the underside of a thick layer (vertical ramp on
  the ambient term); one mip-3 `BaseNoiseTexture` fetch at mid-ray lets a third of a full sheet
  fall below the visibility threshold, so a uniform ceiling becomes a broken deck; and four
  coarse-mip fetches of the density field give a gradient, which is used as a perturbed normal
  and rerun through the sun term. The relief now comes from the density field itself, so it
  moves with the clouds and survives a low sun (`docs/LIGHTING.md` §5).
* `edgeWisp` config item (T2): the cloud-edge feature the user asked for, implemented as two
  extra curl octaves on the density sampling position (8x/16x the base tiling, amplitude decaying
  with height in the shell and following `curlNoiseStrength`) plus a thinning ramp over the
  low-density tail just above the marcher's own visibility threshold. The cloud core is multiplied
  by exactly 1.0. Ships **on at `0.35`** (two curl fetches per marcher step); set it to `0` in a
  preset for a bit-identical return to the ported blob edges. See `docs/TUNING.md` §4.
* `docs/LIGHT-VOLUME.md` (T3): the light volume is baked but nothing on this build draws it —
  neither `EVE/RaymarchCloud` nor `EVE/ReconstructRaymarchedClouds` declares a light-volume
  sampler, so `LIGHT_VOLUME_ON`/`OFF` are empty switches in the *original* too, and the only
  sampler of the global (`EVE/LightVolumeShadow`) is absent from the bundle. What actually
  shades the clouds (in-shell `lightMarchSteps` marching, plus the 2D cloud-shadow map) and what
  restoring light-volume shadows would take.
* **`depthUpsampleThreshold`** config item (T4). The same-surface tolerance of the
  depth-guided upsampler was hard-coded to `0.100000001` in four comparisons; it is now a
  `[0.001, 2]`-clamped config value bound to the `EVEDepthUpsampleThreshold` global
  uniform. Default 0.1 keeps the 1.0.0 output bit-identical, and the shader falls back to
  0.1 when the uniform is unbound, so a failed bind cannot turn the rejection test into
  "reject everything". See `docs/TUNING.md`.
* `docs/SAMPLERS.md`: all 31 texture slots of `EVE/RaymarchCloud` with the C# that supplies
  each one, the wrap/filter it was created with, and the four judgement calls left for
  on-device A/B.
* `docs/TUNING.md`: every knob that changes the picture, with what to look at when tuning it.
* `tools/rebuild.sh`: one command for the whole loop (C# → flatten → offline HLSL check →
  Unity batch bundle → package) with the shader-error grep as the pass criterion.
* **`maxSunSlewBeforeFastRefresh`** config item (T9). The direct-light sweep is spread over
  `directLightTimeSlicing` frames, so slices baked early in the cycle carry a sun direction
  that is up to seven frames stale. Once the sun has moved further than this many degrees
  since the last completed sweep, the remaining slices are baked at once (multiplied by at
  most `timewarpRateMultiplier`). Default 1.0° never triggers during a normal day
  (~0.25°/s over an 8-frame sweep is 0.03°), so the default output matches 1.0.0; `0`
  disables the boost. See `docs/TUNING.md` §2.
* **`reflectionProbeStepSizeMultiplier` / `reflectionProbeGodraysStepCountDivisor`** config
  items (T8). Reflection probes marched clouds at exactly 5x the main camera's step size and
  at exactly a fifth of its godray budget, both hard-coded. They are now `[1, 20]`-clamped
  config values; a non-positive entry falls back to the ported 5, so a hand-edited config
  cannot produce a zero step size or a divide-by-zero. See `docs/TUNING.md` §3.
* `docs/ARCHITECTURE.md`: the three things the code cannot tell you — why a body with any
  `layerRaymarchedVolumeV5` node silently drops all of its 2D layers, how the 2000 R / 4000 R
  load/unload hysteresis works, and how camera identification works now (T10).
* `docs/DIAGNOSTICS.md`: field-by-field table for both `[EVE]` log lines plus the triage
  cookbook for "the sky has no clouds and nothing was logged".
* **`tools/audit_uniforms.py` + `docs/UNIFORMS.md`**: cross-checks every uniform name the C#
  writes against what the bundle's compiled variants declare *and* what the shader sources
  declare, so the three outcomes (works / stripped from this variant / dead everywhere) are
  distinguishable. `docs/UNIFORMS.md` carries the dead list for the two overridden shaders and
  names the unported features behind it — cloud-on-cloud shadows, the lightning occlusion
  array, the colour map, `skylightTintMultiplier`, `stepSizeLight`. A `SetFloat("typo", …)` is
  a silent no-op in Unity; this is the mechanical way to stop shipping those. `tools/rebuild.sh`
  runs the audit after the bundle build and prints both counts on every build.
* **`Utils/CameraRoles.cs`**: `CameraRole` enum plus one cached `GetRole(camera)` lookup, with a
  `CameraRoleMarker` component that a camera can carry to declare its role explicitly. The nine
  name comparisons in the Atmosphere code (`"Camera 00"`, `"Camera 01"`, `"TRReflectionCamera"`,
  `"Reflection Probes Camera"`, `"DepthCamera"`, `"NearCamera"`) all go through it now, so a mod
  that renames or re-parents a camera no longer silently loses clouds in it (T10). Scatterer's
  own copies of the comparisons are left alone on purpose — see `docs/ARCHITECTURE.md` §3.3.

### Changed

* **Edge wisps were rebuilt to fray the silhouette instead of cutting it.** The 1.1.x pass
  multiplied a band of coverage just above the visibility threshold: high curl frequency (8x/16x)
  plus a multiplicative step at the band's upper edge compressed the marcher's own gradual fade
  into a couple of samples -- physically a hard cut, and it read as one. The pass now displaces at
  4x/8x with a larger amplitude (veil curvature instead of tuft width) and modulates the whole
  tail with one extra curl fetch centred on 1.0, so samples are pushed above and below the fade
  rather than the fade being ended (`docs/LIGHTING.md` 5.6).
* **Packaging survives a locked output zip.** `dist/VolClouds-tweak.zip` is regularly held open by
  Explorer (or by whatever showed it to the user), and Windows refuses to replace a file with an
  open handle; the pack step now falls back to `dist/VolClouds-tweak-<version>.zip` instead of
  failing the build. It also copies the two new shader sources into `BuildOut/shaders/`.
* **The diagnostics GPU probe gives up instead of costing every frame.** `CaptureFrameTimings` +
  `GetLatestTimings` ran per camera per frame on builds without frame timing stats — which is every
  KSP install — and always returned 0. This Unity has no `FrameTimingManager.IsFeatureEnabled()`, so
  the build is probed once a second for a minute and the calls stop for good afterwards; `gpuMs`
  keeps printing `n/a`. `docs/DIAGNOSTICS.md` §3.
* **Two more per-event allocations are gone** (extra round): `ScreenSpaceShadowsManager.RegisterCamera`
  rebuilt the whole camera→renderer dictionary through `Where().ToDictionary()` just to drop destroyed
  cameras (now pruned in place), and `WetSurfacesRenderer` looked up the near/far cameras with
  `Camera.allCameras.Where(...).FirstOrDefault()` (two copies of the camera array plus a LINQ
  iterator) — now `CameraRoles.FindFirst()` with one reused buffer.
* **Edge wisps are on by default** (`edgeWisp = 0.35`): 1.1.0 shipped the feature with the
  uniform at `0`, which is bit-identical to the ported algorithm but does nothing. This build turns
  it on at the two-fetch tier. Everything about it is still reversible from the preset, and the value
  `0` remains a pixel-exact return to the 1.0.0 silhouette (`docs/TUNING.md` §4).
* **The per-frame layer-overlap sweep no longer allocates** (T11).
  `ResolveLayerOverlapIntervals` built a fresh `HashSet`, a fresh `List<OverlapInterval>` and one
  `List<CloudsRaymarchedVolume>` per interval, for every camera, every frame. The interval lists
  are rented from a pool that grows to its high-water mark and the "which layers are open" set is
  a plain list (a clouded body has a handful of layers). Two per-cloud-type arrays in
  `SetCloudTypesShaderParams` are cached for the same reason: a `CloudsPainter` repaint calls
  `ApplyShaderParams` on every frame the brush moves.
* **The diagnostics line carries the numbers T8/T9 used to be judged by eye** (T11): the log line
  now ends with `culled=<shell culls>/<other-body skips>`, `directSlices=<baked>/<total slices>`,
  `cpuMs=<avg OnPreRender>@<frames>f` and `gpuMs=<avg>@<samples>s`. GPU time comes from
  `FrameTimingManager` and prints `n/a` when the player was built without frame timing stats
  (KSP's case) instead of a misleading `0.00`. See `docs/DIAGNOSTICS.md`.

---

## [1.0.0] — first packaged release

The first release that ships a drop-in `GameData/` tree, a documented shader override
bundle and both documents (README + this changelog).

### Added

* **Shader override bundle** (`eveshaders_tweak.bundle`). `ShaderLoader` loads it after
  the stock bundle and lets it replace shaders with the same name (log:
  `[EVE] Shader <name> overridden`). Removing the file disables every shader change
  without touching the DLLs.
* **`EVE/ReconstructRaymarchedClouds` in HLSL.** The temporal reconstruct / composite
  stage was not available as an override before; it is now compiled from the recovered
  GLSL and included in the bundle.
* **Depth-aware upscale of the low-resolution ray buffer** (`EVE_DEPTH_AWARE_UPSAMPLE`).
  Four taps in the 1/3-resolution buffer, weighted bilinearly and rejected where the
  scene depth disagrees with the depth at the current pixel; falls back to the previous
  single tap on flat neighbourhoods and when depth is unavailable.
* **Shared noise-volume cache** (`NoiseVolumeCache`). 128³ noise bakes are reference
  counted and shared between layers with identical noise settings. 19 stock layers:
  ~114 MB of noise textures before, ~12 MB now, and one bake instead of nineteen.
* **Shell culling** (`cullShellsOutsideView`). A cloud shell is skipped for a camera when
  it projects entirely outside the view (angular-radius test against the half-diagonal
  FOV, 3° margin). Conservative: never culls when the camera is inside the shell.
* **Diagnostics.** A throttled (5 s) per-camera summary line
  (`camera / body / volumes / bounds / intervals / lightVolume / reflectionProbe /
  resolution / reprojection`) and a per-apply cloud inventory
  (`[EVE] clouds applied: N bodies, M layers`). Both can be switched off.
* `singleBodyPerCamera` — one clouded body per camera, see *Fixed*.

### Changed

* Per-frame intersections, layer bounds and overlap volumes are sorted with a
  zero-allocation stable insertion sort instead of three `LINQ OrderBy(...).ToList()`
  calls. Ordering semantics are preserved (stable, same comparers).
* Ten per-frame `RenderTargetIdentifier[]` allocations moved to cached arrays that are
  refilled only when the render targets are recreated.
* The per-layer cloud-type uniform array is reused instead of reallocated every frame.
* Density-curve lookup texture: `RG16` → `RGHalf`. The curve is sampled once per density
  probe and once per light sample, so 8 bits per channel quantized cloud base and top
  into visible bands. Cost: +32 KB per layer.
* Curl noise volume: `RGB565` → `RGB111110Float`. The curl offset is applied directly to
  the sample position, so 5-6 bit components turned the noise into visible stair steps.
  Cost: +4 MB per distinct noise configuration (shared by the cache above).
* Base noise volume: `R8` → `R16` for the same reason one step earlier — the erosion test
  compares against a threshold, so 8 bits produced contour rings.
* Benchmark numbers for the stock config are in the README.

### Fixed

* **D3D11 clip plane in `EVE/RaymarchCloud`.** The fullscreen quad was emitted with
  `gl_Position.zw = (-1, 1)` (the GL near plane) which is outside the D3D depth range, so
  the pass could be clipped away entirely on Windows. Now `(0, 1)`.
* **Cross-body contamination.** The composite, reconstruction and light volume read
  `planetRadius` / `sphereCenter` from whichever cloud volume happened to be submitted
  first for the camera, so a second clouded body in the same view was composited against
  the wrong sphere. The renderer now keeps one body per camera, and on takeover clears
  the stale volumes, rebases the previous parent position (so the switch frame does not
  produce a motion-vector spike) and re-collects.
* **Command buffer attach/detach was not paired.** Detach was gated on the same flag that
  `OnPostRender` reset, so an early-out could leave the buffer attached and re-add it next
  frame. Attachment is now tracked by its own flag and detached unconditionally.
* **Empty-volume passes are no longer recorded or drawn.**
* **Shader resources are released.** Two noise render textures and three materials per
  layer were created in `Apply()` and never freed, so re-applying a config leaked a
  layer's worth of GPU memory each time. All of them go through `ReleaseShaderResources()`
  now, and `Remove()` calls it.
* **`HistoryManager` indexer** clamped with `Math.Min(x, length)` (off-by-one: index
  `length` threw) instead of `length - 1`.
* **`Sun.Instance` null guard** in the raymarched volume setup.
* **`ShaderLoader` no longer throws** when a bundle shader has the same name as an
  already-loaded one; the override replaces it instead (`Dictionary` indexer, not `Add`).
* **Shader uniform rebinding.** Both shaders addressed their matrices as
  `hlslcc_mtx4x4unity_MatrixVP`, `hlslcc_mtx4x4cloudRotation`, … — the names Unity's GL
  backend invents, not the names the C# sets or the D3D backend binds. Nothing uploaded
  them, so on D3D those uniforms were zero. The tweak copy now uses Unity's real builtin
  names (declared by `UnityCG.cginc`) for the camera matrices and the plain material names
  (`cloudRotation`, `currentVP`, …) as `float4x4` for the rest, with `ev_col0..3` helpers
  that keep the GLSL "index a column" convention the multiplies were written against.

### Known issues

* Both shaders take their y flip from `_ProjectionParams.x`. That is the OpenGL
  convention (Unity sets it to `-1` when the view is flipped); on D3D it is normally `1`.
  If the clouds come out vertically mirrored, dropping the two `* _ProjectionParams.x`
  factors in the vertex stage is the fix.
* The recovered `EVE/RaymarchCloud` variant contains no light-volume sampling, so the
  `LIGHT_VOLUME_ON` / `LIGHT_VOLUME_OFF` variants compile to identical code. Sunrise and
  sunset lighting and cloud-on-cloud shadows should be compared against the original
  bundle before this is considered done.
* `PAINTER_UNSTABLE_MASK_*` and `LIGHTNING_UNSTABLE_MASK_*` are declared for compatibility
  but have no code path in the recovered variant.
* Sampler wrap modes were inferred (`point_clamp` / `linear_clamp`). A flow-map or STBN
  seam would be the symptom if one of them is wrong.
* Not yet verified in a full game session by a second party; the offline checks were
  "all assemblies compile", "the shader bundle compiles with zero shader errors" and
  "the renderer's own diagnostics report the expected volumes per body".

---

## Internal iterations (0.x, unversioned, never packaged)

* **Recovery.** Decompiled the eleven EVE managed assemblies and the Scatterer assembly
  from the shipping volumetric build; extracted the shader sources from
  `eveshaders.bundle`; made the whole tree compile as a solution.
* **Readability pass.** Documented the C# (locals renamed, per-file documentation),
  ported all nineteen shaders to HLSL by hand.
* **First correctness pass.** Multi-body handling, command buffer bookkeeping, resource
  release, GC removal, diagnostics.
* **First shader compile pass.** Made the recovered HLSL legal for D3D (scalar
  broadcasts, GLSL vector comparisons, cross-branch variable scope), consolidated
  samplers, produced the first `eveshaders_tweak.bundle`.
* **GPU memory pass.** Noise cache, texture format upgrades, shell culling.
