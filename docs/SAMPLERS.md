# Sampler semantics table — where each texture slot's filter / wrap comes from

> Produced by T7. Origin: the GLSL taken from the original build declares textures but no samplers
> (GL keeps sampling state on the texture object), so when porting to HLSL there was no source-level
> answer to "which sampler does each texture use", and 1.0.0 used **inference** (two states:
> `point_clamp` / `linear_clamp`). This table replaces inference with "check the C# / check the
> texture-creation site"; the verdict is in the last column.
>
> Two real defects have already been fixed following this table (see §3): the point/repeat state of
> `StbnBlueNoise`, and the repeat state of `_FlowMap`.

## 1. Where the evidence comes from

In Unity the state of a single sampling operation is decided by the "inline sampler state written in
the shader", whereas the original build relies on "the texture object's own `filterMode`/`wrapMode`".
So as long as you find **who created this texture and whether they changed the wrap mode**, you can
work back to the original build's sampling state:

| creation/binding site | wrap | filter |
| --- | --- | --- |
| `Utils/Utils/TextureWrapper.cs:114` | `isClamped ? Clamp : Repeat` (config option, default `false` → **Repeat**) | from the texture import settings (Bilinear) |
| `Utils/Utils/CubemapWrapper.cs:59-60,90` | **Clamp** (six faces, each its own Texture2D) | Bilinear |
| `Atmosphere/Atmosphere/CloudsRaymarchedVolume.cs:1429-1443` `CreateVolumeRT` | **Repeat** | Bilinear + mip |
| `Atmosphere/Atmosphere/CloudsRaymarchedVolume.cs:998-1006` `BakeCurvesTexture` | **Clamp** | Bilinear |
| `ShaderLoader/ShaderLoader/ShaderLoaderClass.cs:78-92` (the two STBN textures) | **Repeat** | **Point** |
| `Utils/Utils/RenderTextureUtils.cs:13,82` (screen-space RTs) | Repeat by default / the history manager passes Clamp | chosen by the call site (mostly Bilinear; the rays one is Point) |
| Unity built-in `_CameraDepthTexture` | Clamp | depth textures read with bilinear (GL's `texture2D` semantics) |

## 2. All 31 slots of `EVE/RaymarchCloud`

| slot | name | origin | original-build semantics | this repo's HLSL uses |
| --- | --- | --- | --- | --- |
| t0 | `_CameraDepthTexture` | Unity built-in camera depth | Clamp / Bilinear | `sampler_trilinear_clamp` ✔ |
| t1 | `_DetailTex` | `CloudsPQSMaterial.DetailTex` → `TextureWrapper.ApplyTexture` | Repeat (`isClamped` can switch it to Clamp) | `sampler_trilinear_clamp` ⚠ see §4 |
| t2 | `DensityCurve` | `BakeCurvesTexture` (explicit Clamp in C#) | Clamp / Bilinear | `sampler_trilinear_clamp` ✔ |
| t3 | `CurlNoiseTexture` | `CreateVolumeRT` (3D, Repeat + mip) | Repeat / Bilinear | `sampler_trilinear_repeat` ✔ |
| t4 | `_FlowMap` | `TextureWrapper` (equirectangular flow map, annular in u) | **Repeat** | ~~clamp~~ → `sampler_trilinear_repeat` ✔ (§3.2) |
| t5 | `BlueNoise` | **no C# in this build binds it at all** | unbound | `sampler_trilinear_clamp` (the sample result is always 0, no effect) |
| t6 | `BaseNoiseTexture` | `CreateVolumeRT` (3D, Repeat + mip) | Repeat / Bilinear | `sampler_trilinear_repeat` ✔ |
| t7 | `DetailNoiseTexture` | **no C# in this build binds it at all** | unbound | `sampler_trilinear_repeat` (same as above, no effect) |
| t8–t13 | `cubeCloudColorMap{±x,±y,±z}` | `CubemapWrapper` (six faces) | Clamp | `sampler_trilinear_clamp` ✔ |
| t14–t19 | `cubeCloudCoverage*` | same as above | Clamp | `sampler_trilinear_clamp` ✔ |
| t20–t25 | `cubeCloudType*` | same as above | Clamp | `sampler_trilinear_clamp` ✔ |
| t26 | `PreviousLayerRays` | `packedNewRaysRT` (an ARGBFloat RT with `FilterMode.Point`) | Point (see §4.4) | `sampler_trilinear_clamp` ⚠ left alone |
| t27 | `PreviousLayerMotionVectors` | **no C# in this build binds it at all** | unbound | `sampler_trilinear_clamp` |
| t28 | `PreviousLayerRaysSecondary` | **no C# in this build binds it at all** | unbound | `sampler_trilinear_clamp` |
| t29 | `StbnBlueNoise` | `ShaderLoaderClass.stbnScalar` (**Point + Repeat**) | **Point / Repeat** | ~~trilinear_clamp~~ → `sampler_point_repeat` ✔ (§3.1) |
| t30 | `combinedOpenGLDistanceBuffer` | `DepthToDistanceCommandBuffer.RenderTexture` | Clamp | `sampler_trilinear_clamp` ✔ |
| t31 | `ShadowCasterCloudCoverage` | `CloudsRaymarchedVolume.SetShadowCasterMaterialParams` (the 2D `AlphaMap` config) | Clamp / Bilinear | `sampler_trilinear_clamp` ✔ (`docs/SHADOW-CASTER.md`) |
| t32–t37 | `cubeShadowCasterCloudCoveragexn/xp/yn/yp/zn/zp` | same as above, the `AlphaCubeMap` config (one texture per face) | Clamp / Bilinear | `sampler_trilinear_clamp` ✔ |

## 3. Two defects already fixed

### 3.1 `StbnBlueNoise`: bilinear + Clamp → Point + Repeat

`ShaderLoaderClass.cs:78-92` explicitly builds `stbnScalar` as `FilterMode.Point` +
`TextureWrapMode.Repeat`. The design premise of STBN is **integer lattice sampling** (`noiseInput.xz`
is an integer coordinate lattice in `[0, stbnDimensions)`); bilinear smears it into the interpolation
of two neighbouring cells, which breaks the "one sample per pixel, cycled over time" protocol, while
Clamp stops the last row/column of tiles from wrapping, leaving a band in the bottom-right corner of
the screen that never changes over time. Changed to `sampler_point_repeat`.

### 3.2 `_FlowMap`: Clamp → Repeat

The flow map is an equirectangular projection (u = azimuth/2π + 0.5, v = polar angle/π, see
`shaders/hlsl/RaymarchCloud.hlsl:1011-1049`), with u joining up again at ±180°. The original build's
texture is created by `TextureWrapper` and defaults to `Repeat` (Clamp only if the config sets
`isClamped`). Sampling with Clamp replicates the last texel on the ±180° meridian indefinitely, which
is exactly the "±180° seam" T1 is meant to look at. All three sampling sites (main path / light path
/ sun direction) were changed to `sampler_trilinear_repeat` in lockstep.

## 4. Still open, but judged low risk

1. **`_DetailTex`'s wrap is decided by config** (`isClamped`). HLSL inline samplers are compile-time
   constants and cannot follow config. Cloud detail texture UVs basically stay inside [0,1] and the
   detail is low-frequency, so a boundary difference only affects the outermost half pixel of the
   texture; Clamp is used for now, and if a hard line shows up at the detail texture border on real
   hardware, switching to `Repeat` is enough.
2. **`_CameraDepthTexture`'s filter**: bilinear, following GL's `texture2D` semantics. If depth were
   point-sampled, reprojected rays would be slightly harder (a change in noise), a magnitude only
   visible in A/B.
3. **`BlueNoise` / `DetailNoiseTexture` are bound by no C# in this build** — the original build may
   have set them from another assembly (or from Scatterer), or they may simply be leftover slots. The
   sample result is always 0, so whichever wrap you pick has no effect on the image.
4. **`PreviousLayerRays` (t26) is a `FilterMode.Point` RT** (the
   `packedNewRaysRT` at `DeferredRaymarchedVolumetricCloudsRenderer.cs:494`), while the shader uses a
   bilinear sampler. On GL the original build's sampling state came from the texture object itself
   (= Point); on D3D it is decided by the inline sampler (= bilinear). Both are defensible, but
   changing the filter directly changes the aliasing shape of reprojection, so it is an item that
   must be A/B'd on real hardware; this round leaves it untouched and only records it. t27/t28 have
   no C# binding at all, so sampling is always 0 and wrap is irrelevant.

## 5. How to re-check

```bash
# per-shader uniform/keyword name table from the original build's bundle (confirm the tN names and the keyword set)
python tools/shader_reflection.py GameData/EnvironmentalVisualEnhancements/eveshaders.bundle --shader EVE/RaymarchCloud

# C# side: who created this texture, and what the wrap is
grep -rn "wrapMode" src/Atmosphere src/Utils src/ShaderLoader
```

The loop after changing a sampler is still `tools/rebuild.sh` (flatten → hlsl_check → Unity recompile →
`grep -c "Shader error" == 0` → package).
