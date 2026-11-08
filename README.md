# VolClouds — reverse-engineered EVE volumetrics

C# source recovered from the shipping binaries of **Environmental Visual Enhancements - Redux
v3.2.2 (raymarched-volumetrics build)**, i.e. the private "volumetric clouds" edition of EVE that
ships with the KSP raymarched-clouds early access package. Goal: a readable, buildable source tree
for study and for re-implementation work (see the sibling `Helmholtz` project).

Scope: the 11 EVE managed assemblies. **Scatterer is not included yet** (its `RaymarchedGodraysRenderer`
is the other half of the volumetric integration, ~19k decompiled lines).

## Provenance / how it was recovered

1. Binaries: `RaymarchedVolumetricsEarlyAccess23_08_26/GameData/EnvironmentalVisualEnhancements/Plugins/*.dll`
   (EVE 3.2.2.0, all 11 assemblies ship with matching portable PDBs).
2. PDBs are *portable* PDBs with intact document tables: they list the original compiler inputs
   (`.\Atmosphere\RaymarchedClouds\LightVolume\LightVolume.cs`, ...) plus a SHA-256 per file. That
   proved the build is a superset of the public `raymarched-volumetrics` branch, and that the
   private build is *newer* (Noise/, WetSurfaces/, ScreenSpaceShadowsManager.cs do not exist upstream).
3. Code: `ilspycmd -p -r <KSP managed dir>` per assembly. Passing the KSP reference directory is
   required — without it ILSpy cannot resolve nested KSP types and emits broken output
   (`UrlFile` instead of `UrlDir.UrlFile`, explicit calls to implicit conversion operators, ...).
4. Shaders: `eveshaders.bundle` is a UnityFS bundle where every `Shader` object holds per-platform
   LZ4 payloads. The GL platform payload is HLSLcc-translated **GLSL text**; a sample of it is kept
   under `shaders/glsl/` (see `shaders/README.md`).

## Build

```
dotnet build VolClouds.sln -c Release
```

- `net481`, `LangVersion 12` (syntax only; the emitted IL is what KSP 1.12.5 / Mono 5.x can load).
- KSP reference assemblies default to `E:\MangoTech\KSP_dlls`; override with `-p:KSPDlls=<dir>`.
- No NuGet packages, no network access needed.
- Current state: all 11 projects compile with 0 errors / 0 warnings. Not yet verified in game.

## Layout

```
src/Atmosphere          raymarched volume pipeline (CloudsRaymarchedVolume,
                        DeferredRaymarchedVolumetricCloudsRenderer, LightVolume, VolumeManager,
                        Clouds2D, Droplets, Lightning, ParticleField, WetSurfaces, Noise, ...)
src/Utils               config/serialisation/GUI/texture helpers shared by all assemblies
src/ShaderLoader        loads eveshaders.bundle at runtime, exposes FindShader/FindComputeShader
src/EVEManager          cfg-driven manager base classes, global EVE addon
src/PQSManager, Terrain, CityLights, CelestialShadows, TextureConfig, PartFX, _BuildManager
shaders/glsl            extracted GLSL for the volumetric shaders + compute kernels (reference)
docs/PIPELINE.md        pass order / render targets recovered from the C#
tools/metadump          prints fully-qualified type names from a managed assembly
tools/scaffold.py       regenerates csproj files + copies sources from the decompile output
```

## Known deviations from the original source

- Naming: public API names are original (`apidump` diff vs the shipped DLLs is empty apart from
  compiler attributes); locals/parameters were renamed for readability per `docs/STYLE.md`, and the
  ones read by reflection or passed as named arguments kept their original names.
- Comments from the original source are gone (they are not in the binaries); the comments here are
  new, written against the decompiled logic and `docs/PIPELINE.md`.
- Shaders: `shaders/glsl/` is the HLSLcc output extracted from the bundles, `shaders/hlsl/` is the
  hand-translated, readable HLSL (same uniforms, same branches; not compiled, no fxc/dxc here).
- `TriangleIndices` / other types use primary constructors, hence `LangVersion 12`.
- `KSPAddon` attributes were re-emitted by hand from the raw custom-attribute blobs
  (`Instantly,true` / `EveryScene,false`).

## Status / next steps

- [x] all assemblies decompile and build
- [x] readable pass over every C# file (comments + local names) and HLSL port of all 19 shaders
- [ ] port the volumetric part into Helmholtz (cloud march, light volume, temporal reprojection)
- [ ] Scatterer's `RaymarchedGodraysRenderer` integration

The recovered code and shaders are blackrack's work, redistributed here only as decompiled source
for personal research; do not ship the binaries or the original assets.
