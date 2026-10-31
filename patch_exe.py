#!/usr/bin/env python3
"""Patch Speedster's game exe (the disc's PCDATA\\GAME.EXE, 501,760 bytes, MD5 6b1149d102cd10e7ad8438471d4bf56e,
linked 9 Apr 1997, Watcom C/C++, window title "Accelerator PC version"; Clockwork Games / Psygnosis) into a copy.

  patch_exe.py <GAME.EXE> <out.exe>     write the patched exe (refuses, writes nothing, on any unexpected byte)
  patch_exe.py --check-caves            re-assemble caves.s with clang and compare with CAVE below

New code (caves.s, assembled bytes in CAVE) goes into a section the patch adds: ".rdeck", VA 0x671000, 0x1000 bytes
at file offset 0x7a800 (the end of the file), readable / writable / executable; its variables from 0x671c00. The
section table had room for a seventh entry (it ended at 0x258, the first section starts at 0x400); SizeOfImage
0x271000 -> 0x272000. The exe has no checksum and loads at its 0x400000 base; the header now also says "relocations
stripped", so no loader ever moves it (the patched call sites had fixups for the addresses they no longer hold).

  rdeck       the section (above) with the code of caves.s.
  noreg       the game read HKLM\\SOFTWARE\\Clockwork_Games\\Speedster (written by the disc's launcher SPEEDSTR.EXE
              at install): SAVE_GAME_PATH = <install folder>\\Speedstr.CFG (settings + best times; ghost cars are
              saved beside it), CD_PATH = the CD's root, where WinMain (0x41d5dc, from 0x44bae6) changed the
              current directory to read pcdata\\..., racexx??\\..., resident\\.... Without the key there was no
              save path, and the config writer (0x42138c) passes fopen's NULL on to fwrite. All 78 registry calls
              (18 RegOpenKeyExA, 6 RegEnumValueA, 54 RegCloseKey; "call cs:[IAT]", 7 bytes) now call stand-ins
              in caves.s: value 0 is SAVE_GAME_PATH = "save\\Speedstr.CFG" and there is no CD_PATH, so the game
              stays in its own folder (the shortcut's Start In, or the exe's folder on Windows), which holds the
              disc's data. No registry use at all, on the Deck or on Windows.
  pace        the frame limiters spun on timeGetTime until 33 ms (16 ms for one mid-frame wait) had passed since
              the frame began ([0x6604c4]): 0x428123, 0x4282b8, 0x42846b (33 ms), 0x428266 (16 ms); and the two
              2-second logo holds 0x421b29, 0x421cfd. Each "call [timeGetTime]" there calls pace33 / pace16 /
              pace_any: Sleep(1) while 2 ms or more remain (timeBeginPeriod(1) once), the game's own loop does the
              last millisecond, so frames are as long as before (33 ms, 30 a second) without a core at 100%.
              (The limit is kept in ebx across the API calls: the first Deck build kept it in ecx, which
              Proton's timeGetTime overwrites with a stack address, so the first 33 ms wait slept forever: the
              front end stayed black, the process asleep in Sleep under 0x428123, 23 Oct 2026.)
  pad         all 30 "call [joyGetPosEx]" call joy: after each read the pad's buttons and D-pad are rewritten
              for the game's "Game Pad A" handling (buttons 1-3 and the stick): A / RT = button 1 (accelerate;
              select), X / B / LT = button 2 (brake; back), Y / R3 = button 3 (rear view), D-pad = the stick
              pushed fully (8 directions; the game itself reads no POV hat or Z axis).
  startselect the keyboard reader 0x40dec4 (DirectInput GetDeviceState; every menu and the race read the keys
              through it) ends in "mov eax, 0x53cd59" at 0x40deeb and 0x40df1b; both jump to kbdpad, which adds
              Enter while the pad's Menu (Start) button is down and Escape while View (Select) is down.
  movie32     the intro movie (pcdata\\intro.mpg, MPEG-1, the game's own decoder) needed a 640x480 24-bit display
              mode (0x44b9f3: SetDisplayMode(640, 480, 24); 0x401925: the player refuses any other surface).
              dgVoodoo2 (DDERR_INVALIDMODE) and Wine have no 24-bit modes, so the intro was skipped. Now 32-bit:
              the mode, the check, and the picture writer 0x462c5d (DGROUP), which doubles each of the 320
              movie pixels across 640: its stores at +0, +3, +6 ... +0x15 per four source pixels become +0,
              +4 ... +0x1c, the step 0x18 -> 0x20, the line skip 2 * pitch - 0x780 -> 2 * pitch - 0xa00.
              Also: before calling its generated (run-time compiled) bit-stream code, the decoder loaded GS
              with 0 (0x453781 "mov gs, eax", the word at 0x4738b4, never written); nothing in the exe uses GS
              afterwards, but Wine's own code on Linux does, and in a Wine test the movie crashed there at its
              first picture. Now "mov eax, eax": the movie plays (Wine 8 in Docker, 23 Oct 2026).
  movieskip   the movie's decoder polls PeekMessageA (0x4029d0) and ends on any WM_KEYDOWN; it calls movpeek,
              which also reports a key when a pad button is down (A, B, X, Y, View, Menu).
  coopwnd     the game makes two windows (both "Accelerator PC version"): A, hidden, then B, owned by A, which it
              shows and gives the focus; but SetCooperativeLevel (exclusive full screen) got A (ebx). On the Deck
              (Proton 9 + gamescope) showing A for the exclusive mode took the focus from B, B taking it back
              deactivated A, Wine minimised A, the surfaces were lost for good, the lock wrapper 0x44c090 gave up
              and the first full-screen copy (0x421a1a) wrote to address 0: no picture, crash (23 Oct 2026). Both
              start-up routines (0x44b4b3, 0x44bc0e) now keep B in ebx ("test eax, eax; jne +0b" after
              CreateWindowExA(B) -> "mov ebx, eax; jmp +0b", the never-taken failure exit dropped), so the
              exclusive window is the one the game shows and focuses. Wine 8 in Docker never showed this.
"""
import hashlib, os, re, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE, MD5 = 501760, "6b1149d102cd10e7ad8438471d4bf56e"
DELTA = 0x400c00                       # AUTO (0x401000) and DGROUP (0x45e000): file offset = VA - 0x400c00
def T(va): return va - DELTA

def rel32(src, dst, op):               # e8 / e9 at src (5 bytes) -> dst
    return bytes([op]) + (dst - (src + 5)).to_bytes(4, "little", signed=True)

SECT_VA, SECT_RVA, SECT_OFF, SECT_SIZE = 0x671000, 0x271000, 0x7a800, 0x1000
CAVE_VA = SECT_VA
CAVE = bytes.fromhex(
    "60c705001c67000100000068cd126700ff155483660085c0741468d712670050ff155c83660085c074046a01ffd068e7"
    "126700ff155483660085c0741168f412670050ff155c836600a3041c670061c3515253bb21000000eb08515253bb1000"
    "0000833d001c6700007505e890ffffffff1580826600833d041c670000741d89da29c20315c404660083fa027c0e39da"
    "7f0a6a01ff15041c6700ebd45b5a59c35152833d001c6700007505e850ffffff833d041c67000074086a01ff15041c67"
    "00ff15808266005a59c3ff742408ff742408ff157482660085c00f85cb000000535152568b7424188b54241483e20f8b"
    "5e2031c98b46103d00600000720e3d00a000007707c682101c67000180ba101c67000074143d00300000730383c9013d"
    "00d00000760383c902f6c301740383c901f6c306740383c902f7c308020000740383c904894e208b46283da08c000073"
    "543d9411000076073d0c7b00007207c7460c000000003d94110000720e3dbc3400007707c74608ffff00003dbc340000"
    "720e3de45700007707c7460cffff00003de4570000720e3d0c7b00007707c746080000000031c05e5a595bc208005152"
    "c705201c670034000000c705241c670080000000c705401c67000000000068201c67000fb6053cc0460050ff15748266"
    "0085c0b8000000007505a1401c67005a59c3e8b7ffffffa8807407800d75cd530080a8407407800d5acd530080b859cd"
    "53005a59c3ff742414ff742414ff742414ff742414ff742414ff15b482660085c07520e876ffffffa8cf74178b442404"
    "c7400400010000c740081b000000b801000000c214008b442414c700ed5e000031c0c2140031c0c20400837c24080074"
    "08b803010000c2200056578b7c241468fa1267005ee83c0000008b442418c7000e0000008b44242085c07406c7000100"
    "00008b7c242468091367005ee8150000008b44242885c07406c700120000005f5e31c0c22000acaa84c075fac357494e"
    "4d4d2e646c6c0074696d65426567696e506572696f64004b45524e454c33322e646c6c00536c65657000534156455f47"
    "414d455f5041544800736176655c53706565647374722e43464700")
SYM = {"pace33": 0x050, "pace16": 0x05a, "pace_any": 0x0a0, "joy": 0x0ca, "kbdpad": 0x1f2, "movpeek": 0x215,
       "fRegOpenKeyExA": 0x256, "fRegCloseKey": 0x265, "fRegEnumValueA": 0x26a}   # labels of caves.s
def C(name): return CAVE_VA + SYM[name]

IAT = {"RegOpenKeyExA": 0x668258, "RegEnumValueA": 0x668254, "RegCloseKey": 0x668250, "joyGetPosEx": 0x668274,
       "timeGetTime": 0x668280, "PeekMessageA": 0x6682b4}
def CALLIAT(name): return b"\x2e\xff\x15" + IAT[name].to_bytes(4, "little")    # call dword ptr cs:[IAT]
def CALLTO(src, name): return rel32(src, C(name), 0xe8) + b"\x90\x90"

def sites(data, name, count):          # every "call cs:[IAT]" of one import in the code (AUTO, 0x401000..)
    found = [0x400 + m.start() + DELTA for m in re.finditer(re.escape(CALLIAT(name)), bytes(data[0x400:0x5d400]))]
    if len(found) != count: sys.exit(f"{name}: {len(found)} call sites, expected {count}; nothing written")
    return found

PACE = {0x428123: "pace33", 0x4282b8: "pace33", 0x42846b: "pace33", 0x428266: "pace16",
        0x421b29: "pace_any", 0x421cfd: "pace_any"}
MOVIE32 = [   # (va, old, new): the 24-bit intro movie made 32-bit (docstring)
    (0x44b9f3, "6a18", "6a20"),                            # SetDisplayMode(640, 480, 24 -> 32)
    (0x401925, "837c245418", "837c245420"),                # the player's bit-depth check
    (0x462c65, "2d80070000", "2d000a0000"),                # line skip: 2 * pitch - 640 * 3 -> 640 * 4
    (0x462cf6, "895703", "895704"), (0x462d05, "895706", "895708"), (0x462d08, "895709", "89570c"),
    (0x462d53, "89570c", "895710"), (0x462d59, "89570f", "895714"), (0x462d68, "895712", "895718"),
    (0x462d6b, "895715", "89571c"),
    (0x462d78, "83c718", "83c720"),                        # 4 source pixels = 8 screen pixels: 24 -> 32 bytes
    (0x453781, "8ee8", "89c0"),                            # "mov gs, eax" (eax = 0) -> "mov eax, eax"
]

COOPWND = [0x44b4b3, 0x44bc0e]       # after CreateWindowExA(B): "test eax, eax; jne +0b" -> "mov ebx, eax; jmp +0b"

def build(data):
    edits = []                         # (file offset, old bytes, new bytes)
    for name, n, stub in (("RegOpenKeyExA", 18, "fRegOpenKeyExA"), ("RegEnumValueA", 6, "fRegEnumValueA"),
                          ("RegCloseKey", 54, "fRegCloseKey")):
        edits += [(T(va), CALLIAT(name), CALLTO(va, stub)) for va in sites(data, name, n)]
    for va, stub in PACE.items():
        edits.append((T(va), CALLIAT("timeGetTime"), CALLTO(va, stub)))
    edits += [(T(va), CALLIAT("joyGetPosEx"), CALLTO(va, "joy")) for va in sites(data, "joyGetPosEx", 30)]
    for va in (0x40deeb, 0x40df1b):    # "mov eax, 0x53cd59" (pop edx / pop ecx / ret follow) -> jmp kbdpad
        edits.append((T(va), bytes.fromhex("b859cd5300"), rel32(va, C("kbdpad"), 0xe9)))
    edits += [(T(va), bytes.fromhex(o), bytes.fromhex(n)) for va, o, n in MOVIE32]
    edits.append((T(0x4029d0), CALLIAT("PeekMessageA"), CALLTO(0x4029d0, "movpeek")))
    edits += [(T(va), bytes.fromhex("85c0750b"), bytes.fromhex("89c3eb0b")) for va in COOPWND]
    return edits

def add_section(data):
    lfanew = struct.unpack_from("<I", data, 0x3c)[0]
    nsec = struct.unpack_from("<H", data, lfanew + 6)[0]
    optsize = struct.unpack_from("<H", data, lfanew + 20)[0]
    sh = lfanew + 24 + optsize + 40 * nsec
    if nsec != 6 or sh != 0x258 or any(data[sh:sh + 40]) or len(data) != SECT_OFF:
        sys.exit("unexpected PE header; nothing written")
    struct.pack_into("<8sIIIIIIHHI", data, sh, b".rdeck", SECT_SIZE, SECT_RVA, SECT_SIZE, SECT_OFF, 0, 0, 0, 0,
                     0xE0000060)       # code | initialised data | execute | read | write
    struct.pack_into("<H", data, lfanew + 6, nsec + 1)
    chars = struct.unpack_from("<H", data, lfanew + 22)[0]
    struct.pack_into("<H", data, lfanew + 22, chars | 1)     # IMAGE_FILE_RELOCS_STRIPPED: never relocated (the
                                       # patched call sites had fixups for the IAT addresses they no longer hold)
    if struct.unpack_from("<I", data, lfanew + 24 + 56)[0] != SECT_RVA: sys.exit("unexpected SizeOfImage")
    struct.pack_into("<I", data, lfanew + 24 + 56, SECT_RVA + SECT_SIZE)
    data += CAVE + bytes(SECT_SIZE - len(CAVE))

def elf_text(path):                    # .text bytes and label offsets of an i386 ELF object (no relocations)
    d = open(path, "rb").read()
    shoff = struct.unpack_from("<I", d, 0x20)[0]; shentsize, shnum, shstrndx = struct.unpack_from("<HHH", d, 0x2e)
    secs = [struct.unpack_from("<10I", d, shoff + i * shentsize) for i in range(shnum)]
    names = [d[secs[shstrndx][4] + x[0]:].split(b"\0")[0].decode() for x in secs]
    if any(n.startswith(".rel") and x[5] for n, x in zip(names, secs)): sys.exit("caves.o has relocations")
    ti = names.index(".text"); text = d[secs[ti][4]:secs[ti][4] + secs[ti][5]]; syms = {}
    for x in secs:
        if x[1] != 2: continue                                   # SHT_SYMTAB
        strs = secs[x[6]]
        for i in range(x[5] // 16):
            nm, val, size, info, oth, shn = struct.unpack_from("<IIIBBH", d, x[4] + 16 * i)
            if shn == ti: syms[d[strs[4] + nm:].split(b"\0")[0].decode()] = val
    return text, syms

def check_caves():
    with tempfile.TemporaryDirectory() as t:
        o = os.path.join(t, "caves.o")
        subprocess.run(["clang", "-target", "i386-pc-linux-gnu", "-c", os.path.join(HERE, "caves.s"), "-o", o], check=True)
        text, syms = elf_text(o)
    ok = text == CAVE and all(syms.get(k) == v for k, v in SYM.items())
    print("caves.s matches CAVE" if ok else "caves.s differs from CAVE / SYM: update patch_exe.py")
    if not ok:
        print("CAVE =", text.hex()); print("SYM =", {k: hex(v) for k, v in syms.items() if k in SYM})
    return ok

def patch(data, label="GAME.EXE"):
    """Returns the patched exe; exits on any unexpected byte."""
    data = bytearray(data)
    if len(data) != SIZE or hashlib.md5(data).hexdigest() != MD5:
        sys.exit(f"{label}: not the 9 Apr 1997 GAME.EXE (size {SIZE}, MD5 {MD5}); nothing written")
    assert len(CAVE) < 0xc00, "CAVE runs into the variables at 0x671c00"
    edits = build(data)
    for off, old, new in edits:
        if bytes(data[off:off + len(old)]) != old or len(old) != len(new):
            sys.exit(f"unexpected bytes at VA {off + DELTA:#x}; nothing written")
    for off, old, new in edits:
        data[off:off + len(new)] = new
    add_section(data)
    print(f"  rdeck noreg pace pad startselect movie32 movieskip coopwnd ({len(edits)} edits)")
    return bytes(data)

def main(src, dst):
    data = patch(open(src, "rb").read(), src)
    tmp = dst + ".tmp"
    open(tmp, "wb").write(data)
    os.replace(tmp, dst)
    print(f"{dst}: MD5 {hashlib.md5(data).hexdigest()}")

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--check-caves": sys.exit(0 if check_caves() else 1)
    if len(sys.argv) != 3: sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
