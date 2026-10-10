# De RPG Maker 2000 a la Super Nintendo

Las herramientas que portan un juego hecho en RPG Maker 2000 a la Super
Nintendo, y el runtime —el motor en ensamblador— que lo corre en la consola:
cómo se lee un juego de RM2k, cómo se lo convierte, y los porqués de
arquitectura que no tienen una línea de código donde vivir. La idea es un
"RPG Maker 2000 PLUS": compatible con RM2k, y con lo que se agregue
disponible para cualquier juego (`snes-rm2k-work/decisiones/rm2k-plus.md`).

Nació portando *A Blurred Line*, y **ABL vive en su propio repo** desde el
2026-10-02: sus datos, sus parches, sus pruebas y sus goldens. La historia
de lo que era suyo se quedó acá, en `git log`.

Lo que **no** está acá: dónde quedamos, que es el repo `snes-rm2k-work`; cómo funciona hoy
cada parte del port, que es `docs/port/` y los comentarios del código; y el
relato de cómo se llegó, que está en `git log`. Qué hay en cada carpeta lo dice
el mapa de arriba de `AGENTS.md`, y `tools/README.md` el de `tools/`.

## Índice

* [Cómo se instala](#cómo-se-instala)
* [Las pruebas de ROM están en ABL, por ahora](#las-pruebas-de-rom-están-en-abl-por-ahora)
* [La arquitectura](#la-arquitectura)
    * [El fondo va en modo 3, siempre](#el-fondo-va-en-modo-3-siempre)
    * [El cartucho es ExHiROM, de 8 MB](#el-cartucho-es-exhirom-de-8-mb)
    * [Las tablas van en el banco 0](#las-tablas-van-en-el-banco-0)
* [Lo que falta](#lo-que-falta)
* [Referencias](#referencias)

## Cómo se instala

**Hace falta `python`, un core de libretro y `ca65` + `ld65`**, y se instalan
las herramientas —los proyectos de Rust, que lista `tools/README.md`— en el
PATH. Un juego las consume de
ahí, y ningún script ni prueba de un juego llama a `cargo`: el porqué está
en `AGENTS.md`. `ca65` y `ld65` salen de cc65, que no viene empaquetado en
todas las distribuciones y se compila de sus fuentes: ver "Referencias".

    just -f tools/justfile install   # instala las herramientas en el PATH
    just -f tools/justfile test      # las pruebas de Python de tools/
    just -f tools/justfile rust-test # las de todos los proyectos de Rust

El runtime viaja con las herramientas: `rm2k-snes-cartridges` lo arma desde
`tools/runtime/` del checkout del que se instaló, junto con los `.inc` que el
conversor escribe para cada juego. Qué pasa entre el juego y la ROM está en
`docs/port/pipeline.md`, y el audio en `docs/port/audio.md`.

Un juego es un directorio con un `rm2k-snes.toml`, que las herramientas
buscan desde donde corren hacia arriba, como cargo su `Cargo.toml`; lo de la
máquina —dónde está el juego original, el RTP, el SoundFont— les llega por
flags. **No hay `justfile` en la raíz**: hasta el 2026-10-02 era el de ABL,
que importaba el suyo, y el de las herramientas usa `justfile_directory()`
para encontrar lo suyo, así que importado desde la raíz lo buscaría en el
lugar equivocado.

## Las pruebas de ROM están en ABL, por ahora

**Hoy este repo no tiene pruebas que corran una ROM.** Las que hay —las de
`tools/tests/` y las de cada proyecto de Rust— prueban cada etapa sola, con
juegos chicos hechos adentro de la prueba. Las que arman un cartucho y lo
corren en un emulador, contra goldens, son de A Blurred Line y se fueron
con él, porque necesitan un juego: la mayoría prueba el motor usando a ABL
de escenario.

Así que **un cambio en `tools/` se verifica corriendo la tanda de ABL con
las herramientas del cambio**: cómo, en "Dónde corre esto" de `AGENTS.md`.
Es el riesgo que señaló el estudio que planeó la separación
(`docs/research/2026-10-02-el-juego-de-pruebas.md`), y lo corta su fase 2:
un juego de pruebas propio, hecho de cero y sin assets con derechos, adonde
se mudan las pruebas del motor.

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

**La excepción, desde el 2026-10-05, es el panorama.** Wally elige por
cada mapa, con lo que dicen el mapa y su panorama y nada más, cómo se
muestra: si nunca se ve, nada; si no se mueve contra el mapa, horneado en
el fondo; si el mapa no dibuja nada encima del héroe, en BG2 en modo 3; si
dibuja poco, en BG2 también, con lo de encima en el fondo y la prioridad de
BG1; y si dibuja más, el mapa va en modo 1, a 4 bits, y el panorama en BG3.
Ver `Way` en `tools/rm2k-snes/wally/src/background/panorama.rs`,
`tools/runtime/pano.s` y, para lo medido,
`docs/research/2026-10-05-los-panoramas.md`.

### El cartucho es ExHiROM, de 8 MB

Desde el 2026-10-01, porque el juego entero no entra en 4 MB con ningún
recorte: ver `snes-rm2k-work/decisiones/el-cartucho-pasa-a-8-mb.md`. Hasta ese día
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
* **El tercer banco de código no es de LoROM**: `FAR2`, desde el
  2026-10-02, es la mitad baja de `$C0`, rápida y sin copia, porque a lo que
  vive ahí se entra sólo con `jsl` a su dirección. Qué código va en cuál de
  los tres lo dice el encabezado de `tools/runtime/main.s`.
* **Sólo los primeros 4 MB son rápidos**: el FastROM no llega a los bancos
  `$40-$7D`. El reparto llena primero los rápidos.
* **Hay ROM que no se usa**: las mitades bajas de `$70-$7D`, donde Mesen2 y
  mesen-s ponen la SRAM aunque el cartucho tenga ROM, y las de `$7E` y `$7F`,
  que son la WRAM.
* **La SRAM está en `$20:6000`**, 8 KB, y las partidas de LoROM no cargan.

Todo eso salió de una ROM de prueba corrida en cinco emuladores antes de mudar
el juego, que es la receta `exhirom` de ABL; el detalle, en la documentación
de `banks.rs`, en `tools/rm2k-snes/cartridge/src/`.

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
`snes-rm2k-work/decisiones/la-grilla-vive-en-la-wram.md` y `docs/port/maps.md`—,
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

* lo decidido y sin empezar está en `snes-rm2k-work/tasks/todo/`, y lo que nos
  gustaría y nadie está haciendo en `snes-rm2k-work/tasks/wishlist/`;
* dónde la ROM no hace lo que RM2k hace, en `snes-rm2k-work/divergencias/`;
* qué comandos de evento se aceptan sin hacerse lo dice
  `ACCEPTED_UNDONE`, en el compilador de eventos
  (`tools/rm2k-snes/events/`), que es una lista ejecutable y no puede
  desincronizarse;
* y lo que ninguna prueba mira, en `pruebas/UNTESTED.md` de ABL.

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
