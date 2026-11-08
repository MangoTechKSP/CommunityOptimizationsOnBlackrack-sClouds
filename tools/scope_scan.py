"""Find HLSL locals declared in a nested block but read from an outer block.

The readability port declared every SSA temporary at its first assignment, so a
temporary that the GLSL pre-declared and filled from an if/else pair now only
exists inside the first branch. This lists every such identifier at once instead
of one per compiler run.

Usage: python tools/scope_scan.py <file.hlsl>
"""
import re
import sys

TYPES = r"(?:const\s+)?(float[234]?|int[234]?|uint[234]?|bool[234]?|float[234]x[234]|half[234]?)"
DECL = re.compile(r"^\s*" + TYPES + r"\s+([A-Za-z_]\w*)\s*(?:=|;)")


def strip_comments(lines):
    out = []
    in_block = False
    for line in lines:
        s = line
        res = []
        i = 0
        while i < len(s):
            if in_block:
                if s.startswith("*/", i):
                    in_block = False
                    i += 2
                else:
                    i += 1
            elif s.startswith("//", i):
                break
            elif s.startswith("/*", i):
                in_block = True
                i += 2
            else:
                res.append(s[i])
                i += 1
        out.append("".join(res))
    return out


def main():
    path = sys.argv[1]
    raw = open(path, encoding="utf-8-sig").read().split("\n")
    code = strip_comments(raw)

    depth = 0
    decls = {}      # name -> (depth at declaration, line number)
    reported = set()
    for idx, line in enumerate(code):
        # close braces first so "} else {" ends at the outer depth
        if line.lstrip().startswith("}"):
            depth -= 1
        m = DECL.match(line)
        if m and depth > 0:
            name = m.group(2)
            # only record the first declaration we see for a name
            decls.setdefault(name, (depth, idx + 1))
        for name, (d, line_no) in decls.items():
            if name in reported or idx + 1 <= line_no:
                continue
            if re.search(r"\b" + re.escape(name) + r"\b", line):
                if depth < d:
                    reported.add(name)
                    print(f"{name:28} declared line {line_no} (depth {d}), first seen at line {idx+1} (depth {depth})")
        depth += line.count("{") - line.count("}") + (1 if line.lstrip().startswith("}") else 0)
    print(f"\n{len(reported)} identifier(s) escape their declaring block")


if __name__ == "__main__":
    main()
