#!/bin/bash
# Corre una ROM y graba un VGM con lo que escribe a los chips de sonido.
#
# blastem tiene una grabación interna en la tecla 'm', que arranca y para. Lo
# que sale es un log de escrituras al PSG y al YM2612 con el tiempo entre
# medio, o sea exactamente lo mismo que produce el conversor de música: sirve
# para comparar lo que suena contra lo que se pidió.
set -euo pipefail

usage="uso: vgmlog.sh ROM SALIDA.vgm [segundos] [region]"
rom=${1:?$usage}
out=${2:?$usage}
seconds=${3:-10}
region=${4:-E}

mkdir -p "$HOME/.config/blastem" /vgm
sed -e 's|^\(\s*\)vgm_path .*|\1vgm_path /vgm|' \
    -e 's|^\(\s*\)vgm_template .*|\1vgm_template log.vgm|' \
    /etc/blastem/default.cfg > "$HOME/.config/blastem/blastem.cfg"
rm -f /vgm/log.vgm

Xvfb :99 -screen 0 640x480x24 >/dev/null 2>&1 &
xvfb_pid=$!
trap 'kill $xvfb_pid 2>/dev/null || true' EXIT
export DISPLAY=:99 SDL_AUDIODRIVER=dummy
for _ in $(seq 50); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.1; done

blastem -g -r "$region" "$rom" >/tmp/blastem.log 2>&1 &
blastem_pid=$!
trap 'kill $blastem_pid $xvfb_pid 2>/dev/null || true' EXIT
sleep 3

win=$(xdotool search --sync --onlyvisible --class blastem | head -1)
xdotool windowfocus --sync "$win"
xdotool key --clearmodifiers m          # arranca la grabación
sleep "$seconds"
xdotool key --clearmodifiers m          # y la corta
sleep 1

[ -s /vgm/log.vgm ] || { echo "no salió el VGM" >&2; cat /tmp/blastem.log >&2; exit 1; }
cp /vgm/log.vgm "$out"
echo "vgm -> $out ($(stat -c %s "$out") bytes)"
