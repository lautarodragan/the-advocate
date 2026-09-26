# El `.msu`: datos que el MSU-1 le sirve a la ROM

El MSU-1 tiene dos partes: las pistas de audio (`<rom>-N.pcm`, ver
`tools/audio/msu.py`) y un **puerto de datos** que lee el `<rom>.msu` como un
flujo. Hasta el 2026-09-25 el `.msu` iba vacío y sólo servía para encender el
MSU-1. Desde ese día lleva **los fondos de batalla**, como piloto: el objetivo
es probar el mecanismo, no ahorrar espacio. La ROM sigue llevando los suyos.

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
tiles de 8bpp y sus 96 colores, los mismos bytes que `fondo_K_T` y
`fondo_cgram` en la ROM.

Lo escribe el conversor —es el que tiene los bytes y decide el orden—, al lado
de cada `.sfc` y con su nombre: `cartuchos.py` le pasa `--msu`. Lo llevan los
tres cartuchos, así que la prueba del camino con MSU-1 corre sobre
`test-main`.

## Cómo sabe la ROM que el `.msu` es el suyo

El conversor emite en el `.inc` la firma que escribió (`msu_datos_firma`) y
dónde quedó cada fondo (`msu_fondo_pos`). Al empezar una pelea con fondo,
`msu_datos_validos` —en `rom/src/msu1.s`— busca la posición 0 y compara los 8
bytes; si coinciden, `esc_llenar` y los colores de `escena_subir` —en
`rom/src/batalla_escena.s`— leen del `.msu`, y `ESC_MSU` queda en 1.

**La firma es del contenido, no del commit**: un `.msu` de otro build con los
mismos fondos se acepta, y está bien, porque son los mismos bytes en las
mismas posiciones. Lo que **no** cubre: un `.msu` con la cabecera intacta y
los datos dañados. La ROM no puede hashear 32 KB por fondo al empezar cada
pelea.

Las posiciones salen del `.inc` y no del índice del archivo: aceptada la
firma son el mismo dato, y leer el índice sería una búsqueda más por pelea.
El índice queda para las herramientas (`msu_datos.leer`) y para sumar
entradas sin cambiar el formato.

## Cuánto tarda

Se mide con `ESC_CUADROS`, que `escena_subir` deja en la RAM al abrir la
pelea: `pruebas/abl/test_msu_datos.py` arma los dos caminos, y leerlo ahí es
una línea. En los emuladores los dos caminos tardan lo mismo, porque el DMA
va a la misma velocidad y buscar es instantáneo. En el FX Pak buscar es leer
la tarjeta SD, y son cuatro búsquedas por pelea: la firma, los tiles para
cada uno de los dos búferes de la WRAM y los colores. Eso **no está medido**.

## El paso siguiente

Que el respaldo de la ROM sea más liviano que lo que viene del `.msu`: un
fondo de menos colores o a menor resolución en la ROM, y el de calidad en el
`.msu`. Ahí la prueba de "se ve igual por los dos caminos" deja de valer tal
cual, y lo que hay que comparar es cada camino contra su propia golden.
