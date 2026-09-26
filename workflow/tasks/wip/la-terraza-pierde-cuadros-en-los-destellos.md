---
name: "La terraza pierde cuadros en los destellos"
description: "Recalcular las paletas de FlashSprite y FlashScreen se come casi todo el cuadro en la terraza del mapa 32"
type: bug
---

taro nota lag en la escena de la terraza (mapa 32) y en el destello azul de
Kersh (`done/dos-destellos-a-la-vez.md`: "mejoró, pero no es perfecto; lo que
queda es lag"). La investigación de los chips (`wishlist/chips-sa-1-y-s-dd1.md`,
"Dónde se va el cuadro hoy") midió que en las vueltas pesadas casi 200 de las
262 líneas se van en recalcular paletas: `destello_tick` ~103 y
`flashes_tick` ~94. Es CPU pura, y medida en snes9x: en el hardware puede ser
peor (ver lo que dé la medición en bsnes del minijuego del mapa 11).

Ideas que propuso esa investigación, sin chip: calcular la paleta destellada
una vez por paso de intensidad y no cada cuadro, o repartir el trabajo entre
cuadros. Medir primero en bsnes.

# Status

2026-09-26, en `wip/`: las dos cuentas rehechas sin cambiar un solo valor;
falta la tanda.

# Dónde se iba el tiempo

Medido con las sondas de línea de la investigación de los chips
(`/extras/scratch/chips/instrumentar.py`, adaptado), en la escena de siempre:
`ir_al_mapa(32, 41, 8)`, arriba, y A cada 20 cuadros hasta la pelea. snes9x y
bsnes dieron lo mismo a una línea.

* **`flashes_tick`, ~94 líneas por destello de personaje.** Casi todo era
  `tabla_canal_flash`: por cada una de las 96 entradas de las tres tablas, dos
  productos y una división del hardware con sus esperas, unos 150 ciclos cada
  una. `armar_paleta` (16 colores), la copia a `FAR_FLASH_PAL` y
  `restaurar_tablas` son lo de menos.
* **`destello_tick`, ~104 líneas en el cuadro impar.** Dos partes: armar las
  tres tablas (`una_tabla_de_destello`, unos 70 ciclos por entrada: comparar,
  restar y un `jsr` que armaba el índice de `prod31_tabla`) y pasar las
  paletas por ellas (`destellar_rango`, ~135 ciclos por color). La segunda es
  la que queda.

# Lo que se hizo

Las dos tablas se arman caminando en vez de calculando cada entrada, con el
mismo resultado entrada por entrada (comprobado para todos los destinos y
fuerzas posibles, 32 x 32 en cada una):

* `tabla_canal_flash`: el numerador de la mezcla crece siempre lo mismo de una
  entrada a la siguiente (255 - alfa), así que se divide una vez y después se
  lleva el resto. ~30 ciclos por entrada.
* `una_tabla_de_destello`: la distancia al destino baja de a uno y después
  sube de a uno, así que X camina la fila de `prod31_tabla`. <30 ciclos.

No se probó "una vez por paso de fuerza": la fuerza de un `FlashSprite` cambia
casi en cada cuadro, y el paso del `FlashScreen` está atado a la fase par e
impar; con lo de arriba ya no hacía falta.

# Lo medido

    terraza, A cada 20 cuadros        antes    después
    cuadros perdidos, ROM de verdad     9         0      (snes9x y bsnes)
    vueltas de más de 262 (sondeada)   62         0
    flashes_tick, peor vuelta         101        42
    destello_tick, peor vuelta        110        91
    los dos juntos, peor vuelta       198       132
    peor vuelta con destellos         290       224      (sondeada: ~27 de sondas)

Banco 0 (`TABLAS`, release): de 721 bytes libres a 777. BSS: un byte más
libre (`dest_v` y `dest_d` ya no se usan; `dest_hacia` pasó a dos bytes).

Lo que queda, si hiciera falta más: `destellar_rango`, 72-91 líneas en cada
cuadro de un `FlashScreen`. Con tablas de palabras ya corridas a su lugar se
ahorraría ~20% por color, pero piden 64 bytes más de la RAM del banco 0 o
pasarlas a la lejana con los índices cambiados de registro.
