"""Compile the tweak HLSL with the system D3D compiler (d3dcompiler_47.dll).

Gives the full error list in milliseconds instead of one error per Unity run.
Usage: python tools/hlsl_check.py <file.hlsl> [vs_entry] [ps_entry]
"""
import ctypes
import ctypes.util
import sys

D3DCOMPILE_ENABLE_STRICTNESS = 1 << 11


def shader_blob_text(blob):
    vtable = ctypes.cast(blob, ctypes.POINTER(ctypes.c_void_p)).contents
    # ID3DBlob: QueryInterface, AddRef, Release, GetBufferPointer, GetBufferSize
    get_buf = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)(
        ctypes.cast(vtable.value + 3 * ctypes.sizeof(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p))[0]
    )
    get_size = ctypes.WINFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p)(
        ctypes.cast(vtable.value + 4 * ctypes.sizeof(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p))[0]
    )
    ptr = get_buf(blob)
    size = get_size(blob)
    return ctypes.string_at(ptr, size)


def release(blob):
    vtable = ctypes.cast(blob, ctypes.POINTER(ctypes.c_void_p)).contents
    rel = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
        ctypes.cast(vtable.value + 2 * ctypes.sizeof(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p))[0]
    )
    rel(blob)


def compile_stage(dll, source, entry, target):
    pCode = ctypes.c_void_p()
    pErr = ctypes.c_void_p()
    hr = dll.D3DCompile(
        source, len(source), b"tweak.hlsl", None, None,
        entry.encode(), target.encode(),
        D3DCOMPILE_ENABLE_STRICTNESS, 0,
        ctypes.byref(pCode), ctypes.byref(pErr),
    )
    err = ""
    if pErr.value:
        err = shader_blob_text(pErr.value).decode("utf-8", "replace")
        release(pErr)
    if pCode.value:
        release(pCode)
    return hr, err


def main():
    path = sys.argv[1]
    vs = sys.argv[2] if len(sys.argv) > 2 else "VS_RaymarchCloud"
    ps = sys.argv[3] if len(sys.argv) > 3 else "PS_RaymarchCloud"
    dll = ctypes.WinDLL("d3dcompiler_47.dll")
    dll.D3DCompile.restype = ctypes.c_long
    src = open(path, "rb").read()
    if src.startswith(b"\xef\xbb\xbf"):
        src = src[3:]
    bad = 0
    for entry, target in ((vs, "vs_5_0"), (ps, "ps_5_0")):
        hr, err = compile_stage(dll, src, entry, target)
        ok = hr == 0
        print(f"=== {entry} ({target}): {'OK' if ok else 'FAIL hr=0x%08x' % (hr & 0xffffffff)}")
        if not ok:
            bad += 1
            print(err.strip())
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
