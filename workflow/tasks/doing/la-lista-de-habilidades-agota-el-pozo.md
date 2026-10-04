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
