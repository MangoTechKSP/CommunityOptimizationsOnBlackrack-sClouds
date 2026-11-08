# Scattering approximations: multiple scattering, ground bounce, light-march jitter

Three additions that change how a cloud is *lit*, all inside `EVE/RaymarchCloud`
(`shaders/hlsl/RaymarchCloud.hlsl`). None of them adds a texture fetch or a pass; they are
arithmetic on data the marcher already has. All three default to the values listed below and can be
set to exactly zero for the 1.0.0 look.

- `multipleScattering` (0..1, default **0.4**) — how much multiple scattering brightens the part of
  the cloud the sun has to travel deepest through. 0 = single scattering only.
- `groundBounce` (0..1, default **0.25**) — how much sunlight reflected off the ground lifts the
  cloud base. 0 = no bounce light.
- `lightMarchJitter` (0..2, default **1.0**) — decorrelates the sun-march sample positions between
  steps. 0 = the stock per-pixel dither only.

The same three appear in the in-game Volumetric Clouds panel (§Lighting), so they can be judged
without editing the preset.

## 1. What the ported shader actually did

`shaders/glsl/RaymarchCloud/...` (the original build's shader) already dithered:

| dither | stock use | line in `shaders/hlsl/RaymarchCloud.hlsl` |
| --- | --- | --- |
| `stbnSampleB` | first sun sample offset | ~1602 |
| `stbnSampleB` (other component) | density / step offset | ~2027 |
| `stbnSampleA` | first camera step offset | ~835 |

So the stock look is already dithered *once per ray*. What it does not do is decorrelate the
samples *along* the sun march: every step of every ray samples at the same phase offset, which is
why the sun-march banding shows up as concentric shells when the sun is low and the optical depth is
high. `EVELightMarchJitter` fixes exactly that one thing.

Single scattering was also the whole model: the ported transmittance fit is applied once, so a
cloud with `opticalDepth > ~4` goes to black in its interior even when it is 40 km across. Real
clouds stay grey because light scatters many times; the multi-scattering term is the cheap
approximation of that.

## 2. Multiple scattering (`EVEMultipleScattering`)

`eve_sun_transmittance_multi(opticalDepth)` starts from the stock fit

```
T(t) = 1 / (0.065 * t * t + 0.35 * t + 1)
```

(`eve_sun_transmittance` is that same expression, factored out unchanged) and adds two octaves at
half and quarter optical depth:

```
T_multi = 0.60 * T(t) + 0.28 * T(0.5 t) + 0.12 * T(0.25 t)
```

then blends with `saturate(EVEMultipleScattering)`:

```
T = lerp(T_single, T_multi, EVEMultipleScattering)
```

The weights sum to 1, so the result can never exceed the single-scattering transmittance. At 0.4
the deep interior of a thick cloud roughly doubles in brightness while thin edges move by a few
percent, which is the intended "keep the shadows, lift the black" behaviour.

Limits, stated so nobody asks for more: this is *not* a diffusion solve. There is no directional
coupling, no forward-scattering peak on the shadowed side, and no view-dependent silver lining. It
is one extra multiply-add per sun step, available on every tier.

## 3. Ground bounce (`EVEGroundBounce`, `EVEGroundBounceTint`)

```
bounce = EVEGroundBounce
       * saturate(1 - shellHeight)^2        // strongest at the cloud base
       * saturate(dot(sunDirection, -planetDirection))  // only when the ground below is lit
```

added to the ambient term as `cloudColor * bounce * EVEGroundBounceTint`. `EVEGroundBounceTint`
defaults to `(1.0, 0.93, 0.82)` — sunlit regolith / soil, slightly warm. Exposed as a uniform but
not as a preset knob: it is a physical constant of the body, and the stock configs have no place to
put a per-body colour yet.

Why it matters visually: before this, a sunset-lit cloud deck had a dark, neutral underside even
with the ground at full brightness. The term is gated on the shell height squared so it cannot
brighten the tops, and on `dot(sun, -planetDirection)` so it cannot lift the underside of a
night-side cloud.

## 4. Light-march jitter (`EVELightMarchJitter`)

```
scale = 1 + (hash(stepIndex, stbnSampleB.x) - 0.5) * 0.3 * saturate(EVELightMarchJitter)
lightMarchPos += sunDirection * (lightStepSize * scale)
```

Accumulation still uses `lightStepSize`, so the optical depth stays unbiased (the hash is uniform
in [-0.5, 0.5]); only the *sample position* moves. Step count is unchanged, so the cost is one hash
per sun step.

The existing temporal reprojection is what turns this into smooth shading: the per-pixel hash
changes the sample offset every frame, and the history buffer averages it. The practical range is
0.5–2; above 2 the marching can step past a whole thin cloud layer. If temporal stability matters
more than banding (screenshot mode, very low framerate), set it to 0 and the shader is bit-identical
to 1.1.2's sun march.

## 5. Vertical structure and sculpted shading (`EVEDetailErosionScale`,
`EVEBaseDarkness`, `EVEMacroBreakup`, `EVESculptStrength`)

### 5.1 Why a thick deck looks flat

A deck that is fully covered has three properties that, together, erase every cue the eye uses
to judge shape:

1. **The sun term saturates.** With the sun overhead and `lightMarchSteps` doing its thing,
   `sunDot * windAccum0` is close to its maximum across most of the visible layer, so there is
   no gradient to read a surface from.
2. **The ambient term is uniform.** `cloudColor * skylightMultiplier * windAccum2` depends on
   the same per-pixel quantities everywhere: same colour, same brightness.
3. **The silhouette is a gradient.** The marcher fades a layer out over several samples, so the
   edge has no line, and the layer has no "top" that catches light.

Photographs of overcast decks look sculpted for exactly the opposite reason: the deck has
*relief* (convective turrets, cells, cellular edges), and the sun rakes across that relief, so
the shading carries the shape even though the layer is complete. The fix therefore cannot be a
coverage knob - the deck is supposed to be complete - it has to put the relief back into the
lighting.

### 5.2 Base darkness: light penetration from the top

Light entering a thick layer is attenuated before it reaches the lower part of the layer. The
shader previously ignored this entirely. It is now a vertical ramp on the ambient term:

```
baseWeight  = saturate((midRadius - innerSphereRadius) / shellThickness)   // 0 bottom, 1 top
attenuation = lerp(1 - saturate(EVEBaseDarkness), 1, smoothstep(0, 1, baseWeight))
skyLightColor *= attenuation
```

`EVEBaseDarkness = 0.22` (shipped; 0.45 was too heavy and greyed the whole deck) darkens a thick deck's underside while leaving
a thin layer alone (its mean `baseWeight` is high). Neutral at 0.

### 5.3 Macro breakup: large-scale holes in a covered layer

One `BaseNoiseTexture` fetch at mip 3, positioned half-way along the pixel's ray through the
shell and scaled to `0.00035` (a few cells across a planet-sized layer):

```
coverageFade *= lerp(1, saturate(sample * 1.8), saturate(EVEMacroBreakup))
```

`EVEMacroBreakup = 0.3` (shipped) lets the coverage field fall below the visibility threshold
in roughly a third of the sheet, which is what turns a uniform ceiling into a broken deck with
visible sky between cells. It is applied *before* `typeProps.x`, so it scales the layer's own
coverage rather than fighting it; a layer whose coverage is below ~0.4 already has the right
amount of sky, so the breakup mostly disappears there. Neutral at 0.

### 5.4 Detail erosion bias

The two existing detail-noise fetches remove density from the sample. The bias was a constant
0.62; it is now scaled by `EVEDetailErosionScale` (1.0 = stock, 2-3 = crisper cauliflower tops,
i.e. the detail eats deeper into the coverage). Values above 1 deepen the erosion rather than
adding fetches, and above ~3 the layer starts to lose its base coverage.

### 5.5 Sculpted shading: density-gradient normals

The real fix for the "flat ceiling" read is to let the density field shade itself. Four
coarse-mip fetches of `BaseNoiseTexture` (0.0024 world scale, so the bumps are cloud-sized) around the resolved mid-position give the local
gradient of the density field; that gradient is used as a perturbed normal and the sun term is
rerun against it:

```
shellNormal   = -planetDirection                       // outward from the planet
sculptNormal  = normalize(shellNormal - gradient * 9 * EVESculptStrength)
sculptLight   = saturate(dot(sculptNormal, _SunDir))
skyColor      *= lerp(1, saturate(0.35 + sculptLight), EVESculptStrength)
skyLightColor *= lerp(1, saturate(0.55 + sculptLight * 0.9), EVESculptStrength * 0.6)
```

`EVESculptStrength = 0.7` (shipped). This is the change that makes a fully covered deck read as
a volume: the relief now comes from the density field itself, so it moves with the clouds, is
independent of the layer's coverage, and survives a low sun. Four fetches per covered pixel at
mip 2, only when `accumulatedDensity > 0`. Neutral at 0.

### 5.6 Edge wisps had to become softer

The 1.1.x wisp pass multiplied a band of the coverage just above the marcher's visibility
threshold. High frequency (8x/16x curl tiling) plus a multiplicative step at the band's upper
edge meant the fade was compressed into a couple of samples: physically a hard cut, and it read
as one. 1.2 instead

* displaces at 4x/8x with a larger amplitude, so the warped silhouette has the curvature of a
  veil instead of the width of a tuft;
* modulates the whole tail by one extra curl fetch centred on 1.0 (`coverageFade *=
  1 + 0.55 * wispAmount * curl`), which pushes samples above and below the marcher's own
  gradual falloff instead of ending it.

The result is a frayed, multi-sample edge rather than a threshold.

### 5.7 Silver lining (1.2.1)

The accumulators are density-weighted (`windAccum0` / `windAccum2` / `decodeE`), so as a layer thins
the pixel simply receives less colour and the deck ends in a dark halo. Photographs show the
opposite: a cloud fringe is the brightest part, because a thin optical path scatters forward instead
of being absorbed. The resolve therefore does

```
coverage  = saturate(1 - marchResult.w)          // how much cloud the ray actually hit
edgeGlow  = saturate(1 - coverage * 3) squared   // peaks while the ray is still mostly clear
finalColor *= 1 + edgeGlow * EVEEdgeGlow
```

Cloud cores get exactly 1.0, clear sky is left at zero (so the lift cannot bleed into a ring around
the cloud), and only the thin fringe is raised. `EVEEdgeGlow = 0.8` shipped; 0 restores 1.2.0.

### 5.8 Contour hardness (1.2.1)

The marcher accumulates a soft optical depth, so the cloud/sky transition is a long gradient and a
deck reads as haze at a distance. `EVEContourHardness` applies a transfer curve to the transmittance:

```
hard = pow(soft, p);  finalColor *= hard / soft;  marchResult.w = 1 - hard
```

The colour is rescaled by the same ratio, so closing the outline does not dim the interior. `p = 1`
is the ported curve; 2.6 (shipped since 1.2.2) gives a carved silhouette against the sky; 3 and up
is for stills only. Since 1.2.3 the power curve is applied to a *thresholded* coverage
(`banded = saturate((coverage - EVEContourThreshold) / EVEContourBand)`), because steepening a
gradient still draws the whole gradient: 0.35 of accumulated coverage is fringe, not cloud, and
dropping it is what shortens the transition from tens of pixels to two or three. The companion scale control is `EVEDetailFrequency` (shipped 1.8), which
multiplies the detail-noise tiling so the same two fetches carve smaller puffs.

## 6. Verification

Offline (no game):

```bash
bash tools/rebuild.sh --skip-unity        # dotnet build + flatten + offline D3DCompile of every entry
```

The check that matters is in the compiled variant, not the source:

```bash
python tools/shader_reflection.py BuildOut/GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle \
  --shader EVE/RaymarchCloud --search MultipleScattering
```

`EVEMultipleScattering`, `EVEGroundBounce`, `EVEGroundBounceTint` and `EVELightMarchJitter` must
appear. If they do not, the names in `CloudsRaymarchedVolume.ApplyShaderParams` and in
`ShaderProperties` have drifted apart.

In game (see `docs/ACCEPTANCE.md` for the camera setup):

1. Cloud interior, sun low: set `multipleScattering` 0 → 0.4 in the panel. The interior should go
   from near-black to grey; edges should barely move. If the whole cloud brightens, the term is
   feeding the lit side — report it.
2. Sunset over a bright surface (ice, sand, high-albedo rock): `groundBounce` 0 → 0.25 should lift
   the deck's underside and add a slight warm cast. At night it must do nothing (it is gated on the
   sun).
3. Sun 5–10° above the horizon, thick deck: `lightMarchJitter` 0 → 1 should remove concentric
   banding in the sun march. If it turns into visible noise instead, the reprojection is not
   averaging — check that `reprojection: 3x1` and that the frame time is stable.
