# Contributing

Thanks for looking. This project patches a commercial mod, so the rules are a little different
from a normal open-source repo.

## What is welcome

* **Bug reports** with the in-game diagnostic block plus the matching `KSP.log` lines. The volumetric-clouds panel
  prints camera, body, layer and interval counts, reprojection factor, light-volume state, culled
  shells and CPU/GPU cost; [`docs/DIAGNOSTICS.md`](docs/DIAGNOSTICS.md) explains every line.
* **Acceptance results.** [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) is a checklist written
  precisely so that a result can be reported as "item 3.2 fails, here is the screenshot".
* **Documentation and tooling.** These are fully ours and MIT licensed; improvements, ports and
  new checks are easy to merge.
* **Algorithm descriptions and re-implementations.** If you have a better scattering model, a
  cheaper shadow test, or a port of one of these techniques to another renderer, send it as
  prose, formulas or code *you* wrote.

## What cannot be accepted

* Any code, shader, asset, config or patch that originates in the mod being optimized. Pull
  requests that copy upstream source, or that carry a diff of it, cannot be merged — see
  [`NOTICE.md`](NOTICE.md). Describe the change and its effect instead; the documentation in
  [`docs/`](docs) is written that way on purpose.
* Rebuilt assemblies or bundle files. Releases are built by the maintainer from a licensed
  install.

## Style for documentation

* English.
* Every claim about behaviour should name the file and the line it was checked against, or the
  observation that establishes it. "It looks like" is not a finding.
* Every knob gets: where it lives, default, allowed range, what it does, and what to look at to
  decide whether it is right.
* Do not describe a change as an optimization unless it removes work that is provably
  unnecessary. Trading effect for frame time is a regression, not an optimization.

## Style for tools

* Python 3, standard library unless a dependency is unavoidable; say why in the file header.
* A tool that validates something must print what it checked and fail loudly — a checker that
  silently passes is worse than no checker.

## Reporting something that looks broken

Include:

1. KSP version, GPU, driver, Windows version.
2. Whether Scatterer is installed.
3. The panel's diagnostic block.
4. The last ~200 lines of `KSP.log` around the first `[EVE]` line.
5. A screenshot with the body and altitude visible.
