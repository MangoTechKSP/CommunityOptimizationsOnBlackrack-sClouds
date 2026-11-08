# Which stage the light volume actually takes part in — T3's conclusion

> This document answers the question left open in three successive versions: "`LIGHT_VOLUME_ON`
> and `LIGHT_VOLUME_OFF` compile to exactly the same code — is the variant lost, or was there never
> a difference?".
>
> Conclusion: **there never was a difference**. The light volume does not pass through either of the
> two overridden shaders at all, and its only consumer, `EVE/LightVolumeShadow`, is not in the stock
> `eveshaders.bundle` — on this build the light volume is a dead path that is **baked but read by
> nobody**. Below is the evidence, and the defensive changes made because of it.

## 1. The two overridden shaders do not sample the light volume (two independent pieces of evidence)

`eveshaders_tweak.bundle` only overrides `EVE/RaymarchCloud` and `EVE/ReconstructRaymarchedClouds`,
so the question reduces to "do these two shaders read the light volume".

**Evidence one: the property tables in the original build.** Use `tools/shader_reflection.py` to dump
the uniform name table of every pass of the two shaders in the original build's bundle
(`m_NameIndices` is that table, capped at 61 names):

```bash
python tools/shader_reflection.py GameData/EnvironmentalVisualEnhancements/eveshaders.bundle --shader EVE/RaymarchCloud
python tools/shader_reflection.py GameData/EnvironmentalVisualEnhancements/eveshaders.bundle --shader EVE/ReconstructRaymarchedClouds
```

Neither table contains any of `lightVolume` / `directLightVolume` / `lightVolumeDimensions` /
`paraboloidToWorld` / `innerLightVolumeRadius`; `directLightVolume` appears **0 times** in the whole
25,468,668 B of deserialized data, and `lightVolume` appears 26 times (all of them in the name
tables of `EVE/ReprojectLightVolume`, `EVE/LightVolumeShadow` and the two compute kernels).

**Evidence two: the original build's GLSL.**
`shaders/glsl/RaymarchCloud/EVE__EVE_RaymarchCloud__15__2b380cb5471d.glsl` has only three
`sampler3D`:

| Line | Declaration |
| --- | --- |
| `:118` | `sampler3D CurlNoiseTexture` |
| `:121` | `sampler3D BaseNoiseTexture` |
| `:122` | `sampler3D DetailNoiseTexture` |

There is no `sampler3D lightVolume` anywhere. The same holds on the
`EVE/ReconstructRaymarchedClouds` side (only the rays/history buffer families).

## 2. So those two keywords are empty switches

`src/Atmosphere/Atmosphere/CloudsRaymarchedVolume.cs:679-702` (`ApplyShaderParams`) switches
`LIGHT_VOLUME_ON/OFF` and `DISCRETE_LIGHT_SAMPLES_ON/OFF` according to
`LightVolumeSettings.UseLightVolume` and `LightMarchSteps > 0` respectively. Each of those two
strings appears **0 times** in the 25.4 MB of original-build data — the original shaders have no
such keyword variants at all, `EnableKeyword` merely flips a switch that nobody reads, so "ON/OFF
compile to the same code" is **correct behavior**, not a variant dropped during the port.

Why it is kept: the C# side logic and the config options were carried over from the original build,
and deleting them would fork `LightVolumeSettings` semantics away from upstream. And don't document
it in `docs/TUNING.md` as a switch that "changes image quality when you toggle it".

## 3. Where the volumetric look of the clouds comes from (not the light volume)

- **Discrete marching along the sun direction inside the shell**: `lightMarchSteps` + `stepSizeLight`
  (declared at `:96` in the original GLSL, where `:553` `u_xlati8 = lightMarchSteps << 1;`
  determines the step count, with the matching `lightMarchSteps` / `lightMarchDistance` in
  `shaders/hlsl/RaymarchCloud.hlsl`), written into the material every frame by `ApplyShaderParams()`
  at `src/Atmosphere/Atmosphere/CloudsRaymarchedVolume.cs:650-690`. The clouds' self-shadowing and
  cloud-on-cloud shadows happen in this loop and have nothing to do with the light volume.
- **The 2D cloud shadow map**: `EVE/ScreenSpaceCloudShadow` (in the original bundle, casts shadows
  normally), which uses `BlendBetween2DShadowsAndLightVolume` to decide "whether the near range
  yields to light-volume shadows". That flag is set by
  `src/Atmosphere/Atmosphere/ScreenSpaceShadowsManager.cs:230/235`, with the condition
  `lightVolumeShadowMaterial != null && cloud2DShadowMaterials.Count > 0` — see the next section:
  the former is permanently null on this build, so the flag is permanently false and the 2D cloud
  shadows take over for the whole range. That is a **safe degradation**, not a defect.

## 4. `EVE/LightVolumeShadow` is not in the bundle

```bash
python tools/shader_reflection.py GameData/EnvironmentalVisualEnhancements/eveshaders.bundle --names-only | grep -i shadow
# EVE/PlanetShadow, EVE/ScreenSpaceCloudShadow, EVE/CloudShadow  --  there is no LightVolumeShadow
```

The stock bundle has 37 `EVE/` shaders in total and no `EVE/LightVolumeShadow`; there is no second
bundle next to `eveshaders.bundle` either. And `ShaderLoaderClass.FindShader`
(`src/ShaderLoader/ShaderLoader/ShaderLoaderClass.cs:134-147`) only queries its own dictionary and
**does not fall back to `Shader.Find`**; when it cannot find the shader it logs
`[EVE] Could not find shader <name>` and returns null. So the original
`new Material(LightVolumeShadowShader)` in `LightVolume.Init()` gets null on a normal install —
Unity's `Material` constructor throws on a null shader, and `LightVolume` is created on the
**per-frame path** in `DeferredRaymarchedVolumetricCloudsRenderer.OnPreRender()`
(`DeferredRaymarchedVolumetricCloudsRenderer.cs:750`), so once it throws it throws every frame.

**Changes (T3 commit):**

| Location | Change |
| --- | --- |
| `src/Atmosphere/Atmosphere/LightVolume.cs` `Init()` | `reprojectLightVolumeComputeShader = ShaderLoaderClass.FindComputeShader("ReprojectLightVolume"); useComputeShader = ... != null;` — if that fails, fall back to the raster path and log one line (previously it dereferenced `GetKernelThreadGroupSizes` directly) |
| same as above | when the raster path is unavailable too (`ReprojectLightVolumeShader == null && !useComputeShader`), set `bakeUnavailable = true` + `LogError`: with neither compute nor raster there is no "reprojection" to speak of |
| same as above | `lightVolumeShadowMaterial = (LightVolumeShadowShader != null) ? new Material(...) : null;`, and log one line when it is null (the comment points at this document) |
| `LightVolume.Update(...)` | starts with `if (updatedThisFrame \|\| released \|\| bakeUnavailable) return;`; at the end, the 10 `Set*` lines that publish `lightVolumeShadowMaterial` and `ScreenSpaceShadowsManager.UpdateLightVolumeShadowMaterial(...)` are wrapped entirely in `if (lightVolumeShadowMaterial != null)` |
| new `LightVolume.BakeUnavailable` (static, does **not** trigger `Instance` creation) | gives callers an honest criterion |
| `DeferredRaymarchedVolumetricCloudsRenderer.cs:750` | `if (useLightVolume && mainFlightCamera && !LightVolume.BakeUnavailable)` |
| `DeferredRaymarchedVolumetricCloudsRenderer.cs:1271` | `scattererCloudLightVolumeEnabled = renderingEnabled && useLightVolume && !LightVolume.BakeUnavailable` |

These guards **change nothing when the shader exists** (when `lightVolumeShadowMaterial != null` the
original path is followed verbatim), so they do not affect any environment that has
`EVE/LightVolumeShadow` installed.

## 5. How to confirm at runtime (for on-machine acceptance)

After installing, check `KSP.log`:

| Log | Meaning |
| --- | --- |
| `[EVE] Could not find shader EVE/LightVolumeShadow` | light-volume shadows unavailable (**expected on this build**, the 2D cloud shadows take over) |
| `[EVE] LightVolume: EVE/LightVolumeShadow is not in the shader bundle, cloud shadows stay on the 2D path` | same as above, the line we added |
| `[EVE] LightVolume: compute shader ReprojectLightVolume missing, using the raster fallback` | the raster reprojection path was used (should not appear under D3D) |
| `[EVE] LightVolume: neither the ReprojectLightVolume compute shader nor EVE/ReprojectLightVolume is in the shader bundle, light volume disabled` | the light volume is off entirely |

Then turn on `diagnosticsEnabled` and look at `[EVE] raymarched pass ... directSlices=N/M` (the
metric is defined in `docs/DIAGNOSTICS.md`): without either of the two Error lines above it should be
non-zero. **If the log shows the light volume baking but `directSlices` stays at 0, that is the T9
slice-ledger problem, not this section's business.**

## 6. What it would take to actually restore light-volume cloud shadows (not done; needs a real machine)

1. Port `shaders/glsl/LightVolumeShadow/*.glsl` to HLSL (the repository already has the GLSL;
   `shaders/hlsl/LightVolumeShadow.hlsl:58` is `Texture3D<float4> lightVolume;`, with the 8 samples
   at `:286-307`), going through the same chain as `tools/flatten_cbuffer.py`;
2. use a Unity batch run to **add** it to `eveshaders_tweak.bundle` (a bundle can only override
   same-named shaders; adding a new shader means changing `EVE-Tweak/Assets/Shaders/` and
   `TweakBundleBuilder`);
3. on-machine A/B: at a sunrise/sunset viewpoint, "do the cloud shadows go from flat to volumetric",
   plus the seam inside/outside 1000 m after toggling `BlendBetween2DShadowsAndLightVolume`.
4. Until then, `directLightTimeSlicing` / `ambientLightTimeSlicing` / `maxSunSlewBeforeFastRefresh`
   in `LightVolumeSettings` only control "how eagerly it bakes" and have no effect on the **visible
   image** — to save GPU you can turn `useLightVolume` off (the clouds' self-shadowing is unaffected,
   see §3).

## 7. Re-check commands

```bash
python tools/shader_reflection.py GameData/EnvironmentalVisualEnhancements/eveshaders.bundle --names-only | grep -i 'lightvolume\|shadow'
python tools/shader_reflection.py GameData/EnvironmentalVisualEnhancements/eveshaders.bundle --shader EVE/RaymarchCloud | grep -i light
grep -c 'sampler3D' shaders/glsl/RaymarchCloud/EVE__EVE_RaymarchCloud__15__2b380cb5471d.glsl   # → 3
grep -rn 'LIGHT_VOLUME_ON\|DISCRETE_LIGHT_SAMPLES' src/ --include=*.cs                      # → one site, ApplyShaderParams
```
