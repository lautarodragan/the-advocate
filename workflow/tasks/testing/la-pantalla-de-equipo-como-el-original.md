---
name: "La pantalla de equipo como el original"
description: "Las ventanas del System y la barra roja de cursor de la pantalla de ítems, llevadas a la de equipar"
type: feature
assignee: Ñandú
---

De taro, el 2026-09-28: "Ahora quiero implementar las mejoras de UI que
hicimos en el menú de items para el menú de equipamiento".

Lo de ítems está en `testing/la-pantalla-de-items-como-el-original.md`
(Jacarandá, `f3b0cc90`): las ventanas del System en BG1 detrás del texto de
BG2, y la barra roja como cursor en lugar del ">". Su sección "Equipar y
habilidades" ya dice qué sirve y qué no: el mecanismo sirve, pero equipar
tiene otra distribución —ayuda, actor con parámetros, ranuras y lista—, así
que lleva su propio juego de ventanas y su propio tilemap, y compone la
pantalla entera en `texto_buf` cada cuadro, así que la barra va distinta.

El original, con Wine: `/shared/capturas/2026-09-28-el-menu/original-equipo*.png`.
Cuatro ventanas: la ayuda arriba a lo ancho, el actor y sus parámetros a la
izquierda, las ranuras a la derecha, y la lista de lo que se puede poner
abajo a lo ancho, en dos columnas. Los términos de parámetros y ranuras en
el color 1 (rojo).
