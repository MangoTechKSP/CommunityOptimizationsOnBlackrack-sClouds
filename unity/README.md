# Unity project assets

The `.shader` wrappers and the batch-mode build script that produce the shader-override bundle
(`eveshaders_tweak.bundle`).

## Why these exist

Unity binds material properties by name and samplers by inline state, so a shader extracted from a
bundle cannot simply be dropped back in. Each override needs:

* a wrapper whose **shader name string is identical** to the one being replaced, e.g.
  `Shader "EVE/RaymarchCloud"`;
* a single pass: `Cull Off ZWrite Off ZTest Always Blend Off`, `target 5.0`;
* the `multi_compile` keywords the C# actually enables;
* the flattened HLSL body (see [`../tools/flatten_cbuffer.py`](../tools/flatten_cbuffer.py)).

## Building a bundle

1. Unity **2019.4.18f1c1**, new 3D project, built-in render pipeline, no packages needed.
2. Put the `.shader` files (and their flattened `.hlsl`) under `Assets/Shaders/`.
3. Put `TweakBundleBuilder.cs` under `Assets/Editor/`.
4. Batch mode:

```
Unity.exe -batchmode -quit -projectPath <this folder> \
  -executeMethod TweakBundleBuilder.CIBuild -logFile build.log
```

5. Pass criterion: `grep -c "Shader error" build.log` is `0`, and the bundle contains one more
   shader than before. The bundle lands in `BuildOut/` inside the project folder — not in the
   repository root.
6. Copy it to `GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle`.

## Which shaders are overridden

| Wrapper | Shader | What it changes |
| --- | --- | --- |
| `EVE_RaymarchCloud.shader` | `EVE/RaymarchCloud` | The main volume march: lighting model, contour, edge wisps, cloud-on-cloud shadow term |
| `EVE_ReconstructRaymarchedClouds.shader` | `EVE/ReconstructRaymarchedClouds` | Depth-aware upsampling and the temporal reconstruction |
| `EVE_RaymarchedCloudShadow.shader` | `EVE/RaymarchedCloudShadow` | New: cloud shadows on the ground |
| `EVE_SkyOptics.shader` | `EVE/SkyOptics` | New: ice halo and rainbows |

The first two wrap shader bodies derived from the original build and are **not** distributed in
this repository — see [`../NOTICE.md`](../NOTICE.md). The last two are our own shaders and are in
[`../source/`](../source).

## Failure modes worth knowing

* A keyword variant missing from the wrapper compiles fine and does nothing.
* A uniform name that does not match the C# reads as zero, silently.
* An inline sampler used but not declared in the file is a compile error; a sampler with the wrong
  wrap mode is a seam you will only see at one altitude.
* KSP reads bundles at startup only. A rebuilt bundle requires restarting the game.
