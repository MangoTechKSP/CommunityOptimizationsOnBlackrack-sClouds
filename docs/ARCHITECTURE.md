# Architecture notes — the rules you cannot see in the code but that bite

This document records the three rules that are easiest to get wrong: why 2D layers get
silently skipped, at what distances cloud layers load and unload, and whether camera
identification and cross-camera shared state are actually safe. Every conclusion below is tied to
specific code lines; read this again before changing any of it.

---

## 1. With a `layerRaymarchedVolumeV5`, there are no 2D layers at all

`src/Atmosphere/Atmosphere/CelestialBodyCloudsHandler.cs:168-180` (`LoadBody`):

```csharp
// When the body has raymarched volumetrics, skip the plain legacy layers.
if (configNode.HasNode("layerRaymarchedVolumeV5") || !hasRaymarchedVolumetrics)
{
    ApplyConfigNode(configNode, objectList);
}
```

The semantics are **per body, not per layer**: `hasRaymarchedVolumetrics` scans every config node
of that body in the constructor, and if **any** node carries `layerRaymarchedVolumeV5`, then every
config node on that body that does **not** carry it is dropped.

Consequences (this is real behavior under a 19-layer config):

- On a body that has a raymarched volume, the old `layer2D` / `layerVolume` layers **do not load**,
  `Layer2D` in `CloudsObject` is `null`, and every `Layer2D?.SetMapViewFade(...)` is a no-op.
- So `mapViewCloudFade` (the toggle in `RaymarchedCloudsQuality`), the fade in/out of
  `CloudsObject.Layer2D`, and the 2D layer's own cloud shadows all **stop working entirely** on
  such bodies, with no log line at all.
- Conversely, if **no** node of a body carries `layerRaymarchedVolumeV5`
  (`hasRaymarchedVolumetrics == false`), the condition `!hasRaymarchedVolumetrics` holds and every
  node loads — so this rule never leaves a pure-2D body empty. The design intent is "in a mixed
  config, raymarched wins".

To debug "why don't my 2D clouds show up", first check whether the body's cfg has any
`layerRaymarchedVolumeV5` at all. To genuinely mix them you have to change this condition (for
example, let `layer2D` and raymarched coexist), but that brings back the 2D layer's cloud shadows
and its draw cost — that is a content decision, not a bug fix.

## 2. Load/unload distance: 2000 R / 4000 R (with hysteresis)

`src/Atmosphere/Atmosphere/CelestialBodyCloudsHandler.cs:64-65`:

```csharp
loadDistance = 2000.0 * celestialBody.Radius;
unloadDistance = 4000.0 * celestialBody.Radius;
```

- The unit is **multiples of the body radius**, not meters. For Kerbin (R = 600 km) that is
  1,200 km to load and 2,400 km to unload.
- The two differ on purpose: that is **hysteresis**, so a body that has loaded does not flicker
  between load and unload at the horizon.
- The test uses "minimum distance from the camera to the body center" (the `minDistance`
  computation in the same class), so it acts **per body**, not per layer: all of a body's cloud
  layers come in and go out together.
- This gate is a different thing from §1 above: distance decides "should this body's clouds exist
  at all", §1 decides "which layers load once they do". The matching log lines are
  `Loading body <name>` / `Unloaded body <name>` (`GenericEVEManager<CloudsObject>.Log`).

When a distant observer (looking back at Kerbin from the Mun, say) sees clouds pop in or out, these
two numbers are the first suspect.

## 3. Camera identification: from name to role

### 3.1 The original approach

The original build of KSP tells cameras apart by GameObject name, and the reference implementations
of EVE and Scatterer both compared strings directly: `"Camera 00"` (near/main), `"Camera 01"`
(far/zoom), `"TRReflectionCamera"`, `"Reflection Probes Camera"`, `"DepthCamera"`, `"NearCamera"`.

The problem: any mod that adds a camera, renames one, or parents a camera to a different
GameObject makes those comparisons silently miss — usually showing up as "no clouds in some
camera" or "clouds misaligned in reflections", and with no error.

### 3.2 Now: `Utils/CameraRoles.cs`

`src/Utils/Utils/CameraRoles.cs` is the single source of truth:

- `CameraRole` enum: `Unknown / MainNear / MainFar / SceneryReflection / ReflectionProbe /
  DepthOnly / NearMirror`.
- `CameraRoles.GetRole(camera)`: first looks for a `CameraRoleMarker` component on the camera (or
  its GameObject) — an explicit marker, so a rename does not matter — then falls back to the
  original name table; results are cached per instance and recomputed automatically when the name
  changes.
- Convenience predicates `IsMainCamera` / `IsReflectionCamera` / `IsSkippedCamera`.

All 9 name comparisons on the `Atmosphere` side have been replaced by these predicates:
`DeferredRaymarchedVolumetricCloudsRenderer.cs:339/344/351/380`, `CloudsPQS.cs:471`,
`DepthToDistanceCommandBuffer.cs:41`, `ParticleField.cs:65`, `ScreenSpaceShadowsManager.cs:106`,
`WetSurfacesRenderer.cs:402/410`.

**For another mod to integrate**: give its own camera an `AddComponent<CameraRoleMarker>()` and set
`role`; to have the cloud pipeline ignore a camera completely, set `role` to
`CameraRole.DepthOnly` (`IsSkippedCamera` returns true).

### 3.3 What was deliberately left alone

There are still 8 name comparisons under `src/Scatterer/` (`OceanRenderer.cs:47`,
`ScatteringCommandBuffer.cs:53`, `ScreenCopyCommandBuffer.cs:59`,
`CausticsLightRaysRenderer.cs:79`, `DisableEffectsChecker.cs:24`, `ReflectionProbeChecker.cs:28`,
`ScreenSpaceScattering.cs:67`, `Scatterer.cs:382-383`). That project is the **baseline port of the
original assembly**, so changing it means diverging from upstream behavior, and all of those code
paths depend on render events that only occur on a real machine, so they cannot be verified
offline. Name matching is self-consistent inside Scatterer (it creates its own cameras and
configures their names), so it stays. If it is ever unified, start here: replace
`farCamera/nearCamera` in `Scatterer.cs:382-383` with `CameraRoles`, and the remaining call sites
will follow naturally.

## 4. Cross-camera shared state: audit conclusion

T10 originally suspected that `static` state such as
`DeferredRaymarchedRendererToScreen.compositeColorMaterial` would collide once there are several
cameras. The audit conclusion is that it **does not**, and the reason is call timing, not field
ownership:

- The **instance** of `DeferredRaymarchedRendererToScreen` is a singleton
  (`deferredRaymarchedRendererToScreen` at `DeferredRaymarchedVolumetricCloudsRenderer.cs:87`), so
  every camera shares the same full-screen quad and the same two materials.
- But every per-camera quantity (`CameraToWorld`, `innerSphereRadius` / `outerSphereRadius`,
  `sphereCenter`, `useCombinedOpenGLDistanceBuffer`, `cloudFade`, `renderQueue`) is written inside
  `DeferredRaymarchedVolumetricCloudsRenderer.OnPreRender()` (the method starting at
  `DeferredRaymarchedVolumetricCloudsRenderer.cs:656`, with the writes around `:711-725`).
- `OnPreRender` is a Unity per-camera message: it is called **before "this camera renders"**, and
  what immediately follows the writes is that camera's own draw call. So values written by camera
  A are only used by camera A's draw, and camera B overwrites them afterwards.
- Therefore the only way to collide is to write per-camera quantities at a frame-level timing such
  as `Update()`. The current code does not do that.

This conclusion rests on a fragile premise: **any refactor that moves those `SetMatrix` /
`SetFloat` lines from `OnPreRender` into `Update` will reintroduce multi-camera misalignment**.
Read this section to the end before changing it.

Two more per-camera facts (not bugs, but easy to misread):

- `CameraToDeferredRaymarchedVolumetricCloudsRenderer` is a `Camera → renderer` dictionary and the
  renderer component lives on the camera's own GameObject, so `reconstructCloudsMaterial`, the
  history RTs and the command buffers are all per-camera.
- The light volume is **a single global copy** (`LightVolume.Instance`), and it is updated only by
  the renderer belonging to the "main flight camera" (`useLightVolume && mainFlightCamera` at
  `:710-713`); reflection probes only read it. This is also the first structure T5 (multiple bodies
  on screen) has to touch.

## 5. One-line index

| Symptom | Look at first |
| --- | --- |
| All 2D cloud layers / cloud shadows gone on a body | §1, whether the cfg has `layerRaymarchedVolumeV5` |
| Distant cloud layers suddenly appear / disappear | §2, the 2000R/4000R hysteresis |
| No clouds in some camera / clouds misaligned in reflections | §3, add a `CameraRoleMarker` |
| Clouds wrong with two cameras (near + far) | §4, per-camera quantities must be written in `OnPreRender` |
| Two bodies with clouds bleed into each other | end of §4 + T5 |
