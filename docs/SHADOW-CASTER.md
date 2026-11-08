# Cloud-on-cloud shadows

Status: **ported as a coverage-map lookup** (1.1.2), not as the stock second density march.
This file records what the C# already did, what the shader now does with it, and what is
still missing.

## 1. What the config asks for

A raymarched layer can name another raymarched layer below it:

```
layerRaymarchedVolume
{
    receiveShadowsFromLayer = Kerbin-clouds2   // this layer sits above Kerbin-clouds2
    receivedShadowsDensity  = 5                // strength knob, 100 when absent
}
```

`src/Atmosphere/Atmosphere/CloudsRaymarchedVolume.cs` links the two objects
(`SetShadowCasterLayerRaymarchedVolume`, `:884` onwards) and then feeds four things to the
materials:

| uniform | written in | value |
| --- | --- | --- |
| `shadowCasterDensity` | `SetShaderParams`, `:928` | `receivedShadowsDensity` (default `100`) |
| `ShadowCasterCloudCoverage` + `cubeShadowCasterCloudCoverage*` | `SetShadowCasterMaterialParams`, `:416` | the caster's coverage map, applied with slot index `3` |
| `shadowCasterSphereRadius` | `SetShadowCasterMaterialParams` `:427` and `SetShaderParams` | the caster's `InnerSphereRadius` |
| `shadowCasterCloudRotation`, `_ShadowDetailRotation`, `shadowCasterTimeFadeDensity/Coverage` | `updateShadowCasterMaterialProperties`, `:1201` | per frame, when a caster exists |
| `alphaMask3`, `useAlphaMask3` | `TextureWrapper.SetAlphaMask(mat, 3)` | one-hot channel selector for the coverage map |

Until 1.1.2 none of those names existed in the ported shader (they showed up as *dead* in
`tools/audit_uniforms.py`), which is why an overcast deck on top of a lower deck used to look
exactly as bright as the deck below it.

## 2. What the shader does now

`shaders/hlsl/RaymarchCloud.hlsl`:

* `eve_shadow_caster_transmittance(cloudMidPosition)` is called once per pixel, right after the
  direct sun term (`skyColor = sunDot * cloudColor * windAccum0`) is assembled in the resolve
  block.
* It walks from the mean cloud position along `_SunDir` to the caster's altitude
  (`innerSphereRadius - shadowCasterSphereRadius`), maps that point into the caster's cloud space
  with `shadowCasterCloudRotation`, and samples the caster's coverage map there: six cube faces
  when the config ships `AlphaCubeMap` (what RSSVE uses), one equirect sample when it ships a
  plain `AlphaMap`.
* The result attenuates **only the direct term**. The ambient term (`skylightMultiplier`) is
  untouched, so a fully covered upper deck keeps its brightness but loses its lit top — which is
  what an overcast deck actually looks like.

Occlusion is

```
occlusion = saturate(coverage * saturate(shadowCasterDensity * 0.1) * shadowCasterTimeFadeCoverage
                     * EVEShadowCasterStrength * aboveRamp)
transmittance = 1 - occlusion
```

* `shadowCasterDensity` is normalised by `0.1`, so the stock `receivedShadowsDensity = 5` becomes
  `0.5` and anything at or above `10` saturates.
* `aboveRamp` is `saturate((innerSphereRadius - shadowCasterSphereRadius) / max(0.02 * casterRadius, 500))`:
  layers at or below their caster get exactly `1.0` (no shadow), and two layers that nearly touch
  fade in instead of popping.
* `EVEShadowCasterStrength` is the new `shadowCasterStrength` quality knob (default `0.5`), and
  `0` short-circuits the whole thing before the lookup, i.e. the 1.1.0 look.

The gate for "is there a caster at all" is `shadowCasterSphereRadius > 0`. It is written on every
apply in `SetShaderParams` (so removing the `receiveShadowsFromLayer` node turns the feature off on
the next apply) and on every frame in `updateShadowCasterMaterialProperties` /
`clearShadowCasterMaterialProperties` (so a caster that disappears mid-flight cannot leave a stale
radius behind).

## 3. Cost

One cube lookup (six `SampleLevel` on a small coverage texture, same as the existing sun-coverage
lookup) and a handful of scalars per pixel, behind a uniform branch that is false for every layer
without a caster. No second march, no extra render target, no extra pass.

## 4. What this is not

The stock shader marches the caster's density field along the sun ray, so a thin wisp of the lower
layer casts a proportional shadow. This build samples the caster's *coverage* map, so the shadow
follows the caster's silhouette at the planet scale but not its small-scale structure. At the
altitudes RSS configs use (2–3 km apart) the two agree on the overcast read; they will disagree on
single small clouds, where this version under-shadows.

Restoring the stock behaviour means porting `CLOUD_SHADOW_CASTER_ON` from a stock variant that
contains it (the six-face stock name table has the branch, the original build's GLSL variant does not):
`docs/UNIFORMS.md` §3 has the full list of names that would come back with it.

## 5. Verifying

Offline:

```bash
python tools/flatten_cbuffer.py
python tools/hlsl_check_unity.py EVE-Tweak/Assets/Shaders/RaymarchCloud.hlsl VS_RaymarchCloud PS_RaymarchCloud
python tools/shader_reflection.py BuildOut/GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle \
    --shader EVE/RaymarchCloud --search ShadowCaster
```

The reflection dump must list `EVEShadowCasterStrength`, `shadowCasterSphereRadius`,
`shadowCasterCoverageIsCube`, `shadowCasterCloudRotation`, `shadowCasterDensity`,
`shadowCasterTimeFadeCoverage`, `alphaMask3`, `useAlphaMask3`, `ShadowCasterCloudCoverage` and the
six `cubeShadowCasterCloudCoverage*` faces.

On device (this is `docs/ACCEPTANCE.md` §3 item 3, now with a knob):

1. Find two stacked layers, e.g. Kerbin with `StockVolumetricClouds` (`Kerbin-clouds1` above
   `Kerbin-clouds2`, `receivedShadowsDensity = 5`).
2. Look at the top deck from above, sun at the side. With `shadowCasterStrength = 0.5` the lit side
   should read noticeably flatter than with `0`; the terminator should stay where it is.
3. `shadowCasterStrength = 0` must look identical to 1.1.1.
4. If the top deck goes uniformly black, the caster's coverage map is not bound (see §2's gate) or
   `shadowCasterDensity` is at its default `100` on a layer that *is* the caster itself.
