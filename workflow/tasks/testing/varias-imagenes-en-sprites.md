---
name: "Varias imágenes en sprites"
description: "El plano de objetos del sistema de imágenes: ShowPicture, MovePicture y ErasePicture con varias imágenes a la vez, para las chicas sobre el mapa, escondiendo los eventos si no hay lugar"
type: feature
assignee: taro
---

Fase 2 de `docs/research/2026-10-01-el-sistema-de-imagenes.md` (Jilguero),
de taro el 2026-10-01. El plano de BG1 en modo 1 para las imágenes grandes
es la fase 3, aparte: taro aprobó el modo 1 sólo mientras una imagen grande
tapa el mapa (`decisiones/las-imagenes-grandes-en-modo-1.md`).

Hecha por Gallareta, desde `main` en `71782626`, con `main` mergeado en
`7d4c1c7b` (Label y JumpToLabel, de Pitogüé). **Espera el visto bueno de
taro a las goldens** —dos commits sólo de goldens— y que la juegue.

## Para mergear

* **Reinstalar en el global**: `just -f tools/justfile install events images
  wally mapdata cartridge` —`map-sprites` es biblioteca de `wally`—. Lo de
  Python no agregó ni renombró ningún script.
* **`rom/parches/manual/mapas/Map0081.*` se borró**: el fork del 81 cambiaba
  el cartel por un mensaje "hasta que la ROM lleve más de una imagen".
* **El experimento de la translucidez es su propio commit**, `Imágenes: el
  experimento de la translucidez…`, con sus goldens en el que le sigue:
  para sacarlo se revierten los dos, y el texto de la divergencia vuelve
  solo a la versión opaca.
* Números de hoy, sobre el árbol mergeado: `just pruebas` da **981** (969
  de `main` más 12 nuevas), `just -f tools/justfile test` **39**, `cargo
  test` de events, images, wally, map-sprites y mapdata en verde.
  `NO_CACHE=1 just cartuchos` y el armado con caché dan el mismo `abl.sfc`,
  `57ce2e2a…`. `test_musica_techos.py` siguió en verde.
* RAM lejana: `$30EC` a `$30FA` —la de la imagen de antes— y `$2580` a
  `$258F`, la que me tocó. Ningún opcode nuevo: `OP_PICTURE`,
  `OP_PICTURE_MOVE` y `OP_PICTURE_ERASE` cambiaron de operandos.
* Espacio, `just espacio` sobre `release`: banco 0 de 1.053 a 1.340 B
  libres (el código salió al banco 1), banco 1 de 3.204 a 2.000 B.

## El diseño

**Cada mapa lleva en su banco de sprites las imágenes que pueden mostrar
sus páginas y las páginas de prueba que corren en él**, después de sus
personajes, y se suben con el banco: mostrar una imagen sube sólo su
paleta, y volver de la pelea o del menú las encuentra donde estaban. El
camino:

1. El scan del compilador junta por mapa las claves de cada `ShowPicture`
   que la consola puede hacer —`PictureKey`: número, nombre, zoom, color
   transparente, con el mapa, por variables, y la posición sólo si cambia
   los pixeles—. Compila cada página con todo lo que tiene una compilación
   de verdad: con las del scan, sin canciones, el cartel del 81 quedaba
   detrás de un `PlayBGM`. Y con los contadores, para que los dígitos de la
   Fortitude sigan siendo del contador.
2. `picture.py` convierte cada una con `rm2k-snes-images picture`, que ahora
   sabe del zoom, del color transparente —índice 0— y de las que van con el
   mapa, que **no se escalan** a 256x224 porque el mapa tampoco; les da una
   ranura por número —las dos primeras— y las corta en objetos de 32x32,
   sin los vacíos.
3. `wally` las pone al final del banco, con **una paleta por ranura desde la
   7 para abajo** —son las que la consola puede mezclar—. Si la caja de la
   animación de batalla deja sin paletas, o si con ellas el mapa no entra
   en ningún reparto de VRAM, las saca y lo dice; sus comandos se aceptan
   sin hacerse.
4. El compilador recibe la tabla de cada mapa; `rm2k-snes-mapdata` emite
   `picture_maps` y `picture_data`; el runtime (`picture_far.s`, banco 1)
   calcula la esquina al mostrarla —cuatro quintos y catorce quinceavos,
   para abajo con negativos, como `Screens::place`; para las del mapa, la
   vista de RM2k centrada en la cámara de la consola— y dibuja después del
   contador.

**Dos ranuras.** Es lo que piden las escenas sobre el mapa: el máximo a la
vez es el rótulo del contador y sus dos dígitos, que son del contador. La
consola de la fase 6 pide nueve; la RAM que había son treinta y un bytes, y
con dos ranuras la rampa de `MovePicture` es una sola para todas —una nueva
termina la de otra ranura—.

**Opción B (esconder los eventos) no está.** En el cartucho sólo el
hovertram del 32 la pediría —165x151, no entra en ningún reparto con los
personajes—, y su escena es Talan, Arden y los guardias hablando alrededor
del tram: esconderlos es esconder la escena. ABLEndBox8 (309) va sobre el
mapa en negro: es de la fase 3.

## Qué se hace de cada opción

    posición por constante            sí
    posición por variables            sí (dos variables, leídas al mostrarla)
    con el mapa (fixed_to_map)        sí, sin escalar: el mapa no se escala
    color transparente                sí, índice 0
    zoom                              sí, achicando; agrandar no compila
    tono, y su rampa en MovePicture   sí, como el cartel de antes
    transparencia                     tres escalones: ≥76 % no se ve; 25-75 %
                                      al 50 % con el experimento, opaca sin él;
                                      <25 % opaca
    MovePicture de lugar o de zoom    no: no compila, se acepta sin hacerse
    rotar, ondear, saturación         no compila
    borrar al cambiar de mapa         sí (`pic_clear`)
    volver de la pelea y del menú     sí: el menú las tapa, y vuelven como
                                      estaban

Las deudas, en `divergencias/lo-que-las-imagenes-en-sprites-no-modelan.md`.

## Las escenas

Las que se dibujan ahora en `release`, contra el estudio:

    4    Oneyearprev     ya estaba
    81   MeanwhileLashe  nueva; el fork del mapa se borró
    95   Fortitude       nueva, arriba del contador
    311  hovershadow     nueva; con el experimento, al 50 % como el original

Las que siguen sin entrar, con su porqué:

    45   ABLrec          siete paletas de personajes y la caja de la animación:
                         no queda una para la imagen
    32   hovertram2      165x151: no entra con los personajes, y B la tapa
    98, 207, 285, 295    sus mapas no están en el cartucho; el conversor las
                         haría igual (el 207 es el caso de por variables, con
                         el mapa y al 40 %)
    309, 49, 285 Advo…   grandes: la fase 3

De las 11 de 21 que el estudio daba a A y B juntas, en el cartucho hay 5 y
se dibujan 4.

## Las pruebas

`rom/pruebas/rpgmaker/test_imagenes_golden.py`, contra goldens, en el mapa
12 —el 4 corre la apertura encima de las páginas de prueba—. Cada comando
visto en rojo con una mutación del runtime, medido: las dos ranuras en la
misma paleta (325 pixeles), la transparencia de la rampa sin guardar (674),
la variable de la x leída para la y (1.172), y la del mapa dibujada como de
la pantalla (349). La vuelta de la pelea **no cobra** la restauración de
las paletas: la tropa 82 no llega a las paletas 6 y 7 —cortar la
restauración antes de ésas la deja en verde—; cobra que las imágenes
vuelvan. El `pic_restore` que había escrito para eso se sacó: la pelea ya
repone las paletas altas desde `cgram_shadow`, donde las deja `pic_palette`,
y el menú no las toca.

Las escenas se llaman con `CallEvent` sobre la página del mapa
(`escena-81`, `-95`, `-311`). Comparadas contra el RPG_RT de 2015 con Wine,
con una copia del juego que arranca en el mapa con la página automática y
sin condiciones —se arma con `ditto`, ver el scratchpad de Gallareta—: la
sombra cae en el mismo lugar del mapa, (39,59)-(140,179) allá y
(40,60)-(138,178) acá.

`test_cores.py` suma tres: dos ranuras, la rampa y la del mapa con la
cámara corrida, en snes9x y bsnes.

Y `test_recorrido_sorbe_golden.py` saca la foto del cartel cuando está
arriba y quieto, en vez de al componer el mensaje del fork.

## Las goldens

Dos commits sólo de goldens. Lado a lado —antes, después y el RPG_RT— en
`/shared/capturas/2026-10-01-imagenes-en-sprites/`, y las dos de la
translucidez —opaca, mezclada, original— en `…/translucidez/`. Ninguna
golden que existía se movió.

## Lo que falta

* Más ranuras, para la consola: es RAM.
* Mover y agrandar con `MovePicture`: la rampa de posición es RAM también.
* Que una imagen comparta una paleta de personaje con lugar, para el
  `ABLrec` del 45.
* Las imágenes por encima de la ventana de mensaje: en RM2k la ventana las
  tapa.
