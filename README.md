# Speedster (PC, 1997) on modern PCs and the Steam Deck

## Why this exists

Speedster felt like a more serious version of Micro Machines, following on from the likes of
Ignition: top-down racing with good handling. On modern systems it needs registry entries from its
installer, a CD in the drive, and a 24-bit display mode for its intro, and it crashes under Proton
before the first picture. This kit sorts that out, so it can be played again.

## What this does

Turns **your own** Speedster CD into a folder that runs on the Steam Deck (Proton) or on Windows
10/11, with no installer and no registry entries:

- **Copied straight from the CD**: the game reads its data from the disc's folders, so they're
  copied as they are, and the exe runs from that folder.
- **No registry, no CD**: the game found its save file and the CD through the installer's registry
  key; it now saves in `game/save/` and reads everything from its own folder.
- **DirectDraw through dgVoodoo2**, 4:3 with black bars at any screen size, and the 640x480 "High
  Res" mode set from the start.
- **The intro movie plays again**: it needed a 24-bit display mode that dgVoodoo and Windows no
  longer offer; the movie player now draws in 32-bit. The pad skips it.
- **CD soundtrack** from OGG files ripped from your disc.
- **Gamepad**: an Xbox-style pad (the Steam Deck's included) works with the D-pad and triggers, and
  Start / View do Enter / Esc, so no Steam Input set-up is needed.
- **No busy waits**: the frame limiter and the logo holds used to spin a CPU core at 100%; now
  they sleep, at the same 30 frames a second.
- A crash at the first full-screen picture under Proton is fixed (the game handed its full screen
  to its hidden window).

**No game files are in this repository.** Everything from the game comes from your disc when you
run `build.py`.

## What you need

| | |
|---|---|
| The game | The **Speedster CD** (Clockwork Games / Psygnosis, 1997, Windows 95; `PCDATA\GAME.EXE` of 9 April 1997) as `.cue` + `.bin` or CloneCD `.ccd` + `.img`, with its audio tracks. `build.py` checks the exe and stops on another version. |
| Python | 3.8 or newer (python.org on Windows; already on macOS/Linux). |
| An OGG encoder | `oggenc` (vorbis-tools; Windows builds at rarewares.org) or `ffmpeg`, on the PATH. |
| dgVoodoo2 **2.79.3** | by Dege: [GitHub release v2.79.3](https://github.com/dege-diosg/dgVoodoo2/releases/tag/v2.79.3). Use 2.79.3: newer versions don't start under Wine/Proton. Keep the zip as downloaded. |
| ogg-winmm **v2025.01.16** | by AyuanX: [GitHub releases](https://github.com/ayuanx/ogg-winmm/releases). This exact release: `build.py` patches one call in its `winmm.dll` and checks the file first. Keep the zip as downloaded. |

## Build

```
python3 build.py SPEEDSTER.cue --dgvoodoo dgVoodoo2_79_3.zip --ogg-winmm ogg-winmm_binary.zip
```

creates `Speedster/` with `game/` and `speedster_launch.sh` (for the Steam Deck), in about a minute.
The same `game/` folder runs on Windows; `--windows` leaves out the launch script. `--out DIR` puts
the result somewhere else. The disc's original exe, launcher and settings file are kept in
`game/_spare/`.

## Play on the Steam Deck

1. Copy `Speedster/` to the Deck, for example to `/home/deck/Games/Speedster/`.
2. Desktop Mode: Steam > Add a Non-Steam Game > Browse > `.../Speedster/game/Speedster.exe`.
   Rename the shortcut "Speedster".
3. Properties > Compatibility: force **Proton 9.0**. Pin it rather than floating on Experimental.
4. Properties > Launch Options:
   ```
   /home/deck/Games/Speedster/speedster_launch.sh %command%
   ```
5. Controller layout: the standard **Gamepad** layout. The game reads the pad itself.

## Play on Windows

Run `game/Speedster.exe`. An Xbox pad works as on the Deck.

## Controls

| Pad | In a race | In the menus |
|---|---|---|
| Left stick or D-pad | steer | choose |
| A or RT | accelerate | select |
| X, B or LT | brake | back |
| Y or R3 | rear view | |
| Start | Enter | select |
| View | Esc: pause | back |

Steering is on / off, as in the game's own pad mode. A, B, X, Y, Start or View skips the intro movie.
The keyboard works as the game always had it: arrows (up accelerates, down brakes), F4 rear view,
Enter, Esc; the Controller screen redefines keys.

## Settings

`game/save/Speedstr.CFG` holds the options, controllers, keys and best-times tables (the game
writes it when you quit through Exit Game); ghost cars are saved beside it. The kit's starting copy
is the disc's with High Res and Player One on the pad ("Game Pad A").

- Screen mode: Options > Screen Mode, High Res (640x480) or Normal (320x200); both show 4:3.
- Music level: `CDDAVolume` in `game/winmm.ini`.
- Deck renderer: `RENDERER=wined3d` before the script path in the launch options uses Wine's own
  DirectDraw instead of dgVoodoo.

**Widescreen**: none. The game is a fixed 4:3 2D picture.

## Troubleshooting

- *No music*: on the Deck `launch.log` must show `WINEDLLOVERRIDES=winmm=n,b;...` (no log: the
  launch option is missing `%command%`), and `game/MUSIC/Track02.ogg` must exist.
- *Settings or best times not kept*: quit through the main menu's Exit Game; that's when the game
  writes `Speedstr.CFG`.
- *No intro movie, or a black screen*: `ddraw.dll` and `dgVoodoo.conf` must be beside
  `Speedster.exe`.
- *Judder on a G-Sync / FreeSync monitor*: turn variable refresh off for this game.

## What's in this repository

| File | What |
|---|---|
| `build.py` | Builds the folder: copies the CD's game files, patches the exe, writes the starting settings, rips the soundtrack, adds the wrappers. Python standard library only. |
| `patch_exe.py` | The exe patches, each explained; adds a code section to the exe. Also runs on its own. |
| `caves.s` | The new code's source (x86 assembly). `python3 patch_exe.py --check-caves` re-assembles it with clang and checks it against the bytes in `patch_exe.py`. |
| `oggwinmm_fix.py` | A 5-byte fix to ogg-winmm v2025.01.16 (its "open cdaudio" string command crashes under Wine). |
| `disc.py` | Reads the CD image: `.cue`/`.bin` or `.ccd`/`.img`, ISO 9660 and audio tracks. |
| `config/` | dgVoodoo2's and ogg-winmm's settings. |
| `steamdeck/speedster_launch.sh` | Proton launch wrapper: DLL overrides. |
| `docs/TECHNICAL.md` | How the game works and what each patch does. |

## Credits

- **Clockwork Games** made Speedster; **Psygnosis** published it. Please own the game: this kit
  needs your disc.
- **Dege**: dgVoodoo2. **AyuanX**: ogg-winmm.

## License

The scripts and docs in this repository: MIT (see `LICENSE`). The license covers only this
repository's own files, not the game, dgVoodoo2 or ogg-winmm.

Not affiliated with or endorsed by the game's rights holders.
