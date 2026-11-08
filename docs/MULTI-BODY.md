# T5 — Clouds with two bodies on screen (current state, blockers, staged plan)

> **This document is analysis and a plan, not implemented code.** T5 committed no behavioural
> change: there is no KSP installation on this machine (`D:\Kerbal Space Program` only has Steam's
> depotcache), and this change **must** be A/B'd on real hardware at a genuine two-body viewpoint
> such as Jool + Laythe. Changing hot paths blind only turns "one body correct" into "both bodies
> wrong", which violates the project's first rule (never trade effect for performance/features).
>
> Current behaviour: `DeferredRaymarchedVolumetricCloudsRenderer.singleBodyPerCamera = true`,
> so a camera keeps the cloud layers of **only the body nearest to that camera** and discards the
> other body's clouds (`shellCulledLayersInInterval` / `singleBodySkippedLayersInInterval` report
> this in the diagnostics line, see `docs/DIAGNOSTICS.md`). A two-body viewpoint therefore does not
> glitch; the distant body simply has no clouds.

---

## 1. Where the single-body assumption lives

Every "this scene contains exactly one sphere with clouds" assumption inside
`DeferredRaymarchedVolumetricCloudsRenderer`, ordered by severity:

| # | Location | Assumption | Consequence (if left unchanged) |
| --- | --- | --- | --- |
| **A** | `src/Atmosphere/Atmosphere/DeferredRaymarchedVolumetricCloudsRenderer.cs:930` `ResolveLayerOverlapIntervals` + `:877` `ResolveLayerIntersections` | All layer shells are **concentric spheres**, so the layers' inner and outer radii can be sorted into a single one-dimensional radial band | Two bodies each bring their own set of concentric spheres. Mixing their radii into one sort interleaves "a band at radius 1.2e6" with "a band at radius 7e4", so the front-to-back order along the ray is completely scrambled → clouds are composited at the wrong depth and near clouds are covered by far ones |
| **B** | `:1161-1162` sets `planetRadius` / `sphereCenter`, read by the shader at `shaders/hlsl/ReconstructRaymarchedClouds.hlsl:121` | The reconstruction stage has **exactly one sphere**: `:236` intersects the ray with the inner and outer shells, `:243-297` decides the march start point, and the binary search at `:334-` maps pixel depth back into in-shell distance using that same sphere | The second body's ray buffer is interpreted with the first body's sphere: shell hit/miss decisions invert and the binary search computes wrong distances → that body's clouds either disappear or are torn into fragments, and they contaminate the shared history buffer |
| **C** | `:747-750` `LightVolume.Instance.Update(volumesAdded, cameraPosition, volumesAdded[0].parentCelestialBody.transform, planetRadius, …)`; `src/Atmosphere/Atmosphere/LightVolume.cs:593` `MoveLightVolumeIfNeeded`, `:653`/`:670` `SetVector(sphereCenter, planetPosition)` | The light volume is a **single global** `Texture3D`, baked around one planet only | The second body's clouds get no light volume of their own. Note that the light volume is itself a dead path in the current build (`docs/LIGHT-VOLUME.md`), so this item produces no visible error today, but as soon as the light volume works it immediately becomes blocker #2 |
| **D** | `:521-528` `historyRT` / `historyMotionVectorsRT` / `historyDistanceRT` / `upscalingHeuristics` / `packedNewRaysRT` / `packedOverlapRaysRT` in `InitRenderTextures` | **One** history chain for temporal reprojection (one per eye / cubemapFace) | Both bodies' rays are written into the same `packedNewRaysRT` and reconstruction rejects/blends against the same history: turn the camera and body A's history pixels are compared with body B's new rays, producing ghosting/flicker. This cannot be solved by "drawing it one more time"; it is a **data ownership** problem |

Also worth recording `:1011`'s `MeshRenderer volumeMeshrenderer = volumesAdded[0].volumeMeshrenderer;`:
**this is not a blocker**, see the next section.

## 2. What is already right (less work than it looks)

Three things mean multi-body support does not need a rewrite from scratch:

1. **The ray-march sphere centre is per-material.** `CloudsRaymarchedVolume.ApplyShaderParams()`
   writes `sphereCenter`/`planetRadius`/`innerSphereRadius`/`outerSphereRadius` into **that layer's
   own** material (`src/Atmosphere/Atmosphere/CloudsRaymarchedVolume.cs:965-995`), and
   `CloudsRaymarchedVolume.Updater.OnWillRenderObject()` (same file, `:33-41`) refreshes them from
   `parent.position` before every render. So `EVE/RaymarchCloud` is itself **already multi-body
   correct**: each layer shell marches around its own sphere centre and computes sun/planet shadows
   against its own planet (`shaders/hlsl/RaymarchCloud.hlsl:143`/`:146`/`:457`/`:510`/`:556`/`:2414`).
2. **`volumesAdded[0].volumeMeshrenderer` only means "take some mesh and draw with it"; geometrically
   it does not matter.** `VS_RaymarchCloud` (`shaders/hlsl/RaymarchCloud.hlsl:108-128`) writes clip
   space straight from `input.position` and **ignores `unity_ObjectToWorld` entirely**; and every
   cloud shell mesh is the same infinite bounding-box quad (`CloudsRaymarchedVolume.cs:587`
   `CreatePrimitive(Quad)` + `:610` `mesh.bounds = ±infinity`). Whichever renderer you pass to
   `DrawRenderer` draws the same full-screen quad, so this line needs no per-body split.
3. **Compositing and depth occlusion do not care about the sphere centre.** The GLSL taken from the
   original build for `EVE/CompositeRaymarchedClouds`
   (`shaders/glsl/CompositeRaymarchedClouds/EVE__EVE_CompositeRaymarchedClouds__15__08e8dc681045.glsl`,
   83 lines) has only `cloudFade` + `colorBuffer` + `_RaymarchedCloudsBackgroundTexture`;
   `EVE/CloudDepthOcclusion` (`shaders/glsl/CloudDepthOcclusion/*.glsl`) uses
   `_WorldSpaceCameraPos` + `unity_CameraInvProjection` + `CameraToWorld` + two buffers and has
   **no sphere uniform at all**. The `innerSphereRadius`/`outerSphereRadius`/`sphereCenter` that
   `:755-757` writes onto `compositeColorMaterial` are **dead uniforms** for this shader (written,
   never read); delete them in passing when doing multi-body work, no need to worry about them.

## 3. Staged plan

Every stage compiles, commits and rolls back independently; **do not touch shaders before P1**.

### P0 (done) — single-body fallback
`singleBodyPerCamera = true`: when a second cloud-bearing body appears in the same camera, keep the
one nearer the camera, drop the other group entirely, and count it in the diagnostics line. The
behaviour is predictable and does not glitch.

### P1 — group the data model by body (est. 1–2 days, pure C#, zero image-quality risk)
- add `struct BodyCloudSet { CelestialBody body; List<CloudsRaymarchedVolume> layers; List<RaymarchedLayerBound> bounds; List<OverlapInterval> intervals; float innerRadius, outerRadius; }`;
- fill `volumesAdded` grouped by `parentCelestialBody`;
- change `ResolveLayerOverlapIntervals` / `ResolveLayerIntersections` to **run once per body** (today they compute over all layers mixed together);
- in `OnPreRender`, turn every `volumesAdded[0].X` into `primaryBody.X` (= the group belonging to the body nearest the camera); behaviour is **exactly the same** as today, it only turns the "implicit single body" into an "explicit single body".
- Acceptance: single-body viewpoints unchanged pixel for pixel (same-viewpoint screenshot comparison on real hardware); two-body viewpoints behave like P0 (the `directSlices`/`culled` numbers in the diagnostics line unchanged).
- **This stage must be run on real hardware first**, because it rearranges data structures on the hot path and the three following stages are built on it.

### P2 — independent ray buffer per body (est. 3–5 days, memory + cost)
- `packedNewRaysRT` / `packedOverlapRaysRT` / `unpackedNewRaysRT` / `unpackedMotionVectorsRT` / `unpackedWeightedDepth` go from single to indexed by `[bodyIndex]`;
- `HandleRenderingCommands` runs once per body, each call doing `SetRenderTarget` on its own buffer;
- Memory: `packedNewRaysRT` is `ARGBFloat`, resolution = screen / (reprojectionXfactor × reprojectionYfactor);
  at the default 3×1 that is about 1920/3 × 1080 = 690k px × 16 B × 2 (flip-flop) = **about 22 MB per body**.
  Two bodies is +22 MB, acceptable.
- Risk: `Lightning`'s occlusion buffer (`lightningOcclusionRT`, `:535`) is also single-instance, so it needs to be split per body or explicitly restricted to the primary body.

### P3 — reconstruction supports multiple spheres (est. 1–2 weeks, **the only stage that changes shaders**)
- `shaders/hlsl/ReconstructRaymarchedClouds.hlsl`: turn `sphereCenter`/`innerSphereRadius`/`outerSphereRadius`
  into small arrays (length 2 recommended, `#define EVE_MAX_CLOUD_BODIES 2`), and change shell
  intersection and march start point in §2–§4 plus the binary search in §6 to "intersect every sphere
  and advance through the nearest one";
- Key constraint: **values must stay exactly identical in the single-body case** (with array length 1 take the path that is verbatim identical to today), otherwise T4's tuned depth-upsampling thresholds and reprojection rejection will drift along with it;
- Running reconstruct once per sphere (`commandBuffer.DrawRenderer(volumeMeshrenderer, reconstructCloudsMaterial, 0, pass)` looped per body, setting its own sphere uniforms and **its own history buffer** each time) is safer than "handling multiple spheres in one pass", but doubles the cost
  — the most expensive trade-off of this stage, see §4.

### P4 — light volume per body (est. 3–5 days, **depends on `docs/LIGHT-VOLUME.md` §6 being finished first**)
Doing this while the light volume is still a dead path makes no sense. Order: first build `EVE/LightVolumeShadow`
(P0 of light volume), then talk about one 3D texture per body (volume dimensions are in `LightVolumeSettings`; one copy is tens of MB,
two need a fresh evaluation).

### P5 — temporal history per body (est. 3–5 days, alongside P3)
Each history chain is a full-screen `DefaultHDR` (8 B/px) + `RGHalf` (4) + `RHalf` (2) + `R8` (1)
= **15 B/px × 2 flip-flop = 30 B/px**. 1920×1080 ≈ 62 MB per camera per body. Two bodies ≈ +62 MB,
plus VR (one copy per eye) and reflection probes (one copy per cubemapFace) — **memory, not compute, is the real limit of this stage**.

## 4. Cost and trade-offs (written down so we do not improvise before touching real hardware)

| Approach | Cost | Risk |
| --- | --- | --- |
| Run the full pipeline once per body (loop P2+P3+P5 N times) | reconstruct is full-screen and heavy (10 binary searches + 4 motion-vector iterations); N=2 nearly **doubles** the main cloud pass cost | memory ×2; low-end machines drop frames outright |
| Multi-sphere single pass (loop over spheres inside the shader in P3) | only a few more intersections, essentially free | the two bodies' rays are distinguished by id, so the body id has to be carried through the packed buffer (possibly encoded into the bit width); the most convoluted option to implement |
| Keep P0 (nearest body only) | 0 | the distant body has no clouds; users can see it |

**Recommended route**: P1 → P2 → implement P3/P5 with "run once per body" and measure the cost (simplest, best correctness);
once real-hardware cost has been measured, decide whether saving that one reconstruct is worth writing "multi-sphere single pass". Do not
write the most convoluted version before measuring.

## 5. What not to do

- **Do not** create a separate `DeferredRaymarchedVolumetricCloudsRenderer` for the second body. Its static dictionaries
  (`:89` `CameraToDeferredRaymarchedVolumetricCloudsRenderer`) and global singletons
  (`:91` `deferredRaymarchedRendererToScreen`, `DeferredRaymarchedRendererToScreen.compositeColorMaterial`)
  are keyed by camera, so two instances would overwrite each other's per-camera uniforms on `compositeColorMaterial`.
  This is exactly the extension of the red line recorded in the architecture rule: "per-camera quantities must be written in `OnPreRender`".
- **Do not** write sphere centres/radii inside `Update()` (same reason: another camera would stomp them).
- **Do not** flip `singleBodyPerCamera` to `false` just to be done with it and declare multi-body support: then both bodies' layers
  enter the same single-body radial sort (blocker A), the output is wrong, and it is worse than today. That comment is already at
  `:93-100`, do not revert it.

## 6. Delivery gate

Every T5 stage must satisfy:

1. `dotnet build VolClouds.sln -c Release` 0 errors, 0 warnings;
2. `bash tools/rebuild.sh` fully green (`shader errors: 0`);
3. single-body viewpoints **pixel-identical** (same viewpoint, same cloud map, same time, A/B screenshots; especially important after P3);
4. two-body viewpoints (Laythe seen from near Jool, or the other way round) confirmed on real hardware: both cloud sets appear, the near one occludes the far one,
   no ghosting when turning the camera, both bodies counted in the diagnostics line;
5. frame rate: record the average and the minimum before and after the change (`cpuMs`/`gpuMs` in `docs/DIAGNOSTICS.md`).

## 7. Re-check commands

```bash
# how many single-body assumptions are left (after P1 only the "primaryBody" layer should remain)
grep -n "volumesAdded\[0\]" src/Atmosphere/Atmosphere/DeferredRaymarchedVolumetricCloudsRenderer.cs

# every place the reconstruct pass reads the sphere centre/radius (P3's change surface)
grep -n "sphereCenter\|innerSphereRadius\|outerSphereRadius" shaders/hlsl/ReconstructRaymarchedClouds.hlsl

# confirm compositing/depth occlusion really do not need the sphere centre (§2 item 3)
grep -a -c "sphereCenter" shaders/glsl/CompositeRaymarchedClouds/*.glsl shaders/glsl/CloudDepthOcclusion/*.glsl   # expect 0
```
