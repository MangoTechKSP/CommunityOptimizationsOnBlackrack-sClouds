# The volumetric-clouds panel

A second toolbar button, next to EVE's own, that opens a compact panel for the raymarched clouds
only. Source: `src/Atmosphere/Atmosphere/VolumetricCloudsWindow.cs`.

## 1. Why it exists

The stock EVE window reaches these settings through Alt+0 → a manager selector → a config-file
selector → an object selector, and a changed value is only re-read on the next preset switch. That is
three nested lists for the one thing this fork added knobs to. The panel is one click, applies the
value when the slider is released, and prints the same numbers the `[EVE] raymarched pass` log line
carries, so a change can be judged without tailing `KSP.log`.

It is a tuning aid, not a second settings system:

* the preset `.cfg` stays the source of truth — a value moved in the panel is written into the
  active preset object **in memory**, so it survives `Apply()` and scene changes within the session,
  but a game restart re-reads the file;
* "Reload preset" throws the live values away and re-reads the file, exactly like switching presets
  in the EVE window.

## 2. What is in it

Status block (from `DeferredRaymarchedVolumetricCloudsRenderer`'s diagnostic snapshot, updated every
5 s):

| line | meaning |
| --- | --- |
| `body / layers / intervals` | which body's clouds are drawn, how many layer shells, how many radial bands the overlap sweep produced |
| `reprojection / light volume` | temporal upscale factor and whether the light-volume path is on |
| `layers culled / other body` | shells this camera refused, and shells skipped because they belong to a farther clouded body (the single-body limit, `docs/MULTI-BODY.md`) |
| `cloud slices baked` | how much of the light volume the frame refreshed (`docs/LIGHT-VOLUME.md` §4) |
| `cpu / gpu` | average `OnPreRender` cost and, if the player reports frame timing, GPU frame time; `n/a` is expected in KSP (`docs/DIAGNOSTICS.md` §3) |

When the count is zero the panel lists the four usual causes instead of leaving the reader with
`volumes=0`.

Three sliders, all live:

| slider | uniform / config | documented in |
| --- | --- | --- |
| Edge wisps | `edgeWisp` → `EVEEdgeWisp` | `docs/TUNING.md` §4 |
| Cloud-on-cloud shadows | `shadowCasterStrength` → `EVEShadowCasterStrength` | `docs/TUNING.md` §5, `docs/SHADOW-CASTER.md` |
| Depth upsampler tolerance | `depthUpsampleThreshold` → `EVEDepthUpsampleThreshold` | `docs/TUNING.md` §1 |

Apply semantics: dragging only marks the batch dirty; releasing the thumb (or pressing **Apply now**,
**Discard**, **Reload preset**, or closing the window) calls
`RaymarchedCloudsQualityManager.ApplyRuntimeOverrides`, which clamps the values, writes them into the
active preset object, reinitialises the renderers and re-applies the materials. Reinitialising per
frame while the thumb moves would rebuild render targets continuously, which is why it waits.

## 3. What it deliberately does not do

* No preset editor, no file writing, no per-body overrides.
* No controls for the raymarch budget (`baseStepSize`, `maxStepSize`, `lightMarchSteps`). Those are
  the ones that actually cost frames, and a slider for them invites benchmarking against a preset
  that no longer matches the shipped one; they stay in the EVE window's quality page.
* It does not replace the EVE window or the Alt+0 shortcut.

## 4. Verifying

Offline: `dotnet build VolClouds.sln -c Release` must stay at 0 warnings / 0 errors — the panel is
compiled into `Atmosphere.dll`, and `Atmosphere.csproj` gained references to
`UnityEngine.AnimationModule` (the launcher's button type pulls it in transitively) and
`UnityEngine.TextRenderingModule` (`FontStyle`) for it.

On device:

1. The toolbar shows two buttons in flight, KSC and the tracking station: EVE's and a cloud glyph.
2. Clicking the cloud glyph opens "Volumetric Clouds" with a status block; clicking it again closes
   it, as does the launcher's own toggle.
3. Move "Cloud-on-cloud shadows" to `0` and release: the effect disappears within a frame or two,
   the status block keeps updating, and no log spam appears.
4. "Reload preset" restores the values from `EVE_RAYMARCHED_CLOUDS_QUALITY.cfg`.
5. The window cannot be dragged off-screen (its title bar stays reachable) and survives a resolution
   change.
