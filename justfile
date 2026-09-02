# Renderiza un mapa a render/MapXXXX.png. Sin dependencias que instalar:
# usa Pillow, que ya está en el sistema.
#   just render        -> mapa 1
#   just render 8
render map_id="1":
  python3 tools/render_map.py --map-id {{map_id}}

# Lista los mapas del juego con su chipset, sus eventos y los assets que falten.
maps:
  python3 tools/list_maps.py

# Lo mismo, pero renderizando todo: verifica que ningún mapa rompa el pipeline.
check:
  python3 tools/list_maps.py --render

# Vuelca los .lmu a data/ como JSON + grillas de tiles en texto, versionables.
export:
  python3 tools/export_json.py --verify

# --- Mega Drive ------------------------------------------------------------
# El cross-compiler de m68k y el emulador viven en un contenedor: no se instala
# nada en el sistema. La imagen base va pinneada por digest.

# edlink es de krikzz y vive en el repo de recursos del EverDrive; no lo
# copiamos a git, se toma de ahí al armar la imagen.
edlink := "/home/taro/git/gaming/mega-ed-pub/edlink.exe"

md-image:
  cp {{edlink}} md/edlink.exe
  podman build -t abl-md md

# ChipSet + mapa -> tiles de 8x8 a 4bpp, paletas de 9 bits y tilemap, más el
# render de Python contra el que se compara después.
md-convert map_id="8":
  mkdir -p md/shots
  python3 tools/md_convert.py --map-id {{map_id}} -o md/src/mapdata \
      --reference md/shots/reference.png
  python3 tools/md_music.py --map-id {{map_id}} -o md/src/musicdata
  python3 tools/render_map.py --map-id {{map_id}} --no-events -o md/shots/python.png

md-build:
  podman run --rm --network=none --mount=type=bind,src=.,dst=/abl -w /abl/md abl-md make

# Corre la ROM sin pantalla y saca un screenshot. Las teclas son la cruceta del
# control 1: se mantienen apretadas para mover la cámara antes de capturar.
md-shot region="E" nombre="origen" teclas="" segundos="4":
  podman run --rm --network=none --mount=type=bind,src=.,dst=/abl abl-md \
      /abl/md/screenshot.sh /abl/md/build/abl.bin \
      /abl/md/shots/{{region}}-{{nombre}}.png 3 {{region}} "{{teclas}}" {{segundos}}

# Simula la caminata con las mismas reglas que la ROM para saber en qué tile
# tuvo que frenar, y de ahí saca la cámara y el rectángulo del sprite.
md-compare region="E" nombre="parado" map_id="8" walk="none":
  python3 tools/md_compare.py md/shots/{{region}}-{{nombre}}.png \
      md/shots/reference.png md/shots/python.png \
      --map-id {{map_id}} --walk {{walk}} \
      -o md/shots/comparacion-{{region}}-{{nombre}}.png

# Todo el camino. El personaje arranca en el tile abierto más cercano al centro
# y se lo camina en cada dirección sin soltar, hasta que choca. Dónde frena se
# calcula en Python con las mismas reglas de colisión: si la ROM y la
# simulación no coinciden, queda en otro tile y la comparación falla. O sea que
# esto verifica la colisión, no sólo el render.
#
# `segundos` es cuánto se mantiene la cruceta: tiene que alcanzar para cruzar
# el mapa a 2 px por cuadro. Para mapas grandes, subilo.
md map_id="8" segundos="12":
  just md-convert {{map_id}}
  just md-build
  just md-shot E parado
  just md-compare E parado {{map_id}} none
  just md-shot E derecha "Right" {{segundos}}
  just md-compare E derecha {{map_id}} right
  just md-shot E izquierda "Left" {{segundos}}
  just md-compare E izquierda {{map_id}} left
  just md-shot E arriba "Up" {{segundos}}
  just md-compare E arriba {{map_id}} up
  just md-shot E abajo "Down" {{segundos}}
  just md-compare E abajo {{map_id}} down
  just md-shot U parado
  just md-compare U parado {{map_id}} none
  just md-shot U derecha "Right" {{segundos}}
  just md-compare U derecha {{map_id}} right

# --- EverDrive por USB -----------------------------------------------------
# El cartucho aparece como un puerto serie. Si no es /dev/ttyACM0, pasale otro.
# Hace falta permiso sobre el dispositivo: normalmente, estar en el grupo
# `uucp` o `dialout`.

# Sube la ROM al EverDrive y la arranca. Sin sacar la SD.
md-upload dev="/dev/ttyACM0":
  podman run --rm --network=none --device {{dev}} --mount=type=bind,src=.,dst=/abl \
      abl-md mono /opt/edlink/edlink.exe run --file /abl/md/build/abl.bin

# Escucha lo que la ROM escriba en el FIFO del cartucho: un printf por USB.
md-usb dev="/dev/ttyACM0":
  podman run --rm --network=none --device {{dev}} \
      abl-md mono /opt/edlink/edlink.exe usbrd --len -1 --tout -1 --print

# Datos del cartucho, para verificar que el USB conecta.
md-devinfo dev="/dev/ttyACM0":
  podman run --rm --network=none --device {{dev}} \
      abl-md mono /opt/edlink/edlink.exe devinf

# Graba lo que la ROM le escribe al PSG y lo compara con lo que pidió el
# conversor de música. Si coinciden, suena exactamente lo que se generó.
md-music map_id="8" segundos="12":
  podman run --rm --network=none --mount=type=bind,src=.,dst=/abl abl-md \
      /abl/md/vgmlog.sh /abl/md/build/abl.bin /abl/md/shots/musica.vgm {{segundos}}
  python3 tools/md_music_check.py md/shots/musica.vgm --map-id {{map_id}}

# La ROM en una ventana de verdad, para moverla con las flechas.
#
# Esta corre en el host, no en un contenedor, y es a propósito. Para abrir una
# ventana había que compartirle /tmp/.X11-unix, y eso le da al contenedor un
# cliente X con acceso al servidor entero: puede leer el teclado de todas las
# ventanas e inyectar eventos en otras. Con ese agujero abierto el contenedor ya
# no aislaba nada, así que no valía lo que costaba.
#
# El emulador es mednafen, de pacman. blastem sería más fiel para Mega Drive,
# pero el único que hay es un binario precompilado bajado de la web en 2019, y
# eso no se corre en el host. Sigue usándose para verificar (md-shot, md-music),
# donde va adentro del contenedor, sin red y sin sockets.
#
# -sound.driver sdl es obligatorio: el driver ALSA propio de mednafen abre el
# dispositivo crudo hw:0, que PipeWire tiene tomado en exclusiva, y falla con
# "Device or resource busy". Por SDL sale por PipeWire y convive con todo.
md-play region="overseas_pal":
  mednafen -command.exit "keyboard 0x0 20+ctrl" -force_module md -md.region {{region}} -sound.driver sdl \
      md/build/abl.bin

# Lo mismo pero mudo.
md-play-mudo region="overseas_pal":
  mednafen -command.exit "keyboard 0x0 20+ctrl" -force_module md -md.region {{region}} -sound 0 md/build/abl.bin

# --- Super Nintendo --------------------------------------------------------
# Rama aparte, para ver si la SNES se acerca más al original que la Mega Drive.
# No toca nada del port a Mega Drive.
#
# Ya no hace falta ningún contenedor acá. El ensamblador de 65816 es nuestro
# (tools/w65.py) y el emulador es mednafen, que está en pacman. Todo el
# toolchain son dos cosas: python y mednafen.
#
# El contenedor sigue existiendo para una sola cosa, snes-validar, que compara
# w65.py contra ca65. No se necesita para compilar.

# ChipSet + mapa -> tiles de 8x8 a 8bpp, paleta de 15 bits y tilemap, más el
# render de Python contra el que se compara después.
snes-convert mapa="7":
  mkdir -p snes/shots
  python3 tools/snes_convert.py --map-id {{mapa}} --reference snes/shots/python.png

snes-build:
  python3 tools/w65.py snes/src/main.s -o snes/build/abl.sfc

# Corre la ROM sin pantalla y captura lo que dibuja. Las teclas se mantienen
# apretadas mientras corre, para capturar con la cámara movida.
snes-shot nombre="mapa" segundos="4" teclas="":
  snes/screenshot.sh snes/build/abl.sfc snes/shots/{{nombre}}.png {{segundos}} "{{teclas}}"

# La captura contra el render de Python, pixel por pixel y a 15 bits.
snes-compare nombre="mapa" x="0" y="0":
  python3 tools/snes_compare.py snes/shots/{{nombre}}.png snes/shots/python.png \
      --camara {{x}} {{y}} -o snes/shots/comparacion-{{nombre}}.png

# Camina en una dirección hasta chocar contra el borde del mapa y compara lo que
# la consola muestra contra lo que Python calcula que tendría que mostrar:
# el mapa, la cámara siguiendo al héroe, y el héroe en su pose parada.
snes-walk mapa="7" direccion="none" segundos="8":
  just snes-shot {{direccion}} {{segundos}} "$(just _tecla {{direccion}})"
  python3 tools/snes_expect.py --map-id {{mapa}} --walk {{direccion}} \
      --saltar snes/shots/saltar-{{direccion}}.txt \
      -o snes/shots/esperado-{{direccion}}.png
  python3 tools/snes_compare.py snes/shots/{{direccion}}.png \
      snes/shots/esperado-{{direccion}}.png \
      --saltar snes/shots/saltar-{{direccion}}.txt \
      -o snes/shots/comparacion-{{direccion}}.png

# Planta al héroe en una celda elegida y compara sin caminar. Llegar a un lugar
# puntual caminando depende de cuántos segundos se mantenga la cruceta, que es
# frágil; acá la cámara queda donde uno quiere y la captura no se negocia.
snes-parado mapa="1" tx="75" ty="88" nombre="parado":
  mkdir -p snes/shots
  python3 tools/snes_convert.py --map-id {{mapa}} --inicio {{tx}} {{ty}}
  just snes-build
  just snes-shot {{nombre}} 4 ""
  python3 tools/snes_expect.py --map-id {{mapa}} --hero-tile {{tx}} {{ty}} \
      --dir down --saltar snes/shots/saltar-{{nombre}}.txt \
      -o snes/shots/esperado-{{nombre}}.png
  python3 tools/snes_compare.py snes/shots/{{nombre}}.png \
      snes/shots/esperado-{{nombre}}.png \
      --saltar snes/shots/saltar-{{nombre}}.txt \
      -o snes/shots/comparacion-{{nombre}}.png

# Pasa los 335 mapas por los límites del hardware sin armar ninguna ROM: dice
# cuáles no entran y por qué. Correr cuando se toque el conversor o el reparto
# de la VRAM.
snes-relevar desde="0":
  python3 tools/snes_survey.py --desde {{desde}}

# Cuánto llega a caminar el héroe en cada mapa, con las mismas reglas que la
# ROM. Sirve para elegir contra qué mapa probar el redibujado: uno enorme lleno
# de paredes frena en la tercera celda y no prueba nada.
snes-recorrido desde="66":
  python3 tools/snes_recorrido.py --desde {{desde}}

# La tanda de regresión: un mapa por cada cosa que puede romperse.
#
# Los tres primeros son los que cerraron los hitos anteriores y tienen que
# seguir en cero. Los tres últimos son los que ejercitan el redibujado: mapa 6
# recorre 100 celdas por los dos ejes, o sea que la ventana da la vuelta tres
# veces a lo alto; mapa 8 es Lashe City, que además necesita 512 tiles de
# sprite y por eso le toca el otro reparto de VRAM; y mapa 52 mide 1000x80
# celdas, con una grilla de 40 KB que cruza el corte de banco de LoROM.
#
# Los dos siguientes ejercitan el reparto de CGRAM: mapa 1 es el primero del
# juego y su capa de encima se lleva cuatro paletas, dejándole 63 colores al
# fondo; mapa 348 es el caso contrario, donde el fondo usa los 95 que puede y la
# capa de encima tiene que fusionar 27 colores para entrar en lo que sobra.
#
# Los dos últimos son el borde de abajo de la pantalla, y van de a pares porque
# se equivocan para lados opuestos. En (75,88) del mapa 1 hay cuatro NPCs justo
# debajo del borde, en la banda donde la Y de OAM es ambigua: con el descarte
# corrido para un lado reaparecen arriba. En (75,90) los mismos cuatro asoman
# apenas la cabeza: con el descarte corrido para el otro lado desaparecen. Uno
# solo de los dos casos deja pasar la mitad de los errores posibles.
#
# Ninguna caminata los tocaba: todas terminan contra un borde del mapa, y ahí la
# cámara queda pegada y los NPCs no caen nunca en esa banda.
#
# Los segundos son cuánto se mantiene la cruceta: tiene que alcanzar para
# cruzar el mapa a 2 pixeles por cuadro.
snes-hitos:
  just snes-heroe 73 8
  just snes-heroe 18 8
  just snes-heroe 119 8
  just snes-heroe 6 18
  just snes-heroe 8 25
  just snes-heroe 52 45
  just snes-heroe 1 18
  just snes-heroe 348 8
  just snes-parado 1 75 88 borde
  just snes-parado 1 75 90 medias

# El héroe: parado y caminando en las cuatro direcciones.
snes-heroe mapa="7" segundos="8":
  just snes-convert {{mapa}}
  just snes-build
  just snes-walk {{mapa}} none {{segundos}}
  just snes-walk {{mapa}} right {{segundos}}
  just snes-walk {{mapa}} left {{segundos}}
  just snes-walk {{mapa}} up {{segundos}}
  just snes-walk {{mapa}} down {{segundos}}

_tecla direccion:
  @case {{direccion}} in up) echo Up;; down) echo Down;; left) echo Left;; right) echo Right;; *) echo "";; esac

# Todo el camino del mapa: convertir, compilar, y verificar la cámara en las
# cuatro esquinas a las que puede llegar.
#
# Cada dirección se mantiene apretada hasta que la cámara choca contra el borde
# del mapa, así que dónde tiene que quedar no se estima: es exactamente
# CAM_MAX_X y CAM_MAX_Y, que salen del tamaño del mapa. Si la ROM se moviera de
# más, de menos, o no frenara, la comparación falla.
snes-mapa mapa="7" segundos="5":
  just snes-convert {{mapa}}
  just snes-build
  just snes-shot centro {{segundos}}
  just snes-compare centro 0 0
  just snes-shot derecha {{segundos}} "Right"
  just snes-compare derecha $(just _cam-x) 0
  just snes-shot abajo {{segundos}} "Down"
  just snes-compare abajo 0 $(just _cam-y)
  just snes-shot esquina {{segundos}} "Right Down"
  just snes-compare esquina $(just _cam-x) $(just _cam-y)

# Los topes de la cámara salen del .inc que generó el conversor, así que las
# recetas no repiten números que dependen del mapa.
_cam-x:
  @grep -oP 'CAM_MAX_X\s*=\s*\K\d+' snes/src/mapdata.inc
_cam-y:
  @grep -oP 'CAM_MAX_Y\s*=\s*\K\d+' snes/src/mapdata.inc

# --- verificación del ensamblador ------------------------------------------
# w65.py reemplaza a ca65 y ld65. Que se pueda confiar en él no es una promesa:
# se genera un fuente con cada mnemónico en cada modo de direccionamiento que la
# tabla declara, se ensambla con las dos cadenas y se comparan los bytes.
#
# Correr esto cada vez que se toquen las tablas de opcodes. Necesita podman, así
# que va desde el host, no desde adentro del contenedor.
#
# Lo que compara es el primer banco: w65.py arma el cartucho entero, 256 KB, y
# snes.cfg describe uno de 32. Del resto se comprueba que sea relleno.
#
# Lo que valida es la codificación de instrucciones, que es lo que se puede
# equivocar en silencio. El layout de la ROM —banqueo LoROM, 128 KB, checksum—
# ya no se compara: ca65 necesitaría una configuración bastante más compleja
# para expresarlo, y main.s dejó de entrar en los 32 KB de snes.cfg cuando el
# banco de muestras creció. A cambio, el layout sí se verifica de punta a punta
# cada vez que la ROM arranca y suena en el emulador.
#
# snes/snes.cfg y snes/Makefile existen sólo para esto.

snes-image:
  podman build -t abl-snes snes

snes-validar:
  python3 tools/w65_coverage.py -o snes/build/cobertura.s
  podman run --rm --network=none --mount=type=bind,src=.,dst=/abl -w /abl/snes abl-snes \
      sh -c 'ca65 --cpu 65816 -o build/cobertura.o build/cobertura.s \
             && ld65 -C snes.cfg -o build/cobertura-ca65.sfc build/cobertura.o'
  python3 tools/w65.py --sin-checksum snes/build/cobertura.s -o snes/build/cobertura-w65.sfc
  python3 tools/w65_check.py snes/build/cobertura-w65.sfc snes/build/cobertura-ca65.sfc

# El MIDI del mapa a muestras BRR y un stream para el DSP.
snes-music mapa="67":
  python3 tools/snes_music.py --map-id {{mapa}}

# Corre la ROM sin pantalla, graba el audio y compara lo que suena contra el
# MIDI. Sirve para verificar sin escuchar: para cada nota que debería estar
# sonando se mide su energía y la de un señuelo un cuarto de tono más arriba.
snes-check mapa="67" segundos="60":
  mkdir -p snes/shots
  snes/record.sh snes/build/abl.sfc snes/shots/tema.wav {{segundos}}
  python3 tools/snes_check.py snes/shots/tema.wav --map-id {{mapa}}

# El mismo MIDI tocado por FluidSynth en la PC, con el mismo SoundFont del que
# salen nuestras muestras, y medido con la misma vara. Es el techo: dice cuánto
# de lo que falta es culpa nuestra y cuánto es de la medición.
snes-referencia mapa="67" banco="/extras/soundfonts/Microsoft GS Wavetable Synth.sf2":
  mkdir -p snes/shots
  fluidsynth -F snes/shots/referencia.wav -r 48000 \
      "{{banco}}" \
      "$(python3 tools/midi_path.py --map-id {{mapa}})"
  python3 tools/snes_check.py snes/shots/referencia.wav --map-id {{mapa}}

# Todo junto: convertir, compilar y verificar.
snes mapa="67": (snes-music mapa) snes-build (snes-check mapa)

# La ROM en una ventana, con sonido. Corre en el host por lo mismo que md-play.
snes-play:
  mednafen -command.exit "keyboard 0x0 20+ctrl" -sound.driver sdl snes/build/abl.sfc
