# NOTICE

## What this repository contains

Everything here was written by the contributors to this project:

* `source/` — new C# classes and two new shader passes (`RaymarchedCloudShadow`, `SkyOptics`).
* `unity/` — the Unity project assets that build the shader-override bundle, including the
  `.shader` wrappers and the batch-mode bundle builder.
* `tools/` — build, inspection and auditing tools.
* `docs/`, `README.md`, `CHANGELOG.md` — documentation.

These are MIT licensed, see [LICENSE](LICENSE).

## What this repository does not contain

It does **not** contain the mod being optimized. Specifically, it deliberately excludes:

* The cloud mod's own source code, in any form — original, reformatted, or reorganized.
* The cloud mod's compiled assemblies of the upstream build we patch against.
* The cloud mod's shader sources, whether in their original form or as any translated form.
* The cloud mod's art assets: `eveshaders.bundle`, cubemaps, cloud coverage textures, noise
  textures, config files, and the texture-set packages.
* Patches or diffs that reproduce the mod's source. The changes this project makes are
  *described* in [`docs/`](docs) — as behaviour, formulas, defaults and validation steps — which
  is enough to re-implement or port them, and is not a copy of the original code.

That is a deliberate choice, not an oversight: the mod is commercial, and redistributing its
code or assets — including "just the changed files" — is not something this project does.

## Why the code here still looks like it belongs to a mod

The new classes and shaders in `source/` are written against the mod's types, constant buffers
and pipeline. They are meaningful only inside a licensed copy of the original source tree, and
they do not compile on their own. That is expected: they are contributions *to* an install you
own, published so the work can be reviewed, ported and re-implemented.

## Using this

The optimization layer is distributed as replacement assemblies and a shader override bundle, and
only works on top of a purchased copy of the original:

* <https://www.patreon.com/blackrack>

If you do not own the original, this repository has nothing for you to run.

## Trademarks and credits

* Volumetric clouds, and the ray-marched cloud build of Environmental Visual Enhancements:
  **blackrack**.
* Environmental Visual Enhancements: **rbray89** and contributors.
* Scatterer: **blackrack**.
* Kerbal Space Program: Squad / Private Division.
* Unity: Unity Technologies.

This is unaffiliated community work. It is not endorsed by, supported by, or connected to any of
the above.

## Takedown

If you hold rights to material that you believe appears here, open an issue and it will be
removed.
