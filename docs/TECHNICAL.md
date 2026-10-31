# How it works

Notes on the Windows 95 release of Speedster (Clockwork Games / Psygnosis, 1997; "Accelerator" in
development), `PCDATA\GAME.EXE` 501,760 bytes, 9 April 1997, Watcom C/C++, MD5
`6b1149d102cd10e7ad8438471d4bf56e`. Addresses are virtual addresses in that exe.

## The disc

Track 1 is a Mode 2 (CD-XA, Form 1) data track; tracks 2-18 are the music (track 18 is 190 seconds
of digital silence). `SPEEDSTR.EXE` was the installer / launcher: it offered DirectX 3a, copied
`SPEEDSTR.CFG` to an install folder, wrote a registry key and started `PCDATA\GAME.EXE` from the
CD. The game reads its data from the CD root's folders: `PCDATA\` (graphics, cars, sounds, the
intro movie `INTRO.MPG`), `RACEXXCF\ RACEXXCR\ RACEXXTF\ RACEXXTR\` (the tracks, forward and
reverse), `RESIDENT\` and `MUSIC\`. `build.py` copies them all and puts the patched exe in the root.

`MUSIC\ACCEL01-15.PCM` and `ACCBLANK.SWP` are directory entries laid over the audio tracks themselves
(each starts at an audio track's first sector), probably left from the PlayStation version's
streamed music. The exe never opens them; `build.py` writes them as empty files, as an unpacked copy
of the disc has them.

The game: DirectDraw (an 8-bit software renderer), DirectInput (keyboard), the Windows joystick API
(`joyGetPosEx`), DirectSound, and MCI `cdaudio` for the music. No copy protection.

## The patches

`patch_exe.py` adds a section `.rdeck` (VA 0x671000, 4 KB, at the end of the file) holding the new
code from `caves.s`. Its header lists each site's bytes and reasoning.

| Patch | Was | Now |
|---|---|---|
| `noreg` | The game read `HKLM\SOFTWARE\Clockwork_Games\Speedster` from the installer: `SAVE_GAME_PATH` (the install folder's `Speedstr.CFG`) and `CD_PATH` (where it changed directory to read the data). Without the key it had no save file, and passed `fopen`'s NULL on to `fwrite` when saving | Its 78 registry calls go to stand-ins: `SAVE_GAME_PATH` = `save\Speedstr.CFG`, no `CD_PATH`, so it reads the data from its own folder |
| `pace` | The frame limiters spun on `timeGetTime` until 33 ms had passed since the frame began (menus and race; one 16 ms mid-frame wait), and the two 2-second logo holds spun too: a CPU core at 100% | `Sleep(1)` while 2 ms or more remain (`timeBeginPeriod(1)` once), the game's loop doing the last millisecond: the same 33 ms frames. The limit is kept in ebx, which Proton's `timeGetTime` leaves alone (ecx it doesn't) |
| `coopwnd` | The game makes two windows, A (hidden) then B (owned by A, shown, focused), but gave A to `SetCooperativeLevel` (exclusive full screen). Under gamescope A took the focus, B took it back, A was minimised, the surfaces were lost for good and the first full-screen copy wrote to address 0 | Both start-up routines (0x44b4b3, 0x44bc0e) give it B, the window the game shows |
| `pad` | The pad through `joyGetPosEx` as the game's "Game Pad A": the stick (digital, past a quarter of the way) and buttons 1-3. On an Xbox pad: A accelerate, B brake, X rear view; no D-pad, no triggers | After every read: A / RT = button 1 (accelerate, select), X / B / LT = button 2 (brake, back), Y / R3 = button 3 (rear view), D-pad = the stick pushed fully |
| `startselect` | Enter (select) and Esc (pause, back) were keyboard only | The keyboard reader adds Enter while Start is held and Esc while View is held |
| `movie32` | The intro movie (MPEG-1, the game's own decoder) needed a 640x480 24-bit display mode, which neither dgVoodoo2 nor Wine offers, so the game skipped it | The mode is 32-bit and the decoder writes 4 bytes a pixel (9 instruction bytes). Its `mov gs, eax` before calling its run-time-compiled bit-stream code is gone too: under Wine the movie crashed there at its first picture |
| `movieskip` | Any key ended the movie; the pad did nothing | A, B, X, Y, View or Start ends it too |

Not patched: the mouse (the game shows no pointer), the two 2-second holds on the Psygnosis logo and
the title screen (as on the disc), quitting (the game's own Exit Game).

## Picture

8-bit palette DirectDraw: 640x480 in the menus, and in races 640x480 ("High Res") or 320x200
("Normal", the disc's default; the kit starts on High Res). dgVoodoo2 2.79.3: `ScalingMode =
stretched_4_3` shows both modes at 4:3 (320x200 would otherwise come out 16:10), bilinear
resampling, vsync. The intro movie is 320 pixels wide, doubled to 640 and drawn on alternate lines
on alternate frames, the original's interlaced look.

## Music

The soundtrack (PC Music Ltd, 16 tracks) is CD audio: `play cdaudio from N to N+1 notify` (TMSF);
with Options > CD Repeat on, the game polls `status cdaudio mode` and restarts a stopped track.
ogg-winmm plays `MUSIC\TrackNN.ogg` (`CDDAPath = MUSIC`: the disc's own folder, so there's one music
folder on a case-insensitive disk too). Each track is ripped from its INDEX 01 to the next track's
start, minus up to 2 seconds of digital silence at its end.

## Starting settings

`Speedstr.CFG` (written by 0x42138c, read by 0x421700) holds the settings and the best-times tables:
0x04 the screen mode (0 Normal, 1 High Res), 0x10 / 0x15 the two players' five keys, 0x1a / 0x1b
their controllers (0 Keyboard, 1 Game Pad A, ...), 0x1c / 0x1d their joystick numbers. The kit's copy
is the disc's with High Res, Player One on Game Pad A and joystick 0.

## ogg-winmm

The game opens the CD with the MCI string `open cdaudio`. ogg-winmm v2025.01.16 answers it by
passing `MCI_OPEN` on to the real winmm with a NULL parameter block. Windows' winmm fails and the
result is ignored; Wine's writes the device ID back through the NULL pointer, an access violation
inside `winmm.dll`. `oggwinmm_fix.py` replaces that one call with `add esp,0x10 ; xor eax,eax` (the
same stack, result 0).
