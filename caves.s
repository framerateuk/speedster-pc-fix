# Speedster PC (GAME.EXE, 9 Apr 1997, 501,760 bytes, Watcom C/C++; Clockwork Games / Psygnosis): new code for
# patch_exe.py. It goes into a section patch_exe.py adds to the exe, ".rdeck" at VA 0x671000 (file offset
# 0x7a800, 0x1000 bytes, readable / writable / executable): this code from 0x671000, its variables from 0x671c00
# (zero when the exe loads). The exe always loads at its 0x400000 base (no ASLR flag, an EXE), so absolute
# addresses are used throughout.
#
# Assembled with Apple clang (integrated assembler):
#   clang -target i386-pc-linux-gnu -c caves.s -o caves.o
# patch_exe.py carries the resulting bytes (CAVE) and checks them against this file when clang is around
# (patch_exe.py --check-caves). docs/TECHNICAL.md explains each routine.
.intel_syntax noprefix
.set BASE, 0x671000

# imports used (IAT slots of GAME.EXE)
.set joyGetPosEx,      0x668274
.set timeGetTime,      0x668280
.set PeekMessageA,     0x6682b4
.set GetModuleHandleA, 0x668354
.set GetProcAddress,   0x66835c

# game variables
.set KBD,    0x53cd59                # DirectInput keyboard state (256 bytes, DIK_ order), filled by 0x40dec4
.set FRAME0, 0x6604c4                # timeGetTime at the start of the current frame (the frame limiters' base)
.set P1JOY,  0x46c03c                # Player One's joystick number (Speedstr.CFG)

# our variables (.rdeck from 0x671c00, zero at load)
.set INITED, 0x671c00                # 1 once init has run
.set SLEEPP, 0x671c04                # Sleep (0 = not found: then the limiters spin as before)
.set ZSEEN,  0x671c10                # 16 bytes, one per joystick number: its Z axis has been seen at rest
.set JI,     0x671c20                # a JOYINFOEX (52 bytes) for kbdpad and movpeek

.macro PUSHI v                       # push imm32 (clang's intel syntax would make "push offset" 16-bit)
  .byte 0x68
  .long \v
.endm

.text
start:

# ---------------------------------------------------------------------------------------------------------------
# init: once, from the first frame limiter call. timeBeginPeriod(1) (so that Sleep(1) sleeps about 1 ms on
# Windows too; Wine's timer is 1 ms anyway) and Sleep's address, both found with GetModuleHandleA /
# GetProcAddress (the exe imports neither). Keeps every register.
init:
  pushad
  mov dword ptr [INITED], 1
  PUSHI BASE + (s_winmm - start)
  call dword ptr [GetModuleHandleA]
  test eax, eax
  jz 1f
  PUSHI BASE + (s_tbp - start)
  push eax
  call dword ptr [GetProcAddress]
  test eax, eax
  jz 1f
  push 1
  call eax                           # timeBeginPeriod(1)
1:
  PUSHI BASE + (s_kernel32 - start)
  call dword ptr [GetModuleHandleA]
  test eax, eax
  jz 2f
  PUSHI BASE + (s_sleep - start)
  push eax
  call dword ptr [GetProcAddress]
  mov dword ptr [SLEEPP], eax
2:
  popad
  ret

# ---------------------------------------------------------------------------------------------------------------
# pace33 / pace16 (patch pace): called in place of "call [timeGetTime]" at the top of the game's frame-limit
# spins, each of the form
#     do { now = timeGetTime(); elapsed = now - [FRAME0]; } while (elapsed < LIMIT);  [FRAME0] = now
# (LIMIT 33 ms: 0x428123 menus, 0x4282b8 race, 0x42846b; 16 ms: 0x428266, the mid-frame wait). They spun a CPU
# core at 100% for most of every frame. Here: Sleep(1) while 2 ms or more remain, then return the time, so the
# game's own loop still ends the frame on the same millisecond as before (30.3 frames a second at 33 ms).
# Returns eax = timeGetTime(); keeps every other register.
pace33:
  push ecx
  push edx
  push ebx
  mov ebx, 0x21
  jmp pace_c
pace16:
  push ecx
  push edx
  push ebx
  mov ebx, 0x10
pace_c:                              # ebx = LIMIT: callee-saved, so it survives the API calls (a first build
                                     # kept it in ecx, which Proton's timeGetTime changes: the menus hung)
  cmp dword ptr [INITED], 0
  jne 1f
  call init
1:
  call dword ptr [timeGetTime]
  cmp dword ptr [SLEEPP], 0
  je 2f
  mov edx, ebx
  sub edx, eax
  add edx, dword ptr [FRAME0]        # remaining = LIMIT - (now - [FRAME0])
  cmp edx, 2
  jl 2f                              # under 2 ms left (or already late): the game spins the rest
  cmp edx, ebx
  jg 2f                              # [FRAME0] in the future: leave it to the game
  push 1
  call dword ptr [SLEEPP]
  jmp 1b
2:
  pop ebx
  pop edx
  pop ecx
  ret

# pace_any: the two 2-second logo holds (0x421b29, 0x421cfd: "while (timeGetTime() - start < 2000)", start in
# ebx). Sleep(1), then the time. Keeps every register but eax.
pace_any:
  push ecx
  push edx
  cmp dword ptr [INITED], 0
  jne 1f
  call init
1:
  cmp dword ptr [SLEEPP], 0
  je 2f
  push 1
  call dword ptr [SLEEPP]
2:
  call dword ptr [timeGetTime]
  pop edx
  pop ecx
  ret

# ---------------------------------------------------------------------------------------------------------------
# joy (patch pad): every "call [joyGetPosEx]" in the game (30) calls this instead; same arguments (uJoyID,
# JOYINFOEX *), same result. After a successful read it rewrites the buttons and axes for the game's
# "Game Pad A" handling, which knows only the stick (X / Y beyond a quarter of the way) and buttons 1-3:
#   button 1 = accelerate, in menus select     <- A, RT
#   button 2 = brake, in menus back            <- X, B, LT
#   button 3 = rear view                       <- Y, R3
# Buttons as Windows / Proton number an Xbox pad: A 1, B 2, X 4, Y 8, LB 0x10, RB 0x20, View 0x40, Menu 0x80,
# L3 0x100, R3 0x200. The triggers share the Z axis (rest 0x8000, RT pulls it to 0, LT to 0xffff); a joystick
# whose Z has not yet been seen near the middle is not read for triggers (a pad without them, a throttle).
# The D-pad (POV hat, hundredths of a degree, 0xffff centred) moves the X / Y axes fully (8 directions).
joy:
  push dword ptr [esp + 8]
  push dword ptr [esp + 8]
  call dword ptr [joyGetPosEx]
  test eax, eax
  jnz 9f
  push ebx
  push ecx
  push edx
  push esi
  mov esi, dword ptr [esp + 0x18]    # JOYINFOEX *
  mov edx, dword ptr [esp + 0x14]    # joystick number
  and edx, 0xf
  mov ebx, dword ptr [esi + 0x20]    # dwButtons as read
  xor ecx, ecx                       # the buttons the game gets
  mov eax, dword ptr [esi + 0x10]    # dwZpos
  cmp eax, 0x6000
  jb 1f
  cmp eax, 0xa000
  ja 1f
  mov byte ptr [ZSEEN + edx], 1
1:
  cmp byte ptr [ZSEEN + edx], 0
  je 3f
  cmp eax, 0x3000
  jae 2f
  or ecx, 1                          # RT
2:
  cmp eax, 0xd000
  jbe 3f
  or ecx, 2                          # LT
3:
  test bl, 0x01
  jz 4f
  or ecx, 1                          # A
4:
  test bl, 0x06
  jz 5f
  or ecx, 2                          # B or X
5:
  test ebx, 0x208
  jz 6f
  or ecx, 4                          # Y or R3
6:
  mov dword ptr [esi + 0x20], ecx
  mov eax, dword ptr [esi + 0x28]    # dwPOV
  cmp eax, 36000
  jae 8f                             # centred (0xffff) or none
  cmp eax, 4500
  jbe 10f                            # up (incl. up-right)
  cmp eax, 31500
  jb 11f
10:
  mov dword ptr [esi + 0xc], 0       # up
11:
  cmp eax, 4500
  jb 12f
  cmp eax, 13500
  ja 12f
  mov dword ptr [esi + 8], 0xffff    # right
12:
  cmp eax, 13500
  jb 13f
  cmp eax, 22500
  ja 13f
  mov dword ptr [esi + 0xc], 0xffff  # down
13:
  cmp eax, 22500
  jb 8f
  cmp eax, 31500
  ja 8f
  mov dword ptr [esi + 8], 0         # left
8:
  xor eax, eax
  pop esi
  pop edx
  pop ecx
  pop ebx
9:
  ret 8

# ---------------------------------------------------------------------------------------------------------------
# readpad: JI = Player One's pad (raw, not through joy), buttons only. Returns eax = dwButtons, 0 if no pad.
# Keeps every register but eax.
readpad:
  push ecx
  push edx
  mov dword ptr [JI], 52             # dwSize
  mov dword ptr [JI + 4], 0x80       # JOY_RETURNBUTTONS
  mov dword ptr [JI + 0x20], 0
  PUSHI JI
  movzx eax, byte ptr [P1JOY]
  push eax
  call dword ptr [joyGetPosEx]
  test eax, eax
  mov eax, 0
  jnz 1f
  mov eax, dword ptr [JI + 0x20]
1:
  pop edx
  pop ecx
  ret

# kbdpad (patch startselect): the keyboard reader 0x40dec4 (GetDeviceState into KBD, used by every menu and
# the race) jumps here on success instead of "mov eax, KBD; pop edx; pop ecx; ret". The pad's Menu button
# (Start) adds Enter, its View button (Select) adds Escape, as if pressed on the keyboard.
kbdpad:
  call readpad
  test al, 0x80
  jz 1f
  or byte ptr [KBD + 0x1c], 0x80     # DIK_RETURN
1:
  test al, 0x40
  jz 2f
  or byte ptr [KBD + 0x01], 0x80     # DIK_ESCAPE
2:
  .byte 0xb8                         # mov eax, KBD
  .long KBD
  pop edx
  pop ecx
  ret

# ---------------------------------------------------------------------------------------------------------------
# movpeek (patch movieskip): the intro movie's decoder (0x4029d0) calls PeekMessageA(PM_REMOVE) between
# pictures and ends the movie on any WM_KEYDOWN. Here, when no message is waiting and a pad button is down
# (A, B, X, Y, View or Menu), it returns a made-up WM_KEYDOWN instead.
movpeek:
  push dword ptr [esp + 0x14]
  push dword ptr [esp + 0x14]
  push dword ptr [esp + 0x14]
  push dword ptr [esp + 0x14]
  push dword ptr [esp + 0x14]
  call dword ptr [PeekMessageA]
  test eax, eax
  jnz 1f
  call readpad
  test al, 0xcf
  jz 1f
  mov eax, dword ptr [esp + 4]       # MSG *
  mov dword ptr [eax + 4], 0x100     # message = WM_KEYDOWN
  mov dword ptr [eax + 8], 0x1b      # wParam = VK_ESCAPE
  mov eax, 1
1:
  ret 0x14

# ---------------------------------------------------------------------------------------------------------------
# The registry (patch noreg). The game read HKLM\SOFTWARE\Clockwork_Games\Speedster, which the disc's
# launcher (SPEEDSTR.EXE) wrote at install: value 0 SAVE_GAME_PATH = <install folder>\Speedstr.CFG (settings,
# best times; ghost cars go beside it) and CD_PATH = the CD's root (the game changes its current directory there
# and reads pcdata\..., racexx??\..., resident\...). Its 78 registry calls now come here: every key opens, value
# 0 is SAVE_GAME_PATH = "save\Speedstr.CFG" (relative: the current directory is the game folder), there is no
# value 1 (so no CD_PATH: the game stays in its own folder, where the data is). Nothing is read or written in
# the registry.
fRegOpenKeyExA:                      # (hKey, lpSubKey, ulOptions, samDesired, phkResult)
  mov eax, dword ptr [esp + 0x14]
  mov dword ptr [eax], 0x5eed
  xor eax, eax
  ret 0x14

fRegCloseKey:                        # (hKey)
  xor eax, eax
  ret 4

fRegEnumValueA:                      # (hKey, dwIndex, lpValueName, lpcchValueName, lpReserved, lpType, lpData, lpcbData)
  cmp dword ptr [esp + 8], 0
  je 1f
  mov eax, 0x103                     # ERROR_NO_MORE_ITEMS
  ret 0x20
1:
  push esi
  push edi
  mov edi, dword ptr [esp + 0x14]    # lpValueName
  PUSHI BASE + (s_name - start)
  pop esi
  call strcpy_
  mov eax, dword ptr [esp + 0x18]    # lpcchValueName
  mov dword ptr [eax], 14
  mov eax, dword ptr [esp + 0x20]    # lpType
  test eax, eax
  jz 2f
  mov dword ptr [eax], 1             # REG_SZ
2:
  mov edi, dword ptr [esp + 0x24]    # lpData
  PUSHI BASE + (s_path - start)
  pop esi
  call strcpy_
  mov eax, dword ptr [esp + 0x28]    # lpcbData
  test eax, eax
  jz 3f
  mov dword ptr [eax], 18             # strlen("save\\Speedstr.CFG") + 1
3:
  pop edi
  pop esi
  xor eax, eax
  ret 0x20

strcpy_:                             # esi -> edi, with the 0
  lodsb
  stosb
  test al, al
  jnz strcpy_
  ret

# ---------------------------------------------------------------------------------------------------------------
s_winmm:    .asciz "WINMM.dll"
s_tbp:      .asciz "timeBeginPeriod"
s_kernel32: .asciz "KERNEL32.dll"
s_sleep:    .asciz "Sleep"
s_name:     .asciz "SAVE_GAME_PATH"
s_path:     .asciz "save\\Speedstr.CFG"
s_path_end:
