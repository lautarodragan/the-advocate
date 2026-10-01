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
