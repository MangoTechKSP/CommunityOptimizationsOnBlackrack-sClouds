"""Dump a UnityFS bundle (KSP eveshaders.bundle) with UnityPy.

Replaces the old hand-rolled unpack_bundle.py (broken on LZ4/LZMA blocks).
Requires: pip install UnityPy

Usage:
  python tools/dump_bundle.py <bundle> --list
  python tools/dump_bundle.py <bundle> --shaders        # shader reflection: names, keywords, uniforms
  python tools/dump_bundle.py <bundle> --textures       # sampler-relevant texture settings (wrap/filter/format)
  python tools/dump_bundle.py <bundle> --raw <outdir>   # extract every TextAsset / raw blob
"""
import argparse
import os
import sys


def short(v, n=110):
    s = str(v)
    return s if len(s) <= n else s[:n] + "..."


def iter_objects(env):
    for obj in env.objects:
        yield obj


def get_type_name(obj):
    try:
        return obj.type.name
    except Exception:
        return str(obj.type)


def as_dict(obj):
    """Best-effort flat dict of a parsed object."""
    try:
        data = obj.read_typetree()
        return data
    except Exception:
        try:
            return obj.read().__dict__
        except Exception:
            return None


def list_objects(env):
    rows = []
    for obj in env.objects:
        name = ""
        try:
            d = obj.read_typetree()
            name = d.get("m_Name", "") or d.get("m_Name", "")
        except Exception:
            pass
        rows.append((get_type_name(obj), obj.path_id, name))
    for t, pid, name in sorted(rows):
        print("%-22s path_id=%-12d %s" % (t, pid, name))
    print("total objects: %d" % len(rows))


def dump_shaders(env):
    for obj in env.objects:
        if get_type_name(obj) != "Shader":
            continue
        d = as_dict(obj)
        if not d:
            continue
        print("=" * 100)
        print("Shader: %r  path_id=%d  parsed=%s" % (d.get("m_Name"), obj.path_id, d.get("m_ParsedForm") is not None))
        pf = d.get("m_ParsedForm") or {}
        if not pf:
            print("  (no parsed form; keys: %s)" % ", ".join(list(d.keys())[:12]))
            continue
        print("  root_signature: %s" % short(pf.get("m_RootSignature")))
        pi = pf.get("m_PropInfo") or {}
        props = pi.get("m_Props") or []
        print("  properties (%d):" % len(props))
        for p in props:
            print("    %-40s type=%-10s flags=%s" % (p.get("m_Name"), p.get("m_Type"), p.get("m_Flags")))
        subs = pf.get("m_SubShaders") or []
        print("  subshaders: %d" % len(subs))
        for si, sub in enumerate(subs):
            passes = sub.get("m_Passes") or []
            print("   [sub %d] tags=%s passes=%d" % (si, short(sub.get("m_Tags")), len(passes)))
            for pi_, p in enumerate(passes):
                print("     [pass %d] name=%r progMask=%s" % (pi_, p.get("m_Name"), p.get("m_ProgramMask")))
                print("        keywords: %s" % short(p.get("m_KeywordNames"), 400))
                print("        state: %s" % short(p.get("m_State"), 300))
                for slot in ("m_ProgVertex", "m_ProgFragment"):
                    ptr = p.get(slot)
                    if not ptr:
                        continue
                    prog = ptr.read() if hasattr(ptr, "read") else ptr
                    try:
                        pdd = prog.read_typetree()
                    except Exception:
                        pdd = as_dict(prog) or {}
                    common = pdd.get("m_CommonParameters") or []
                    print("        %s uniforms (%d):" % (slot, len(common)))
                    for u in common:
                        print("          %-46s type=%-6s array=%s" % (u.get("m_Name"), u.get("m_Type"), u.get("m_ArraySize")))


def dump_textures(env):
    wrap = {0: "Repeat", 1: "Clamp", 2: "Mirror", 3: "MirrorOnce"}
    filt = {0: "Point", 1: "Bilinear", 2: "Trilinear"}
    for obj in env.objects:
        t = get_type_name(obj)
        if t not in ("Texture2D", "Cubemap", "Texture2DArray", "Texture3D"):
            continue
        d = as_dict(obj)
        if not d:
            continue
        ts = d.get("m_TextureSettings") or {}
        print("%-12s %-30s %4dx%-4d fmt=%-3s mips=%-3s wrap=%-9s/%-9s/%-9s filter=%-9s aniso=%s" % (
            t, d.get("m_Name"), d.get("m_Width"), d.get("m_Height"), d.get("m_TextureFormat"),
            d.get("m_MipCount"),
            wrap.get(ts.get("m_WrapU"), ts.get("m_WrapU")),
            wrap.get(ts.get("m_WrapV"), ts.get("m_WrapV")),
            wrap.get(ts.get("m_WrapW"), ts.get("m_WrapW")),
            filt.get(ts.get("m_FilterMode"), ts.get("m_FilterMode")),
            ts.get("m_Aniso")))


def dump_raw(env, outdir):
    os.makedirs(outdir, exist_ok=True)
    for obj in env.objects:
        t = get_type_name(obj)
        name = ""
        try:
            name = (obj.read_typetree() or {}).get("m_Name", "")
        except Exception:
            pass
        if t in ("TextAsset", "Shader", "Material"):
            try:
                data = obj.get_raw_data() if hasattr(obj, "get_raw_data") else None
            except Exception:
                data = None
            if data:
                safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in (name or str(obj.path_id)))
                path = os.path.join(outdir, "%s_%d_%s.bin" % (t, obj.path_id, safe))
                with open(path, "wb") as f:
                    f.write(data)
                print("wrote %s (%d B)" % (path, len(data)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--shaders", action="store_true")
    ap.add_argument("--textures", action="store_true")
    ap.add_argument("--raw", default=None)
    args = ap.parse_args()

    import UnityPy
    # Some bundles need the compressed-file fallback disabled; default is fine.
    env = UnityPy.load(args.bundle)
    print("loaded %s: %d files, %d objects" % (args.bundle, len(env.files), len(env.objects)))
    for f in env.files:
        print("  file: %s (%d B)" % (f, len(env.files[f].reader.bytes) if hasattr(env.files[f], "reader") else 0))
    if args.list:
        list_objects(env)
    if args.shaders:
        dump_shaders(env)
    if args.textures:
        dump_textures(env)
    if args.raw:
        dump_raw(env, args.raw)


if __name__ == "__main__":
    main()
