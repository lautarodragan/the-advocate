---
name: "El espaciado sin tocar código"
description: "Que cambiar [text] letter_spacing no pida tocar el motor: el banco del menú calculado y no fijo, y el conversor revisando todo lo que tiene ancho contado; ABL pasa a +1"
type: feature
assignee: taro
---

De taro, el 2026-10-03, después de probar las tres ROMs de Tordo: "me quedo
con +1. me gustan todas, igualmente, y me gustaría mantener la perilla". Y
preguntó si cambiar el espaciado pide tocar código. Hoy sí, en tres lugares
fijos: el banco del menú (con +1 faltan 2 tiles, con +2 26), los nombres en
celdas contadas (ranuras, habilidades de la pelea) y el pozo de pares de la
tienda y la pelea. Ver `workflow/tasks/testing/el-espaciado-entre-letras.md`.

## Hecho (Benteveo)

Worktree de las herramientas desde `c66f453f`; ABL en el clon
`/extras/scratch/benteveo/abl` desde `e700650`, rama `espaciado-1`.

### El banco del menú

**El tope no se puede subir.** Tordo vio que BG1 queda libre hasta `$4C00`
en todas las disposiciones, pero entre `$2000` y `$4C00` ya está todo: el
banco del menú ($2000-$3C00, 448 tiles), su tilemap ($3C00), las ventanas
de la elección de actor y del menú en BG1 (`TARGET_VRAM`, $4000, 58 de 64
tiles de 8bpp) y su tilemap ($4800). Aun empacando perfecto, el menú tendría
460 tiles y con +2 pide 474.

Lo que se hizo es que **el menú no pague por lo que no muestra**: los
encabezados y las filas de las ranuras. Si los nombres no entran con el
banco en el orden de siempre, `rm2k-snes-screens` lo vuelve a juntar con
ese texto al final (`slots::Order::MenuFirst`) y el menú y la elección de
actor componen sus nombres desde donde terminan sus propios tiles
(`SLOT_MENU_TILES`, `tl_strip_menu`), encima del texto de las ranuras. La
pantalla de ranuras sube el banco entero cada vez que abre, así que no le
afecta. Con 0 no se reordena, y el runtime nuevo sólo se arma si
`SLOT_MENU_TILES` difiere de `SLOT_TILES`: **la ROM con 0 sale byte por
byte igual** (37dde95f…, verificado).

    espaciado   banco   el menú muestra   nombres del menú   ranuras
    +0          314     314                78 de 134          40 de 134
    +1          355     278                94 de 170          48 de 92
    +2          368     288                106 de 160         56 de 80

`tl_strip` ya no podía pisar el tilemap: `tl_strip_new` deja el nombre en
blanco si no entra (`bcs full`). Que no pase lo cuida el conversor, que si
ni reordenando entra se niega diciendo qué pide cada pantalla.

### Lo que se corta

El conversor avisa —WARNING en `conversor.log`, una línea por lugar, con
cada nombre, sus pixeles y lo que se ve— y no se niega: la consola corta y
sigue, como con las otras cosas que el cartucho lleva de menos. Revisa:

* `rm2k-snes-screens`: los actores en el menú (13 celdas) y en las ranuras
  (7), las medicinas en la elección de actor (dos renglones de 11) y el
  equipo en su pantalla (19).
* `rm2k-snes-battle`, que ahora recibe la fuente: actores y enemigos (14),
  habilidades (11), ítems (14) y comandos de habilidad (10).
* No se revisan la lista de ítems ni la tienda: 20 letras entran en las 24
  celdas que tienen con cualquier fuente que el motor acepte (una letra
  avanza 8 a lo sumo).

Con ABL:

    espaciado   ranuras   enemigos   habilidades   ítems de la pelea
    +0          3         14         26            0
    +1          3         14         26            0
    +2          3         14         28            4

**Casi todo eso es corte por letras, no por pixeles**, y es de antes de la
perilla: el cartucho guarda tantas letras como celdas, de cuando una letra
ocupaba una. "Gang Member" no entra en la ranura con 0 porque tiene 11
letras y la ranura guarda 7, aunque mida 55 de 56 pixeles; los catorce
enemigos son nombres de 15 letras o más que entrarían.

### Las habilidades

En la pelea el nombre se cortaba en 11 letras: 41 de las habilidades de ABL
con 0, cuando por pixeles no entran 3 (Tordo contó 6 sobre las 367 de la
base; el cartucho lleva las que el grupo puede usar). Ahora guarda 13, que
es lo que deja el registro de una fila de la capa de texto (`TL_RECORD`,
56 bytes, con las dos columnas); agrandarlo no entra en la RAM. Quedan 26
cortadas con 0. Eso sí cambia la ROM con 0, y va en su propio commit.

Hacerlas entrar todas pediría más celdas (correr el guión y el costo) o un
registro más grande: no se hizo. La tarea de las seis queda en `todo/`
con esto anotado.

### El pozo de pares

El conversor cuenta lo que piden las listas más cargadas, con los textos
más anchos que el cartucho puede poner en ellas (`rm2k_snes_text::cells`):
es una cota, no lo que pasa.

    espaciado   tienda   pelea: habilidades   pelea: ítems   (de 191)
    +0          142      283                  195
    +1          168      325                  228
    +2          191      350                  255

Y medido en la ROM: la pelea de `batalla` con Talan (actor 14, que puede
llegar a saber 54 habilidades) sabiéndolas todas, con la lista abierta.
**Ya con 0 el pozo se agota**: la séptima fila de habilidades sale a medias
y el primer renglón de los comandos no sale. Con 1 se agota en la sexta.
Es de antes de la perilla y no se arregló: ver
`workflow/tasks/todo/la-lista-de-habilidades-agota-el-pozo.md`.

### ABL en +1

`rm2k-snes.toml` con `letter_spacing = 1`, y el arnés le pasa la perilla
del proyecto al modelo de las pantallas (`screen_stage.spacing`), así que
las `_dibujo` esperan lo que corresponde.

**Cambian 106 goldens de la tanda, sólo letras**: miradas todas lado a lado.
Las cajas que se rearman cortan los renglones en otro lugar, algunas
descripciones pasan a dos renglones, y la lista de habilidades muestra dos
letras más de los nombres largos (ése es el cambio de las trece letras).
Ninguna del recorrido. Se repitió la tanda hasta que no apareció ninguna
roja nueva: ocho vueltas, por las escenas de varias goldens seguidas.

Dos pruebas miraban un cuadro justo y se corrieron un cuadro con los
mensajes rearmados; se tocaron las pruebas, no la ROM:

* la celebración de la granja miraba las ranuras en un cuadro con la
  pantalla apagada a mano después del salto —pasa igual con 0, un cuadro
  antes, que `CADA` no miraba—: `sin_errores` ya no cuenta lo que no se ve;
* `items-2` capturaba en el cuadro en que llegaba la descripción, que con
  1 va en dos renglones y llega uno después: ahora mira el 78. La deuda
  del texto que llega después del cursor crece un cuadro ahí (seis a siete).

### Verificado

* Con 0, `abl.sfc` sale igual, `37dde95f…`, con los commits del runtime y
  del conversor. El de las trece letras la cambia a propósito
  (`2ae0e1b3…` con 0).
* La tanda de ABL con 1, con `screens`, `mapdata`, `convert`, `battle` y
  `cartridge` en local: **1045 en verde**. `abl.sfc` con 1: `e765fa06…`.
* `cargo test` de `text`, `screens`, `mapdata`, `battle` y `convert`, y
  `just -f tools/justfile test`: 27.
* Lo que la tanda **no** cubre: el reordenamiento con 2 (armado y medido,
  no jugado ni corrida la tanda); la negativa del conversor cuando ni
  reordenando entra (la cubre la prueba de `screens` con 24 ranuras).

## Para taro

Jugar el +1: los mensajes, el menú con el grupo entero, una medicina desde
el menú (los nombres del menú van ahora encima del texto de las ranuras),
guardar en una ranura, una tienda y una pelea con habilidades. Las goldens
lado a lado y las capturas del pozo, en
`/shared/capturas/2026-10-03-espaciado-1/`, con su LEEME.

Ramas: herramientas, `worktree-agent-a06268194b190fc7f`; ABL,
`espaciado-1` del clon `/extras/scratch/benteveo/abl`.

Al mergear, reinstalar `screens`, `mapdata`, `convert` y `battle`. `text`
cambió, pero es biblioteca y va adentro de ésos; el runtime viaja con el
checkout.
