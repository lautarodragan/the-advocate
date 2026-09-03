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

# Todo lo de esta corrida en un directorio propio, igual que screenshot.sh y
# por lo mismo: dos de éstos a la vez peleaban por el display :99 y por el WAV
# de salida. Que HOME salga de acá arregla de paso lo que antes había que
# recordar a mano —mednafen guarda al salir las opciones de la línea de
# comandos, y screenshot.sh pasa -sound 0; compartiendo HOME, esto grababa
# silencio sin decir nada—.
tmp=$(mktemp -d)
export HOME="$tmp/mednafen"
mkdir -p "$HOME"
log="$tmp/mednafen.log"
wav="$tmp/out.wav"
pid=""

Xvfb -displayfd 3 -screen 0 640x480x24 3>"$tmp/display" >/dev/null 2>&1 &
xvfb_pid=$!
trap 'kill $xvfb_pid ${pid:-} 2>/dev/null || true; rm -rf "$tmp"' EXIT
for _ in $(seq 100); do [ -s "$tmp/display" ] && break; sleep 0.1; done
[ -s "$tmp/display" ] || { echo "Xvfb no arrancó" >&2; exit 1; }
export DISPLAY=":$(tr -d '[:space:]' <"$tmp/display")" SDL_AUDIODRIVER=dummy
for _ in $(seq 50); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.1; done

timeout "$((seconds + 8))" mednafen \
    -soundrecord "$wav" \
    -sound 1 \
    -sound.driver dummy \
    -video.driver 0 \
    -snes.correct_aspect 0 \
    "$rom" >"$log" 2>&1 &
pid=$!
sleep "$seconds"
kill $pid 2>/dev/null || true
wait $pid 2>/dev/null || true

[ -s "$wav" ] || { echo "no salió WAV" >&2; tail -20 "$log" >&2; exit 1; }
mkdir -p "$(dirname "$out")"
cp "$wav" "$out"
echo "wav -> $out ($(stat -c %s "$out") bytes)"
