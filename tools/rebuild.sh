#!/usr/bin/env bash
# Full rebuild chain (the handover notes §2) in one shot:
#   C# -> HLSL flatten -> offline HLSL check -> Unity batch bundle -> package.
#
# Unity 2019.4.18f1 is looked up here, in this order:
#   1. $UNITY_EXE
#   2. the paths this project has actually lived at
#   3. the registry-free default install of Unity Hub on Windows
# The first candidate that exists wins; the resolved path is printed.
#
# Usage: bash tools/rebuild.sh [--skip-unity] [--skip-pack]
set -e
cd "$(dirname "$0")/.."

SKIP_UNITY=0
SKIP_PACK=0
for arg in "$@"; do
  case "$arg" in
    --skip-unity) SKIP_UNITY=1 ;;
    --skip-pack) SKIP_PACK=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

find_unity() {
  if [ -n "$UNITY_EXE" ] && [ -x "$UNITY_EXE" ]; then echo "$UNITY_EXE"; return; fi
  local candidates=(
    "E:/unity/editor/2019.4.18f1/Editor/Unity.exe"
    "D:/E/unity/editor/2019.4.18f1/Editor/Unity.exe"
    "C:/Program Files/Unity/Hub/Editor/2019.4.18f1/Editor/Unity.exe"
    "C:/Program Files/Unity/Editor/Unity.exe"
  )
  local c
  for c in "${candidates[@]}"; do
    if [ -x "$c" ]; then echo "$c"; return; fi
  done
}

echo "== 1/5 C# =="
dotnet build VolClouds.sln -c Release 2>&1 | tail -4

echo "== 2/5 flatten HLSL for Unity (generated files under EVE-Tweak/Assets/Shaders/) =="
python tools/flatten_cbuffer.py

echo "== 3/5 offline HLSL check =="
python tools/hlsl_check_unity.py EVE-Tweak/Assets/Shaders/RaymarchCloud.hlsl \
  VS_RaymarchCloud PS_RaymarchCloud
python tools/hlsl_check_unity.py EVE-Tweak/Assets/Shaders/ReconstructRaymarchedClouds.hlsl \
  VS_ReconstructRaymarchedClouds PS_ReconstructRaymarchedClouds
# The authored shaders (ground shadow, sky optics) are not ported code, but they still have to
# compile without Unity before the batch build, for the same reason.
python tools/hlsl_check_unity.py EVE-Tweak/Assets/Shaders/RaymarchedCloudShadow.hlsl \
  VS_ShadowMask PS_ShadowMask
python tools/hlsl_check_unity.py EVE-Tweak/Assets/Shaders/RaymarchedCloudShadow.hlsl \
  VS_ShadowDarken PS_ShadowDarken
python tools/hlsl_check_unity.py EVE-Tweak/Assets/Shaders/SkyOptics.hlsl \
  VS_SkyOptics PS_SkyOptics

# Uniform audit (docs/UNIFORMS.md): reports names the C# writes that no shader declares. It is
# informational -- a dead name can be a deliberate port gap -- but printing the count every build is
# what keeps a rename from turning a feature off silently. Needs the tweak bundle, so after step 4 it
# sees this build's bundle rather than the previous one.
audit_uniforms() {
  local bundle="BuildOut/GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle"
  if [ ! -f "$bundle" ]; then
    echo "   (no tweak bundle yet - skipping uniform audit)"
    return
  fi
  local counts
  counts=$(python tools/audit_uniforms.py "$bundle" \
    --include CloudsRaymarchedVolume.cs,DeferredRaymarchedVolumetricCloudsRenderer.cs \
    --quiet-ok 2>&1 | awk '/^== /{print}' )
  echo "$counts" | sed 's/^/   /'
}

if [ "$SKIP_UNITY" -eq 0 ]; then
  echo "== 4/5 Unity batch bundle =="
  UNITY="$(find_unity)"
  if [ -z "$UNITY" ]; then
    echo "!! Unity 2019.4.18f1 not found - set UNITY_EXE or pass --skip-unity" >&2
    exit 1
  fi
  echo "   using $UNITY"
  "$UNITY" -batchmode -quit \
    -projectPath "$(pwd)/EVE-Tweak" \
    -executeMethod TweakBundleBuilder.CIBuild \
    -logFile "$(pwd)/EVE-Tweak/build.log" || true
  # Unity always exits 0; the log is the only verdict (the handover notes §4.9).
  errors=$(grep -c "Shader error" EVE-Tweak/build.log || true)
  echo "   shader errors: $errors"
  if [ "$errors" != "0" ]; then
    grep -n "Shader error" EVE-Tweak/build.log | head -20 >&2
    exit 1
  fi
else
  echo "== 4/5 Unity batch bundle - skipped =="
fi

echo "== uniform audit (informational, docs/UNIFORMS.md) =="
audit_uniforms


if [ "$SKIP_PACK" -eq 0 ]; then
  echo "== 5/5 package =="
  bash tools/pack-buildout.sh | tail -6
else
  echo "== 5/5 package - skipped =="
fi
