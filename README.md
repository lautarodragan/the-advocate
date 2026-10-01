# A Blurred Line en Super Nintendo

Un port de *A Blurred Line*, un juego hecho en RPG Maker 2000, a la Super
Nintendo: cómo se lee el juego original, cómo se lo vuelca a un formato que se
pueda mirar, y el port con los porqués que no tienen una línea de código donde
vivir.

Lo que **no** está acá: dónde quedamos, que es `workflow/`; cómo funciona hoy
cada parte del port, que es `docs/port/` y los comentarios del código; y el
relato de cómo se llegó, que está en `git log`. Qué hay en cada carpeta lo dice
el mapa de arriba de `AGENTS.md`, y cada una con README explica lo suyo.

## Índice

* [El juego original](#el-juego-original)
* [Los datos en formato versionable](#los-datos-en-formato-versionable)
* [Cómo se arma](#cómo-se-arma)
* [La arquitectura](#la-arquitectura)
    * [El fondo va en modo 3, siempre](#el-fondo-va-en-modo-3-siempre)
    * [El cartucho es ExHiROM, de 8 MB](#el-cartucho-es-exhirom-de-8-mb)
    * [Las tablas van en el banco 0](#las-tablas-van-en-el-banco-0)
* [Lo que falta](#lo-que-falta)
* [Referencias](#referencias)

## El juego original

**No está en el repo**: se lee de la carpeta que diga `ABL_GAME_DIR` —que
`rom/justfile` le pasa a las herramientas como `--game-dir`—, y de ahí
salen los mapas (`.lmu`), la base de datos (`RPG_RT.ldb`), el árbol de mapas
(`RPG_RT.lmt`), las imágenes, los MIDI y los WAV. Lo que el juego no trae lo
pone el RTP de Don Miguel, que tampoco es nuestro para redistribuir: ver
`docs/rpgmaker/rtp.md`. Lo que hay que saber del formato —los ChipSets, las dos
capas— está en `docs/rpgmaker/`.

El mapa de arranque del juego es el 4, un cuarto vacío que sólo teletransporta.
El primer mapa de verdad es el 1.

## Los datos en formato versionable

    just datos         # el juego -> rom/data/ y rom/build/ditto-exacto/, con Ditto

`rom/data/` tiene los mismos datos que los `.lmu` pero en un formato que git puede
versionar de verdad: se puede ver qué cambió, revisarlo y editarlo a mano. Y
**es de donde el port lee el juego**: `tools/rpgmaker/lcf.py` sale de acá, así
que el conversor y las pruebas están mirando estos archivos y no los binarios.
Quién lo escribe es **Ditto** (`tools/rm2k/ditto/`), que además sabe volver: `ditto
pack` rearma los archivos del juego byte por byte desde el volcado exacto, que
la misma corrida deja en `rom/build/ditto-exacto/` y que no se versiona. El
porqué de la decisión está en `DITTO.md` y lo que hay adentro, en
`rom/data/README.md`.

## Cómo se arma

**Hace falta `python`, un core de libretro y `ca65` + `ld65`**, más las
herramientas del repo —los proyectos de Rust y los scripts de Python que se
ejecutan, que lista `tools/README.md`—, que **se consumen desde el PATH**: se
instalan una vez, y ningún script ni prueba de este juego llama a `cargo`. El porqué está en `AGENTS.md`. `ca65` y `ld65` salen de
cc65, que no viene empaquetado en todas las distribuciones y se compila de sus
fuentes: ver "Referencias".

    just -f tools/justfile install   # instala las herramientas en el PATH
    just cartuchos                   # arma las ROMs: release y las de prueba
    just pruebas                     # la tanda entera; arma antes lo que haga falta

El repo tiene dos mitades: `tools/`, las herramientas y el runtime
—`tools/runtime/`, el motor en ensamblador, que se arma junto con los `.inc`
de cada juego—, y `rom/`, que es A Blurred Line: su `justfile`, `data/`,
`parches/`, `pruebas/` y `build/`. Las recetas de ABL corren desde la raíz
del repo, porque el `justfile` de ahí importa el de `rom/`, o parado en
`rom/`; las de las herramientas, con `just -f tools/justfile`.

La ROM que se juega sale en `rom/build/release/abl.sfc`, con su `abl.msu` y las
pistas de MSU-1 al lado. Qué pasa entre el juego y la ROM está en
`docs/port/pipeline.md`, y el audio en `docs/port/audio.md`; qué ROMs hay y
qué prueba cubre qué, en `rom/pruebas/README.md`; qué hace cada carpeta de
`tools/`, en `tools/README.md`.

## La arquitectura

### El fondo va en modo 3, siempre

El mapa va en **modo 3, con 8 bits por pixel**, en todos los mapas. Ahí cada
pixel del fondo es un índice directo a CGRAM y no hay paleta por tile, así que
el problema de repartir los colores en grupos tales que ningún tile necesite
dos no existe. No era evitable de otra forma: hay mapas con tiles de 16, 17 y
19 colores, y ésos no entran en una paleta de 15 por más paletas que haya.
Cuesta el doble de VRAM por tile, 64 bytes en vez de 32.

El precio es que el modo 3 tiene **dos capas de fondo y nada más**: BG1 es el
mapa y BG2 la capa de encima junto con la ventana de mensaje. Lo que en RM2k
pediría una tercera —el panorama, la lluvia como capa— no tiene dónde ir, y los
sprites siguen en 4 bits: 15 colores y el transparente, que elige Adeleine
(`tools/snes/adeleine/`). Cómo se reparten la VRAM y la CGRAM mapa por mapa,
en `docs/port/vram.md` y `docs/port/cgram.md`.

### El cartucho es ExHiROM, de 8 MB

Desde el 2026-10-01, porque el juego entero no entra en 4 MB con ningún
recorte: ver `workflow/decisiones/el-cartucho-pasa-a-8-mb.md`. Hasta ese día
era **LoROM**, y el código se escribió para LoROM; lo que cambió y lo que no
tiene una razón que no está en ninguna línea:

* **Los datos van en bancos de 64 KB, desde `$0000`**, y el banco siguiente
  sigue al anterior: lo que se recorre a mano cruzando bancos —el stream de
  la música, las muestras que se suben al SPC700, el bloque de textos— sólo
  le suma uno al banco. En LoROM cada banco eran los 32 KB de `$8000` a
  `$FFFF`, y el siguiente seguía desde su `$8000`.
* **El código sigue viendo los bancos 0 y 1 como en LoROM**: 32 KB desde
  `$8000`, en `$00` y en su espejo rápido, `$80`. En ExHiROM ésos no son la
  misma ROM —`$80` es de los primeros 4 MB y `$00` de los segundos—, así que
  el armado pone los dos bancos de código dos veces en el archivo. Cuesta
  64 KB, y a cambio el runtime no se enteró: los vectores siguen cayendo en
  `$00`, el `jml` a `+ FAST` sigue llevando al espejo rápido, y Mednafen
  —que con `snes_faust` lee `$80-$BF` de los segundos 4 MB, distinto del
  cartucho— ve lo mismo que la consola.
* **Sólo los primeros 4 MB son rápidos**: el FastROM no llega a los bancos
  `$40-$7D`. El reparto llena primero los rápidos.
* **Hay ROM que no se usa**: las mitades bajas de `$70-$7D`, donde Mesen2 y
  mesen-s ponen la SRAM aunque el cartucho tenga ROM, y las de `$7E` y `$7F`,
  que son la WRAM.
* **La SRAM está en `$20:6000`**, 8 KB, y las partidas de LoROM no cargan.

Todo eso salió de una ROM de prueba corrida en cinco emuladores antes de mudar
el juego, `just exhirom`; el detalle, en la documentación de `banks.rs`, en
`tools/rm2k-snes/cartridge/src/`.

### Las tablas van en el banco 0

El banco 0 es el del código, y la CPU ve sus 32 KB de `$8000` a `$FFFF`: ver
arriba.

`lda tabla, x` direcciona **el registro de banco de datos**, no el banco donde
esté la tabla. Ese registro vale 0 y nunca lo tocamos —salvo en la pelea, que
lo pone en `$7E` y lo dice—, así que una tabla en otro banco se lee del lugar
equivocado, sin ningún error, con bytes que casualmente están ahí. Y se arregla
a medias con facilidad, porque lo que sigue funcionando son las escrituras
directas y los borrados por DMA, que llevan el banco explícito: alcanza para
que la corrupción de pantalla desaparezca y el error de fondo quede.

Así que hay un segmento `TABLES` que el enlazador pone en el banco 0, y todo lo
que la CPU recorra con un índice tiene que estar ahí. **Y el banco 0 son 32 KB,
así que la tabla que crece con el contenido se muda**: se lee con
`lda f:tabla, x`, que lleva el banco en la instrucción; cuesta un byte por
instrucción y **obliga a que el índice sea X**, porque el direccionamiento
absoluto largo indexado con Y no existe.

Lo que no entra en un banco no puede recorrerse con un índice: la grilla de
celdas de un mapa grande no entra, y se lee con un puntero de 24 bits. Vive
descomprimida en la mitad alta de los dos bancos de la WRAM —ver
`workflow/decisiones/la-grilla-vive-en-la-wram.md` y `docs/port/maps.md`—,
que tiene la misma forma que un banco de LoROM: pasarse del `$FFFF` no lleva
al `$0000` del banco siguiente sino a su `$8000`. `ptr_more` y `ptr_minus` son las únicas
rutinas que saben eso; todo lo demás las usa y se olvida del tema.

Y una tabla mudada, o una que se recorra con `[ptr], y`, **tiene que
declararse con `.block`** para no quedar partida entre dos bancos: ver
`block` en el `asm.rs` de `tools/rm2k-snes/mapdata/`. El acomodo se niega a armar con una
etiqueta de RODATA sin declarar, y lo que cruza a propósito —el stream de la
música, lo que se sube al SPC700— lleva `.crossbank`, y cruza sólo entre dos
bancos que se siguen: el reparto lo hace
`rm2k-snes-assemble` antes de `ca65`, ver `resolve` en
`tools/rm2k-snes/cartridge/src/banks.rs`.

## Lo que falta

No se escribe acá, porque acá envejecía sin que nadie lo notara:

* lo decidido y sin empezar está en `workflow/tasks/todo/`, y lo que nos
  gustaría y nadie está haciendo en `workflow/tasks/wishlist/`;
* dónde la ROM no hace lo que RM2k hace, en `workflow/divergencias/`;
* qué comandos de evento se aceptan sin hacerse lo dice
  `ACCEPTED_UNDONE`, en el compilador de eventos
  (`tools/rm2k-snes/events/`), que es una lista ejecutable y no puede
  desincronizarse;
* y lo que ninguna prueba mira, en `rom/pruebas/UNTESTED.md`.

## Referencias

**De acá salen los números y la semántica, no de la memoria**: ya pasó una vez
que tres códigos de comando de RM2k se pusieron de memoria y estaban mal.

RPG Maker 2000:

* [liblcf](https://github.com/EasyRPG/liblcf) — el formato LCF, los ids de
  chunk y los códigos de comando; de ahí sale el esquema de Ditto
* [EasyRPG Player](https://github.com/EasyRPG/Player) — el intérprete de
  referencia: qué hace cada comando y cada orden de ruta
* [Game-Decompilations](https://github.com/SamidyFR/Game-Decompilations) —
  una lista de decompilaciones, para lo que EasyRPG no explica

La consola:

* [fullsnes](https://problemkaputt.de/fullsnes.htm), de nocash — la
  referencia del hardware entero
* los documentos de anomie —registros, tiempos, el SPC700—, que la mayoría de
  las demás referencias citan
* el [wiki de superfamicom.org](https://wiki.superfamicom.org/)
* "SNES translucency", de Bregalad — el color math explicado; está en
  `docs/snes/snes-translucency-by-bregalad.txt`
* [sd2snes](https://github.com/mrehkopf/sd2snes) — el firmware del FX Pak
  Pro: cómo implementa de verdad el MSU-1
* [el desensamblado de Final Fantasy VI](https://github.com/everything8215/ff6)
  — el texto como un byte por letra que compone el 65816, que es lo que hace
  la ventana de mensaje

Los emuladores, que además de correr la ROM son el código que se lee cuando la
documentación no alcanza —con cuáles se prueba a mano y qué implementa cada
uno, en `docs/snes/emulators.md`—:

* [bsnes](https://github.com/bsnes-emu/bsnes),
  [snes9x](https://github.com/snes9xgit/snes9x),
  [Mesen2](https://github.com/SourMesen/Mesen2),
  [Mesen-S](https://github.com/SourMesen/Mesen-S),
  [ares](https://github.com/ares-emulator/ares) y
  [Mednafen](https://mednafen.github.io/)

Y [cc65](https://github.com/cc65/cc65), de donde salen `ca65` y `ld65`.
