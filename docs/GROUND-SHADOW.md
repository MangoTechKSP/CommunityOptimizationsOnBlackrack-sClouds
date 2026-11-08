# Cloud shadows on the ground (`EVE/RaymarchedCloudShadow`)

The stock build could darken the ground with a 2D screen-space shadow (`EVE/ScreenSpaceCloudShadow`),
but the volumetric layers had no equivalent: a 40 km raymarched deck cast no shadow on the terrain
below it. This pass adds that, and it is deliberately the cheap approximation, not a second marcher.

Files:

- `shaders/hlsl/RaymarchedCloudShadow.hlsl` — the shader (two passes, no ported code).
- `EVE-Tweak/Assets/Shaders/EVE_RaymarchedCloudShadow.shader` — the Unity wrapper.
- `src/Atmosphere/Atmosphere/DeferredRaymarchedVolumetricCloudsRenderer.cs`
  (`UpdateGroundShadowPass`, `SetShadowLayer`, `DetachGroundShadow`).

## 1. How it works

Per frame, for the main flight camera only:

1. Pick the **two lowest** cloud layers whose coverage map is a cubemap (a 2D `AlphaMap` layer cannot
   be sampled by this build — see `docs/UNIFORMS.md` §3 — so it also cannot cast this shadow).
2. Bind their coverage cubemaps, cloud rotation matrices, inner/mid radii and the sun direction.
3. Draw a quarter-resolution mask (`R8`): for each pixel, reconstruct the world position of the
   ground, march that position along the sun ray into each layer's shell, sample the layer coverage
   at the ray midpoint of that segment and add `coverage * extinction` to the optical depth. The mask
   is `exp(-opticalDepth)`, i.e. the fraction of sunlight that reaches the ground.
4. Multiply the frame by the mask, bilinearly upsampled, **before** the cloud composite pass runs.

The ordering is the reason the shadow looks right: the terrain is darkened first, then the clouds
are drawn on top of it at full brightness. A shadow applied after the composite would also darken
the clouds, which reads as a dirty lens rather than as a shadow.

Extinction per layer is `2.2` (`ShadowCoverageExtinction`), which puts a fully covered texel at
about 11% sun before the strength knob. `_ShadowStrength` (preset `cloudShadowStrength`, default
0.6) scales the mask towards 1 (no shadow) and also gates the pass: 0 removes the command buffer
entirely.

## 2. What it is not

- **Not a density march.** The real optical depth of the layer is approximated by its coverage map,
  so a small isolated cumulus with full coverage casts the same shadow as a solid overcast texel.
  Coverage is dilated by the upsampling (quarter res), which is why the shadow is soft. If you need
  a crisp shadow from a small cloud, that requires marching the noise volume from the ground — a
  second marcher, 10–20× the cost, not in this build.
- **Two layers only.** With three stacked decks the third casts nothing. Rare in practice and it
  keeps the shader to 12 texture slots.
- **Cubemap coverage only.** The stock volumetric configs in `StockVolumetricClouds` use a 2D
  `AlphaMap`; those layers are skipped rather than half-supported.
- **No cloud-on-cloud here.** The layers shadowing each other is `docs/SHADOW-CASTER.md`.

## 3. Cost

One quarter-resolution pass (`pixelWidth/4 × pixelHeight/4`, minimum 64²) plus a full-screen
multiply. Each mask pixel does at most `2 layers × 1 cube fetch × 2 faces` plus a depth read: no
loops over the volume. On a 1080p frame that is ~130k pixels, and the multiply is blended, not
sampled. Turn it off with `cloudShadowStrength = 0` if a machine is fill-rate-bound.

## 4. Verification

Offline:

```bash
bash tools/rebuild.sh                    # includes Unity, prints "shader errors: 0"
python - <<'PY'
# the two new shaders must be in the bundle the loader will read
import subprocess
print(subprocess.run(["python","tools/shader_reflection.py",
  "BuildOut/GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle","--names-only"],
  capture_output=True, text=True).stdout)
PY
```

In game:

1. Sun 20–45° up, camera at 2–5 km above a lit surface, a thick deck above: the ground should have
   moving dark patches that line up with the clouds (the coverage map is the same one the clouds use).
2. Panel slider `Ground shadow` 0 → 0.6: the patches appear/disappear, nothing else changes.
3. Set it to 0 and check the diagnostic line: the pass must be gone (it is not counted there, but the
   frame time should drop by the mask cost; `cpuMs` should not move).
4. Night side or sun below the horizon: no shadow (`_ShadowSunUp` is 0).

Expected log on an install whose bundle predates 1.2.0:

```
[EVE] Ground shadow: EVE/RaymarchedCloudShadow is not in the shader bundle, clouds do not darken the ground
```

That is a version mismatch, not a bug: deploy the current zip (`docs/ACCEPTANCE.md` §1).
