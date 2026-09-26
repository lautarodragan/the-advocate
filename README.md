# A Blurred Line en Super Nintendo

Un port de *A Blurred Line*, un juego hecho en RPG Maker 2000, a la Super
Nintendo. Acá está todo: cómo se lee el juego original, cómo se lo vuelca a un
formato que se pueda mirar, y el port entero con sus trampas y lo que falta.

Lo que **no** está acá: dónde quedamos —eso es `workflow/`— y el relato de cómo
se llegó, que está en `git log`.

## Índice

* [Leer el juego original](#leer-el-juego-original)
    * [Piezas](#piezas)
    * [Lo que hay que saber del formato](#lo-que-hay-que-saber-del-formato)
    * [El RTP](#el-rtp)
* [Los datos en formato versionable](#los-datos-en-formato-versionable)
* [El port a Super Nintendo](#el-port-a-super-nintendo)
    * [Por qué](#por-qué)
    * [Veredicto](#veredicto)
    * [El mapa](#el-mapa)
    * [La cámara](#la-cámara)
    * [Los mapas que no entran](#los-mapas-que-no-entran)
        * [El mapa no se guarda como tilemap](#el-mapa-no-se-guarda-como-tilemap)
        * [El reparto de la VRAM lo decide el conversor](#el-reparto-de-la-vram-lo-decide-el-conversor)
        * [El reparto de CGRAM, también](#el-reparto-de-cgram-también)
    * [El agua se mueve, y cuesta un DMA de 1664 bytes](#el-agua-se-mueve-y-cuesta-un-dma-de-1664-bytes)
    * [El save point: anima quieto y guarda a disco](#el-save-point-anima-quieto-y-guarda-a-disco)
    * [El menú de pausa](#el-menú-de-pausa)
    * [La pantalla de ítems](#la-pantalla-de-ítems)
    * [El equipo, y las pantallas de texto](#el-equipo-y-las-pantallas-de-texto)
    * [La tienda](#la-tienda)
    * [La batalla por turnos](#la-batalla-por-turnos)
        * [La pelea sin manejadores, y el Game Over](#la-pelea-sin-manejadores-y-el-game-over)
        * [El menú: las cinco órdenes del ABL](#el-menú-las-cinco-órdenes-del-abl)
        * [Las habilidades](#las-habilidades)
        * [El fondo y los monstruos: una sola imagen](#el-fondo-y-los-monstruos-una-sola-imagen)
        * [Los encuentros al azar](#los-encuentros-al-azar)
        * [La música y los efectos de la pelea](#la-música-y-los-efectos-de-la-pelea)
    * [La lluvia](#la-lluvia)
    * [Los efectos de sonido](#los-efectos-de-sonido)
    * [El paquete de audio de cada mapa](#el-paquete-de-audio-de-cada-mapa)
    * [El MSU-1](#el-msu-1)
    * [Las animaciones de batalla: el sonido y la luz](#las-animaciones-de-batalla-el-sonido-y-la-luz)
    * [El dibujo de las animaciones de batalla](#el-dibujo-de-las-animaciones-de-batalla)
    * [El cartel de "One year previously"](#el-cartel-de-one-year-previously)
        * [Lo que costaría el sistema de imágenes entero](#lo-que-costaría-el-sistema-de-imágenes-entero)
    * [Varios mapas en la ROM](#varios-mapas-en-la-rom)
        * [Las tres piezas del intérprete de eventos](#las-tres-piezas-del-intérprete-de-eventos)
        * [Un opcode por comando](#un-opcode-por-comando)
        * [Las mecánicas que no son un opcode](#las-mecánicas-que-no-son-un-opcode)
            * [Atravesar paredes vale mientras dura la ruta](#atravesar-paredes-vale-mientras-dura-la-ruta)
        * [Varios temas en el cartucho](#varios-temas-en-el-cartucho)
        * [Cómo se verifica](#cómo-se-verifica)
    * [El personaje](#el-personaje)
        * [Las poses se suben en caliente](#las-poses-se-suben-en-caliente)
        * [Los eventos translúcidos van horneados](#los-eventos-translúcidos-van-horneados)
        * [El color math, implementado y descartado](#el-color-math-implementado-y-descartado)
        * [Los quince colores de un sprite](#los-quince-colores-de-un-sprite)
        * [El giro hacia el héroe](#el-giro-hacia-el-héroe)
    * [La colisión](#la-colisión)
    * [La pila y la BSS comparten los ocho kilos](#la-pila-y-la-bss-comparten-los-ocho-kilos)
    * [Las tablas van en el banco 0](#las-tablas-van-en-el-banco-0)
    * [Cómo está armado](#cómo-está-armado)
    * [El banco de muestras](#el-banco-de-muestras)
    * [Cómo se suelta una nota](#cómo-se-suelta-una-nota)
    * [La percusión](#la-percusión)
    * [Toolchain](#toolchain)
    * [Cómo se verifica el ensamblador](#cómo-se-verifica-el-ensamblador)
    * [Cómo se verificaba el audio](#cómo-se-verificaba-el-audio)
    * [El parche de bsnes](#el-parche-de-bsnes)
    * [Trampas del hardware](#trampas-del-hardware)
    * [El inventario, y lo que una condición de ítem hace](#el-inventario-y-lo-que-una-condición-de-ítem-hace)
    * [Las dos preguntas de actor de una rama](#las-dos-preguntas-de-actor-de-una-rama)
    * [Las variables de RM2k](#las-variables-de-rm2k)
    * [Lo que falta](#lo-que-falta)
* [Referencias](#referencias)

## Los datos en formato versionable

    just datos         # el juego -> data/ y rom/build/ditto-exacto/, con Ditto

`data/` tiene los mismos datos que los `.lmu` pero en un formato que git puede
versionar de verdad: se puede ver qué cambió, revisarlo y editarlo a mano. Y
**es de donde el port lee el juego**: `tools/rpgmaker/lcf.py` sale de acá, así que el
conversor y las pruebas están mirando estos archivos y no los binarios. Quién lo
escribe es **Ditto** (`tools/ditto/`), que además sabe volver: `ditto pack` rearma los
330 archivos byte por byte —desde el volcado exacto, que la misma corrida deja
en `rom/build/ditto-exacto/` y que no se versiona—. El porqué de la decisión
está en `DITTO.md` y lo que hay adentro, en `data/README.md`.

#### Los eventos translúcidos van horneados

El "Trans" de una página —`translucent`— en RM2k dibuja el evento con
opacidad 160 de 255. La consola tiene transparencia de verdad, el color math,
pero la aplica a todos los sprites de las paletas 4 a 7 a la vez: un mapa con
translúcidos tendría que dejarles esas cuatro paletas solas, y el 9 —donde están
los fuegos de los barriles— lleva once personajes en las ocho.

Tramarlos —dejar caer parte de sus pixeles, que es lo que hacían los juegos de la
época— tampoco alcanza en este juego. **Los fuegos del mapa 9 están sobre negro
casi puro**: no hay nada que asomarse por los huecos, así que la trama no simula
transparencia, agujerea la llama. Ningún patrón lo arregla, porque el problema no
es la densidad.

Así que la mezcla **se calcula en el conversor y queda horneada en el
gráfico**. Lo que lo permite es una medición: las 70 páginas translúcidas del
juego —35 mapas— son todas estáticas, `move_type` 0 y sin ruta propia. Si ni el
objeto ni el fondo se mueven, la mezcla al 160/255 contra el fondo real da
siempre lo mismo y se puede calcular una vez: sale exacta, sin trama y sin
gastar color math ni paletas reservadas. El fondo es la **capa de abajo** del
mapa en la celda donde el evento está parado —la de encima se dibuja después y
tapa al sprite, así que donde el sprite se ve el fondo es la de abajo—, tomado
en `(x*16 - 4, y*16 - 16)`, que es donde `charset.draw` apoya el cuadro de
24x32. Las doce poses caen en el mismo lugar de la pantalla, así que todas se
mezclan contra el mismo pedazo: el save point del mapa 8, que anima quieto,
sale bien cuadro por cuadro.

### Las tablas van en el banco 0

`lda tabla, x` direcciona **el registro de banco de datos**, no el banco donde
esté la tabla. Ese registro vale 0 al arrancar y nunca lo tocamos, así que una
tabla en otro banco se lee del lugar equivocado — sin ningún error, con bytes
que casualmente están ahí.

Y se arregla a medias con facilidad, porque lo que sigue funcionando son las
escrituras directas —apagar el HDMA, los scrolls— y los borrados por DMA, que
llevan el banco explícito: alcanza para que la corrupción de pantalla
desaparezca y el error de fondo quede.

Hay un segmento `TABLAS` que el enlazador pone en el banco 0. Todo lo que
la CPU recorra con un índice tiene que estar ahí.

**Y el banco 0 son 32 K, así que la que crece con el contenido se muda.** Van
tres: la tabla de bloques, la de textos y `mapa_tabla`, el registro de 144
bytes por mapa —con los 28 mapas de Lashe City son 4 KB—. Una tabla mudada se
lee con `lda f:tabla, x`, que lleva el banco en la instrucción y no en el
registro de banco de datos; cuesta un byte por instrucción y **obliga a que el
índice sea X**, porque el direccionamiento absoluto largo indexado con Y no
existe. Los dos usos de `mapa_tabla` con Y pasaron a X, con X yendo y volviendo
por la pila.

Y lo que no entre en un banco no puede recorrerse con un índice, punto: la
grilla de celdas llega a 40 KB. Ésa se lee con un puntero de 24 bits, y ahí
aparece la otra cara de LoROM: **un banco sólo tiene sus 32 K de arriba**, así
que pasarse del `$FFFF` no lleva al `$0000` del banco siguiente sino a su
`$8000`. Dos rutinas de diez líneas, `ptr_mas` y `ptr_menos`, son las únicas que
saben eso; todo lo demás las usa y se olvida del tema.

Y una tabla mudada, o una que se recorra con `[ptr], y`, **tiene que
declararse con `.bloque`** para no quedar partida entre dos bancos: ver
`bloque` en `tools/port/snes_convert.py`.

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

### Toolchain

**Tres cosas: `python`, un core de libretro y `ca65` + `ld65`**, más las
herramientas de Rust del repo —`gunter` para las muestras, `ditto` y
`protocol`—, que **se consumen desde el PATH**: se instalan una vez con `just
herramientas` y ningún script ni prueba de este juego llama a `cargo`. El
porqué de eso está en `AGENTS.md`, y cómo se compila `cc65`, que no viene
empaquetado en Arch, también. Nada de esto pide un contenedor.

La ROM la arma `tools/ensamblado/ensamblar.py`: `ca65`, después `ld65` con el mapa de
memoria que escribe el conversor —un área por banco, ver `tools/ensamblado/bancos.py`—, y
encima el checksum de la cabecera y la tabla de símbolos que leen las pruebas.

### Lo que se perdió con el ensamblador propio

**`ca65` no comprueba el ancho del acumulador en una etiqueta a la que se
llega saltando**, y es el error más difícil de encontrar a mano. El ensamblador lleva el ancho en
orden de lectura, así que en

    bne baja
    rep #$20
    .a16
    lda tira_paso_col
    bra entra
    baja:            <- se llega acá en ocho bits
    cmp #DIR_DOWN    <- pero el ensamblador cree que en dieciséis

el `cmp` se emite con un inmediato de **dos** bytes, la CPU en ocho lee uno
solo, y el segundo —el $00 del byte alto— se ejecuta como `BRK`: la ROM se va
por la ventana y dibuja cualquier cosa. No lo ve el diff, no lo ve la
comparación pixel a pixel, y bisecar con `rts` tampoco sirve, porque desbalancea
la pila y uno termina midiendo eso.

Hoy todas las etiquetas a las que se llega saltando con otro ancho lo declaran
con `.a8`/`.a16`/`.i8`/`.i16`, pero **no lo comprueba nadie**: una etiqueta
nueva que lo necesite y no lo diga es un `BRK` que aparece lejos. Si
una ROM se va por la ventana sin razón aparente, mirar primero ahí.

### Trampas del hardware

Las del 65816 y las del PPU viven en el código, pegadas a la instrucción o al
registro que muerden: se llega a ellas desde ahí, no desde acá. Lo que queda son
las dos que no tienen una línea donde vivir, porque valen para `rom/src/` entero.

**Un `jsr` te devuelve `X` e `Y` como se le da la gana.** No hay convención de
llamada acá: cada rutina usa los índices para lo suyo. Cuando un registro es un
cursor que tiene que sobrevivir a una llamada —el del bytecode del intérprete lo
es— hay que guardarlo con `phy` en el que llama, y el que llama es el único que
sabe que hace falta.

**El ancho de A y de X/Y es estado, y el ensamblador lo cree.** Las directivas
`.a8` y `.a16` no describen: mandan. Toda etiqueta a la que se salte desde otro
ancho tiene que declarar el suyo, y toda transferencia entre registros de ancho
distinto —`tax` con X de 16 bits, `ldx` con un índice de un solo byte— se lleva
el byte de al lado. Nada de esto da error: sale una instrucción de un largo
distinto del que el CPU lee, o un índice con basura en el byte alto.

## Referencias

Clonadas adentro del contenedor, en `/extras/ref`. **De ahí salen los números y
la semántica de RM2k, no de la memoria**: ya pasó una vez que tres códigos de
comando se pusieron de memoria y estaban mal.

* `liblcf` — el formato LCF y los ids de chunk
* `easyrpg-player` — el intérprete de referencia
* `Game-Decompilations` — para lo que easyrpg no explica
