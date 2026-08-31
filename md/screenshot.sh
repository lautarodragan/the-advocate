#!/bin/bash
# Corre una ROM en blastem sin pantalla y saca un screenshot del framebuffer.
#
# blastem no tiene modo headless ni opción de screenshot por línea de comandos,
# pero sí un screenshot interno (tecla 'p') que guarda el framebuffer nativo a
# 320x224, sin escalado ni corrección de aspecto. Así que: Xvfb para darle una
# pantalla, xdotool para apretarle la tecla, y listo.
set -euo pipefail

usage="uso: screenshot.sh ROM SALIDA.png [warmup] [region] [teclas] [segundos]"
rom=${1:?$usage}
out=${2:?$usage}
warmup=${3:-3}
region=${4:-E}   # E = Europa/PAL: 240 renglones, que es lo que mide el mapa
keys=${5:-}      # teclas a mantener apretadas antes de capturar (las flechas
hold=${6:-4}     # son la cruceta del control 1 en blastem)

mkdir -p "$HOME/.config/blastem" /shots
sed -e 's|^\(\s*\)screenshot_path .*|\1screenshot_path /shots|' \
    -e 's|^\(\s*\)screenshot_template .*|\1screenshot_template shot.png|' \
    /etc/blastem/default.cfg > "$HOME/.config/blastem/blastem.cfg"
rm -f /shots/shot.png

Xvfb :99 -screen 0 640x480x24 >/dev/null 2>&1 &
xvfb_pid=$!
trap 'kill $xvfb_pid 2>/dev/null || true' EXIT
export DISPLAY=:99
# No hay tarjeta de sonido en el contenedor y blastem aborta si SDL no puede
# abrir audio.
export SDL_AUDIODRIVER=dummy
for _ in $(seq 50); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.1; done

# -g desactiva OpenGL: bajo Xvfb no hay GL acelerado y el render por software
# alcanza de sobra para esto.
blastem -g -r "$region" "$rom" >/tmp/blastem.log 2>&1 &
blastem_pid=$!
trap 'kill $blastem_pid $xvfb_pid 2>/dev/null || true' EXIT
sleep "$warmup"

if ! kill -0 $blastem_pid 2>/dev/null; then
    echo "blastem terminó antes de tiempo:" >&2; cat /tmp/blastem.log >&2; exit 1
fi

# SDL ignora las teclas sintéticas de XSendEvent (que es lo que hace
# "xdotool key --window"), así que hay que enfocar la ventana y mandar la
# tecla por XTEST.
win=$(xdotool search --sync --onlyvisible --class blastem | head -1)
xdotool windowfocus --sync "$win"

if [ -n "$keys" ]; then
    for key in $keys; do xdotool keydown --clearmodifiers "$key"; done
    sleep "$hold"
    for key in $keys; do xdotool keyup --clearmodifiers "$key"; done
    sleep 0.5
fi

xdotool key --clearmodifiers p
for _ in $(seq 50); do [ -s /shots/shot.png ] && break; sleep 0.1; done

if [ ! -s /shots/shot.png ]; then
    echo "no salió screenshot; log de blastem:" >&2; cat /tmp/blastem.log >&2; exit 1
fi
cp /shots/shot.png "$out"
echo "screenshot -> $out"
