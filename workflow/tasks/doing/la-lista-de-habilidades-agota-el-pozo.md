---
name: "La lista de habilidades de la pelea agota el pozo de pares"
description: "Con una página entera de habilidades, la capa de texto de la pelea se queda sin pares de tiles: una fila sale a medias y el primer renglón de los comandos no sale, ya con letter_spacing en 0"
type: bug
assignee: Carpintero
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
