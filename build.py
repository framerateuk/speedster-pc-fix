#!/usr/bin/env python3
"""Build a ready-to-run Speedster folder for modern PCs from your own CD.

Usage:
  python3 build.py DISC.cue|DISC.ccd --dgvoodoo DGVOODOO.zip --ogg-winmm OGG-WINMM.zip [--out DIR] [--windows]

  DISC          your Speedster CD (Clockwork Games / Psygnosis, 1997, Windows 95) as .cue + .bin or .ccd + .img,
                with its audio tracks
  --dgvoodoo    dgVoodoo2 2.79.3 zip (or its unpacked folder)
  --ogg-winmm   ogg-winmm v2025.01.16 release zip (or folder)
  --out         where to create Speedster/ (default: this folder)
  --windows     a folder for Windows only: the same game/ folder, without the Steam Deck launch script

Needs Python 3.8+ and an Ogg Vorbis encoder on the PATH: oggenc (vorbis-tools) or ffmpeg.
Nothing from the game is in this repository: every game file comes from your disc.
"""
import argparse, hashlib, os, shutil, struct, subprocess, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import disc, oggwinmm_fix, patch_exe

PATCHED_MD5 = "2bec0ca64fd4a848a70aa04864ed3452"
CFG_MD5 = "d23ef3d2789876a9c1f64e6cf9def18c"            # the disc's SPEEDSTR.CFG
# The game reads its data from the CD root's folders; everything is copied but these (DirectX 3a, the launcher /
# installer, its uninstaller, autorun). The disc's SPEEDSTR.EXE, SPEEDSTR.CFG and GAME.EXE go to _spare/.
SKIP = {"AUTORUN.INF", "UNINSTAL.EXE", "SPEEDSTR.EXE", "SPEEDSTR.CFG", "PCDATA/GAME.EXE"}
SPARE = [("PCDATA/GAME.EXE", "GAME.EXE"), ("SPEEDSTR.EXE", "SPEEDSTR.EXE"), ("SPEEDSTR.CFG", "SPEEDSTR.CFG")]


def md5(data): return hashlib.md5(data).hexdigest()


def skipped(key):
    top = key.split("/")[0]
    return key in SKIP or top == "DIRECTX" or (key == top and top.startswith("DSETUP") and top.endswith(".DLL"))


def starting_cfg(d):
    """Speedstr.CFG (written by GAME.EXE 0x42138c, read by 0x421700): the settings and the best-times tables.
    0x04 dword Screen Mode (0 Normal 320x200, 1 High Res 640x480), 0x1a Player One's controller (0 Keyboard,
    1 Game Pad A, ...), 0x1c Player One's joystick number. Changed from the disc's: High Res, Player One on Game
    Pad A, joystick 0 (the pad). The keys and the default best times stay as on the disc."""
    d = bytearray(d)
    if md5(d) != CFG_MD5: sys.exit("this CD's SPEEDSTR.CFG is not the one the kit was made for")
    d[0x04:0x08] = (1).to_bytes(4, "little"); d[0x1a] = 1; d[0x1c] = 0
    return bytes(d)


def encoder():
    if shutil.which("oggenc"): return lambda wav, ogg: ["oggenc", "-Q", "-q", "7", wav, "-o", ogg]
    if shutil.which("ffmpeg"):
        return lambda wav, ogg: ["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-c:a", "libvorbis", "-q:a", "7", ogg]
    sys.exit("needs oggenc (vorbis-tools) or ffmpeg on the PATH to encode the soundtrack")


def rip(tracks, music):
    enc = encoder(); os.makedirs(music, exist_ok=True); zero = bytes(2352); n = 0
    with tempfile.TemporaryDirectory() as tmp:
        for t in tracks:
            if t.kind != "AUDIO": continue
            data = disc.audio(t)          # INDEX 01 to the next track's start
            tail = 0                      # minus up to 2 s of digital silence at the end (the gap before the next track)
            while tail < 150 and data[len(data) - (tail + 1) * 2352:len(data) - tail * 2352] == zero: tail += 1
            if tail: data = data[:len(data) - tail * 2352]
            wav = os.path.join(tmp, f"track{t.n:02d}.wav")
            with open(wav, "wb") as o:
                o.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " +
                        struct.pack("<IHHIIHH", 16, 1, 2, 44100, 176400, 4, 16) + b"data" +
                        struct.pack("<I", len(data)) + data)
            subprocess.run(enc(wav, os.path.join(music, f"Track{t.n:02d}.ogg")), check=True); os.remove(wav)
            print(f"  MUSIC/Track{t.n:02d}.ogg  {len(data) / 2352 / 75:6.1f} s"); n += 1
    if n != 17: sys.exit(f"expected 17 audio tracks (the game's music), found {n}: is the image missing them?")


def take(src, member):
    """Bytes of the file whose path ends with `member` (case-insensitive) in a zip or folder."""
    want = member.lower()
    if os.path.isdir(src):
        for d, _, fs in os.walk(src):
            for f in fs:
                p = os.path.join(d, f)
                if os.path.relpath(p, src).replace(os.sep, "/").lower().endswith(want): return open(p, "rb").read()
    else:
        with zipfile.ZipFile(src) as z:
            for name in z.namelist():
                if name.lower().endswith(want): return z.read(name)
    sys.exit(f"{member} not found in {src}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("disc"); ap.add_argument("--dgvoodoo", required=True); ap.add_argument("--ogg-winmm", required=True)
    ap.add_argument("--out", default=HERE); ap.add_argument("--windows", action="store_true")
    a = ap.parse_args()

    tracks = disc.tracks(a.disc)
    data = [t for t in tracks if t.kind != "AUDIO"]
    if not data: sys.exit("no data track in " + a.disc)
    dt = disc.DataTrack(data[0])
    entries = {p.upper(): (p, is_dir, l, s) for p, is_dir, l, s in dt.walk()}
    if "PCDATA/GAME.EXE" not in entries: sys.exit("no PCDATA\\GAME.EXE on this CD: it isn't the Speedster disc the kit was made for")
    got = md5(dt.read_file(*entries["PCDATA/GAME.EXE"][2:]))
    if got != patch_exe.MD5:
        sys.exit(f"this CD's PCDATA\\GAME.EXE is not the 9 April 1997 one the kit was made for (MD5 {got}); "
                 "nothing else is supported yet")
    winmm = oggwinmm_fix.patch(take(a.ogg_winmm, "winmm.dll"))    # before anything is written: the release must match

    pkg = os.path.join(os.path.abspath(a.out), "Speedster"); game = os.path.join(pkg, "game")
    if os.path.exists(pkg): sys.exit(f"{pkg} already exists: move or delete it first")

    print("1/5 game files from the CD")
    data_sectors = data[0].end - data[0].start
    for key, (p, is_dir, l, s) in entries.items():
        if skipped(key): continue
        dst = os.path.join(game, *p.split("/"))
        if is_dir: os.makedirs(dst, exist_ok=True)
        elif l >= data_sectors:          # MUSIC\ACCEL*.PCM, ACCBLANK.SWP: entries over the audio tracks themselves
            os.makedirs(os.path.dirname(dst), exist_ok=True)       # (left from the PlayStation version, probably);
            open(dst, "wb").close()                                # the exe never opens them: empty files
        else: dt.copy_file(l, s, dst)
    for f, dst in SPARE:
        dt.copy_file(*entries[f][2:], os.path.join(game, "_spare", dst))
    os.makedirs(os.path.join(game, "save"))
    open(os.path.join(game, "save", "Speedstr.CFG"), "wb").write(starting_cfg(dt.read_file(*entries["SPEEDSTR.CFG"][2:])))

    print("2/5 exe patches")
    out = patch_exe.patch(dt.read_file(*entries["PCDATA/GAME.EXE"][2:]))
    if md5(out) != PATCHED_MD5: sys.exit("patching gave an unexpected Speedster.exe")
    open(os.path.join(game, "Speedster.exe"), "wb").write(out)     # in the root: the game reads its data from there

    print("3/5 soundtrack")
    rip(tracks, os.path.join(game, entries["MUSIC"][0]))   # beside the disc's (empty) MUSIC\ACCEL*.PCM placeholders

    print("4/5 wrappers and settings")
    open(os.path.join(game, "ddraw.dll"), "wb").write(take(a.dgvoodoo, "MS/x86/DDraw.dll"))
    open(os.path.join(game, "winmm.dll"), "wb").write(winmm)
    for f in ("dgVoodoo.conf", "winmm.ini"):
        shutil.copyfile(os.path.join(HERE, "config", f), os.path.join(game, f))

    print("5/5 Steam Deck launch script" if not a.windows else "5/5 done")
    if not a.windows:
        launch = os.path.join(pkg, "speedster_launch.sh")
        shutil.copyfile(os.path.join(HERE, "steamdeck", "speedster_launch.sh"), launch); os.chmod(launch, 0o755)
    print(f"\ndone: {pkg}  (see README.md)")


if __name__ == "__main__":
    main()
