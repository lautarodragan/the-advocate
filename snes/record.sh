#!/bin/bash
# Corre una ROM de SNES sin pantalla y graba el audio a un WAV.
#
# mednafen tiene -soundrecord, que vuelca lo que sale del DSP. Con eso se puede
# medir qué está sonando en vez de confiar en el oído.
#
# El driver de sonido va en dummy: no hace falta que suene por parlante para
# grabar, y así no depende de que haya un dispositivo libre. Para escucharlo de
# verdad hay que usar -sound.driver sdl, porque el ALSA propio de mednafen abre
# hw:0, que PipeWire tiene tomado.
set -euo pipefail

usage="uso: record.sh ROM SALIDA.wav [segundos]"
rom=${1:?$usage}
out=${2:?$usage}
seconds=${3:-4}

# Configuración propia, separada de la de screenshot.sh: mednafen guarda las
# opciones de la línea de comandos al salir, y aquél pasa -sound 0. Compartiendo
# HOME, esto grababa silencio sin decir nada.
export HOME=/tmp/mednafen-audio
mkdir -p "$HOME"
Xvfb :99 -screen 0 640x480x24 >/dev/null 2>&1 &
xvfb_pid=$!
trap 'kill $xvfb_pid 2>/dev/null || true' EXIT
export DISPLAY=:99 SDL_AUDIODRIVER=dummy
for _ in $(seq 50); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.1; done

rm -f /tmp/out.wav
timeout "$((seconds + 8))" mednafen \
    -soundrecord /tmp/out.wav \
    -sound 1 \
    -sound.driver dummy \
    -video.driver 0 \
    -snes.correct_aspect 0 \
    "$rom" >/tmp/mednafen.log 2>&1 &
pid=$!
sleep "$seconds"
kill $pid 2>/dev/null || true
wait $pid 2>/dev/null || true

[ -s /tmp/out.wav ] || { echo "no salió WAV" >&2; tail -20 /tmp/mednafen.log >&2; exit 1; }
cp /tmp/out.wav "$out"
echo "wav -> $out ($(stat -c %s "$out") bytes)"
