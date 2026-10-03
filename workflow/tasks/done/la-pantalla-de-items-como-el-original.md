---
name: "La pantalla de ítems como el original"
description: "Los colores del texto y los separadores de ventana del original en la pantalla de ítems, dentro de lo que deja la resolución de la SNES"
type: feature
assignee: Jacarandá
---

De taro, el 2026-09-28: "mejorar un poco la estética de la pantalla de
items. el limite de resolución de la snes complica las cosas, pero
deberíamos poder usar los colores de texto igual que en el original, y los
mismos separadores".

Lo más cercano ya hecho: `testing/el-menu-como-rm2k.md` (Tero), que sacó los
colores del skin del juego y comparó contra capturas del original con Wine.

## Qué hace el original

Mirado con el RPG_RT de 2015 corriendo con Wine, sobre una copia del juego
cuyo mapa 4 arranca con Kersh y Core en el grupo y nueve ítems en el
inventario —usables, de equipo y de switch—, y en easyrpg-player
(`Scene_Item`, `Window_Item`, `Window_Help`, `Window::RefreshFrame`,
`RefreshBackground` y `RefreshCursor`). Las capturas, a 320x240, están en
`/shared/capturas/2026-09-28-items/original-*.png`.

- **Dos ventanas pegadas**: la de ayuda arriba, de 32 de alto, y la de la
  lista abajo. Cada una es `Window` con el System del juego (`ablskin`): el
  fondo es el recuadro de 32x32 de arriba a la izquierda **estirado** a la
  ventana —`message_stretch` en 0—, que es negro con dos franjas apenas más
  claras (15,15,15) en la fila 27-28 y la columna 29; y el marco son dos
  pixeles, uno gris (67,67,67) afuera y uno oscuro (29,29,30) adentro. El
  separador entre las dos ventanas no es un dibujo aparte: son los dos marcos
  juntos, cuatro pixeles.
- **El cursor es una barra roja** (83,0,0), el recuadro del System en x=64,
  con un pixel transparente alrededor; no hay ">".
- **Colores del texto**: el nombre, los ":" y la cantidad en el color 0 si el
  ítem se puede usar y en el 3 —el gris— si no (`Window_Item::DrawItem`). La
  descripción en el 0. Los colores 0 y 3 del skin, medidos en la captura, son
  **los mismos** que ya daba la ROM a 15 bits: el degradé del blanco
  (239/231/247/255) y el del gris (181/156/123/99/74), con la sombra.
- La lista va en dos columnas de 144 pixeles con la fuente a 6.
- La elección de actor (`Scene_ActorTarget`) tiene a la izquierda el nombre
  del ítem y "Owned Items" en rojo —el color 1— con la cantidad, y a la
  derecha el grupo con la fila elegida en la barra roja.

## Qué difería en la ROM

- Colores del texto: **nada**, ya salían del skin (`pantalla_items`).
- Qué va en gris: los materiales, libros y especiales van en gris y en el
  original en blanco, porque la ROM todavía no sabe usarlos. No es un color:
  es `item_usable`, y cambiarlo sin implementarlos sería mentir. Queda así.
- **Sin ventanas ni separadores**: todo sobre negro.
- **El cursor era un ">"**.
- Una columna de once filas desde y=48, con la fuente a una letra por celda.

## Qué se hizo

- Las dos ventanas con el System del juego, en **BG1**, que en esta pantalla
  estaba apagado: el texto sigue en BG2 sin saber nada de ellas. Los
  glifos ya tenían el bit de prioridad (por la pelea), así que el texto queda
  arriba de las franjas del fondo. Los tiles, de 8bpp, van en el banco de la
  fuente detrás de ella y el tilemap en $3800; el conversor comprueba que
  entren (`_controlar_marco_de_items`). Deduplicados también espejados, son
  17 tiles.
- El cursor es la barra del System, cuatro pixeles más ancha que el texto de
  cada lado. Moverlo es copiar dos filas de celdas de BG1 —de un tilemap con
  la barra o del de sin barra—: 128 bytes por DMA en el vblank.
- La ayuda mide 48 —dos renglones— y la lista arranca en y=56 con **diez**
  filas y no once: con once la última tocaba el marco de abajo.
- El código nuevo va en el banco 1 (`banco_de_la_pantalla.s`); el banco 0
  ganó bytes, porque el ">" se escribía desde ahí.

## Qué no entra

- Las dos columnas: con letras de ocho pixeles no entran dos nombres de
  veinte letras en 256. Sigue una columna.
- La fuente a seis pixeles: ya estaba declarado.
- La ventana de "Owned Items" en la elección de actor: esa pantalla es la del
  menú, con su banco, y no se tocó.

## Equipar y habilidades

**No se tocaron.** Lo que sirve para ellas es el mecanismo —`ventana.cursor`,
`marco_items` a partir de una lista de ventanas, BG1 detrás del texto y la
barra por DMA de filas—, pero no es gratis: equipar tiene otra distribución
—el actor, los parámetros, las ranuras y la lista—, así que lleva su propio
juego de ventanas y su propio tilemap, y compone la pantalla entera en
`texto_buf` cada cuadro, así que la barra se haría distinto. Los tiles de sus
ventanas entrarían en el mismo lugar de VRAM, porque las dos pantallas no
están abiertas a la vez. Habilidades no tiene pantalla todavía ("Tech Skill"
va en gris en el menú). La tienda, que usa la misma fuente, igual que equipar.

## Pruebas

- `items` e `items-2` cambian: las ventanas, la barra en lugar del ">", y la
  lista una celda más abajo. Nueva `items-gris`: el cursor sobre el Club, en
  gris, con su descripción. La elección de actor no cambia: es la pantalla del
  menú.
- `render_items` dibuja las ventanas y la barra, y
  `test_la_lista_se_corre_cuando_el_cursor_se_sale` cuenta con `ITEM_FILAS`.
- Antes, ahora y el original, lado a lado, en
  `/shared/capturas/2026-09-28-items/`.
- Verificado con `just cartuchos` y `just pruebas` sobre esta rama: todo en
  verde. `just espacio release`: el banco 0 pasó de 175 a 205 B libres.

## Qué tiene que mirar taro

- Abrir los ítems: las dos ventanas con su marco gris, y las franjas apenas
  más claras del fondo —a la derecha y abajo—, que en el original también
  están y cuestan verlas.
- Mover el cursor: la barra roja sigue, y cuando la lista se corre también.
- Usar una poción y volver con B: la lista vuelve con las ventanas.
- Cerrar el menú: el mapa con sus colores y su scroll de siempre (BG1 se
  prende en esta pantalla y el mapa lo repone al volver).
