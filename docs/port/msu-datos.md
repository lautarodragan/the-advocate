# El `.msu`: datos que el MSU-1 le sirve a la ROM

El MSU-1 tiene dos partes: las pistas de audio (`<rom>-N.pcm`, ver
`rm2k-snes-msu`, en `tools/rm2k-snes-audio/src/tracks.rs`) y un **puerto de datos** que lee el `<rom>.msu` como un
flujo. Hasta el 2026-09-25 el `.msu` iba vacío y sólo servía para encender el
MSU-1. Desde ese día lleva **los fondos de batalla**, que empezaron como
piloto, y desde el 2026-09-27 **todos los del juego**, estén o no en los mapas
del cartucho: ver "Los fondos" abajo. Y desde el 2026-09-26, detrás, **los
efectos de sonido de calidad** de cada paquete de audio: ver "Los efectos"
abajo.

La ROM lleva los fondos que piden las peleas del cartucho, y **livianos**:
128x64 en 4bpp y 16 colores, que la ROM agranda al doble, contra los 256x128
en 8bpp y 96 colores del `.msu` —ver "The light fallback" en
`tools/port/scene.py`—. Así se ve a ojo de qué lado salió el fondo, y cada
uno cuesta en la ROM un octavo de lo que pesa en el `.msu`. Una pelea cuyo
fondo la ROM no lleva usa, sin MSU-1, uno de reemplazo.

## La regla

**Sin MSU-1 el juego anda igual.** taro juega en Mednafen, que no lo tiene.
Así que lo que viene del `.msu` **reemplaza** algo que la ROM ya tiene, nunca
lo agrega: sin MSU-1, con un `.msu` de otro build, vacío o cortado, o si el
MSU-1 no termina de buscar a tiempo, la ROM usa lo suyo.

## El puerto, del lado de la consola

    $2000..$2003  escribir: la posición, 32 bits little-endian. La escritura
                  a $2003 es la que busca.
    $2000         leer: el bit 7 prendido mientras busca ("data busy")
    $2001         leer: el byte que sigue; avanza solo

Se lee por DMA con el origen **fijo** en `$00:2001` —el bit 3 de `DMAP`—, que
va a la velocidad de cualquier DMA, 8 ciclos maestros por byte: 32 KB son
unos tres cuartos de cuadro, lo mismo que desde la ROM. Qué emuladores lo
implementan, en `docs/snes/emulators.md`.

## El formato

Lo arma `tools/port/msu_data.py`, y su docstring es la referencia: una firma
de 8 bytes (del sha256 de lo que sigue), `"ABLD"`, la versión, un índice de
`(posición, largo)` por entrada, y las entradas. Cada fondo son dos: sus 512
tiles de 8bpp y sus 96 colores, tal cual van a la WRAM y a la CGRAM. La ROM
tiene en `backdrop_dir` y `backdrop_cgram` otra cosa: el respaldo liviano, que
`scn_fill` y `scn_double` agrandan a 8bpp y al doble.

La disposición, desde la versión 2 (2026-09-27):

    $000000  la cabecera y el índice, rellenos con ceros hasta $10000
    $010000  los fondos del juego, por número: el fondo k ocupa $8200
             bytes desde $10000 + k × $8200 —sus tiles, y $8000 más
             adelante sus colores; el resto es relleno hasta el sector
             de 512 bytes—
    detrás   los efectos, desde el final del último lugar de fondo

**La región de los fondos es fija**: el fondo k está en el mismo byte en el
`.msu` de cualquier cartucho, porque el número de un fondo sale del juego y
no de los mapas que se lleven (ver "Los fondos"). En la versión 1 iban
seguidos detrás del índice, y el índice crece con los efectos de cada
cartucho: el lugar de un fondo se corría con cualquier cambio de audio.
Cuántos fondos son y cuánto pesa el `.msu` lo imprime el conversor, en
`conversor.log` ("`.msu:` N fondo(s) y M efecto(s) en B bytes").

Lo escribe el conversor —es el que tiene los bytes y decide el orden—, al lado
de cada `.sfc` y con su nombre: `rm2k-snes-cartridges` le pasa `--msu`. Lo llevan los
dos cartuchos, y la prueba del camino con MSU-1 corre sobre `release`, que es
la ROM que se juega.

## Cómo sabe la ROM que el `.msu` es el suyo

El conversor emite en el `.inc` la firma que escribió (`msu_data_signature`) y
dónde quedó cada fondo (`msu_backdrop_pos`, por número de fondo: es la cuenta de
arriba, en una tabla para que la ROM no multiplique). Al empezar una pelea
con fondo,
`msu_data_valid` —en `tools/runtime/msu1.s`— busca la posición 0 y compara los 8
bytes; si coinciden, `scn_fill` y los colores de `scene_upload` —en
`tools/runtime/battle_scene.s`— leen del `.msu`, y `SCN_MSU` queda en 1.

**La firma es del contenido, no del commit**: un `.msu` de otro build con los
mismos fondos se acepta, y está bien, porque son los mismos bytes en las
mismas posiciones. (El respaldo liviano, "The light fallback", no cambió el `.msu`: el de calidad
es el de antes, byte por byte, y con él la firma.) Lo que **no** cubre: un `.msu` con la cabecera intacta y
los datos dañados. La ROM no puede hashear 32 KB por fondo al empezar cada
pelea.

Las posiciones salen del `.inc` y no del índice del archivo: aceptada la
firma son el mismo dato, y leer el índice sería una búsqueda más por pelea.
El índice queda para las herramientas (`msu_data.read`) y para sumar
entradas sin cambiar el formato.

## Los fondos

**Los fondos del juego** son todos los que una pelea puede pedir: los que
nombran los `EnemyEncounter` y los `ChangeBattleBG` de todo el juego, los del
árbol de mapas y los de los terrenos. Se ordenan por nombre sin mirar
mayúsculas, que es como RM2k los busca, y el lugar de cada uno en esa lista es
su **número**: `scene.game_backdrops`. Un nombre que no está ni en el juego
ni en el RTP (`ABL_RTP_DIR`) no entra; esa pelea va sin fondo, como en RM2k.

Qué fondo pide una pelea es lo de RM2k —`Game_Map::SetupBattle` y
`Spriteset_Battle` de easyrpg-player—: el que nombra el `EnemyEncounter`; o,
si es un encuentro al azar o el comando pide "el del lugar", el del mapa
subiendo por el árbol; y si el mapa no nombra ninguno, **el del terreno de la
celda que pisa el héroe**. Ése lo resuelve la ROM al empezar la pelea
(`scn_terrain`, en `tools/runtime/battle_scene.s`), con `backdrop_terrain`. Así
salen las peleas del mundo.

**La ROM lleva todos los que las peleas del cartucho pueden pedir**: los que
nombran las tropas, los de los mapas con encuentros al azar y los de los
terrenos de esos mapas cuando no nombran ninguno —ver "Which backdrops there are" en
`tools/port/scene.py`—. Sin MSU-1, una pelea cuyo fondo la ROM no lleva usa
**el de reemplazo**, `[battle] fallback_backdrop` del archivo de proyecto
—por qué ése, en su comentario—:
`backdrop_fallback` dice, por número de fondo, cuál de la ROM se dibuja. Lo
pidió taro el 2026-09-27, porque las peleas del mundo salían en negro, y
negro confunde; el mismo día pidió que la ROM llevara todos los de
`release`, y desde ahí el reemplazo queda para una tropa que pelea "del
lugar" en un mapa sin encuentros, donde el conversor no puede saber qué
terreno va a pisar el héroe. Con MSU-1 cada pelea lee el suyo del `.msu`. La ROM lleva dos números por pelea: `SCN_BACKDROP`, el
del juego, que es el que se busca en el `.msu`, y `SCN_FALLBACK`, el de la
ROM.

Lo que cuesta cada fondo que la ROM lleva lo imprime el conversor ("fondo de
batalla … en la ROM … B"): 4.096 bytes de tiles y 32 de colores, que es
propiedad del formato, más 4 de puntero.

## Cuánto tarda

Se mide con `SCN_FRAMES`, que `scene_upload` deja en la RAM al abrir la
pelea: `rom/pruebas/abl/test_msu_datos.py` arma los dos caminos, y leerlo ahí es
una línea. En snes9x y en bsnes el `.msu` tarda **menos** que la ROM
—medido en la pelea del droide—: los dos son DMA a la misma velocidad y ahí
buscar es instantáneo, pero el respaldo lleva un DMA por tile para los planos
fijos y después se agranda con la CPU, pixel por pixel doble: unos cuatro
cuadros más que cuando era de 256x128 —medido con `SCN_FRAMES` en la pelea
del mundo, el 2026-09-27—.

**Mednafen es el único emulador en el que buscar tarda**
(`-force_module snes_faust`; qué hace cada uno, en
`docs/snes/emulators.md`): cada búsqueda cuesta uno o dos cuadros, y son
cuatro por pelea —la firma, los colores y los tiles para cada uno de los dos
búferes de la WRAM—. Medido el 2026-09-26 en la pelea del droide, jugada
desde el título con la pista del mapa sonando: `SCN_FRAMES` en 11 con el
`.msu`, contra 5 sin él en Mednafen y 4 con él en snes9x y en bsnes. O sea
unos siete cuadros de espera, poco más de una décima de segundo. La RAM de
Mednafen se lee guardando el estado (F5): el `.mc0` de `~/.mednafen/mcs/` es
un gzip, y la WRAM va entera en su entrada `WRAM`.

En el FX Pak buscar dentro de su búfer de 16 KB es inmediato, y fuera de él
es leer la tarjeta SD —`prepare_data` en `src/msu1.c` de sd2snes, su
firmware—.
Eso **no está medido**. El tope de la espera —`MSU_WAIT`, en
`tools/runtime/msu1.s`— es unas diez veces lo que tarda Mednafen.

Si una búsqueda no llega a tiempo, lo que ya se leyó del `.msu` es el fondo
de calidad y lo que sigue saldría del liviano, que no comparten ni colores ni
tiles: `scene_upload` lo nota y rehace el fondo entero desde la ROM. Ningún
emulador tarda tanto como para cortar la espera, así que ese camino **no lo
corre ninguna prueba**.

## Los efectos

Detrás de los fondos van los efectos de sonido de cada paquete de audio,
enteros y a la tasa que le entra a ese paquete con la ARAM libre de música
—el reparto es de `rm2k-snes-audio`, en su `msu.rs`—: por paquete, en el orden de la
tabla, y adentro de cada uno en orden de SRCN, que es como los sube
`upload_placed`. Así la ROM **busca una vez por paquete** y lee de corrido;
un efecto que está en dos paquetes va dos veces. Lo escribe `write_msu`
en snes_convert.py, que también emite lo que la ROM necesita: `se_msu_pkg` y
`se_msu_rows` —dónde está cada efecto de cada paquete y cuánto mide— y
`se_msu_pitch_pkg` y `se_msu_pitch` —la altura de cada sonido con la
versión de cada paquete, sólo de los sonidos cuyo efecto es de ahí, y dos
paquetes con la misma lista la comparten—, y al lado un `efectos.json`
legible.

La firma es la misma de los fondos y se mira una vez por encendido, en la
primera carga de paquete (`se_msu_prepare`, en `tools/runtime/msu_effects.s`).
Sin firma, los efectos salen de la ROM como siempre. Una búsqueda que no llega
a tiempo deja ese efecto sin subir: no suena, porque la versión de la ROM
tiene otra altura. Lo cubre `rom/pruebas/abl/test_msu_efectos.py`, menos esa
espera, por lo mismo que la de los fondos.

## Cómo se prueba

La tanda corre sin MSU-1, así que sus goldens de batalla son el respaldo
liviano. `rom/pruebas/abl/test_msu_datos.py` corre los dos caminos en snes9x y
en bsnes y compara **cada uno contra su golden** —`msu-datos-rom` y
`msu-datos-msu`— y el fondo limpio de la WRAM contra los bytes que arma el
conversor: el de calidad tal cual y el liviano agrandado a 8bpp y al doble.
Lo mismo con una pelea del mundo, cuyo fondo es el del terreno que pisa el
héroe —`msu-mundo-rom`, su respaldo, y `msu-mundo-msu`, el de calidad—, y
que cada fondo esté en su lugar fijo con los mismos bytes en el `.msu` de
todos los cartuchos. El reemplazo lo cubre
`test_escena_una_pelea_cuyo_fondo_no_esta_usa_el_reemplazo`, en
`rom/pruebas/rpgmaker/test_batalla_escena_dibujo.py`.

**La espera no la cubre la tanda**, porque los tres cores de libretro que
hay acá buscan en el acto, y el arnés no puede simular la demora: ve la
memoria, no el bus, así que no tiene cómo contestar otra cosa cuando la ROM
lee `$2000`. Lo que la ejercita es Mednafen, a mano: un cartucho que abra la
pelea al empezar la partida —los flags de `release` con `batalla-droide`
como página 0—, Xvfb y `xdotool` para pasar el título, F5 en la pelea, y
leer `SCN_MSU` del `.mc0`. Así se verificó el 2026-09-26, y además jugando
hasta el droide con la partida de la tanda cargada en la SRAM de Mednafen.
Meterlo en la tanda costaría un cartucho más y una prueba que corre en
tiempo real contra un emulador con ventana; no se hizo. Lo que sigue sin
correr nadie es el corte por tope, arriba.
