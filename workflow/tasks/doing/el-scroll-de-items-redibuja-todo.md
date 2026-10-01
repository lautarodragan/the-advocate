---
name: "El scroll de la lista de ítems redibuja la pantalla entera"
description: "Al bajar por la lista de ítems la pantalla queda negra un cuadro y se redibujan también los bordes de las ventanas, no sólo el texto"
type: bug
assignee: Hurón
---

De taro, el 2026-09-30, jugando: "el scroll en el menú de ítems parece causar
un redibujado completo de la pantalla, y flashea por un segundo. Creo que el
problema principal es que queda negra por un cuadro, y que se redibujan
también los bordes de las ventanas y no solo el texto".

Hecho es: al pasar de una página de la lista a la otra, sólo cambia el texto
de la lista, sin ningún cuadro negro ni redibujado de los bordes, medido
cuadro a cuadro en una prueba.

## Lo que se hizo (Hurón, 2026-09-30)

**La causa.** `move` en `items.s`, cuando el cursor se salía de las diez
filas, apagaba la pantalla (`INIDISP = $80`), volvía a subir el banco entero
—`items_screen_upload`: la fuente, el tilemap en blanco, las paletas, los
tiles y el tilemap de las ventanas— y repintaba la lista letra por letra
directo en la VRAM. Era a propósito y estaba declarado desde que nació la
pantalla (`0b060661`, 2026-09-11: "un cuadro en negro"); las ventanas se
sumaron a ese camino el 2026-09-28 (`f3b0cc90`), cuando `items_screen_upload`
pasó a subirlas también. El equipo y la tienda ya no lo hacían: componen la
pantalla entera en `text_buf` y la suben de un DMA por vblank.

**El arreglo.** La pantalla de ítems hace lo mismo que esas dos: compone el
texto entero en `text_buf` con los escritores de `text_screens.s`
(`scr_text`, `scr_glyph`, `scr_number`) y lo sube con `scr_upload` al
principio de cada vblank, después de leer el control. Mover el cursor o correr
la lista sólo recompone el búfer; la pantalla se apaga sólo al entrar y al
volver de la elección de actor. Se fueron `glyph_pair`, `text_write`,
`items_desc_upload` y la tabla `item_row_vram`; el conversor emite
`ITEM_LIST_POS` en su lugar.

**Lo medido** (una ROM instrumentada aparte, que leía el contador de líneas;
snes9x y bsnes dan lo mismo ±1): el DMA de 1.792 B termina en la línea 239,
las dos barras del cursor en la 243, y el vblank llega hasta la 261.
Recomponer la pantalla termina hacia la línea 145–170 del cuadro siguiente:
entra en un cuadro, así que no hizo falta repartir nada en dos.

**La prueba**: `test_correr_la_lista_cambia_solo_el_texto` en
`test_menu_items_dibujo.py` mira cuadro a cuadro un scroll hacia abajo y uno
hacia arriba, y pide que cada cuadro sea entera la pantalla de antes o la de
después. Contra la ROM de antes da rojo: el primer cuadro después de apretar
difiere en 7.479 pixeles —negro salvo la última fila—, en snes9x y en bsnes.

**El equipo y la tienda** no tienen el problema: sólo apagan la pantalla al
entrar (la tienda también al pasar de un modo a otro, que es cambiar de
pantalla y no correr una lista).

**Goldens**: ninguna cambió. La tira de cuadros, antes y después, está en
`/shared/capturas/2026-09-30-scroll-de-items/`.

**Espacio**: el banco 0 de `release` ganó 422 B (de 182 a 604 libres sobre la
base `69164d82`, con `just espacio`).

**Al mergear**: nada de Rust para instalar por esta rama;
`tools/port/mapdata.py` cambió de contenido, sin renombres.

**Para taro**: bajar y subir por una lista de más de diez ítems; la lista se
corre sin flash.
