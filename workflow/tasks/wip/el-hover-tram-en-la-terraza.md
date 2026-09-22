---
name: "El Hover Tram en la terraza"
description: "Dibujar la nave del techo del Warehouse, horneada en un fork del mapa"
---

**Que se vea el Hover Tram** en la cinemática del techo del `Sector 27 Warehouse`
(mapa 32), donde hoy no se ve nada.

En RM2k es un `ShowPicture` —`hovertram2`, el evento `EV0003`, página 0,
comando 1, parámetros `[10, 0, -90, 110, 1, 65, ...]`—. Lo importante: **no se
mueve**. No hay ningún `MovePicture`; queda anclada al mapa y es la cámara la
que se desliza hasta ella con los `PanScreen` de `EV0005`. La borran tres
`ErasePicture` de `EV0005` y algunos eventos comunes.

Por eso no hace falta el sistema de imágenes: **se hornea en un fork del mapa**,
como el público del Auditorio, con ChipSet propio.

Medido el 2026-09-22:

- la imagen es de 254x232 y se muestra al **65%**: 165x151 px, **170 tiles de
  8x8 con algo dibujado** (5,3 KB a 4bpp) en **55 celdas de 16x16**, y 164
  colores a 15 bits;
- el mapa 32 tiene **las 8 paletas de sprite ocupadas** —diez personajes—, así
  que como objetos no entra; del fondo usa 58 de 103 colores, quedan 45;
- **el AGENCY CAPTAIN se ve debajo del tram**, así que va en la **capa de
  encima**, que en la consola se dibuja por encima de los sprites, y sus tiles
  necesitan el bit "por encima del héroe" o el conversor los hornea en el fondo;
- en las capturas el tram cae entero sobre el piso de la terraza, sin cielo
  detrás.

Lo que hay que medir antes de dibujar nada:

1. **si esa zona se ve fuera de la cinemática**; si no, alcanza con dibujarlo
   fijo y no hace falta `TileSubstitution` para prenderlo y apagarlo;
2. **cómo queda con los colores que entran**, que es la decisión artística;
3. **dónde cae exactamente**: RM2k lo ubica en su pantalla de 320x240 y la
   cámara del port es de 256x224.

Un defecto del original, medido: la imagen trae **dos píxeles** en (199,192) y
(199,193) pintados casi del color de la clave de transparencia pero no igual, así
que en el juego original se ven rosados. Están en el borde del recorte. Si
sobreviven al 65%, se tratan como transparentes y se anota la divergencia.

Referencia: `/extras/capturas/hovertram/`, tres capturas de EasyRPG que sacó
taro (el contador de FPS no es del juego).
