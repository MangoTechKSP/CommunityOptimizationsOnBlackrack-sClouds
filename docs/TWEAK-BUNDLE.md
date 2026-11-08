# Tweaking EVE shaders without repacking the 19-shader bundle

`ShaderLoaderClass` now loads an **optional override bundle** after the stock one:

```
GameData/EnvironmentalVisualEnhancements/eveshaders.bundle      <- stock, untouched, 19 shaders + computes
GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle <- optional, only what you edited
```

Same-named shaders / compute shaders in `eveshaders_tweak.bundle` replace the stock ones;
every name it does not contain keeps coming from the original bundle. Missing file = no-op.
Proof it worked, in `KSP.log`:

```
[EVE] Shader EVE/RaymarchCloud overridden
```

The indexer fix in the same file also removed a latent crash: `shaderDictionary.Add(name, …)`
would throw if a bundle shader ever shadowed a stock shader with the same name.

## One-time setup (≈30 min, Unity 2019.4.18f1c1 — the version KSP 1.12 runs)

1. Unity Hub → new project **3D (Built-in Render Pipeline)**, editor **2019.4.18f1c1**,
   path e.g. `E:\MangoTech\VolClouds.Unity`.
2. Copy the HLSL you want to change from
   `E:\MangoTech\VolClouds\shaders\hlsl\` into `Assets/EVE/Shaders/`.
3. Add a ShaderLab shell around it with **exactly the original shader name**, e.g.
   `Shader "EVE/RaymarchCloud" { Properties {…} SubShader { … HLSLPROGRAM … } }`.
   The cbuffer fields in the ported `.hlsl` are the property list; `Cbuffer.hlsl`-style
   grouping is already done in those files.
4. Select the `.shader` asset → Inspector → **AssetBundle: `eveshaders_tweak`** (type
   `eveshaders_tweak`, extension `.bundle`). Do **not** put the stock shaders in here.
5. `Assets/Editor/BuildTweak.cs`:

```csharp
using UnityEditor;
using UnityEngine;

public static class BuildTweak
{
    [MenuItem("EVE/Build tweak bundle")]
    public static void Build()
    {
        const string outDir = "BuildOut";
        System.IO.Directory.CreateDirectory(outDir);
        BuildPipeline.BuildAssetBundles(outDir,
            BuildAssetBundleOptions.ChunkBasedCompression,
            BuildTarget.StandaloneWindows64);
        Debug.Log("[EVE] tweak bundle -> " + outDir + "/eveshaders_tweak.bundle");
    }
}
```

6. Menu **EVE → Build tweak bundle**, then copy `BuildOut/eveshaders_tweak.bundle` into
   `GameData/EnvironmentalVisualEnhancements/`. Nothing else in GameData changes.

Iteration loop after that: edit `.hlsl` → rebuild in Unity (seconds) → copy one file → **restart KSP**
(shader changes are not hot-reloadable in a meaningful way).

## Do not

- Do not try to make one bundle containing all 19 shaders first — that is the 2–5 day path
  (render state, keywords, variants for every shader). The override lane exists precisely to
  skip it: only the shaders you actually edit go in.
- Do not rename a shader while tweaking. The name is the join key into `shaderDictionary`
  (`ShaderLoaderClass.FindShader`) and it is also embedded in `ShaderProperties.cs` constants.
- Do not ship `eveshaders_tweak.bundle` to users; it is a development lane.

## First three candidates (both visual and cost win)

| Change | File | Visual | Perf |
|---|---|---|---|
| Two-lobe HG energy normalisation `(1-k)·HG(g1)+k·HG(g2)`, k≈0.3, g1≈0.75, g2≈−0.25 | `RaymarchCloud.hlsl` (phase term feeding the sky-light accumulator, ~`:2205`) | thicker, less "flat grey" | none |
| Analytic planet shadow: `dot(p−sphereCenter, sunDir) > 0` ⇒ lit, else smoothstep on perpendicular distance / `planetRadius` (and early-out when `w ≤ 1`) | `RaymarchCloud.hlsl` (`:503`, `:509`, `:2279` already have the sphere test) | stops clouds glowing behind the planet | **saves** light-march steps |
| Depth-aware bilateral upsample of the reconstructed clouds | `ReconstructRaymarchedClouds.hlsl` | fixes smearing at wing/terrain edges | allows a cheaper rays resolution for the same quality |

Start with #2 — it is the only one that is simultaneously a visual fix and a straight reduction
in work, so it is verifiable in both directions.
