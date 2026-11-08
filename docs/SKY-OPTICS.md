# Sky optics: 22° ice halo and rainbow (`EVE/SkyOptics`)

Two atmospheric-optics effects that the stock build has no version of at all: the 22° halo around
the sun and a rainbow near the antisolar point. They cannot live inside the cloud shader — a rainbow
is most visible where the sky is *clear*, and the cloud composite only covers its own pixels — so
they are a separate additive full-screen pass.

Files:

- `shaders/hlsl/SkyOptics.hlsl` — the shader.
- `EVE-Tweak/Assets/Shaders/EVE_SkyOptics.shader` — Unity wrapper (`Blend One One`).
- `DeferredRaymarchedVolumetricCloudsRenderer.UpdateSkyOpticsPass` — binds the uniforms and appends the
  blit to the frame's cloud command buffer (since 1.2.4; it used to be a separate
  `SkyOpticsRenderer` component).

## 1. Where it draws, and why there

Draw order in the sky, from the existing passes:

| pass | event | source |
| --- | --- | --- |
| Scatterer atmosphere | `BeforeForwardAlpha` | `src/Scatterer/Scatterer/ScatteringCommandBuffer.cs` |
| ground cloud shadow | `AfterForwardOpaque` | `DeferredRaymarchedVolumetricCloudsRenderer.UpdateGroundShadowPass` |
| **sky optics (this)** | **`AfterForwardOpaque`, same buffer, before the composite** | `DeferredRaymarchedVolumetricCloudsRenderer.UpdateSkyOpticsPass` |
| EVE cloud composite | `AfterForwardOpaque`, same buffer | `DeferredRaymarchedVolumetricCloudsRenderer` (`CloudRenderingCameraEvent`) |

1.2.3 and earlier drew it at `AfterForwardAlpha` from a separate component, which is *after* the
cloud composite — so the bow was painted over every deck in front of it. Since 1.2.4 the blit is
appended to the cloud buffer ahead of the composite, so the clouds are painted over the bow: a
rainbow lives behind a cloud deck, not on top of it. Both are still additive and still after
Scatterer's atmosphere, so neither is swallowed by atmospheric scattering.

The pass reads scene depth through `_SkyDepthTexture` (bound per frame by the renderer) and writes
nothing where depth says "something is in front of you", so terrain, vessels and parts occlude it
correctly. It deliberately does not touch `_CameraDepthTexture`: overwriting that mid-frame would
change what the composite and the ground-shadow mask read.

## 2. Ice halo (`_SkyHaloStrength`, preset `skyHaloStrength`, default 0.4)

A 22° ring made of three tinted rings at 21.7° (red inside), 22.1° (green) and 22.4° (blue outside),
plus a wide 4.5° glow at 22° to soften the edge. Angular distance is `acos(dot(viewDir, sunDir))`.

Gates:

- `_SkyHaloStrength` 0 → the effect is off and the whole pass is skipped.
- Sun elevation below −1° → fades out (no halo with the sun down).
- Sun elevation above 55° → fades out (the ring is below the horizon of the ice crystals in the
  configs these clouds target; also the most common "why is there a ring" complaint).

`_SkySunElevation` is computed in C# and passed in; the shader never recomputes the vertical.

## 3. Rainbow (`_SkyRainbowStrength`, preset `skyRainbowStrength`, default 0.55)

Everything is measured from the antisolar point (`-sunDir`):

| feature | angular radius | colour order |
| --- | --- | --- |
| primary bow | 42.4° red outside → 41.4° green → 40.4° blue inside | red outside |
| secondary bow | 50.4° → 51.4° → 52.4° | reversed (red inside), ×0.12 |
| Alexander's dark band | 46°, width 2.6° | absorbs 55% |

Gates: strength 0 → off; sun elevation above 42° → the bow is below the horizon and fades out; sun
below −2° → off. The bow is only visible when the antisolar point is in view, which is what makes it
a "turn around at sunset" effect rather than a sky-wide tint.

Band widths are Gaussian sigma: 1.2° for the primary bow (1.6° for the secondary), plus a 3.2° wide
glow at 41.4° inside the primary bow — the inside of a real bow is brighter than the surrounding
sky, and without that glow a ring reads as a decal.

The 42° geometry is real; the intensities are art-directed (a real bow is much brighter than a halo,
and both are far brighter than any HDR sky these clouds are tone-mapped against). Scale the two
strengths independently.

## 4. Cost and failure modes

- One full-screen pass, no texture fetch except the depth read, no loops. It only runs on the main
  flight camera (`CameraRole.MainNear`), never in reflection probes or the far scale camera.
- `skyHaloStrength = skyRainbowStrength = 0` removes the command buffer: zero cost.
- Missing shader (an old bundle) logs once and disables the pass:

```
[EVE] Sky optics: EVE/SkyOptics is not in the shader bundle, halo and rainbow disabled
```

## 5. Verification

Offline:

```bash
bash tools/rebuild.sh
python tools/shader_reflection.py BuildOut/GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle --names-only
# must list EVE/SkyOptics and EVE/RaymarchedCloudShadow next to the two ported shaders
```

In game:

1. Sunrise, sun 5–15° up, clear sky: a bright ring around the sun at ~22° (hold a 22° reference —
   the width of a fist at arm's length). Slider `Ice halo` 0 → 0.4.
2. Same time, turn 180°: the bow should appear opposite the sun, red on the outside, with a faint
   second bow further out and a darker gap between them. Slider `Rainbow` 0 → 0.55.
3. Fly a mountain range in front of the sun: the halo must be cut by the terrain, not drawn over it.
4. Midday (sun > 45°): both effects gone.
