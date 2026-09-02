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

# Configuración propia: mednafen guarda al salir lo que se le pase por línea de
# comandos, y el -sound 0 de acá le arruinaba la grabación a record.sh.
export HOME=/tmp/mednafen-video
mkdir -p "$HOME"

Xvfb :99 -screen 0 640x480x24 >/dev/null 2>&1 &
xvfb_pid=$!
trap 'kill $xvfb_pid $pid 2>/dev/null || true' EXIT
export DISPLAY=:99 SDL_AUDIODRIVER=dummy
for _ in $(seq 50); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.1; done

# La cruceta va atada a las flechas. Por defecto mednafen usa WASD, que además
# depende de la configuración de quien corra esto; fijarlo acá hace que el
# script no dependa de nada de afuera. Los números son scancodes de SDL.
timeout "$((seconds + 20))" mednafen \
    -snes.input.port1.gamepad.up    "keyboard 0x0 82" \
    -snes.input.port1.gamepad.down  "keyboard 0x0 81" \
    -snes.input.port1.gamepad.left  "keyboard 0x0 80" \
    -snes.input.port1.gamepad.right "keyboard 0x0 79" \
    -sound 0 \
    -snes.correct_aspect 0 \
    -snes.stretch 0 \
    -snes.xscale 1 -snes.yscale 1 \
    "$rom" >/tmp/mednafen.log 2>&1 &
pid=$!
sleep 3

# Dónde está la ventana del emulador se le pregunta a X, que lo sabe. Deducirlo
# de los pixeles no es confiable: el fondo del servidor es negro y un mapa con
# el borde de arriba negro se confunde con él, así que el recorte se desliza
# hacia abajo y la comparación falla por algo que no tiene nada que ver.
#
# Mednafen le pone a la ventana el nombre de la ROM, no "Mednafen". Y no se la
# busca con `xdotool search --name`, que no la encuentra: sin gestor de ventanas
# mednafen publica _NET_WM_NAME pero no WM_NAME, y `search` mira la segunda.
# Enumerar y preguntar el nombre de cada una sí funciona.
nombre=$(basename "${rom%.*}")
window=""
for _ in $(seq 50); do
    for w in $(xdotool search "" 2>/dev/null); do
        if [ "$(xdotool getwindowname "$w" 2>/dev/null)" = "$nombre" ]; then
            window=$w
            break
        fi
    done
    [ -n "$window" ] && break
    sleep 0.1
done
[ -n "$window" ] || echo "aviso: no encontré la ventana del emulador" >&2

if [ -n "$keys" ]; then
    for key in $keys; do
        xdotool keydown ${window:+--window "$window"} "$key" 2>/dev/null || true
    done
fi
sleep "$seconds"

geom=$(xdotool getwindowgeometry --shell "$window" 2>/dev/null || true)
win_x=$(printf '%s\n' "$geom" | sed -n 's/^X=//p')
win_y=$(printf '%s\n' "$geom" | sed -n 's/^Y=//p')

mkdir -p "$(dirname "$out")"
import -display :99 -window root -silent "$out.raw.png" 2>/dev/null
kill $pid 2>/dev/null || true
wait $pid 2>/dev/null || true

[ -s "$out.raw.png" ] || { echo "no salió captura" >&2; tail -20 /tmp/mednafen.log >&2; exit 1; }
python3 "$(dirname "$0")/../tools/snes_crop.py" "$out.raw.png" "$out" \
    ${win_x:+--en "$win_x" "$win_y"}
rm -f "$out.raw.png"
