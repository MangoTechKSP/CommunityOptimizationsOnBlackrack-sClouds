#!/usr/bin/env bash
# Rebuild everything and produce a deployable package:
#   BuildOut/                -> original mod layout (README.md:13)
#   dist/VolClouds-tweak.zip -> drop-in for the KSP root (GameData/ + docs)
#
# The shader bundle itself is built by Unity (see BUILD-NOTES.md 7.4); this
# script only copies it and warns when it is older than the HLSL sources.
set -e
cd "$(dirname "$0")/.."

echo "== 1/5 build C# =="
dotnet build VolClouds.sln -c Release | tail -4

EVE=BuildOut/GameData/EnvironmentalVisualEnhancements/Plugins
SCA=BuildOut/GameData/Scatterer/Plugins
mkdir -p "$EVE" "$SCA" BuildOut/shaders

echo "== 2/5 copy assemblies =="
for p in Atmosphere CelestialShadows CityLights EVEManager PQSManager PartFX \
         ShaderLoader Terrain TextureConfig Utils _BuildManager; do
  cp "src/$p/bin/Release/$p.dll" "$EVE/"
done
cp src/Scatterer/bin/Release/Scatterer.dll "$SCA/"

echo "== 3/5 copy shader bundle =="
BUNDLE=EVE-Tweak/BuildOut/eveshaders_tweak.bundle
if [ -f "$BUNDLE" ]; then
  for s in shaders/hlsl/RaymarchCloud.hlsl shaders/hlsl/ReconstructRaymarchedClouds.hlsl; do
    if [ "$s" -nt "$BUNDLE" ]; then
      echo "!! WARNING: $s is newer than the bundle - rerun the Unity batch build" >&2
    fi
  done
  cp "$BUNDLE" BuildOut/GameData/EnvironmentalVisualEnhancements/
  MANIFEST="$BUNDLE.manifest"
  if [ -f "$MANIFEST" ]; then
    echo "   bundle assets: $(grep -c '^  Assets/' "$MANIFEST" || true)"
    sed -n 's/^- Assets\/Shaders\/\(.*\.shader\)$/   contains \1/p' "$MANIFEST"
  fi
else
  echo "!! no bundle at $BUNDLE - the package will not override any shader" >&2
fi

echo "== 4/5 copy shader sources (reference only, KSP does not read them) =="
cp EVE-Tweak/Assets/Shaders/RaymarchCloud.hlsl \
   EVE-Tweak/Assets/Shaders/ReconstructRaymarchedClouds.hlsl \
   EVE-Tweak/Assets/Shaders/RaymarchedCloudShadow.hlsl \
   EVE-Tweak/Assets/Shaders/SkyOptics.hlsl \
   EVE-Tweak/Assets/Shaders/EVE_RaymarchCloud.shader \
   EVE-Tweak/Assets/Shaders/EVE_ReconstructRaymarchedClouds.shader \
   EVE-Tweak/Assets/Shaders/EVE_RaymarchedCloudShadow.shader \
   EVE-Tweak/Assets/Shaders/EVE_SkyOptics.shader \
   BuildOut/shaders/
git diff -- shaders/hlsl/ > BuildOut/shaders/shaders.patch || true

echo "== 5/5 zip =="
mkdir -p dist
# A previously shipped zip can be held open by Explorer (or by the harness that showed it to
# the user) and Windows refuses to replace a file with an open handle. Fall back to a
# versioned name instead of failing the build: the contents are identical, only the name moves.
OUT=dist/VolClouds-tweak.zip
if ! rm -f "$OUT" 2>/dev/null; then
  VERSION=$(sed -n 's/^## \[\([0-9.]*\)\].*/\1/p' CHANGELOG.md | head -1)
  OUT="dist/VolClouds-tweak-${VERSION:-$(date +%Y%m%d-%H%M)}.zip"
  echo "   !! dist/VolClouds-tweak.zip is locked by another process; writing $OUT instead" >&2
  # The versioned name can be locked too (zip viewer / Explorer preview holding it open), in which
  # case a timestamped name is the only thing that can be written. Never fail the pack over a name.
  if [ -e "$OUT" ] && ! rm -f "$OUT" 2>/dev/null; then
    OUT="dist/VolClouds-tweak-$(date +%Y%m%d-%H%M%S).zip"
    echo "   !! $OUT was locked too; writing a timestamped archive instead" >&2
    export VOLCLOUDS_ZIP="$OUT"
  fi
fi
export VOLCLOUDS_ZIP="$OUT"
python - <<'EOF'
import os, zipfile
root = "BuildOut"
out = os.environ.get("VOLCLOUDS_ZIP") or "dist/VolClouds-tweak.zip"
docs = [
    ("README-OPTIMIZATIONS.md", "README.md"),
    ("CHANGELOG.md", "CHANGELOG.md"),
    (os.path.join(root, "BUILD-NOTES.md"), "BUILD-NOTES.md"),
]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for base, _, files in os.walk(os.path.join(root, "GameData")):
        for f in files:
            full = os.path.join(base, f)
            z.write(full, os.path.relpath(full, root))
    for src, arc in docs:
        z.write(src, arc)
print("wrote", out, os.path.getsize(out), "bytes")
EOF

unzip -l "$OUT" | tail -24
