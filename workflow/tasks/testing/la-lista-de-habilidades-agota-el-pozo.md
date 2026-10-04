---
name: "La lista de habilidades de la pelea agota el pozo de pares"
description: "Con una página entera de habilidades, la capa de texto de la pelea se queda sin pares de tiles: una fila sale a medias y el primer renglón de los comandos no sale, ya con letter_spacing en 0"
type: bug
assignee: taro
---

Lo midió Benteveo el 2026-10-03, al hacer que el conversor cuente el pozo
(`workflow/tasks/*/el-espaciado-sin-tocar-codigo.md`).

La capa de texto de la pelea tiene 191 pares de tiles (`TL_POOL_WHOLE`, de
`SLOT_VRAM` a `ITEM_BORDER_MAP`). La lista de habilidades con catorce
nombres, la descripción, los cuatro renglones del grupo y los dos de los
comandos pide más que eso. Medido en la ROM, en la pelea del caso
`batalla` con Talan —el actor 14, que puede llegar a saber 54— al frente y
sabiéndolas todas, con la lista abierta:

* con 0, la séptima fila sale a medias ("Candl…") y el primer renglón de
  los comandos no sale;
* con 1, se corta en la sexta.

Las capturas, `pozo-0-14.png`, `pozo-1-14.png` y `pozo-2-14.png`, en
`/shared/capturas/2026-10-03-espaciado-1/`. El conversor lo avisa como
WARNING ("battle text: the skill list asks for…"), con una cota que pasa
del pozo en los tres espaciados.

Caminos posibles, sin medir: más pares para la pelea —`$3800-$3C00` es el
tilemap de la escena, así que no sale de ahí—, o no dibujar lo que la lista
tapa en RM2k mientras está abierta.

## Carpintero, 2026-10-04

Worktree de las herramientas desde `fe0f90ee`; ABL en el clon
`/extras/scratch/carpintero/abl` desde `4cd8eb6`, rama `texto-de-la-pelea`.

### Lo medido antes de tocar nada

El experimento de Benteveo (Talan al frente sabiendo sus 54, la lista
abierta) con `abl.sfc` en +1: antes de abrirla quedan 118 pares libres, y
con la lista abierta 16, y aun así la séptima fila sale cortada y el primer
renglón de los comandos no sale. Los 16 son pares que volvieron al pozo
después del cambio de tilemap: las filas que se compusieron cuando no
había quedaron en blanco y no se vuelven a componer, porque su registro no
cambió. Lo que la pantalla pide es unos 205.

**La lista no se desplaza**: `ba_skill_list` junta 16 a lo sumo
(`BA_SKILL_MAX`) y la pantalla muestra 14. Con las 54, Talan sólo puede
usar las primeras 16, y las dos últimas sin verlas. Es otra cosa; va en su
tarea.

### Dónde hay VRAM

En la pelea, de la palabra 0 a la `$1FFF` no hay nada de la pelea: son los
sprites del mapa —y en algunos repartos tiles o un tilemap—, que
`back_from_battle` vuelve a subir enteros, y la palabra 0 es el tile
transparente de la escena (64 bytes en cero). Con la base de BG2 en 0 y no
en `SLOT_VRAM`, el par 0 es ése y quedan 255 pares, los que numera un byte.

### Lo que se eligió: 447 pares, desde la palabra 0 hasta el tilemap de la escena

Primero se probó con 255 —sólo hasta `$1FFF`, lo que numera un byte, y sin
tocar la RAM—: con +1 alcanzaba y quedaban 20 libres, pero con +2 la lista
volvía a cortarse (`pozo-con-255-pares-2.png`). Así que el texto llega hasta
el tilemap de la escena, `$3800`: 447 pares, y **ésa es una pantalla con
todas sus celdas entintadas** —la pelea escribe en filas pares, catorce
renglones de 32 celdas—, así que ninguna fuente ni espaciado la agota. Los
otros caminos se descartaron sin escribirlos: no dibujar lo que RM2k tapa
movía goldens quitando texto, y componer sólo las filas visibles no sirve
porque la lista no se desplaza (ver abajo) y lo que falta es una página
entera.

Lo que costó, en `text_layer.s`:

* El número de un par pasa a una palabra (`TL_PAIR`, `TL_FREE`,
  `TL_UPLOAD`). Los libres y los que esperan el cambio de tilemap comparten
  un arreglo, unos desde abajo y otros desde arriba.
* La RAM: el escenario donde se compone una fila (`TL_STAGE`, 2 KB) se
  mudó a `ANIMB_BUF` (`$7E7000`-`$7E77FF`), el cuadro de la animación de
  batalla del mapa: sólo se arma en el mapa, y toda vuelta al mapa lo limpia
  (`anim_buf_clear`). Queda dicho en `far_ram.s`.
* Devolver los pares que esperaban el cambio era un bucle en el vblank; con
  447 no entraba, y pasa a un `mvn` en `tl_step`, fuera del vblank.

Y en la pelea: `battle_bank_upload` (en `screen_bank.s`) limpia la palabra 0
—el par en blanco, que es también el tile transparente de la escena— y le
da al texto los 447; `BG12NBA` pone la base de BG2 en 0. Lo que hay en
`$0000`-`$37FF` es del mapa y `back_from_battle` ya lo vuelve a subir
entero. El conversor avisa contra 447 y no contra los 191 de la tienda.

### Medido

En la ROM, con el caso `batalla` y Talan sabiendo sus 54 (y aparte sus 16
de nombre más largo), la lista abierta y el cursor recorriéndola. Libres en
el peor momento, de 447:

    espaciado   libres
    +0          170
    +1          132
    +2          113

Con los tres se ve todo: `pozo-despues-0.png`, `-1` y `-2`.

### Verificado

* La tanda de ABL con +1 sólo con este cambio: **1045 en verde, ninguna
  golden se movió**. Y otra vez con el de los nombres: ver la otra tarea.
* `just -f tools/justfile test`: 27. `cargo test -p rm2k-snes-convert`.
* Lo que la tanda **no** cubre: no hay caso con una lista que agote los
  191; lo cubre sólo el experimento de arriba, que no se commiteó.

### Lo que se encontró de paso

**La lista de la pelea no se desplaza**: junta 16 a lo sumo y muestra 14.
Va en `workflow/tasks/todo/la-lista-de-habilidades-de-la-pelea-no-se-desplaza.md`.

## Para taro

Una pelea con habilidades, con la lista abierta y moviendo el cursor, y
volver al mapa: que los personajes y el fondo estén bien (la pelea pisa
ahora también los sprites del mapa y el reparto que tenga debajo de
`$3800`; `back_from_battle` ya los reponía). Las capturas, en
`/shared/capturas/2026-10-04-texto-de-la-pelea/`, con su LEEME.

Ramas: herramientas, `worktree-agent-af8dc9ad89d8d7220`; ABL,
`texto-de-la-pelea` del clon `/extras/scratch/carpintero/abl`.

Al mergear, reinstalar `convert` (avisa contra 447) y `battle` (la otra
tarea). El runtime viaja con el checkout.
