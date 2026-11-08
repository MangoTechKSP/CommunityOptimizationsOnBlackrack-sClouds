"""Cross-check the uniform names the C# sets against the names the shipped shaders declare.

Motivation: a `material.SetFloat("typo", x)` is a silent no-op in Unity -- no warning, no
exception, the uniform just stays at whatever the shader initialised it to. That is exactly
how the light-volume path ended up baking textures nothing read (see docs/LIGHT-VOLUME.md),
and how a shader that is not in the bundle (docs/DIAGNOSTICS.md 4.5) can look wired up while
doing nothing. This tool makes that class of bug mechanical to find.

It extracts every uniform name a bundle's shaders declare (property block + both program
signatures + the keyword table), then greps the C# for

  * `SetFloat("name", ...)` and the other Material/CommandBuffer setters by literal name
  * `Shader.PropertyToID("name")` / `ShaderProperties.x = Shader.PropertyToID("name")`
  * `shader.SetGlobalFloat("name", ...)` etc.

and reports every name the C# writes that no shader in the bundle declares. A name can be
legitimately absent (it may target a stock KSP/Unity shader, or a different bundle), so the
output is a list to triage, not an error list -- but every remaining row should have a reason.

Requires UnityPy (`pip install UnityPy`).

Usage:
  python tools/audit_uniforms.py EVE-Tweak/BuildOut/.../eveshaders_tweak.bundle
  python tools/audit_uniforms.py work/eveshaders_orig.bundle --src src --md docs/UNIFORMS.md
  python tools/audit_uniforms.py <bundle> --name EVEEdgeWisp      # where is one name used?
"""
import argparse
import os
import re
import sys

SETTERS = (
    "SetFloat", "SetVector", "SetColor", "SetInt", "SetMatrix", "SetTexture", "SetBuffer",
    "SetFloatArray", "SetVectorArray", "SetColorArray", "SetMatrixArray", "SetTextureArray",
    "SetGlobalFloat", "SetGlobalVector", "SetGlobalColor", "SetGlobalInt", "SetGlobalMatrix",
    "SetGlobalTexture", "SetGlobalFloatArray", "SetGlobalVectorArray", "SetGlobalBuffer",
)
# `X.SetFloat("name", ...)` / `shader.SetGlobalTexture("name", ...)`
RE_SETTER = re.compile(
    r"\.(?:%s)\(\s*\"([^\"]+)\"" % "|".join(SETTERS)
)
# `Shader.PropertyToID("name")`
RE_PROPERTY_ID = re.compile(r"Shader\.PropertyToID\(\s*\"([^\"]+)\"")
# `private static int cloudFade = Shader.PropertyToID("cloudFade");` -> capture the field name too
RE_FIELD_PROPERTY_ID = re.compile(
    r"(?:(?:private|public|internal|protected|static|readonly|\s)+)?\bint\s+(\w+)\s*=\s*Shader\.PropertyToID\(\s*\"([^\"]+)\""
)


def _program_uniform_names(prog, sub_depth=0):
    """Every uniform name a serialized program declares.

    Unity 2019 stores one `m_SubPrograms` entry per hardware tier; the real names live in
    `m_VectorParams`/`m_MatrixParams`/`m_TextureParams`/`m_BufferParams`/`m_UAVParams` (and
    occasionally `m_ConstantBuffers[*].m_ConstantParams`), NOT in `m_CommonParameters` -- that
    one is usually empty on D3D variants, which is why an audit that only reads it reports
    working uniforms as missing.
    """
    if prog is None or sub_depth > 2:
        return
    try:
        prog = prog.read_typetree() if hasattr(prog, "read") else prog
    except Exception:
        return
    if not isinstance(prog, dict):
        return
    for u in prog.get("m_CommonParameters") or []:
        yield u.get("m_Name")
    for key in ("m_VectorParams", "m_MatrixParams", "m_TextureParams", "m_BufferParams",
                "m_UAVParams"):
        for u in prog.get(key) or []:
            yield u.get("m_Name")
    for cb in prog.get("m_ConstantBuffers") or []:
        for u in (cb or {}).get("m_ConstantParams") or []:
            yield u.get("m_Name")
    for sub in prog.get("m_SubPrograms") or []:
        for name in _program_uniform_names(sub, sub_depth + 1):
            yield name


def declared_names(bundle_path):
    """name -> set of shader names that declare it."""
    import UnityPy

    env = UnityPy.load(bundle_path)
    names = {}

    def add(name, owner):
        if not name:
            return
        names.setdefault(name, set()).add(owner)

    for obj in env.objects:
        if obj.type.name == "ComputeShader":
            d = obj.read_typetree()
            owner = "compute:" + (d.get("m_Name") or "<unnamed>")
            for kern in d.get("m_Kernels") or []:
                for u in kern.get("m_CommonParameters") or []:
                    add(u.get("m_Name"), owner)
            continue
        if obj.type.name != "Shader":
            continue
        pf = obj.read_typetree().get("m_ParsedForm") or {}
        owner = pf.get("m_Name") or "<unnamed>"
        prop_info = pf.get("m_PropInfo") or {}
        for p in prop_info.get("m_Props") or []:
            add(p.get("m_Name"), owner)
        for sub in pf.get("m_SubShaders") or []:
            for p in sub.get("m_Passes") or []:
                name_indices = p.get("m_NameIndices")
                if isinstance(name_indices, list):
                    for entry in name_indices:
                        if isinstance(entry, (list, tuple)) and entry:
                            add(entry[0], owner)
                        elif isinstance(entry, dict):
                            add(entry.get("m_Name"), owner)
                for slot in ("m_ProgVertex", "m_ProgFragment", "m_ProgGeometry", "m_ProgHull",
                             "m_ProgDomain"):
                    for key in (slot, slot[0].lower() + slot[1:]):
                        prog = p.get(key)
                        break
                    else:
                        continue
                    for name in _program_uniform_names(prog):
                        add(name, owner)
    return names


def scan_sources(src_root):
    """list of (name, kind, file, line) for every C# site that names a uniform."""
    sites = []
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [d for d in dirnames if d not in ("obj", "bin", ".git")]
        for fn in filenames:
            if not fn.endswith(".cs"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                fh = open(path, encoding="utf-8", errors="replace")
            except OSError as exc:
                print("skipping %s (%s)" % (path, exc), file=sys.stderr)
                continue
            with fh:
                for lineno, line in enumerate(fh, 1):
                    stripped = line.strip()
                    if stripped.startswith("//"):
                        continue
                    for m in RE_SETTER.finditer(line):
                        sites.append((m.group(1), "setter", path, lineno))
                    for m in RE_FIELD_PROPERTY_ID.finditer(line):
                        sites.append((m.group(2), "id-field:" + m.group(1), path, lineno))
                    if not RE_FIELD_PROPERTY_ID.search(line):
                        for m in RE_PROPERTY_ID.finditer(line):
                            sites.append((m.group(1), "property-id", path, lineno))
    return sites


def scan_shader_sources(roots):
    """identifier -> set of files, from shader source text (hlsl/glsl/cginc).

    Needed because D3D strips uniforms the compiled variant does not reference: a name that
    is missing from the bundle's tables may still be a live uniform of the shader source, and
    a name that is missing everywhere is a genuine dead write.
    """
    ident = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    found = {}
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            for fn in filenames:
                if not fn.endswith((".hlsl", ".glsl", ".cginc", ".shader", ".compute")):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                except OSError:
                    continue
                for name in set(ident.findall(text)):
                    found.setdefault(name, set()).add(path)
    return found


def rel(path, root):
    try:
        return os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:
        return path


def matches(path, patterns):
    """True when any substring pattern appears in the (slash-normalised) path.

    An empty/absent pattern list matches nothing, so callers can write
    `matches(p, include) and not matches(p, exclude)`.
    """
    if not patterns:
        return False
    p = path.replace(os.sep, "/")
    return any(pat in p for pat in patterns)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", help="eveshaders bundle (tweak or stock)")
    ap.add_argument("--src", default="src", help="C# root to scan (default: src)")
    ap.add_argument("--name", default=None, help="only report this uniform")
    ap.add_argument("--only-shaders", default=None,
                    help="comma separated shader names; only their declarations count as valid "
                         "(e.g. EVE/RaymarchCloud,EVE/ReconstructRaymarchedClouds)")
    ap.add_argument("--include", default=None,
                    help="comma separated path substrings; only C# files matching one are scanned")
    ap.add_argument("--exclude", default=None,
                    help="comma separated path substrings; C# files matching one are skipped")
    ap.add_argument("--shader-sources", default="shaders/hlsl,shaders/glsl",
                    help="comma separated shader source roots used to tell 'stripped from the "
                         "compiled variant' from 'dead everywhere' (default: shaders/hlsl,shaders/glsl)")
    ap.add_argument("--md", default=None, help="write a markdown table here")
    ap.add_argument("--quiet-ok", action="store_true",
                    help="do not list names that are declared (only the misses and a count)")
    args = ap.parse_args()

    if not os.path.isfile(args.bundle):
        sys.exit("no such bundle: %s" % args.bundle)
    if not os.path.isdir(args.src):
        sys.exit("no such source root: %s" % args.src)

    declared = declared_names(args.bundle)
    if args.only_shaders:
        wanted = [s.strip() for s in args.only_shaders.split(",") if s.strip()]
        declared = {n: o for n, o in declared.items() if o & set(wanted)}

    splits = lambda s: [p.strip() for p in s.split(",") if p.strip()] if s else None
    includes, excludes = splits(args.include), splits(args.exclude)
    sites = [s for s in scan_sources(args.src)
             if (not includes or matches(s[2], includes)) and not matches(s[2], excludes)]
    if args.name:
        sites = [s for s in sites if s[0] == args.name]

    used = {}
    for name, kind, path, lineno in sites:
        used.setdefault(name, []).append((kind, path, lineno))

    shader_sources = scan_shader_sources(splits(args.shader_sources) or [])
    declared_here = sorted(n for n in used if n in declared)
    stripped = sorted(n for n in used if n not in declared and n in shader_sources)
    dead = sorted(n for n in used if n not in declared and n not in shader_sources)

    print("bundle:   %s" % args.bundle)
    print("declared: %d uniform names across %d shaders/objects" %
          (len(declared), len({o for owners in declared.values() for o in owners})))
    print("C# sites: %d names used at %d call sites" %
          (len(used), sum(len(v) for v in used.values())))
    print("")

    if not args.quiet_ok:
        print("== declared by the compiled variant (C# name -> shaders) ==")
        for name in declared_here:
            owners = ", ".join(sorted(declared[name]))
            print("  %-46s %s" % (name, owners))
        print("")

    print("== in shader source but stripped from the compiled variant (%d) ==" % len(stripped))
    print("   (harmless: the variant does not reference it, so the write is a no-op there)")
    for name in stripped:
        print("  %s" % name)
    print("")

    print("== DEAD: no shader in this bundle and no shader source mentions it (%d) ==" % len(dead))
    for name in dead:
        print("  %s" % name)
        for kind, path, lineno in used[name]:
            print("      %-22s %s:%d" % (kind, rel(path, os.getcwd()), lineno))
    if not dead:
        print("  (none -- every name the C# writes exists as a shader source declaration)")

    if args.md:
        lines = ["| uniform | used at | declared by |", "| --- | --- | --- |"]
        for name in sorted(used):
            where = "<br>".join("%s:%d" % (rel(p, os.getcwd()), ln) for _, p, ln in used[name])
            owners = "<br>".join(sorted(declared[name])) if name in declared else "**none**"
            lines.append("| `%s` | %s | %s |" % (name, where, owners))
        with open(args.md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        print("\nwrote %s" % args.md)


if __name__ == "__main__":
    main()
