# In-Game Acceptance Checklist (T1)

> This machine has no KSP install (`D:\Kerbal Space Program` holds nothing but Steam's depotcache), so
> this item **can only be carried out by someone who has the game**. The goal of this checklist is to
> turn "install it and take a look" into "work down the table and tick the boxes, so that on failure
> you know exactly which section to read". Verdicts go back into §7 and are then recorded in the acceptance log.
>
> Every item here targets: **KSP 1.12.5 + D3D11 (Windows) + EVE volumetric-cloud build + Scatterer**.
> Switching to OpenGL or to another KSP version is a new acceptance surface — do not mix it in.

---

## 1. Deployment (5 minutes)

1. Back up the existing `GameData/EnvironmentalVisualEnhancements/` and `GameData/Scatterer/` directories.
2. Extract `GameData/` from `dist/VolClouds-tweak.zip` into the KSP root directory, overwriting files of the same name.
3. Confirm that these two files exist and carry a fresh timestamp:
   - `GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle` (should be ≈ 33 KB)
   - `GameData/EnvironmentalVisualEnhancements/Plugins/Atmosphere.dll`
4. **Do not** delete the original build's `eveshaders.bundle` — the override bundle stacks on top of it, and the original build has to stay there as the fallback.
5. Start the game and enter the flight scene of an **atmospheric body** (Kerbin or Laythe). No clouds on the KSC screen or in the tracking station is normal.

### Rollback (do this if any step goes wrong)

| What to roll back | How | What to expect |
| --- | --- | --- |
| Just the shaders | Delete `eveshaders_tweak.bundle` | The original build's shaders are used, the DLL-side optimizations stay, clouds look exactly as before |
| The quality knobs | Delete `GameData/EnvironmentalVisualEnhancements/EVE_RAYMARCHED_CLOUDS_QUALITY.cfg` (or delete the relevant lines) | Back to the default values |
| Everything | Restore the two directories backed up in §1 | Byte-for-byte identical to before the install |

---

## 2. The three log lines to confirm first

Search `KSP.log` (`<KSP>/KSP.log`, or `%LOCALAPPDATA%Low\Squad\Kerbal Space Program\Player.log`) for `[EVE]`:

| Log line | Meaning | What it means if it is missing |
| --- | --- | --- |
| `[EVE] Shader EVE/RaymarchCloud overridden` | The override bundle took effect | The bundle was never read → see §4.1 |
| `[EVE] Shader EVE/ReconstructRaymarchedClouds overridden` | Same thing, second shader | Same as above |
| `[EVE] raymarched pass: …` (one line every 5 s) | The cloud pipeline is running every frame | The cloud pipeline never started → see §4.1 |

The two lines below are **expected and are not errors** (`docs/LIGHT-VOLUME.md` explains them):

```
[EVE] LightVolume: EVE/LightVolumeShadow is not in the shader bundle, cloud shadows stay on the 2D path
[EVE] LightVolume: compute shader ReprojectLightVolume missing, using the raster fallback   ← only when compute is missing
```

The first line **always appears with the original build's bundle** (that shader was never in the stock
bundle, see `docs/LIGHT-VOLUME.md` §4); it is an informational log, not a fault.

How to read each field of the `[EVE] raymarched pass:` line, and exactly what `cpuMs`/`gpuMs`/`culled`/`directSlices`
mean, is all in **`docs/DIAGNOSTICS.md`**.

---

## 3. The six acceptance items

Each item states up front how to set up the camera / the pass criteria / where to look first on failure.
**A criterion is either "no worse than the original build" or "the numbers in the log make sense"** —
never "it feels about right".

### 3.1 Do the clouds appear?

- **Setup**: 80 km circular orbit around Kerbin, day side, look up at the zenith, default FOV.
- **Pass**: there are volumetric clouds in the sky, they read as volume (not a flat texture pasted on the sky), and the clouds show light/dark gradation.
- **Also confirm**: `volumes=` in `[EVE] raymarched pass:` is at least 1; `reprojection=` is the factor
  for your quality tier (default `3x1`).
- **Look here first on failure**: the four paths in `docs/DIAGNOSTICS.md` §4.1 (camera identification → quality tier → layer loading → two bodies).
  If the log does not contain even a `[EVE]` line → the bundle never made it into the package / was never read (same command as in `docs/SAMPLERS.md` §5).

### 3.2 Is it upside down?

- **Setup**: same position, find an **asymmetric** cloud (flat base, fluffy top).
- **Pass**: cloud tops are up and cloud bases are down; ground features are not mirrored.
- **How failure looks**: the whole picture is flipped vertically, or the clouds sit below the horizon.
- **Fix**: the D3D y-flip note — `_ProjectionParams.x` is normally `1` on D3D, so if it really is
  flipped, remove the `* _ProjectionParams.x` factor from both vertex shaders (`shaders/hlsl/RaymarchCloud.hlsl:108-128`,
  `shaders/hlsl/ReconstructRaymarchedClouds.hlsl:178-196`) and re-run `bash tools/rebuild.sh`.

### 3.3 Sunrise/sunset lighting, and cloud-on-cloud shadows

- **Setup**: find a sunrise or sunset position (sun elevation 0–10°) where the clouds are layered in depth toward the sun.
- **Pass**: clouds clearly have a lit side and a shadowed side, with warm rims; you can see cloud clumps casting onto
  each other (dark bands).
- **Where this criterion comes from**: this item originally started as a T3 doubt ("light volume ON/OFF compiles
  identically"). The conclusion after investigating is that **the two overridden shaders do not sample the light
  volume at all**; the sense of depth comes from the `lightMarchSteps` march inside the shell plus the 2D
  `EVE/ScreenSpaceCloudShadow` (`docs/LIGHT-VOLUME.md` §1–§3). So:
  - if the lighting is **the same as the original build** → pass (T3's conclusion is confirmed);
  - if the lighting is **clearly flatter than the original build** and cloud-on-cloud shadows **disappear** → fail;
    that is a T3 regression. Roll the bundle back and retest once to confirm whether this build causes it, then
    attach the comparison shots and `KSP.log` to the issue.
- **Do not** turn on the `LIGHT_VOLUME_*` keyword for this item: that is a no-op switch (`docs/LIGHT-VOLUME.md` §2).

### 3.4 The ±180° longitude seam, and the `_FlowMap` tile seam

- **Setup**: low equatorial orbit (80 km), **keep looking straight ahead** along the orbit, so that the same cloud
  field travels from one side of the view to the other and crosses the centre of the view near the horizon;
  a full lap is even better.
- **Pass**: the cloud field is continuous at every longitude, with no dead-straight "knife cut" line running
  through the cloud layer; cloud motion shows no sudden misalignment of the repeating tile pattern at the seam.
- **What this item fixed**: T7 — `_FlowMap` and `StbnBlueNoise` used to be sampled with clamp samplers, but they
  are actually created as Repeat (`docs/SAMPLERS.md` §2). After the fix the seam should be **gone**; if a
  **new** seam appears, a third sampler is still set up wrong (checklist in `docs/SAMPLERS.md` §4).
- **Note**: `PreviousLayerRays` uses `packedNewRaysRT` with `FilterMode.Point`, and this is **deliberately left
  alone** (changing it would change reprojection aliasing and needs its own A/B); it is not a defect.

### 3.5 Two bodies in one frame (Jool + Laythe)

- **Setup**: from high above Jool or from Laythe orbit, frame Jool and Laythe together.
- **Current expected behaviour (this is a **degradation**, not a pass)**: the camera keeps only the clouds of the
  body **closest** to it; the other body's clouds are **not drawn at all for that frame**; no garbage, no
  misalignment, no flicker. In `[EVE] raymarched pass:` the second number of `culled=` (layers dropped by the
  single-body rule) should be > 0.
- **Pass criterion**: **no misalignment and no flicker**, and the `culled` counters in the diagnostic line agree
  with what you observe.
- **Fail**: if the second body's clouds "hang at the wrong height in the sky" or rotate along with the first
  body → `singleBodyPerCamera` has stopped working (`docs/MULTI-BODY.md` §1, blocker A); save `KSP.log`.
- **Do not** set `singleBodyPerCamera` to `false` just "to try both bodies": that walks straight into blocker A in
  `docs/MULTI-BODY.md` §1 and is worse than what you have now (both the code comment and the document say so).

### 3.6 Frame rate (you want both the minimum and the average)

- **Setup**: three fixed segments, 60 s each — do not use "instantaneous FPS":
  1. 80 km orbit, level view, clouds covering about 1/3 of the screen;
  2. the same spot, looking up at the zenith, clouds filling the screen;
  3. a sunset position (the heaviest lighting and shadow load).
- **Record**: press `Alt+F12` to open KSP's performance window, or use external RTSS/Afterburner; record the
  **average** and the **1% low** (not "the worst single frame").
- **Comparison baseline**: same position, same save, same quality tier, once with and once without
  `eveshaders_tweak.bundle` (the DLL-side optimizations cannot be isolated with that switch alone, so this item
  is mainly about **whether anything got worse**).
- **Pass**: the average frame rate in all three segments is not below the original build, and the 1% low is not
  noticeably worse; the zenith segment showing the widest gap is normal (full-screen clouds).
- **Together with the diagnostic line**: `cpuMs=` is this machine's self-timed `OnPreRender` cost (GPU excluded),
  while `gpuMs=` is usually `n/a` on KSP (the player build does not enable *Enable Frame Timing Stats*); the
  reason and the alternative measurement methods are in `docs/DIAGNOSTICS.md` §3.

---

## 4. Where to look first when something goes wrong

| Symptom | Look here first |
| --- | --- |
| No clouds at all, and no `[EVE]` in the log either | Install is wrong / `eveshaders.bundle` was deleted by mistake → `docs/DIAGNOSTICS.md` §4.1 |
| The `[EVE] Shader … overridden` lines are there, but there are no clouds | The last three paths in `docs/DIAGNOSTICS.md` §4.1 (quality tier / layer loading / camera identification) |
| Clouds are upside down | The §3.2 fix (`_ProjectionParams.x`) |
| Cloud lighting is flatter than the original build, cloud shadows are gone | §3.3 / `docs/LIGHT-VOLUME.md` |
| The cloud field has a seam | The open-suspects list in `docs/SAMPLERS.md` §4 |
| Two bodies misaligned / flickering | `docs/MULTI-BODY.md` §1 |
| Frame rate dropped | `cpuMs`/`culled`/`directSlices` in `[EVE] raymarched pass:` first, then `docs/DIAGNOSTICS.md` §4.4 |

---

## 5. Knobs added this round — check them in game while you are there

These defaults are all designed so that "change nothing = 1.0.0"; what you are verifying is that **the switch
really works and its default is harmless**. Where to configure them and the full description are in `docs/TUNING.md`.

| Item | How to try it | What to expect |
| --- | --- | --- |
| `edgeWisp` (T2, default 0) | add `edgeWisp = 0.5` to `EVE_RAYMARCHED_CLOUDS_QUALITY.cfg` | Wispy strands appear on cloud edges; coverage, colour and shadow direction are unchanged (`docs/TUNING.md` §4) |
| `depthUpsampleThreshold` (T4, default 0.1) | try `0.02` and `0.5` | Smaller: the cloud/terrain boundary gets sharper but aliases; larger: the boundary gets blurrier (`docs/TUNING.md` §1) |
| `reflectionProbeStepSizeMultiplier` / `reflectionProbeGodraysStepCountDivisor` (T8, default 5/5) | look at cloud reflections on water or metal surfaces, set them to `2` and `10` | 2 = finer, more expensive reflections; 10 = coarser, faster; the main view is unaffected (`docs/TUNING.md` §3) |
| `maxSunSlewBeforeFastRefresh` (T9, default 1.0 degree) | watch cloud lighting under time warp | Under time warp the cloud lighting **keeps up with the sun quickly**, and after you leave warp there is no lingering re-bake (`docs/TUNING.md` §2) |

---

## 6. Minimum requirements for calling it a pass

- §3.1, §3.2 and §3.4 **must pass** (clouds must appear, the orientation must be right, there must be no seam);
- §3.3, §3.5 and §3.6 **must be "no worse than the original build"** (better is optional, worse is not);
- apart from the two "expected information" lines listed above, there **should be no new `[EVE]` errors** in the log;
- if any item fails, leave `KSP.log` + screenshots + a description of the camera position in the table in §7, and
  **do not** touch the code without a log.

## 7. Verdict table to fill in

| # | Item | Result (pass/fail/not tested) | Notes / screenshot path |
| --- | --- | --- | --- |
| 3.1 | Do the clouds appear? |  |  |
| 3.2 | Is it upside down? |  |  |
| 3.3 | Lighting and cloud-on-cloud shadows |  |  |
| 3.4 | ±180° and `_FlowMap` seam |  |  |
| 3.5 | Two bodies in one frame |  |  |
| 3.6 | Frame rate (average / 1% low) |  |  |
| 5 | The four knobs are harmless at their defaults |  |  |

When the table is filled in, copy the verdicts line by line into the acceptance log (replace "highest
priority, because none of the conclusions have been verified yet" with the actual result), and archive this
table together with `KSP.log`.
