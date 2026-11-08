"""Dump shader reflection (uniform names + keyword variants) from a UnityFS bundle.

Answers the open questions in the handover notes §7.2: which uniform names the ORIGINAL D3D
variants actually declare for a given shader, which keyword sets exist, and how many
textures each variant binds.

Requires UnityPy (`pip install UnityPy`).

Usage:
  python tools/shader_reflection.py <bundle> [--shader EVE/RaymarchCloud] [--names-only]
  python tools/shader_reflection.py <bundle> --search unity_MatrixVP
"""
import argparse


def prog_of(pass_dict, slot):
    for key in (slot, slot[0].lower() + slot[1:]):
        v = pass_dict.get(key)
        if v is not None:
            return v
    return None


def read_ptr(ptr):
    if ptr is None:
        return None
    if hasattr(ptr, "read"):
        try:
            return ptr.read_typetree()
        except Exception:
            try:
                return ptr.read().__dict__
            except Exception:
                return None
    return ptr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("--shader", default=None)
    ap.add_argument("--names-only", action="store_true")
    ap.add_argument("--search", default=None, help="print only uniform names containing this substring")
    args = ap.parse_args()

    import UnityPy
    env = UnityPy.load(args.bundle)

    for obj in env.objects:
        if obj.type.name not in ("Shader", "ComputeShader"):
            continue
        d = obj.read_typetree()
        if obj.type.name == "ComputeShader":
            name = d.get("m_Name") or "<compute>"
            if args.shader and args.shader != name:
                continue
            print("=" * 90)
            print("ComputeShader: %r path_id=%d" % (name, obj.path_id))
            for kern in d.get("m_Kernels") or []:
                print("  kernel %r" % kern.get("m_Name"))
                for u in kern.get("m_CommonParameters") or []:
                    print("    %-46s type=%-6s array=%s" % (u.get("m_Name"), u.get("m_Type"), u.get("m_ArraySize")))
            continue

        pf = d.get("m_ParsedForm") or {}
        name = pf.get("m_Name") or "<unnamed>"
        if args.shader and name != args.shader:
            continue
        if args.names_only:
            print(name)
            continue
        print("=" * 90)
        print("Shader: %r path_id=%d" % (name, obj.path_id))
        pi = pf.get("m_PropInfo") or {}
        props = [p.get("m_Name") for p in (pi.get("m_Props") or [])]
        print("  properties(%d): %s" % (len(props), ", ".join(props)))
        print("  dependencies: %s  fallback: %r" % (pf.get("m_Dependencies"), pf.get("m_FallbackName")))
        for si, sub in enumerate(pf.get("m_SubShaders") or []):
            passes = sub.get("m_Passes") or []
            print("  [sub %d] passes=%d tags=%s" % (si, len(passes), sub.get("m_Tags")))
            for pidx, p in enumerate(passes):
                kws = p.get("m_NameIndices")
                if isinstance(kws, list):
                    kw = [k[0] if isinstance(k, (list, tuple)) else k.get("m_Name") if isinstance(k, dict) else k for k in kws]
                else:
                    kw = kws
                print("    [pass %d] name=%r mask=%s keywords=%s" % (pidx, p.get("m_Name"), p.get("m_ProgramMask"), kw))
                for slot in ("m_ProgVertex", "m_ProgFragment"):
                    prog = read_ptr(prog_of(p, slot))
                    if not prog:
                        continue
                    common = prog.get("m_CommonParameters") or []
                    names = [u.get("m_Name") for u in common]
                    if args.search:
                        names = [n for n in names if n and args.search in n]
                    print("      %s uniforms(%d):" % (slot, len(common)))
                    for u in common:
                        if args.search and args.search not in (u.get("m_Name") or ""):
                            continue
                        print("        %-48s type=%-6s array=%s" % (u.get("m_Name"), u.get("m_Type"), u.get("m_ArraySize")))


if __name__ == "__main__":
    main()
