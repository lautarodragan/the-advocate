#!/usr/bin/env bash
# Captura el juego original corriendo en EasyRPG, sin pantalla.
#
#   rom/easyrpg.sh MAPA SEGUNDOS SALIDA      (AVANZAR=1 para pasar de página)
#
# Y con variables de entorno, lo que el player acepta para depurar:
#
#   CELDA="70 97"   dónde arranca el héroe, con --start-position
#   GRUPO="11"      con qué actores, con --start-party
#   TECLAS="Down"   qué teclas mandarle, una por segundo, en vez de Enter
#   REPLAY=archivo  la entrada desde un archivo, con --replay-input; ver abajo
#   TITULO=1        arrancar en la pantalla de título en vez de en MAPA
#   PARTIDAS=dir    dónde deja y busca las partidas, en vez de en SALIDA
#   EXTRA="..."     cualquier otro argumento suelto
#
# **Las teclas por xdotool se pierden.** Medido el 2026-09-10 con
# --record-input: de cuatro `xdotool key` llegaron dos, porque suelta la tecla
# en milisegundos y el player la muestrea a 60 cuadros. Para una secuencia que
# tenga que llegar entera —hablarle al save point, guardar, volver al título y
# abrir el menú de cargar— va REPLAY, que es el formato de --record-input:
#
#   H EasyRPG Player Recording
#   V 2 0.8.1.1
#   F 600,DECISION          en el cuadro 600, Enter
#   F 700,DECISION
#
# Las teclas se llaman como en `Input::InputButton`: DECISION, CANCEL, UP,
# DOWN, LEFT, RIGHT. Así se consiguió la captura del menú de archivos con una
# partida de verdad: guardar sobre el save point del mapa 8 con
# `CELDA="9 56" GRUPO="14 12"`, y después `TITULO=1` con DECISION en el cuadro
# 400 —el cursor ya arranca en "Resume the Story" cuando hay partida; un DOWN
# antes lo lleva a "End" y el juego se cierra—.
#
# `--start-position` es lo que hace posible pedirle una escena concreta en vez
# de esperar a que el juego llegue sola: sin eso, mirar dos NPCs que se tapan en
# la fila 98 del mapa 1 pedía jugar hasta ahí.
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
# Corre sin tope de cuadros a propósito: cuanto más rápido emule, menos hay que
# esperar para llegar al mensaje. Que se coma los cores mientras dura está bien;
# taro prefiere eso a que las pruebas tarden, y si molesta lo acota por el
# contenedor. Lo que sí importa es el orden de apagado de acá abajo —primero el
# player, después el Xvfb—: al revés, el player sobrevive a su pantalla y se
# queda en el lazo libre para siempre. Ya pasó con un proceso de una prueba.
# Con FPS=60 se le pone tope.
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

rm -rf "$SALIDA"; mkdir -p "$SALIDA" "${PARTIDAS:-$SALIDA}"
printf '[Player]\nAutomaticScreenshots=1\nAutomaticScreenshotsInterval=1\n' \
    > "$CFG/config.ini"

Xvfb :99 -screen 0 640x480x24 >/dev/null 2>&1 &
XVFB=$!
sleep 2
if [ "${TITULO:-0}" = "1" ]; then
    ARRANQUE=""
else
    ARRANQUE="--new-game --start-map-id $MAPA"
fi
DISPLAY=:99 "$ERPG/easyrpg-player" --project-path "$JUEGO" \
    --rtp-path /extras/rtp $ARRANQUE --window \
    ${CELDA:+--start-position $CELDA} ${GRUPO:+--start-party $GRUPO} \
    ${REPLAY:+--replay-input $REPLAY} \
    ${EXTRA:-} \
    --no-vsync ${FPS:+--fps-limit $FPS} --config-path "$CFG" \
    --save-path "${PARTIDAS:-$SALIDA}" \
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
    if [ -n "${TECLAS:-}" ]; then
        for t in $TECLAS; do
            DISPLAY=:99 xdotool key --window "$VENTANA" "$t" 2>/dev/null
        done
    elif [ "${AVANZAR:-0}" = "1" ]; then
        DISPLAY=:99 xdotool key --window "$VENTANA" Return 2>/dev/null
    fi
done
kill $PLAYER 2>/dev/null; wait $PLAYER 2>/dev/null
kill $XVFB 2>/dev/null;   wait $XVFB 2>/dev/null
rm -rf "$CFG"
if [ -n "${PARTIDAS:-}" ]; then
    mv "$PARTIDAS"/*.png "$SALIDA"/ 2>/dev/null
fi
echo "$(ls "$SALIDA"/*.png 2>/dev/null | wc -l) capturas en $SALIDA"
