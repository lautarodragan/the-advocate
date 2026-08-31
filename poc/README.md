# rm2k-md — "hola mundo" de RPG Maker 2000 en Sega Mega Drive

PoC mínimo: mapa de tiles convertido de un ChipSet de RM2k, personaje de un
CharSet de RM2k, caminata con la cruceta y cámara que sigue al jugador.
Sin diálogos, sin eventos, sin audio.

## Build

    sudo apt install binutils-m68k-linux-gnu gcc-m68k-linux-gnu
    make assets     # PNG de RM2k -> src/assets.c
    make            # -> build/rm2k.bin

## Estructura

    tools/make_placeholder_assets.py   genera ChipSet/CharSet de prueba con layout real de RM2k
    tools/rm2k2md.py                   ChipSet/CharSet PNG -> tiles 4bpp + paletas de 9 bits
    tools/fixrom.py                    parchea fin de ROM y checksum de la cabecera
    src/boot.S                         vectores, cabecera de cartucho, entry point
    src/main.c                         init del VDP, render, input, cámara
    md.ld                              linker script (ROM en 0x000000, RAM en 0xFF0000)

## Mapa de la VRAM

    0x0000  tile 0 en blanco
    0x0020  tileset (96 tiles de RM2k x 4 = 384 tiles del VDP)
    0x3020  sprite (12 frames x 12 tiles)
    0xB000  plano window (sin usar)
    0xC000  plano A (64x32 celdas = 512x256 px)
    0xE000  plano B (sin usar)
    0xF000  tabla de sprites
    0xFC00  tabla de hscroll

## Usar assets reales

    python3 tools/rm2k2md.py /ruta/ABL/ChipSet/loquesea.png \
                             /ruta/ABL/CharSet/loquesea.png -o src/assets

El bloque de tiles que se lee es el "lower layer" del ChipSet (x=192..287).
Verificar contra el chipset real antes de confiar en el recorte.

## Lo que falta (en orden)

1. Streaming de columnas/filas: hoy el mapa entero entra en el plano (32x16
   tiles). Un mapa de RM2k de verdad no entra; hay que redibujar la columna o
   fila que entra en pantalla al scrollear.
2. Segunda capa: RM2k tiene lower + upper layer. Van al plano B y al A, con el
   bit de prioridad para lo que tapa al personaje.
3. Colisión: leer el terrain/passability de la LDB en vez de dejar caminar
   sobre el agua.
4. Leer mapas reales: `lcf2xml` de EasyRPG Tools convierte .lmu/.ldb a XML.
5. Autotiles: el bloque x=0..191 del ChipSet, que es donde está el agua
   animada y los bordes de terreno.

---

## Versión SNES (`src/snes/`, `tools/rm2k2snes.py`)

    sudo apt install cmake
    git clone https://github.com/vhelin/wla-dx && cd wla-dx && cmake -B build && cmake --build build
    python3 tools/rm2k2snes.py assets/ChipSet_placeholder.png assets/CharSet_placeholder.png -o assets/snes
    wla-65816 -o build/snes_main.o src/snes/main.asm
    wlalink -S linkfile build/rm2k.sfc

Mismo mapa, mismo chipset, distinto resultado de color: el Mega Drive aplasta
42 colores a 16; la SNES los empaqueta en 3 de sus 8 paletas sin perder ninguno.

### Diferencias que muerden

* El tilemap de 64x32 de la SNES son **dos pantallas de 32x32 pegadas**, no un
  array lineal de 64 de ancho. El del Mega Drive sí es lineal.
* Sprites: 24x32 es un tamaño legal de OBJ en Mega Drive (3x4 celdas) pero no
  en SNES, donde hay que paddear a 32x32.
* La SNES sólo deja escribir VRAM en vblank o force blank. El streaming de
  columnas al scrollear (paso 1 del roadmap) es más ajustado acá.
* Mapa de la VRAM: tiles BG en palabra $0000, tilemap en $2000, tiles OBJ
  en $4000 (base 2 de OBSEL).
