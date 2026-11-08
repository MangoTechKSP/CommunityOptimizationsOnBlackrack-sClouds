# Documentation

Design notes, mechanisms, tuning references and the acceptance checklist for the optimization pass.

| Document | Read it when |
| --- | --- |
| [ARCHITECTURE](ARCHITECTURE.md) | You are about to touch the cloud lifecycle, camera identification, or anything shared between cameras |
| [LIGHTING](LIGHTING.md) | You want to know how a cloud is lit, and which model replaced which |
| [TUNING](TUNING.md) | You want to change how the clouds look, and need the knob, its default, its range and what to look at |
| [SHADOW-CASTER](SHADOW-CASTER.md) | You are looking at cloud-on-cloud shadows |
| [GROUND-SHADOW](GROUND-SHADOW.md) | You are looking at shadows the clouds cast on the ground |
| [SKY-OPTICS](SKY-OPTICS.md) | You are looking at the halo or the rainbows |
| [LIGHT-VOLUME](LIGHT-VOLUME.md) | You are touching the baked 3D light volume, its sweep or its time slicing |
| [SAMPLERS](SAMPLERS.md) | You are adding a texture, or a shader stopped sampling correctly |
| [UNIFORMS](UNIFORMS.md) | A feature is silently doing nothing on the shader side |
| [MULTI-BODY](MULTI-BODY.md) | Two planets are on screen at once and something is drawn with the wrong geometry |
| [PANEL](PANEL.md) | You are using or extending the in-game volumetric-clouds window |
| [DIAGNOSTICS](DIAGNOSTICS.md) | You are reading a log line and want to know what it means |
| [ACCEPTANCE](ACCEPTANCE.md) | You are about to install a build and want to verify it properly |
| [BUILDING](BUILDING.md) | You want to reproduce the release |
| [TWEAK-BUNDLE](TWEAK-BUNDLE.md) | You want to override another shader |
| [FUTURE-FEATURES](FUTURE-FEATURES.md) | You want to know what is planned and what it would cost |

---

## Conventions used in these documents

**Paths are relative to a local working tree that is not part of this repository.** The documents
were written while working in a full source tree of the patched mod, so they cite paths like
`src/Atmosphere/Atmosphere/CloudsManager.cs:412`, `shaders/glsl/...` and `shaders/hlsl/...`. Those
paths are kept because they are the most precise reference available for a claim; they are not
links, and no file at those paths is distributed here. See [`../NOTICE.md`](../NOTICE.md).

**`file:line` references are evidence.** When a document says "this is why X happens", the line
number is where that was checked. If you are reading this against a tree that has drifted, the line
may have moved — the class and method name next to it has not.

**"The original build"** always means the unmodified release of the mod, as installed. "Shipped"
and "default" mean the current release of this pass.

**Sections numbered §n** inside a document are referenced from other documents by number, not by
link, because the number is stable and the file it lives in may be split later.

## Writing style for these documents

* Every claim about behaviour names the code or the observation that establishes it.
* Every knob gets: where it lives, default, range, effect, and what to look at.
* Numbers are written with their unit and the resolution they were measured at.
* "Looks fine" is not a result. "Item 4.2 passes at 8 km over Kerbin, screenshot X" is.
