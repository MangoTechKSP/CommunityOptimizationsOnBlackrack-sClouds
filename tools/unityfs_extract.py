"""Decompress a UnityFS bundle into one flat blob (all SerializedFiles concatenated).

LZ4/LZMA block support via the `lz4` + stdlib `lzma` modules (pip install lz4).

Usage:
  python tools/unityfs_extract.py <bundle> <out.bin> [--strings out.txt]
"""
import struct
import sys


def read_cstr(buf, off):
    end = buf.index(b"\x00", off)
    return buf[off:end].decode("utf-8", "replace"), end + 1


def decompress(kind, data, out_size):
    # UnityFS block compression: 0=none 1=LZMA 2=LZ4 3=LZ4HC
    if kind == 0:
        return data
    if kind == 1:
        import lzma
        # Unity stores the LZMA data as a raw stream preceded by the 5-byte
        # props + 8-byte size header only sometimes; try both layouts.
        for fmt in (lzma.FORMAT_ALONE,):
            try:
                return lzma.decompress(data, format=fmt)
            except Exception:
                pass
        # props (5 bytes, first byte = properties) + raw stream
        props = data[0]
        lc = props % 9
        rest = props // 9
        lp = rest % 5
        pb = rest // 5
        dict_size = struct.unpack_from("<I", data, 1)[0]
        filt = [{"id": lzma.FILTER_LZMA1, "lc": lc, "lp": lp, "pb": pb,
                 "dict_size": max(dict_size, 4096)}]
        dec = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=filt)
        return dec.decompress(data[5:], out_size)
    if kind in (2, 3):
        import lz4.block
        return lz4.block.decompress(data, uncompressed_size=out_size)
    raise ValueError("unsupported block compression %d" % kind)


def extract(path):
    buf = open(path, "rb").read()
    off = 0
    sig, off = read_cstr(buf, off)
    assert sig == "UnityFS", sig
    version = struct.unpack_from(">I", buf, off)[0]; off += 4
    unity_version, off = read_cstr(buf, off)
    unity_rev, off = read_cstr(buf, off)
    total_size = struct.unpack_from(">q", buf, off)[0]; off += 8
    cinfo_size = struct.unpack_from(">I", buf, off)[0]; off += 4
    uinfo_size = struct.unpack_from(">I", buf, off)[0]; off += 4
    flags = struct.unpack_from(">I", buf, off)[0]; off += 4
    print("UnityFS v%d unity=%s rev=%s size=%d flags=%#x cinfo=%d uinfo=%d"
          % (version, unity_version, unity_rev, total_size, flags, cinfo_size, uinfo_size))

    info_raw = buf[off:off + cinfo_size]; off += cinfo_size
    # flags bit 0x40 = blocksInfo is compressed (block flags bits 0x3f = compression type)
    block_info_comp = flags & 0x3F
    if flags & 0x40:
        info = decompress(block_info_comp, info_raw, uinfo_size)
    else:
        info = info_raw

    p = 16  # hash
    block_count = struct.unpack_from(">i", info, p)[0]; p += 4
    blocks = []
    for _ in range(block_count):
        u, c, f = struct.unpack_from(">IIH", info, p); p += 10
        blocks.append((u, c, f & 0x3F))
    nodes = 0
    if flags & 0x200:
        nodes = struct.unpack_from(">i", info, p)[0]; p += 4
        for _ in range(nodes):
            _, _ = struct.unpack_from(">qq", info, p); p += 16
            _, p = read_cstr(info, p)
    print("blocks=%d nodes=%d block_info_comp=%d" % (len(blocks), nodes, block_info_comp))

    off = (off + 15) & ~15
    chunks = []
    for u, c, f in blocks:
        raw = buf[off:off + c]; off += c
        chunks.append(decompress(f, raw, u))
    return b"".join(chunks)


def dump_strings(blob, out_path, min_len=4):
    import re
    pat = re.compile(rb"[\x20-\x7e]{%d,}" % min_len)
    seen = set()
    with open(out_path, "w", encoding="utf-8", errors="replace") as f:
        for m in pat.finditer(blob):
            s = m.group().decode("ascii", "replace")
            if s not in seen:
                seen.add(s)
                f.write("%08x %s\n" % (m.start(), s))
    print("strings: %d unique -> %s" % (len(seen), out_path))


if __name__ == "__main__":
    blob = extract(sys.argv[1])
    open(sys.argv[2], "wb").write(blob)
    print("wrote %s (%d B)" % (sys.argv[2], len(blob)))
    if len(sys.argv) > 4 and sys.argv[3] == "--strings":
        dump_strings(blob, sys.argv[4])
