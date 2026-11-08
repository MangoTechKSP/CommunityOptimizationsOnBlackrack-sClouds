# Diagnostic Line Reference (DIAGNOSTICS)

The most typical failure mode on the ray-marched cloud path is **silent failure**: the camera name is not
recognised, the quality tier has clouds switched off, the layers never load, the body gets culled away…
and the sky simply has no clouds, with not a single word in the log. That is why this path periodically writes
diagnostic lines to `KSP.log`. This document is the field table and the troubleshooting manual for those lines.

Both switches live in C# and default to on:

| Switch | Location | Which line it controls |
| --- | --- | --- |
| `DeferredRaymarchedVolumetricCloudsRenderer.diagnosticsEnabled` | `src/Atmosphere/Atmosphere/DeferredRaymarchedVolumetricCloudsRenderer.cs` | `[EVE] raymarched pass: ...` (one line per camera every 5 s) |
| `CloudsManager.DiagnosticsEnabled` | `src/Atmosphere/Atmosphere/CloudsManager.cs` | `[EVE] clouds applied: ...` (one line each time a config is applied) |

Changing either default requires a C# rebuild (`dotnet build VolClouds.sln -c Release`); no shader rebuild is needed.

## 1. `[EVE] raymarched pass: ...`

```
[EVE] raymarched pass: camera=Camera 00 body=Kerbin volumes=3 bounds=6 intervals=2 lightVolume=True
      reflectionProbe=False resolution=1920x1080 reprojection=2x2 culled=1/0 directSlices=4/32
      cpuMs=0.42@300f gpuMs=n/a@0s
```

It is really a single line (wrapped here for readability). Each camera gets its own line: the main flight camera,
`Camera 01` (far scene), `TRReflectionCamera` (Scatterer's reflection) and `Reflection Probes Camera` (Unity
reflection probes) all emit one, so confirm that `camera=` is the one you care about before interpreting anything.

| Field | Meaning | Expected value |
| --- | --- | --- |
| `camera` | Name of the camera GameObject | Whichever camera you are looking through |
| `body` | Body that owns `volumesAdded[0]` | The body under your feet; `none` = this renderer got no layers at all this frame |
| `volumes` | Number of ray-marched layers submitted this frame | ≥ 1. **0 is the most common failure** (see §4.1) |
| `bounds` | Enter/exit events of the layer bounds (2 per layer) | Normally `volumes * 2` |
| `intervals` | Number of radius overlap bands | ≥ 1; > 1 when several layers overlap |
| `lightVolume` | Whether this frame uses the light volume (any layer with `useLightVolume` true) | `True` in most configurations |
| `reflectionProbe` | Whether this renderer is serving a reflection camera | `False` for the main camera, `True` for probes |
| `resolution` | Internal raymarch resolution (not the screen resolution) | Determined by the quality tier and `screenFraction` |
| `reprojection` | Sub-pixel grid used for temporal reprojection | `1x1`/`2x1`/`2x2`/`3x2`/`4x3`/`4x4`/`8x4` |
| `culled` | Layers culled by the shell test / layers dropped by the "single body" rule, over this interval | See §4.2 |
| `directSlices` | Direct slices actually baked into the light volume this frame / total slices in the volume | See §4.3 |
| `cpuMs` | Average time this camera spends in `OnPreRender`; `@Nf` is the number of frames in the average | Single-digit milliseconds per frame; tens of milliseconds means the CPU side is overloaded |
| `gpuMs` | Average GPU frame time; `@Ns` is the number of samples obtained | Usually `n/a@0s`, see §3 |

A few details on how some fields are counted:

- The numerator of `culled` is accumulated **across several cameras** (`EnableForThisFrame` is called per layer
  and the stack is cleared per camera), so `culled=1/0` means "over these 5 s, submission was skipped once because
  the shell was outside the view, and zero times because of the body rule". It is a cumulative counter, not an
  instantaneous value; it resets after the line is written.
- `directSlices` is an instantaneous **this-frame** value (not cumulative), while `culled`/`cpuMs`/`gpuMs` are
  interval averages or interval totals.
- `cpuMs` measures only `OnPreRender` (the part that submits command buffers) and excludes the `OnPostRender`
  wrap-up and the layer management done in `Update`; it is a relative metric, for comparing "is the CPU more
  expensive before or after flipping this switch" — the absolute number means nothing.
- A reflection probe's `resolution` is usually smaller than the main camera's, and its step size is coarser because
  of `reflectionProbeStepSizeMultiplier` (default 5) — that is by design, not a bug. The relevant knobs are in
  `docs/TUNING.md` §3.

## 2. `[EVE] clouds applied: ...`

```
[EVE] clouds applied: 3 bodies, 12 layers total
[EVE]   Kerbin: 5 layers (4 raymarched, 1 of them with volume, 1 2D-only)
```

One round is printed every time a config is applied or reloaded, and it answers "what did the config layer
actually recognise": the number of bodies, the total number of layers, and how many raymarched / with-volume /
2D-only layers each body has.

**`layerRaymarchedVolumeV5` takes effect per body**: as soon as one config node on a body carries that node,
every other node on the same body that does **not** carry it is dropped entirely. So when you see "some body has
only 1 layer left", read the summary line first — that is usually not a load failure, but this rule having eaten
the 2D layers. Details in `docs/ARCHITECTURE.md` §1.

## 3. Why `gpuMs` is often `n/a`

GPU time comes from `UnityEngine.FrameTimingManager`, which only produces data when **Player Settings → Enable
Frame Timing Stats** is enabled. KSP itself does not enable that option, so in this build the live value is
usually `gpuMs=n/a@0s`.

This is **deliberately not making up a number**: when `GetLatestTimings` returns 0 we print `n/a` instead of
pretending it was `0.00 ms`. If you really need GPU time:

1. Use external tools: the frame-time graph in MSI Afterburner / RTSS, NVIDIA Nsight, or a single-frame capture
   in RenderDoc (RenderDoc is the most accurate on the `EVE/RaymarchCloud` draw call — one capture shows the GPU
   time and sample count of every pass).
2. Or judge by different criteria instead of measuring time: `resolution`/`reprojection` directly reflect the load
   tier, `directSlices` reflects the refresh intensity of the light volume, and comparing `cpuMs` between the two
   settings also shows the CPU-side change.

If KSP is ever patched to enable Frame Timing Stats, this cell turns into a true value automatically, with no
code change.
**Cost**: this Unity (2019.4) has no `FrameTimingManager.IsFeatureEnabled()`, so when it cannot get samples it
steps aside on its own — it probes once per second, and after 60 consecutive failures it permanently disables the
whole sampling path (`gpuTimingUnavailable`), so it stops calling `CaptureFrameTimings`/`GetLatestTimings` per
frame per camera. While probing, `gpuMs` still prints `n/a`.

## 4. Troubleshooting manual

### 4.1 No clouds in the sky at all, `volumes=0`

Check in this order; these all fail **silently**:

1. **The camera is not recognised**. `CameraRoles.GetRole` checks the `CameraRoleMarker` component first, then the
   name table (`Camera 00`/`Camera 01`/`TRReflectionCamera`/`Reflection Probes Camera`/`DepthCamera`/`NearCamera`).
   A mod of your own that renames cameras (or renders the picture through a different camera) falls straight out.
   → Attach a `CameraRoleMarker` to the camera and set the role there; do not rename it. See `docs/ARCHITECTURE.md` §3.
2. **The quality tier switched the clouds off**: `raymarchedCloudsEnabled = false` in
   `EVE_RAYMARCHED_CLOUDS_QUALITY.cfg`, or `renderCloudsInReflectionProbes = false` while you are looking at a
   reflection. No diagnostic line at all means `OnPreRender` is never even reached (`renderingEnabled == false`) —
   distinguish this case from "there is a line but `volumes=0`".
3. **The layers never loaded**: the body is beyond the `2000 R` unload line, the config node was eaten by the
   rule in §2, or the body name does not match in `CloudsManager`. Check the `[EVE] clouds applied` summary line.
4. **Two bodies in view at once**: `singleBodyPerCamera` keeps only the body closer to the camera, and no layers
   from the other side are submitted for that whole frame → `culled=?/N` goes up. That is the current design
   (see the multi-body notes), not a fault.

### 4.2 `culled` is high but the picture is fine

That is normal. The semantics of `cullShellsOutsideView` are exactly "if the cloud shell lies entirely outside
the frustum, do not submit this full-screen quad", so the number keeps climbing while the player looks down at
the ground — where there should be no clouds anyway. It is only suspicious when `culled` is high **and** looking
up shows no clouds either; in that case check the frustum test in `IsCloudShellOutsideView` (the
`shellCullFovMarginDegrees = 3.0` margin).

Setting it to `false` gives you an A/B: with it off, every layer draws a full-screen quad and the shader decides
per pixel. The frame rate drops a notch, but you can immediately separate "the cull test is wrong" from "the
shader math is wrong".

### 4.3 `directSlices` and the light volume

The denominator of `directSlices` is the total slice count of the light volume
(`LightVolumeSettings.verticalResolution`); the numerator is the number of slices actually written into the
texture this frame. Behaviour (after the light-volume sweep fix):

- Steady state: `verticalResolution / directLightTimeSlicing` (default `32 / 8 = 4`), and that number goes up by
  1 on the "leftover slice" frames, so that one cycle covers exactly 32 slices and never stays a few slices short
  the way the old code did.
- The sun is slewing (time warp, pressing `,`/`.` in a lander, `TimeWarp` across a day boundary): once the
  accumulated yaw exceeds `maxSunSlewBeforeFastRefresh` (default 1°, see `docs/TUNING.md` §2) the rate is scaled
  up proportionally, up to `timewarpRateMultiplier` times, and at most a full 32 slices are swept in one frame.
- `directSlices=0/32`: the light volume is not being updated. Check `lightVolume=False` first (`useLightVolume`
  switched off in the layer config), then check whether this is a reflection probe (probes never take light
  samples).

### 4.4 `cpuMs` went up but the picture did not improve

Compare `volumes`/`intervals` first: if the layer count is unchanged while `cpuMs` rises, it is the **submission
side** that got more expensive (number of command buffers, number of `SetRenderTarget` calls), not the shader. If
you really want shader-side sample counts, capture one frame with RenderDoc, or just read the description of that
group of step knobs in `BUILD-NOTES.md`.

### 4.5 The four startup "missing file / missing shader" log lines

All of these are **degradation, not a crash**: when one appears a feature is missing, but the clouds themselves
keep rendering as usual:

| Log | Meaning | Consequence |
| --- | --- | --- |
| `[EVE] stbn.R8 is missing from GameData/...` | The install is missing the STBN blue-noise texture | A 1×1 constant is used instead, `StbnBlueNoise` dithering is dead → visible banding in reprojection/TAA |
| `[EVE] stbn.R8 is N bytes, expected 1048576` | Truncated file / incomplete extraction | Same as above |
| `[EVE] stbn_unitvec3.ARGB32 is missing ...` | Modern EVE installs no longer ship this file | Harmless: none of the 37 shaders declares `StbnUnitVec3` (0 hits in the 25 MB serialized bundle), so it is skipped |
| `[EVE] ScreenSpaceShadows: EVE/InvisibleShadowCaster is not in the shader bundle` | That shader is missing | That 100 km shadow-caster quad is disabled (otherwise it would smear across the camera with the default material); the per-camera shadow renderer still registers as usual |
| `[EVE] ScreenSpaceShadows: EVE/Blend... or EVE/DownscaleDepth is not in the shader bundle` | That shader is missing | The screen-space shadow pass for that camera is turned off; 2D cloud shadows / eclipse shadows are unaffected |
| `[EVE] WetSurfaces: EVE/WetSurfacesAccumulationMask is not in the shader bundle` | That shader is missing | That layer does not bake the rain mask; the wet-surface effect is skipped |

Historical lesson (before 1.0.0): `ShaderLoaderClass.LoadShaders()` read `stbn_unitvec3.ARGB32` with a bare
`File.ReadAllBytes`, so a missing file threw inside `Start()` → `loaded` stayed `false` forever →
`GlobalEVEManager` set up no manager at all → **no clouds in the sky at all**, while the log held nothing but a
`FileNotFoundException`. That path now uses `LoadRawNoise`, which only degrades and never throws.

## 5. Re-check commands

```bash
cd /e/MangoTech/VolClouds
dotnet build VolClouds.sln -c Release          # after changing diagnostic code
bash tools/rebuild.sh                          # after changing shaders (C# is rebuilt too)
```

The diagnostic lines themselves do not go into the bundle, so changing only them needs no shader rebuild; but
`tools/rebuild.sh` also verifies in passing that the Unity-side shader compile is not broken (`shader errors: 0`).
