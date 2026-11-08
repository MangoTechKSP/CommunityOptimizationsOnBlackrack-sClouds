# Future features / roadmap

What is planned, why it is worth doing, how it would be built, what it would cost, and how it
would be judged. Nothing here is a promise; the order changes as acceptance results come in.

Two rules apply to every item:

* **No effect is traded for frame time.** If an item cannot be made affordable, it does not ship.
* **Every new behaviour has a knob whose 0 value reproduces the previous look exactly**, because
  the only way to tell a shading bug from an intended change is to be able to turn it off.

---

## 1. Cloud layer realistic interaction

*Status: designed, not implemented. Highest-value gameplay item on the list.*

### The problem

Today the cloud field is a function of position and time only. A craft flies through a deck and
the deck does not notice: no wake, no hole closing behind the wing, no vortex drawing wisps into a
spiral, no shock wave clearing a cone ahead of a supersonic airframe, no exhaust plume thinning the
cloud it passes through. The clouds are scenery, not a medium.

That is the single biggest gap between this and the reference footage everyone compares it to.
Clouds that react are also the cheapest way to make flight feel fast, because the feedback is
local, visible and motion-coupled.

### What "interaction" means here

Four independent mechanisms, in increasing cost. Each is separately switchable.

**1.1 Wake and displacement (v1)**

Whatever moves through the cloud leaves a tube of disturbed density behind it. Implemented as a
*world-space clearance field*, not as a modification of the cloud noise:

* A small 3D texture — 48³ `R8` is 110 KB, 64³ is 262 KB — is kept aligned to the camera and
  re-centred when the camera moves more than half a cell. Because interaction is local (a few
  kilometres), camera-aligned is enough; no per-planet field is needed.
* Each frame the field is updated with a ping-pong pass: read the previous field, multiply by a
  decay term, then stamp the current emitters as swept segments (a capsule per frame, so the wake
  is continuous instead of a string of beads).
* The density function multiplies by `1 - field(p)` after the base density is computed. One
  trilinear fetch in a path that already does three.

Emitters come from the C# side: up to 16 vessel-based sources, each as two `float4` uniforms
(position, direction/radius) plus one strength. Uploaded once per frame; no per-part allocation,
no managed garbage, no per-frame `new` at all.

**1.2 Wingtip vortices (v1.1)**

A wing leaves two counter-rotating tubes. Their velocity field is analytic (a line-vortex
tangential term), and it is *added to the curl displacement* that already exists in the shader —
so the wisps at the edge of the deck spiral into the vortex instead of being pushed sideways.
Cost: arithmetic on data the displacement step already has, plus the same field fetch. This is
what makes a high-G turn look like a high-G turn.

**1.3 Rotor and prop wash (v1.1)**

A downward cylinder of clearance under a rotor, with a fade at both ends and a slight taper, plus
an outward ring at the ground contact point when close to terrain. Same field, different stamp
shape. Helicopter and VTOL flight over a deck is the showcase.

**1.4 Shock clearing and vapour cone (v2)**

Supersonic flight should carve a cone: the cloud is pushed out of the Mach cone and, in humid
layers, a thin vapour sheet forms on the cone surface. Implemented analytically in the density
function from the emitter's Mach number and axis — no new texture, no new pass. This is also the
honest way to render the "bow shock" look: it is a density discontinuity, not a decal.

**1.5 Exhaust heat (v2, uncertain)**

A plume reduces density along its axis and adds a small emissive term. The density part is cheap
and belongs in the same field. The emissive part needs an additive pass and a light probe, and it
risks looking like a glow sprite; it stays on the list as "investigate", not "planned".

### Interaction between decks (v2, separate item)

Two decks at different altitudes currently only interact through cloud-on-cloud shadowing (which
is already implemented). A real coupling would be convective: the top of a lower deck feeds
towers into the base of an upper deck under unstable lapse rate, and wind shear advects one layer
past the other. Cheap approximation: a vertical coupling term that samples the layer above and
below and, only where both are near their base/top, adds a soft column. Expensive to tune, easy
to make look like a mistake — do the vessel interaction first, then judge whether this is worth
it.

### Cost estimate

| Part | Work | Runtime cost |
| --- | --- | --- |
| Wake field + density hook + emitter upload | 3–5 days | 1 dispatch, < 0.3 ms; +1 texture fetch in the march |
| Vortex term in the displacement step | 2 days | arithmetic only |
| Rotor/prop stamps + ground ring | 2 days | same field |
| Shock cone + vapour sheet | 2–3 days | arithmetic only |
| Panel controls + diagnostics | 1 day | none |
| Acceptance and tuning in game | 3–5 days | none |

### Acceptance

1. Fly a craft through a deck at 200 m/s: a visible hole forms and closes over ~2–3 s.
2. Same flight with `wakeInteraction = 0`: the frame is indistinguishable from the current build
   (A/B by screenshot, same camera, same time).
3. Vortices: a high-G turn in a thin deck shows two spiral wisps; `vortexStrength = 0` removes
   them and nothing else.
4. Rotor: a helicopter hovering under a deck clears a column; the column follows the craft.
5. Supersonic: the cone is crisp at Mach 1.3 and softens with distance; no cone below Mach 1.
6. Panel reports the field dispatch time; the frame-time delta on the reference machine is under
   0.5 ms at 2560×1440.
7. Time warp, scaled space, main menu: interaction silently disabled, no allocation, no log spam.

### Why the field, and not "just subtract a sphere in the shader"

Because the marcher takes up to 100+ density samples per pixel. Any per-sample test against
emitters costs 16× more than one fetch. A 48³ field gives the same look at the cost of one
texture read, and it makes decay, overlap and continuous trails trivial — all three are hard to do
analytically and all three are what makes the effect read as physical.

---

## 2. Multi-body rendering

*Status: analysed in [`MULTI-BODY.md`](MULTI-BODY.md), not implemented.*

The renderer's composite, reconstruction and light-volume stages all read the first volume's planet
radius and sphere centre, so a second planet in frame is drawn with the first planet's geometry.
Nearest-body-wins is implemented as a stopgap; a real fix needs per-body render targets, a
per-volume light volume, and a shader that takes geometry per volume rather than per camera.
Estimated 2–3 weeks. Gate: Jool and Laythe in one frame, both correct, at shipped quality.

## 3. Cloud base height that follows the ground

*Status: designed, not implemented.*

Two related wants: a cloud base that undulates over terrain (sea level to ~8 km) and regions that
have no cloud at all.

* Keeping the shell a sphere and remapping height **inside** the density lookup is cheap and does
  not break the analytic sphere intersection. `h' = h - bump(dir)`, one extra fetch, one knob,
  default 0.
* A true terrain-following base needs a per-body cubemap baked from `PQS.GetSurfaceHeight` — 6×128²
  samples, a few hundred milliseconds at load, cached per body.
* Regions without cloud are **already supported**: the eighteen `cubeCloudCoverage*` textures are a
  per-direction coverage mask, and a painter exists for authoring them. The work is documentation
  and a preset, not code.

Caveat, and it is a real one: if Parallax (or any terrain-replacement mod) changes the rendered
terrain, a height map baked from `PQS.GetSurfaceHeight` will not match what the player sees. The
bake has to come from whatever the renderer actually uses, or the feature has to accept a visible
offset.

## 4. Light volume at full quality

*Status: partially done.*

The bake now closes its sweep and survives time warp, but the volume is still low resolution and
sliced over many frames. Streaming quality (more slices close to the camera, fewer far away) is
the next step, and it is mostly a scheduling change, not a shader change.

## 5. Temporal robustness

The reconstruction stage reprojects using motion vectors and a heuristic depth test. Two known
weaknesses: thin geometry edges, and fast camera rotation (the history becomes wrong faster than
the blend weight adapts). A neighbourhood clamp (variance clipping of the history) is the standard
fix and costs one extra fetch in a pass that runs at half resolution.

## 6. Performance instrumentation, round 2

The panel reports CPU and GPU milliseconds for the passes it knows. The light-march pass is not
counted, and the worst case — a deck directly overhead — is the one nobody measures. The plan is a
per-cell sun-axis interval table for the light march (the same structure the main march already
uses for candidate volumes) plus counters for "field evaluations per pixel", so a regression can
be attributed to a stage without a profiler capture.

## 7. Hair-level silhouette detail

1.2.3 made the fringe read as hair rather than blobs by discarding the sub-threshold fringe and
frequencing the displacement up by 3×. The next step is anisotropic, direction-aware fray along
the curl field, which needs a derivative-aware erosion term rather than more octaves.

---

## Not planned

* Anything that reaches frame time by dropping resolution, density, shadow resolution or step
  counts. That is a settings change, not an optimization, and it is already available to users.
* Bundling or redistributing the original mod, its assets or its shaders. See [`NOTICE`](../NOTICE.md).
* OpenGL. The bundle and the code path are D3D11; keeping a second platform green is a project of
  its own.
* Per-part particle systems for contrails. Different feature, different mod's job.
