#!/usr/bin/env python3
"""ayuanx ogg-winmm v2025.01.16: stop the string "open cdaudio" from crashing under Wine.

    python3 oggwinmm_fix.py <winmm.dll from the release zip> <out winmm.dll>      (build.py runs it for you)

fake_mciSendStringA answers "open cdaudio" (and "open ... type cdaudio alias x") by calling
fake_mciSendCommandA(0xCDDA, MCI_OPEN, 0, NULL). With no flags, that passes the call on to the real winmm. On
Windows the real call fails and the result is ignored; Wine's mciSendCommandA writes the device ID back through
the NULL parameter block and the game dies with an access violation inside winmm.dll. Games that open the CD with
mciSendCommand never reach this. The one call site (all three string paths jump to it) becomes
"add esp,0x10; xor eax,eax": the same stack as the stdcall it replaces, result 0. The skipped call does nothing
in ogg-winmm itself (no flags: no notify, no state).
"""
import hashlib, sys

IN_MD5 = "f4896addb8e4da30ebcfa2d9cc203c0e"
OFF = 0x1955                       # VA 0x639C2555: call 0x639C3A70 (pushes 0xCDDA, 0x803, 0, 0 above it)
OLD = bytes.fromhex("e816150000")
NEW = bytes.fromhex("83c41031c0")  # add esp,0x10 ; xor eax,eax


def patch(data, label="winmm.dll"):
    d = bytearray(data)
    if hashlib.md5(d).hexdigest() != IN_MD5:
        sys.exit(f"{label}: not ogg-winmm v2025.01.16's winmm.dll (MD5 {IN_MD5}): use that release")
    if d[OFF:OFF + 5] != OLD or d[OFF - 7:OFF] != bytes.fromhex("c70424dacd0000"):
        sys.exit(f"{label}: unexpected bytes at {OFF:#x}")
    d[OFF:OFF + 5] = NEW
    return bytes(d)


if __name__ == "__main__":
    if len(sys.argv) != 3: sys.exit(__doc__)
    open(sys.argv[2], "wb").write(patch(open(sys.argv[1], "rb").read(), sys.argv[1]))
