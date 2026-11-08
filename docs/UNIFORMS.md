# Uniform audit — every name the C# writes, against what the shaders actually declare

`material.SetFloat("typo", x)` is a **silent no-op** in Unity: no warning, no exception, the
uniform simply keeps whatever the shader initialised it to. Every visual bug in this project that
survived the offline build loop so far was of that shape — the light volume baked textures that no
shader read (`docs/LIGHT-VOLUME.md`), `EVEEdgeWisp` would have done nothing if the name disagreed by
one letter, and the shader loader built materials from shaders the bundle does not contain
(`docs/DIAGNOSTICS.md` §4.5). `tools/audit_uniforms.py` turns that class of bug into a table.

## 1. How to run it

```bash
# the two shaders we override, against the C# that feeds them
python tools/audit_uniforms.py BuildOut/GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle \
    --include CloudsRaymarchedVolume.cs,DeferredRaymarchedVolumetricCloudsRenderer.cs --quiet-ok

# whole EVE side against the original bundle (Scatterer ships its own shaders, so exclude it)
python tools/audit_uniforms.py GameData/EnvironmentalVisualEnhancements/eveshaders.bundle --exclude Scatterer/ --quiet-ok

# where is one uniform used, and does anything declare it?
python tools/audit_uniforms.py GameData/EnvironmentalVisualEnhancements/eveshaders.bundle --name EVEEdgeWisp

# a full table on disk
python tools/audit_uniforms.py BuildOut/GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle \
    --include CloudsRaymarchedVolume.cs --md docs/UNIFORMS-table.md
```

It reads three sources of truth and therefore reports **three** categories, which is the point:

| category | meaning | action |
| --- | --- | --- |
| declared by the compiled variant | the name is in the bundle's per-pass name table | nothing, it works |
| in shader source, stripped from the variant | the source declares it but this compiled keyword set does not reference it | harmless for this variant; the write is a no-op *here* |
| dead | no shader in the bundle **and** no shader source mentions it | triage: either a port gap (see §3) or a write aimed at a shader outside this bundle |

Distinguishing the last two matters: D3D strips unused uniforms, so "absent from the bundle" alone
does **not** mean the write is broken. Only the third category is a real finding.

## 2. Numbers for the two shaders this package overrides

`eveshaders_tweak.bundle` (33,196 B, `EVE/RaymarchCloud` + `EVE/ReconstructRaymarchedClouds`):

* ~130 uniform/keyword names declared in the two compiled variants;
* 57 names written by `CloudsRaymarchedVolume.cs` + `DeferredRaymarchedVolumetricCloudsRenderer.cs`;
* 16 of those are declared in the shader source but stripped from the variant
  (`CloudCoverage`, `_DetailScale`, `_flowSpeed`, `invLayerHeight`, `invNewRaysRenderResolution`,
  `invPaddedReconstructedTextureResolution`, `invReconstructedTextureResolution`, `layerHeight`,
  `lightMarchAttenuationMultiplier`, `minMaxNoiseTilings`, `newRaysRenderResolution`, …) — expected,
  no action;
* 12 are **dead** (listed below), down from 15: `shadowCasterDensity`,
  `shadowCasterSphereRadius` and `ShadowCasterCloudCoverage` became live in 1.1.2 when
  cloud-on-cloud shadows were ported (`docs/SHADOW-CASTER.md`).

The exact counts move with every shader change; `tools/rebuild.sh` prints them after the bundle
build, so trust that line over this table.

Whole EVE side against the original bundle: 436 names declared across 36 shaders/objects, 340 names
written from C# at 448 sites, 36 stripped, the rest dead — most of the dead set targets stock KSP or
Scatterer shaders and is out of scope, which is why the useful view is always scoped per shader.

## 3. The dead names, and what each one means

Nothing here is deleted: the same C# runs against the **stock** shaders when this override bundle is
not installed, and several of these names are perfectly valid there. The point of the list is that a
reader can now tell a deliberate port gap from a typo.

### 3.1 Cloud-on-cloud shadows: partially ported in 1.1.2

The stock `EVE/RaymarchCloud` declares a whole shadow-caster layer feature. 1.1.2 ported the
*bookkeeping* end of it (the uniforms and the coverage bindings now exist in the shader) and
approximates the effect with a caster-coverage lookup instead of the stock second density march:

| name | written at | state now |
| --- | --- | --- |
| `shadowCasterDensity` | `CloudsRaymarchedVolume.cs` `SetShaderParams` | **live** |
| `shadowCasterSphereRadius` | `SetShaderParams` + `SetShadowCasterMaterialParams` | **live** |
| `ShadowCasterCloudCoverage`, `cubeShadowCasterCloudCoverage*` | `SetShadowCasterMaterialParams` (slot 3) | **live** |
| `shadowCasterCloudRotation`, `shadowCasterTimeFadeDensity`, `shadowCasterTimeFadeCoverage` | `updateShadowCasterMaterialProperties` | **live** (the two time fades are declared, only coverage is consumed) |
| `_ShadowDetailRotation`, `_ShadowDetailTex` | `updateShadowCasterMaterialProperties` | still dead: the approximation does not need the caster's detail texture |
| `EVEShadowCasterStrength`, `shadowCasterCoverageIsCube` | new, written by `SetShaderParams` | **live** (the tuning knob and the 2D/cube selector) |

Still missing versus stock: the density march through the caster layer, so small isolated caster
clouds under-shadow (a coverage-map lookup only sees the silhouette). Details, cost and the
verification steps are in `docs/SHADOW-CASTER.md`; the knob is `docs/TUNING.md` §5.

### 3.2 Lightning does not light neighbouring layers

`lightningTransformsArray`, `maxConcurrentLightning`, `PreviousLayerLightningOcclusion` are written
(and declared in the stock variant) but absent from the port, so a flash lights only its own layer.

### 3.3 Colour map / painter type map

`CloudColorMap`, `cubeCloudColorMap`, `cubeCloudCoverage`, `cubeCloudType`, `CloudType` —
stock declares them, the port declares some and strips them, `CloudColorMap`/`cubeCloudColorMap` are
absent entirely. The painter's per-type colour map therefore does not affect the raymarched pass.

### 3.4 Cosmetic or recomputed-in-shader

| name | why it is dead here |
| --- | --- |
| `skylightTintMultiplier` | the port only declares `skylightMultiplier` and applies no tint; the C# value (`skylightTintMultiplier`) is silently ignored |
| `stepSizeLight` | the shader derives the light-march step from `lightMarchDistance / lightMarchSteps`; the uploaded value is unused |
| `directPhaseFunctionProperties`, `multiplePhaseFunctionProperties`, `multipleScatteringBrightnessArray` | the original build's variant has no phase-property uniforms at all; phase weights are baked into the compiled code from that variant |
| `noiseErosionDepth` | erosion-by-depth was not in the original build's variant |
| `screenshotModeIterations` | the port reads the iteration count from `frameNumber`/quality uniforms instead |
| `scattererEnabled` | the port has no Scatterer branch in the raymarch pass |
| `CloudSDF`, `cubeCloudSDF`, `AccumulatedVerticalCoverageTexture` | SDF / accumulated-coverage paths were not in the original build's variant (the painter uses the cubemap coverage uniforms that *are* declared) |
| `StbnUnitVec3` | no shader declares it anywhere; the loader now skips the missing file (`docs/DIAGNOSTICS.md` §4.5) |

## 4. How to read a new finding

1. If the name is in the `declared` table → fine.
2. If it is in the shader source → the variant stripped it; fine for this keyword set.
3. If it is dead → ask *which shader was it meant for*. If the answer is "the one we override", it is
   either a port gap (document it, §3) or a typo (fix it). If the answer is "a stock or Scatterer
   shader", leave it — this bundle cannot see it.

Run the audit after any shader rename or any new `SetFloat`/`SetVector`/`SetTexture` in a shader-facing
code path. It exits 0 either way: it reports, it does not judge.
