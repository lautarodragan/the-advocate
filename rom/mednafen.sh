#!/bin/bash
# Corre una ROM en **mednafen** y captura lo que dibuja. Segunda opinión.
#
# La tanda corre en snes9x, por libretro, cuadro a cuadro y sin servidor X. Esto
# es lo contrario en todo: otro emulador, con ventana, esperando segundos de
# reloj. Existe por una razón concreta y medida: snes9x es permisivo en cosas
# donde la consola real no lo es, y en un mismo día se colaron dos errores que
# sólo mednafen ve —una variable de RAM sin inicializar, que snes9x tapa porque
# arranca la RAM en cero, y escrituras a CGRAM fuera del vblank, que snes9x
# acepta—. Los dos los encontró taro jugando, con la tanda en verde.
#
# Este archivo estuvo borrado unos días: cuando se migró la tanda a libretro,
# mednafen quedó como un camino que nadie corría, y eso en este repo es peor que
# no tenerlo. Vuelve con `snes-mednafen`, que sí lo corre.
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

# Todo lo de esta corrida vive en un directorio propio y se va con ella. Antes
# eran tres cosas fijas —el display :99, HOME y el log— y las tres hacían que
# dos capturas simultáneas se pisaran: comparten un solo servidor X, y como
# acá se captura la raíz del display entero y la ventana se busca por el
# basename de la ROM, la segunda captura podía salir de la ROM equivocada sin
# que nada avisara.
#
# Configuración propia: mednafen guarda al salir lo que se le pase por línea de
# comandos, y el -sound 0 de acá le arruinaba la grabación a record.sh.
tmp=$(mktemp -d)
export HOME="$tmp/mednafen"
mkdir -p "$HOME"
log="$tmp/mednafen.log"
pid=""

# -displayfd deja que el servidor elija un display libre y lo informe, en vez
# de clavar uno: dos corridas a la vez no tienen por qué pelearse por :99.
Xvfb -displayfd 3 -screen 0 640x480x24 3>"$tmp/display" >/dev/null 2>&1 &
xvfb_pid=$!
trap 'kill $xvfb_pid ${pid:-} 2>/dev/null || true; rm -rf "$tmp"' EXIT
for _ in $(seq 100); do [ -s "$tmp/display" ] && break; sleep 0.1; done
[ -s "$tmp/display" ] || { echo "Xvfb no arrancó" >&2; exit 1; }
export DISPLAY=":$(tr -d '[:space:]' <"$tmp/display")" SDL_AUDIODRIVER=dummy
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
    "$rom" >"$log" 2>&1 &
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
import -display "$DISPLAY" -window root -silent "$out.raw.png" 2>/dev/null
kill $pid 2>/dev/null || true
wait $pid 2>/dev/null || true

[ -s "$out.raw.png" ] || { echo "no salió captura" >&2; tail -20 "$log" >&2; exit 1; }
python3 "$(dirname "$0")/../tools/snes_crop.py" "$out.raw.png" "$out" \
    ${win_x:+--en "$win_x" "$win_y"}
rm -f "$out.raw.png"
