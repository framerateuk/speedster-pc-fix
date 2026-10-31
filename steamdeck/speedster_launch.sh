#!/bin/bash
# Speedster (Clockwork Games / Psygnosis, 1997) Steam Deck launch wrapper.
#
# Keep it beside game/ (build.py puts it there). With the folder at /home/deck/Games/Speedster:
#   Shortcut target: /home/deck/Games/Speedster/game/Speedster.exe, Start In: .../game/
#   Compatibility: Proton 9.0
#   Launch Options: /home/deck/Games/Speedster/speedster_launch.sh %command%
#
# Speedster.exe is the disc's PCDATA\GAME.EXE patched (patch_exe.py): it needs no registry and no CD, reads the
# data from its current directory (Start In = game/), keeps settings + best times + ghost cars in game/save/.
# Every launch sets DLL overrides so Wine loads the wrappers beside the exe:
#   ddraw.dll   dgVoodoo2 2.79.3 DirectDraw (the game's 8-bit 640x480 / 320x200 modes and the 32-bit intro movie,
#               scaled to the screen's height at 4:3 with black bars; dgVoodoo.conf)
#   winmm.dll   ogg-winmm: the game's MCI "cdaudio" music from game/MUSIC/Track02..18.ogg (winmm.ini)
# RENDERER (before the script path in Launch Options, or a file RENDERER beside this script holding the word):
#   dgvoodoo  (default) ddraw from dgVoodoo2
#   wined3d   plain Wine DirectDraw, for comparison (picture stretched by gamescope, not 4:3)

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$HERE/launch.log"
log() { echo "[$(date '+%H:%M:%S')] $*" >>"$LOG"; }
: >"$LOG"
log "args: $*"
log "cwd: $(pwd)"

[ -z "${RENDERER:-}" ] && [ -s "$HERE/RENDERER" ] && RENDERER="$(tr -d ' \n' < "$HERE/RENDERER")"
RENDERER="${RENDERER:-dgvoodoo}"
log "RENDERER=$RENDERER  STEAM_COMPAT_DATA_PATH=${STEAM_COMPAT_DATA_PATH:-unset}"

# Proton appends its own overrides after ours.
case "$RENDERER" in
  dgvoodoo) OVR="ddraw=n,b" ;;
  wined3d)  OVR="ddraw=b" ;;
  *)        log "unknown RENDERER '$RENDERER', using dgvoodoo"; OVR="ddraw=n,b" ;;
esac
export WINEDLLOVERRIDES="winmm=n,b;${OVR}${WINEDLLOVERRIDES:+;$WINEDLLOVERRIDES}"
log "WINEDLLOVERRIDES=$WINEDLLOVERRIDES"

# Debugging: if a file named PROTON_LOG exists beside this script, Proton writes steam-<appid>.log here. A file
# WINEDEBUG beside it adds Wine debug channels (e.g. +ddraw,+joystick,+mci). Create / delete them from Desktop Mode.
if [ -e "$HERE/PROTON_LOG" ]; then
  export PROTON_LOG=1 PROTON_LOG_DIR="$HERE"
  log "PROTON_LOG on -> $HERE/steam-*.log"
  if [ -s "$HERE/WINEDEBUG" ]; then
    export WINEDEBUG="+timestamp,+tid,+seh,+loaddll,$(tr -d ' \n' < "$HERE/WINEDEBUG")"
    log "WINEDEBUG=$WINEDEBUG"
  fi
fi

# Frame rate / GPU load overlay (DXVK, under dgVoodoo's D3D11): a file DXVK_HUD beside this script holding e.g. fps.
if [ -s "$HERE/DXVK_HUD" ]; then
  export DXVK_HUD="$(tr -d ' \n' < "$HERE/DXVK_HUD")"
  log "DXVK_HUD=$DXVK_HUD"
fi

for f in Speedster.exe ddraw.dll dgVoodoo.conf winmm.dll winmm.ini MUSIC/Track02.ogg PCDATA/FRONT.GFX \
         PCDATA/INTRO.MPG RESIDENT/ANIMTEXT.VRM RACEXXTF save/Speedstr.CFG; do
  [ -e "$HERE/game/$f" ] || log "WARNING: game/$f missing"
done
log "save/: $(ls "$HERE/game/save" 2>/dev/null | tr '\n' ' ')"

# Testing another Proton without touching Steam's settings: a file PROTON_VERSION beside this script holding a folder
# name from steamapps/common (e.g. "Proton 11.0") replaces the Proton in Steam's command line.
if [ -s "$HERE/PROTON_VERSION" ]; then
  want="$(head -1 "$HERE/PROTON_VERSION")"; args=()
  for a in "$@"; do
    case "$a" in */steamapps/common/*/proton) a="${a%/steamapps/common/*}/steamapps/common/$want/proton";; esac
    args+=("$a")
  done
  set -- "${args[@]}"
  log "PROTON_VERSION=$want"
fi

log "exec: $*"
exec "$@"
