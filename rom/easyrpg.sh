#!/usr/bin/env bash
# Captura el juego original corriendo en EasyRPG, sin pantalla.
#
#   rom/easyrpg.sh MAPA SEGUNDOS SALIDA      (AVANZAR=1 para pasar de página)
#
# Es el único oráculo externo que tiene este repo. Todo lo demás se compara
# contra nuestra propia referencia en Python, y ahí vale la trampa de siempre:
# si los dos lados se equivocan igual, la comparación da cero. Una captura del
# juego de verdad rompe ese empate — y ya lo hizo: con ella se descubrió que el
# índice 0 de la paleta del System es transparente y que la fuente del juego es
# rmg2000 y no ttyp0. Las dos cosas daban una ventana que se veía bien.
#
# EasyRPG no vive en el repo. Se baja a /extras, del mismo lado que el juego:
#   curl -sL -o /extras/erpg.tar.gz \
#     https://easyrpg.org/downloads/player/0.8.1.1/easyrpg-player-0.8.1.1-linux.tar.gz
#   mkdir -p /extras/erpg && tar xzf /extras/erpg.tar.gz -C /extras/erpg
#
# Ojo con una trampa del binario oficial: trae su propio SDL2 compilado **sin
# el backend de wayland**. Con SDL_VIDEODRIVER=wayland puesto en el entorno
# —que es común en Arch— falla con "wayland not available" y el mensaje no dice
# que la culpa es de la variable. Acá se corre sobre Xvfb, así que no aplica;
# desde el host, `SDL_VIDEODRIVER=x11`.
#
# El `--fps-limit` no es cosmético: con `--no-vsync` y sin tope, un player que
# sobreviva a su Xvfb corre el lazo libre y se come todos los cores. Ya pasó
# con un proceso que quedó colgado de una prueba.
#
# Las capturas no se piden con F7 sino con las automáticas de EasyRPG, cada un
# segundo: inyectar la tecla depende de que la ventana ya exista y de que el
# juego haya terminado de cargar, y eso salía distinto en cada corrida.
set -uo pipefail
MAPA=${1:-145}
SEGUNDOS=${2:-20}
SALIDA=${3:-/extras/capturas/easyrpg}
ERPG=${ERPG:-/extras/erpg}
JUEGO=${GAME_DIR:-/extras/abl-rm}
CFG=$(mktemp -d)

rm -rf "$SALIDA"; mkdir -p "$SALIDA"
printf '[Player]\nAutomaticScreenshots=1\nAutomaticScreenshotsInterval=1\n' \
    > "$CFG/config.ini"

Xvfb :99 -screen 0 640x480x24 >/dev/null 2>&1 &
XVFB=$!
sleep 2
DISPLAY=:99 "$ERPG/easyrpg-player" --project-path "$JUEGO" \
    --rtp-path /extras/rtp --new-game --start-map-id "$MAPA" --window \
    --no-vsync --fps-limit 60 --config-path "$CFG" --save-path "$SALIDA" \
    </dev/null >"$CFG/log" 2>&1 &
PLAYER=$!
sleep 12                        # que cargue la base y el mapa
# Con AVANZAR=1 se le manda Enter una vez por segundo y el juego pasa de
# página; sin eso el primer mensaje se queda quieto esperando al jugador, que
# es lo que hace falta para comparar contra una página conocida. Avanzar
# dejaba capturas de la página cuatro y la comparación medía dos textos
# distintos.
VENTANA=$(DISPLAY=:99 xdotool search --name "EasyRPG" | tail -1)
for _ in $(seq 1 "$SEGUNDOS"); do
    sleep 1
    if [ "${AVANZAR:-0}" = "1" ]; then
        DISPLAY=:99 xdotool key --window "$VENTANA" Return 2>/dev/null
    fi
done
kill $PLAYER 2>/dev/null; wait $PLAYER 2>/dev/null
kill $XVFB 2>/dev/null;   wait $XVFB 2>/dev/null
rm -rf "$CFG"
echo "$(ls "$SALIDA"/*.png 2>/dev/null | wc -l) capturas en $SALIDA"
