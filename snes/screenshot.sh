#!/bin/bash
# Corre una ROM de SNES sin pantalla y captura lo que dibuja.
#
# El atajo de captura de mednafen es una tecla, así que usarlo pediría simular
# pulsaciones y adivinar cuál es su ventana. Se captura el display entero de
# Xvfb y después se recorta en Python, que es bastante más difícil de romper.
#
# Las teclas, si se pasan, se mantienen apretadas mientras la ROM corre: sirven
# para capturar con la cámara movida o el personaje caminando.
set -uo pipefail

usage="uso: screenshot.sh ROM SALIDA.png [segundos] [teclas]"
rom=${1:?$usage}
out=${2:?$usage}
seconds=${3:-4}
keys=${4:-}

export HOME=/tmp/mednafen
mkdir -p "$HOME"

Xvfb :99 -screen 0 640x480x24 >/dev/null 2>&1 &
xvfb_pid=$!
trap 'kill $xvfb_pid $pid 2>/dev/null || true' EXIT
export DISPLAY=:99 SDL_AUDIODRIVER=dummy
for _ in $(seq 50); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.1; done

timeout "$((seconds + 20))" mednafen \
    -sound 0 \
    -snes.correct_aspect 0 \
    -snes.stretch 0 \
    -snes.xscale 1 -snes.yscale 1 \
    "$rom" >/tmp/mednafen.log 2>&1 &
pid=$!
sleep 3

if [ -n "$keys" ]; then
    window=$(xdotool search --name Mednafen 2>/dev/null | tail -1)
    for key in $keys; do
        xdotool keydown ${window:+--window "$window"} "$key" 2>/dev/null || true
    done
fi
sleep "$seconds"

mkdir -p "$(dirname "$out")"
import -display :99 -window root -silent "$out.raw.png" 2>/dev/null
kill $pid 2>/dev/null || true
wait $pid 2>/dev/null || true

[ -s "$out.raw.png" ] || { echo "no salió captura" >&2; tail -20 /tmp/mednafen.log >&2; exit 1; }
python3 "$(dirname "$0")/../tools/snes_crop.py" "$out.raw.png" "$out"
rm -f "$out.raw.png"
