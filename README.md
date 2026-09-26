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
* [Por qué la Super Nintendo](#por-qué-la-super-nintendo)
* [La arquitectura](#la-arquitectura)
    * [El fondo va en modo 3, siempre](#el-fondo-va-en-modo-3-siempre)
    * [Las tablas van en el banco 0](#las-tablas-van-en-el-banco-0)
    * [Los eventos translúcidos van horneados](#los-eventos-translúcidos-van-horneados)
    * [Cómo está armado el audio](#cómo-está-armado-el-audio)
    * [Trampas del hardware](#trampas-del-hardware)
* [Lo que falta](#lo-que-falta)
* [Referencias](#referencias)

## El juego original

**No está en el repo**: vive en `/extras/abl-rm` —se puede apuntar a otra
copia con `ABL_GAME_DIR`— y de ahí salen los mapas (`.lmu`), la base de datos
(`RPG_RT.ldb`), el árbol de mapas (`RPG_RT.lmt`), las imágenes, los MIDI y los
WAV. Lo que el juego no trae lo pone el RTP de Don Miguel, que tampoco es
nuestro para redistribuir: ver `docs/rpgmaker/rtp.md`. Lo que hay que saber del
formato —los ChipSets, las dos capas— está en `docs/rpgmaker/`.

El mapa de arranque del juego es el 4, un cuarto vacío que sólo teletransporta.
El primer mapa de verdad es el 1.

## Los datos en formato versionable

    just datos         # el juego -> data/ y rom/build/ditto-exacto/, con Ditto

`data/` tiene los mismos datos que los `.lmu` pero en un formato que git puede
versionar de verdad: se puede ver qué cambió, revisarlo y editarlo a mano. Y
**es de donde el port lee el juego**: `tools/rpgmaker/lcf.py` sale de acá, así
que el conversor y las pruebas están mirando estos archivos y no los binarios.
Quién lo escribe es **Ditto** (`tools/ditto/`), que además sabe volver: `ditto
pack` rearma los archivos del juego byte por byte desde el volcado exacto, que
la misma corrida deja en `rom/build/ditto-exacto/` y que no se versiona. El
porqué de la decisión está en `DITTO.md` y lo que hay adentro, en
`data/README.md`.

## Cómo se arma

**Hace falta `python`, un core de libretro y `ca65` + `ld65`**, más las
herramientas de Rust del repo —`ditto`, `protocol`, `gunter` y `voodoo`—, que
**se consumen desde el PATH**: se instalan una vez y ningún script ni prueba de
este juego llama a `cargo`. El porqué, y cómo se compila `cc65`, que no viene
empaquetado en Arch, están en `AGENTS.md`. Nada de esto pide un contenedor.

    just herramientas     # instala ditto, protocol, gunter y voodoo
    just cartuchos        # arma las ROMs: release y las de prueba
    just pruebas          # la tanda entera; arma antes lo que haga falta

La ROM que se juega sale en `rom/build/release/abl.sfc`, con su `abl.msu` y las
pistas de MSU-1 al lado. Qué pasa entre el juego y la ROM está en
`docs/port/pipeline.md`; qué ROMs hay y qué prueba cubre qué, en
`pruebas/README.md`; qué hace cada carpeta de `tools/`, en `tools/README.md`.

## Por qué la Super Nintendo

El MIDI de la PC lo tocaba un sintetizador **por muestras**, y la SNES también
es por muestras: el problema deja de ser "imitar un piano con cuatro
operadores", como en el YM2612 de la Mega Drive, y pasa a ser "comprimir estas
muestras", que es mecánico. De paso, 15 bits de color contra 9 y ocho paletas
contra cuatro. Hubo un port a Mega Drive; vive aparte, en `abl-sega`.

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
sprites siguen en 4 bits: 15 colores y el transparente, que se eligen en
`tools/port/asignador.py`. Cómo se reparten la VRAM y la CGRAM mapa por mapa,
en `docs/port/vram.md` y `docs/port/cgram.md`.

### Las tablas van en el banco 0

El cartucho es **LoROM**: cada banco tiene sólo sus 32 KB de arriba, de
`$8000` a `$FFFF`.

`lda tabla, x` direcciona **el registro de banco de datos**, no el banco donde
esté la tabla. Ese registro vale 0 y nunca lo tocamos —salvo en la pelea, que
lo pone en `$7E` y lo dice—, así que una tabla en otro banco se lee del lugar
equivocado, sin ningún error, con bytes que casualmente están ahí. Y se arregla
a medias con facilidad, porque lo que sigue funcionando son las escrituras
directas y los borrados por DMA, que llevan el banco explícito: alcanza para
que la corrupción de pantalla desaparezca y el error de fondo quede.

Así que hay un segmento `TABLAS` que el enlazador pone en el banco 0, y todo lo
que la CPU recorra con un índice tiene que estar ahí. **Y el banco 0 son 32 KB,
así que la tabla que crece con el contenido se muda**: se lee con
`lda f:tabla, x`, que lleva el banco en la instrucción; cuesta un byte por
instrucción y **obliga a que el índice sea X**, porque el direccionamiento
absoluto largo indexado con Y no existe.

Lo que no entra en un banco no puede recorrerse con un índice: la grilla de
celdas de un mapa grande no entra, y se lee con un puntero de 24 bits. Ahí
aparece la otra cara de LoROM: pasarse del `$FFFF` no lleva al `$0000` del
banco siguiente sino a su `$8000`. `ptr_mas` y `ptr_menos` son las únicas
rutinas que saben eso; todo lo demás las usa y se olvida del tema. Y una tabla
mudada, o una que se recorra con `[ptr], y`, **tiene que declararse con
`.bloque`** para no quedar partida entre dos bancos: ver `bloque` en
`tools/port/snes_convert.py`.

### Los eventos translúcidos van horneados

El "Trans" de una página —`translucent`— en RM2k dibuja el evento con opacidad
160 de 255. La consola tiene transparencia de verdad, el color math, pero la
aplica a todos los sprites de las paletas 4 a 7 a la vez, y un mapa con
translúcidos tendría que dejarles esas cuatro paletas solas. Probado, además,
tiene dos costos que taro no aceptó: ver
`workflow/decisiones/el-color-math-no-se-usa.md`. Tramarlos —dejar caer parte
de sus pixeles, que es lo que hacían los juegos de la época— tampoco alcanza en
este juego: **los fuegos del mapa 9 están sobre negro casi puro**, así que la
trama no simula transparencia, agujerea la llama.

Así que la mezcla **se calcula en el conversor y queda horneada en el
gráfico**. Lo que lo permite es que las páginas translúcidas del juego son
todas estáticas —`move_type` 0 y sin ruta propia—: si ni el objeto ni el fondo
se mueven, la mezcla contra la capa de abajo de su celda da siempre lo mismo y
se puede calcular una vez, exacta, sin trama y sin gastar color math ni
paletas. Cómo, en `decorar_translucido` (`tools/rpgmaker/rm2k.py`); lo que se
pierde, en `workflow/divergencias/los-translucidos-quedan-opacos.md`.

### Cómo está armado el audio

El audio lo maneja el **SPC700**, un procesador aparte con sus propios 64 KB
de ARAM. El 65816 no puede tocar el DSP: sólo hablarle al SPC700 por cuatro
puertos. Al encender, el SPC700 corre una ROM interna con un protocolo de
carga, el IPL; con él se suben un driver mínimo y el directorio de muestras, y
de ahí en más el driver atiende comandos: pares (registro, valor) para el DSP,
y ternas de bytes para subir a la ARAM el paquete de muestras de cada mapa
mientras la música suena. Ver `DRIVER` en `tools/audio/snes_music.py`.

**Toda la lógica vive en Python**: el conversor decide qué nota va a qué voz,
con qué muestra y con qué envolvente, y deja por tema un stream **por nota**.
En la consola, el 65816 lo expande a escrituras al DSP cuadro a cuadro
—`music_frame`, en `rom/src/musica.s`— y se las pasa al driver; el formato
está en "el formato por nota" de `snes_music.py`. Las muestras salen del
SoundFont con el que se compuso el juego, y qué va a la ARAM en cada mapa lo
dice `workflow/decisiones/un-solo-banco-de-muestras.md`.

### Trampas del hardware

Las del 65816 y las del PPU viven en el código, pegadas a la instrucción o al
registro que muerden, y la que más veces mordió está en `AGENTS.md`. Lo que
queda acá son las que no tienen una línea donde vivir, porque valen para
`rom/src/` entero.

**Un `jsr` te devuelve `X` e `Y` como se le da la gana.** No hay convención de
llamada acá: cada rutina usa los índices para lo suyo. Cuando un registro es un
cursor que tiene que sobrevivir a una llamada —el del bytecode del intérprete lo
es— hay que guardarlo con `phy` en el que llama, y el que llama es el único que
sabe que hace falta.

**El ancho de A y de X/Y es estado, y el ensamblador lo cree.** Las directivas
`.a8` y `.a16` no describen: mandan. Toda transferencia entre registros de
ancho distinto —`tax` con X de 16 bits, `ldx` con un índice de un solo byte— se
lleva el byte de al lado. Y toda etiqueta a la que se salte desde otro ancho
tiene que declarar el suyo, porque `ca65` lleva el ancho en orden de lectura y
**no lo comprueba**:

    bne baja
    rep #$20
    .a16
    lda tira_paso_col
    bra entra
    baja:            <- se llega acá en ocho bits
    cmp #DIR_DOWN    <- pero el ensamblador cree que en dieciséis

El `cmp` se emite con un inmediato de **dos** bytes, la CPU en ocho lee uno
solo, y el segundo —el `$00` del byte alto— se ejecuta como `BRK`: la ROM se va
por la ventana y dibuja cualquier cosa. No lo ve el diff, no lo ve la
comparación pixel a pixel, y bisecar con `rts` tampoco sirve, porque
desbalancea la pila y uno termina midiendo eso. Si una ROM se va por la ventana
sin razón aparente, mirar primero ahí.

## Lo que falta

No se escribe acá, porque acá envejecía sin que nadie lo notara:

* lo decidido y sin empezar está en `workflow/tasks/todo/`, y lo que nos
  gustaría y nadie está haciendo en `workflow/tasks/wishlist/`;
* dónde la ROM no hace lo que RM2k hace, en `workflow/divergencias/`;
* qué comandos de evento se aceptan sin hacerse lo dice
  `ACEPTADOS_SIN_HACER`, en `tools/port/eventos.py`, que es una lista
  ejecutable y no puede desincronizarse;
* y lo que ninguna prueba mira, en `pruebas/UNTESTED.md`.

## Referencias

Clonadas adentro del contenedor, en `/extras/ref`. **De ahí salen los números y
la semántica de RM2k, no de la memoria**: ya pasó una vez que tres códigos de
comando se pusieron de memoria y estaban mal.

* `liblcf` — el formato LCF y los ids de chunk
* `easyrpg-player` — el intérprete de referencia
* `Game-Decompilations` — para lo que easyrpg no explica
