# Tuning knobs — what changes when you move one number

> This document covers only the switches a player or author can change that genuinely affect the
> image. Each one spells out: where the config key lives, its default value, which behaviour that
> default is equivalent to, the allowed range, and what to look at to judge you got it right.
> Anything not listed here is handled as the reference implementation's original algorithm — don't
> go changing it.

## Where the config lives

Under `GameData/EnvironmentalVisualEnhancements/` you'll find
`EVE_RAYMARCHED_CLOUDS_QUALITY.cfg` (EVE's own quality preset file). Each preset is one
`RaymarchedCloudsQuality` node; reload the config in-game after editing, or restart.

```cfg
EVE_RAYMARCHED_CLOUDS_QUALITY
{
    name = high
    temporalUpscaling = x9
    depthUpsampleThreshold = 0.1     // ← the T4 item in this document
    ...
}
```

## 1. `depthUpsampleThreshold` (default 0.1)

**Scope**: only the depth-guided upsampling (`EVE_DEPTH_AWARE_UPSAMPLE`) of
`EVE/ReconstructRaymarchedClouds` — the four bilinear taps. It does **not** affect the test inside
the nine-tap motion-vector reprojection (that 0.1 is intrinsic to the reference algorithm and stays
verbatim per the project's first rule).

**Semantics**: the ray buffer is at 1/N resolution, and reconstructing to full screen does a
weighted bilinear for each low-resolution texel. A neighbouring texel only participates when the
scene depth there is "on the same surface" as the current pixel's depth; the test is

```
|dTap - dCentre| / dCentre < depthUpsampleThreshold
```

| Value | What you see |
| --- | --- |
| `0.1` (default, = the hardcoded constant in 1.0.0) | Output is **bit-identical** to 1.0.0; the change is pure exposure |
| Smaller, `0.02`–`0.05` | Cloud-on-terrain boundaries (distant ridges, sea horizon) get sharper and the halo narrower; the cost is that edge pixels are more likely to drop wholesale into the "stock single-tap" branch, and fine high-frequency detail starts to appear |
| Larger, `0.2`–`0.5` | Boundary transitions get softer and less jittery; the cost is clouds bleeding onto foreground objects (cloud showing through behind a foreground ridge) |

**Allowed range**: `<= 0` in the config means "use the default 0.1"; the C# side finally clamps to
`[0.001, 2]` (`RaymarchedCloudsQualityManager.DepthUpsampleThreshold`). There is one more safety net
in the shader: if the uniform never gets bound it reads 0, and `eve_depth_upsample_tolerance()` falls
back to 0.1, so a "failed bind" can never turn into the catastrophic "threshold 0" behaviour.

**How to verify you got it right** (the parts doable without KSP are marked):

1. Offline: `bash tools/rebuild.sh`, and look for `PS_ReconstructRaymarchedClouds ... OK` and
   `shader errors: 0`; then run `python tools/shader_reflection.py EVE-Tweak/BuildOut/eveshaders_tweak.bundle --shader EVE/ReconstructRaymarchedClouds`
   to confirm `EVEDepthUpsampleThreshold` appears in the `$Globals` list (proof the uniform really
   made it into the variant instead of being stripped).
2. In-game: find a camera position where "cloud sits behind a distant ridge / the sea horizon",
   freeze time, and A/B three settings on the same frame (0.05 / 0.1 / 0.3), watching the
   **boundary between cloud and terrain**: the default must be exactly identical to 1.0.0 (the
   regression baseline), 0.05 must have a harder edge, and 0.3 a softer one where you can see cloud
   bleeding onto the ridge.
3. Jitter: record 5 s from a static camera and check the boundary for new frame-to-frame flicker (a
   lower threshold amplifies reprojection noise).

## 2. `maxSunSlewBeforeFastRefresh` (default 1.0 degrees, a child of `LightVolumeSettings`)

**Scope**: only the light volume's **direct light** time slicing (`directLightTimeSlicing`). Ambient
light is always sliced at a constant rate by `ambientLightTimeSlicing`, because ambient temporal
blending uses `volumeSlices / ambientLightSlicesToUpdateEveryFrame` as its denominator, and letting
that grow frame to frame would break the blend weights.

**Why it's needed**: the whole volume of 32 slices is refreshed over 8 frames, which means each
slice lags up to 7 frames between being baked and being used. The sun moves, and that lag shows up
as "the light on the clouds trails the sun's actual position" (slow drift). The old formula only
shortened the period under time acceleration (`TimeWarp.CurrentRate`); in normal flight the sun's
daily motion is too small for the problem to be visible, but at a sunrise/sunset camera position with
shutter-speed screenshots, or after a high-thrust burn swings the camera direction sharply, you'd see
the light "swim" into place.

**Semantics**: accumulate the angle the sun has turned since the last **full** sweep finished; exceed
this value and the remaining slices are refreshed within a single frame. The acceleration multiplier
reuses `timewarpRateMultiplier` (default 3).

| Value | What you see |
| --- | --- |
| `0` | Off (= 1.0.0 behaviour; only time acceleration affects the period) |
| `1.0` (default) | **Never triggers** while the sun moves normally (normal daily motion is ~0.25°/s, so a full 8-frame sweep covers only 0.03°); it only fires on a real jump. Default output matches 1.0.0 |
| `0.2`–`0.5` | More sensitive: light near the horizon at sunrise/sunset keeps up better; the cost is an occasional frame that bakes up to 32 extra slices (a one-off GPU spike) |

**Two things fixed along the way** (both in the same change):

1. **Slice allocation no longer truncates**: the old formula `volumeSlices / (int)slicing` with
   `slicing=10`, `volumeSlices=32` baked 3 slices per frame and only walked 30 per period, so the
   pointer could never catch up with itself (the cycle never closed). Now the remainder is spread
   over the first few frames (4,4,3,3,...) and one period is exactly 32. For the default `8/32` both
   versions bake 4 per frame and are bit-identical.
2. **Divide by zero**: with `slicing` set to 1 and time acceleration > 2, the old code's
   `(int)(1/3.0)=0` threw `DivideByZeroException`. Now it clamps to ≥1.
3. **Out-of-bounds and skipped slices on the multi-slice path**: the D3D path is "one draw writes at
   most 16 slices", and it cannot wrap past the end of the volume. The old code still advanced the
   pointer by 16 with no wrap present, so some slices were skipped; now it advances by the number
   actually written, stops at the end of the volume, and continues on the next frame.

**How to verify** (offline part): `dotnet build` + `bash tools/rebuild.sh`; there are no unit tests
on the C# side, so logic verification means plugging `volumeSlices`/`directLightTimeSlicing` in:
`32/8 → 4 per frame, one cycle every 8 frames`; `32/10 → 4,4,3,3,3,3,3,3,3,3 = 32`;
`32/1 → 32 per frame`. In-game part: at a sunrise camera position, record one clip with
`maxSunSlewBeforeFastRefresh` at 0 and one at 1.0 — the default setting should show no difference;
at 0.2 the light on clouds near the horizon should hug the sun's position more closely (compare with
fixed time acceleration and a fixed camera).

## 3. `reflectionProbeStepSizeMultiplier` / `reflectionProbeGodraysStepCountDivisor` (default 5 / 5)

**Scope**: affects only the **reflection probe** copy of the material
(`reflectionProbeRaymarchedCloudMaterial`); the main camera's stepping is completely unaffected. The
probe's clouds are there for part specular, portholes and water, and it is a low-resolution cubemap
refreshing far less often than the main view.

**These two numbers used to be hardcoded** (the `* 5f` in
`CloudsRaymarchedVolume.ApplyShaderParams`, the `/ 5f` in `UpdateShaderParams`); promoting them to
config defaults to behaviour exactly identical to 1.0.0.

| Item | Semantics | Turning it down | Turning it up |
| --- | --- | --- | --- |
| `reflectionProbeStepSizeMultiplier` | Multiplies the probe's `baseStepSize`/`maxStepSize`/`adaptiveStepSizeFactor` all at once | Finer clouds in reflections (more accurate boundaries on distant ridges and cloud seas), more expensive probe updates | Cheaper, but reflected clouds degrade sooner into "a blurry bright patch" |
| `reflectionProbeGodraysStepCountDivisor` | Probe godray step count = main camera budget / this value | The backlit light shafts in reflections are more complete | Cheaper, but shafts disappear from reflections sooner |

**The probe's existing settings (not part of these two switches — touching them flips a bigger
switch)**:

- `renderCloudsInReflectionProbes` (default `true`): set it to `false` and
  `DeferredRaymarchedVolumetricCloudsRenderer` skips the reflection camera
  (`TRReflectionCamera`/`Reflection Probes Camera`) entirely, so clouds vanish from reflections
  altogether. This is the cheapest setting.
- The probe material always has `lightMarchSteps = 0`, `stepSizeLight = 0` (no light samples), so
  clouds in the probe are **not** affected by the light volume or the discrete light sampling; that's
  also why the probe doesn't need to match the main camera's setting.

**How to verify**: `dotnet build` + `bash tools/rebuild.sh` (C# change, no shader rebuild needed).
In-game: find a specular surface (the back of a solar panel, or water), fix the camera, and take one
screenshot each with `reflectionProbeStepSizeMultiplier` at 1 and at 5 — cloud boundaries in the
reflections at 1 should hug the main view more closely; with `renderCloudsInReflectionProbes = false`
you see no clouds in reflections at all. Probe per-frame cost can be checked against the diagnostics
lines in `docs/DIAGNOSTICS.md` (the probe camera prints a line of its own).

## 4. `edgeWisp` (default 0.35 = on, 0 = off)

**Scope**: changes only the **density sampling** of `EVE/RaymarchCloud`; albedo, phase, lighting and
temporal reprojection are untouched. The main camera and the reflection probe read the same value (a
probe whose silhouette disagrees with the main view would show seams in reflections).

**What it does** (`shaders/hlsl/RaymarchCloud.hlsl`, T2):

1. **Two more curl-domain warps.** The original build's algorithm already has one curl displacement
   (`nextPos += curl*strength`); with `edgeWisp > 0`, two or three more are stacked on top, at 8×/16×
   the base noise frequency. The low-frequency one shoves the cloud lump off-centre, and the two
   high-frequency ones fold that "shoved boundary" once more — that is what turns the boundary from a
   smooth blob into strands. Amplitude =
   `edgeWisp * curlNoiseStrength * 0.42 * pow(1 - shellHeight, 3)`: a **cubic falloff**, so the
   displacement only lives in the outermost few percent (a linear falloff stretches the strands into
   branches — that's exactly where the 1.2.0 in-game shots came from). Layers with curl therefore get
   strands, and layers without curl don't get them out of thin air. Frequencies 4×/8×, and the third
   one (`edgeWisp ≥ 0.5`) is 12×.
2. **A multiplicative modulation** (replacing the old threshold thinning band as of 1.2.0). A 16×
   curl is sampled once more to get `wispField`, then
   `coverageFade *= 1 + edgeWisp * 0.85 * wispField`; the factor is centred on 1.0, so total cloud
   mass is conserved and the body isn't shrunk; it only pushes density up or down where the cloud is
   thin, so the edge breaks up **softly** instead of being cut hard. The 0.85 is the "crisper"
   setting: the bigger the push, the stronger the contrast in the strands.

| `edgeWisp` | Effect | Cost |
| --- | --- | --- |
| `0` | **Pixel-identical** to 1.0.0: the loop runs 0 times and the thinning factor is exactly 1.0 | 0 |
| `0.35` (default) | 2 extra curls, thinning band 0.018–0.032, fine strands appear at the edges | +2 `CurlNoiseTexture` samples per step |
| `0.5`–`1.0` | 3 extra curls, wider band, strandier and brighter | +3 samples per step; only noticeable at high step counts (small `maxStepSize`) |

**Why 0.35 and not more**: 0.5 is the "two becomes three" threshold; cross it and the cost goes up
50% for very little visual gain. 0.35 sits inside the two-curl range, where the thinning band is
already enough to turn the fading samples into a hard edge. If you want strandier edges, add more —
but work the cost out first.

**Why it's only on in this version**: this is an effect, not an optimization. Early users said to
hold off, and 1.1.x explicitly asked for it. The default lives in
`RaymarchedCloudsQuality.edgeWisp`, and every preset in `EVE_RAYMARCHED_CLOUDS_QUALITY.cfg` carries a
line for it; to get the 1.0.0 blob edges back, write `edgeWisp = 0` in the preset (that setting is a
pixel-exact rollback).

**How to verify** (offline):

```bash
python tools/hlsl_check_unity.py EVE-Tweak/Assets/Shaders/RaymarchCloud.hlsl VS_RaymarchCloud PS_RaymarchCloud
python tools/shader_reflection.py EVE-Tweak/BuildOut/eveshaders_tweak.bundle --shader EVE/RaymarchCloud | grep EVEEdgeWisp
```

**How to verify** (in-game, needs an A/B): same camera, same cloud map, same time, one screenshot
each with `edgeWisp = 0` and `0.35`:
- Edges: strand contrast goes up, fine wisps appear between cloud lumps;
- **Coverage**: the total cloud area in the frame should differ at the noise level (cloud cores
  multiply by 1.0, only the fade band is cut). If a whole cloud visibly shrinks, the
  `curlNoiseStrength` term is over-amplifying the amplitude, and you should back `edgeWisp` off;
- Lighting: albedo and phase are untouched, so colour, shadow direction and sunrise/sunset lighting
  must not change. **If they do, it's a bug.**
- Framerate: only visible at high march-step settings (low `maxStepSize`); measure once each with
  `cpuMs` from `docs/DIAGNOSTICS.md` or an external GPU tool — the difference should be far smaller
  than the step-budget items.

## 5. `shadowCasterStrength` (default 0.5 = on, 0 = off)

**Scope**: changes only the **direct light term** of `EVE/RaymarchCloud`; ambient light, albedo,
density and stepping are untouched. The main camera and the reflection probe read the same value.

**What it does** (`shaders/hlsl/RaymarchCloud.hlsl`, see `docs/SHADOW-CASTER.md`):
a layer configured with `receiveShadowsFromLayer = some lower layer` attenuates its own direct light
by "the lower layer's coverage at the point where the sun direction crosses that lower layer's
altitude"; ambient light is kept, so a fully overcast layer reads as "flat" rather than "dark".

| Value | Behaviour |
| --- | --- |
| `0` | Off. Equivalent to the 1.1.1 image (the shader returns 1.0 before the lookup) |
| `0.2` | Just enough to see the light differ between layers |
| `0.5` (default) | Release default: lit faces on upper layers flatten noticeably, the direction of the light/dark boundary doesn't move |
| `1.0` | Upper layers are almost pure ambient; the sun side goes fully white, the shadow side is unchanged |

**Why 0.5**: occlusion = coverage × `saturate(receivedShadowsDensity × 0.1)` × time fade × this
item. RSS configs are typically `receivedShadowsDensity = 5` (0.5 after normalising), so 1.0 would
drop direct light to 0 across the whole cloud region and stack up like one big blackboard; 0.5 sits
between "you can see the layering" and "a little depth survives".

**Offline verification**:

```bash
python tools/shader_reflection.py BuildOut/GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle     --shader EVE/RaymarchCloud --search ShadowCaster
grep -c EVEShadowCasterStrength eveshaders_tweak.reflection.txt   # should be 1
```

**In-game verification**: take Kerbin's two layers (`Kerbin-clouds1` from `StockVolumetricClouds` on
top, `receiveShadowsFromLayer = Kerbin-clouds2`), sun to the side, and compare `0` against `0.5`:
the upper layer's lit faces should flatten, the light/dark boundary shouldn't move, and the shadow
side shouldn't change; `0` must be pixel-identical to 1.1.1. If the whole layer goes black, see
`docs/SHADOW-CASTER.md` §5 item 4 (coverage texture not bound).

## 6. Lighting, sky and vertical structure (1.2.0)

These knobs all live in `EVE_RAYMARCHED_CLOUDS_QUALITY.cfg`, and all of them can also be dragged in
the volumetric cloud panel. The semantics, the formulas and the reasoning behind each default are
written up in `docs/LIGHTING.md` (lighting and vertical structure), `docs/GROUND-SHADOW.md` (ground
cloud shadows) and `docs/SKY-OPTICS.md` (sun halos and rainbows).

| Key | Default | Range | Effect |
| --- | --- | --- | --- |
| `multipleScattering` | 0.4 | 0–1 | Single scattering vs the four-term scattering approximation; 0 = dead black interior, 1 = everything solved as multiple scattering |
| `groundBounce` | 0.25 | 0–1 | Ground albedo bouncing up into the cloud base; 0 = off |
| `lightMarchJitter` | 1.0 | 0–2 | Jitter amplitude of the sun march; 0 = the deterministic stepping of the original port |
| `detailErosionScale` | 2.4 | 0.5–4 | How deep detail noise erodes; 1 = stock, 2.4 = release (close-up detail), 3 = harder cauliflower tops |
| `detailFrequency` | 3.0 | 0.5–8 | Detail-noise frequency multiplier: >1 makes erosion act on smaller cloud lumps; 1 = stock, 3.0 = release |
| `baseDarkness` | 0.22 | 0–0.8 | Light penetration from the top: thick layers get a darker base; the 0.45 setting greys the whole layer out |
| `macroBreakup` | 0.18 | 0–1 | Large-scale break-up of full-coverage layers; 0 = stock (higher values break clouds into lumps more readily) |
| `sculptStrength` | 0.85 | 0–1 | Density-gradient normal shading (makes flat slabs read as volume); 0 = the 1.1.x look |
| `edgeGlow` | 0.8 | 0–2 | Silver lining: thin edges brighten instead of going black; 0 = the 1.2.0 look |
| `contourHardness` | 2.6 | 1–6 | Transmittance curve: >1 steepens the cloud/sky transition and tightens the silhouette |
| `contourThreshold` | 0.35 | 0–0.9 | Coverage below this "skirt" is discarded whole; 0 = 1.2.2's pure power curve |
| `contourBand` | 0.18 | 0.02–0.6 | Width of the remaining transition (in coverage units, 0.18 ≈ 2 px); smaller looks more cut out |
| `cloudShadowStrength` | 0.6 | 0–1 | Cloud shadows on the ground; 0 = off (even the pass is unhooked) |
| `skyHaloStrength` | 0.4 | 0–1 | 22° ice halo; 0 = off |
| `skyRainbowStrength` | 0.55 | 0–1 | Primary + secondary bow (drawn behind the clouds since 1.2.4); 0 = off |

`sculptStrength`, `baseDarkness` and `macroBreakup` are the three items 1.2.0 added specifically to
fix "large flat clouds that don't read as three-dimensional"; `edgeWisp` became soft multi-sample erosion as of
1.1.2 (see §4). The four lighting/sky items add only one 3D sample or four full-screen computations
per frame; the cost is written up in each document's "Cost" section.

## 7. `edgeGlow` and the three contour items (1.2.3, defaults 0.8 / 2.6 / 0.35 / 0.18)

**Scope**: changes only the **composite stage** of `EVE/RaymarchCloud`; it doesn't touch stepping,
doesn't touch density, and adds no new samples.

**`edgeGlow` (silver lining)**: the accumulator is density-weighted, so brightness drops directly
where the layer thins out, and the edge of a whole cloud becomes a black rim (the signature look of
the 1.2.0 in-game shots). Now an edge weight is computed from `coverage = 1 - transmittance`:
`edgeGlow = (1 - saturate(coverage * 3))^2`, then `finalColor *= 1 + edgeGlow * EVEEdgeGlow`. Cloud
cores (high coverage) multiply by 1.0 and are unaffected; out in the sky `finalColor` is already 0 so
it can't bleed out into a halo, and only that ring of "still cloud, but thin" gets brightened. 0 =
neutral, above 1 it starts washing out, 2 is the ceiling.

**`contourHardness` (contour hardness)**: the marcher's transmittance is a soft transition, so the
silhouette drags a long haze behind it. This item raises `coverage` to `coverage^p` and then scales
the colour by the same ratio (`coverageRatio = hard/soft`), and `marchResult.w` is changed to
`1 - coverage^p` along with it:
- `1` = the original curve from the port (pixel-identical);
- `2.6` (default since 1.2.2) = the transition steepens noticeably, there's a visible edge between
  cloud and sky, and cloud-core brightness is unchanged;
- `1.5` = the 1.2.1 default: the transition is steeper but the edge still hazes out;
- `3`–`6` = hard edge, good for screenshots, but banding starts to show in motion.

There's a companion **scale** knob too: `detailFrequency` (default 1.8) multiplies the detail-noise
sampling coordinates so the same erosion acts on smaller cloud lumps — that's what 1.2.1's in-game
feedback "detail should act on a smaller scale" turned into; it only changes sampling coordinates and
adds no samples.

**`contourThreshold` + `contourBand` (1.2.3)**: 1.2.2 only made the gradient steeper, the gradient
itself was still there (in-game feedback: "the gradient is too long"). Now it's discard first, then
stretch: `banded = saturate((coverage - threshold) / band)` — coverage below 0.35 is thrown away
whole as skirt, and the 0.35–0.53 range is pulled to full, so the edge is only two or three pixels
wide. Threshold 0 + band 1 is equivalent to 1.2.2's pure power curve.

All three are one multiply / one `pow` per pixel, so the cost is negligible; they are also 1.2.1's
two algorithm-level answers to "edges go black" and "contours aren't hard enough" (not config-level
cover-ups).

## 8. Unrelated to performance

This item only changes the image criterion — not the step count, not the sample count — so framerate
is unaffected (apart from branch-prediction noise). If you want framerate, you want the
`baseStepSize`/`maxStepSize` group; see the reflection probe notes in `BUILD-NOTES.md`.
