# El `.msu`: datos que el MSU-1 le sirve a la ROM

El MSU-1 tiene dos partes: las pistas de audio (`<rom>-N.pcm`, ver
`tools/audio/msu.py`) y un **puerto de datos** que lee el `<rom>.msu` como un
flujo. Hasta el 2026-09-25 el `.msu` iba vacío y sólo servía para encender el
MSU-1. Desde ese día lleva **los fondos de batalla**, como piloto: el objetivo
es probar el mecanismo. La ROM sigue llevando los suyos, pero **livianos**:
4bpp y 16 colores, contra los 8bpp y 96 del `.msu` —ver "El respaldo
liviano" en `tools/port/escena.py`—. Así se ve a ojo de qué lado salió el
fondo, y la ROM ahorra la mitad de cada uno.

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

Lo arma `tools/port/msu_datos.py`, y su docstring es la referencia: una firma
de 8 bytes (del sha256 de lo que sigue), `"ABLD"`, la versión, un índice de
`(posición, largo)` por entrada, y las entradas. Cada fondo son dos: sus 512
tiles de 8bpp y sus 96 colores, tal cual van a la WRAM y a la CGRAM. La ROM
tiene en `fondo_trozo` y `fondo_cgram` otra cosa: el respaldo liviano, que
`esc_llenar` agranda a 8bpp al copiarlo.

Lo escribe el conversor —es el que tiene los bytes y decide el orden—, al lado
de cada `.sfc` y con su nombre: `cartuchos.py` le pasa `--msu`. Lo llevan los
dos cartuchos, y la prueba del camino con MSU-1 corre sobre `release`, que es
la ROM que se juega.

## Cómo sabe la ROM que el `.msu` es el suyo

El conversor emite en el `.inc` la firma que escribió (`msu_datos_firma`) y
dónde quedó cada fondo (`msu_fondo_pos`). Al empezar una pelea con fondo,
`msu_datos_validos` —en `rom/src/msu1.s`— busca la posición 0 y compara los 8
bytes; si coinciden, `esc_llenar` y los colores de `escena_subir` —en
`rom/src/batalla_escena.s`— leen del `.msu`, y `ESC_MSU` queda en 1.

**La firma es del contenido, no del commit**: un `.msu` de otro build con los
mismos fondos se acepta, y está bien, porque son los mismos bytes en las
mismas posiciones. (El respaldo liviano no cambió el `.msu`: el de calidad
es el de antes, byte por byte, y con él la firma.) Lo que **no** cubre: un `.msu` con la cabecera intacta y
los datos dañados. La ROM no puede hashear 32 KB por fondo al empezar cada
pelea.

Las posiciones salen del `.inc` y no del índice del archivo: aceptada la
firma son el mismo dato, y leer el índice sería una búsqueda más por pelea.
El índice queda para las herramientas (`msu_datos.leer`) y para sumar
entradas sin cambiar el formato.

## Cuánto tarda

Se mide con `ESC_CUADROS`, que `escena_subir` deja en la RAM al abrir la
pelea: `pruebas/abl/test_msu_datos.py` arma los dos caminos, y leerlo ahí es
una línea. En snes9x y en bsnes el `.msu` tarda **menos** que la ROM
—medido en la pelea del droide—: los dos son DMA a la misma velocidad y ahí
buscar es instantáneo, pero el respaldo se copia de a un tile, con dos DMA de
32 bytes cada uno y los registros rearmados en el medio.

**Mednafen es el único emulador en el que buscar tarda**
(`-force_module snes_faust`; qué hace cada uno, en
`docs/snes/emulators.md`): cada búsqueda cuesta uno o dos cuadros, y son
cuatro por pelea —la firma, los colores y los tiles para cada uno de los dos
búferes de la WRAM—. Medido el 2026-09-26 en la pelea del droide, jugada
desde el título con la pista del mapa sonando: `ESC_CUADROS` en 11 con el
`.msu`, contra 5 sin él en Mednafen y 4 con él en snes9x y en bsnes. O sea
unos siete cuadros de espera, poco más de una décima de segundo. La RAM de
Mednafen se lee guardando el estado (F5): el `.mc0` de `~/.mednafen/mcs/` es
un gzip, y la WRAM va entera en su entrada `WRAM`.

En el FX Pak buscar dentro de su búfer de 16 KB es inmediato, y fuera de él
es leer la tarjeta SD —`prepare_data` en `src/msu1.c` de sd2snes, su
firmware—.
Eso **no está medido**. El tope de la espera —`MSU_ESPERA`, en
`rom/src/msu1.s`— es unas diez veces lo que tarda Mednafen.

Si una búsqueda no llega a tiempo, lo que ya se leyó del `.msu` es el fondo
de calidad y lo que sigue saldría del liviano, que no comparten ni colores ni
tiles: `escena_subir` lo nota y rehace el fondo entero desde la ROM. Ningún
emulador tarda tanto como para cortar la espera, así que ese camino **no lo
corre ninguna prueba**.

## Cómo se prueba

La tanda corre sin MSU-1, así que sus goldens de batalla son el respaldo
liviano. `pruebas/abl/test_msu_datos.py` corre los dos caminos en snes9x y
en bsnes y compara **cada uno contra su golden** —`msu-datos-rom` y
`msu-datos-msu`— y el fondo limpio de la WRAM contra los bytes que arma el
conversor: el de calidad tal cual y el liviano agrandado a 8bpp.

**La espera no la cubre la tanda**, porque los tres cores de libretro que
hay acá buscan en el acto, y el arnés no puede simular la demora: ve la
memoria, no el bus, así que no tiene cómo contestar otra cosa cuando la ROM
lee `$2000`. Lo que la ejercita es Mednafen, a mano: un cartucho que abra la
pelea al empezar la partida —los flags de `release` con `batalla-droide`
como página 0—, Xvfb y `xdotool` para pasar el título, F5 en la pelea, y
leer `ESC_MSU` del `.mc0`. Así se verificó el 2026-09-26, y además jugando
hasta el droide con la partida de la tanda cargada en la SRAM de Mednafen.
Meterlo en la tanda costaría un cartucho más y una prueba que corre en
tiempo real contra un emulador con ventana; no se hizo. Lo que sigue sin
correr nadie es el corte por tope, arriba.
