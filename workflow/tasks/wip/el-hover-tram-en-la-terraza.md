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

# Las tres respuestas, medidas el 2026-09-22

Los scripts que las sacan están en `/extras/scratch/hover-tram/`.

## 1. No se ve fuera de la cinemática: va fijo, sin `TileSubstitution`

La terraza es una región **cerrada de 224 celdas** —`conecta.py`, con la misma
pasabilidad que usa el conversor, `rm2k.passability_map`—: desde la planta baja
no se llega caminando, y desde la terraza no se sale.

La única entrada es el `Teleport` a **(43,2)** de `EV0003`, que es un evento de
**contacto** en (38,28) sin condiciones y que hace el `ShowPicture`
**inmediatamente antes** de teleportar. Las únicas salidas son el `Teleport` de
contacto de `EV0004` en (43,1) y el final de `EV0005`, que manda al mapa 33.

O sea que **cada vez que la cámara puede ver esas celdas, RM2k tiene la imagen
puesta**. No hay ningún estado donde la zona se vea sin el tram, así que no hace
falta prenderlo ni apagarlo.

## 2. Dónde cae: pixel del mapa (308,35), 165x150

La imagen escalada al 65% con vecino más cercano queda en **165x150** —no 151—
y su esquina cae en el **pixel (308,35) del mapa**, que es la **celda (19,2) más
(4,3) adentro**: no está alineada a la grilla.

Se midió contra la captura 1 de EasyRPG en dos pasos independientes
—`ubicar.py` y `ubicar_tram.py`—: primero la cámara de la captura, calzando una
región de mapa puro contra el mapa rendido, que da **(256,16)** con 93,7% de
pixeles iguales; después el tram, que calza con **97,3% de sus pixeles opacos
exactamente iguales**. El 65% con vecino más cercano es entonces lo que hace
RM2k, y el `ShowPicture` de `[..., -90, 110, 1, 65, ...]` es el **centro** de la
imagen, anclado al mapa (`origin` 0 en RM2k).

La caja es de **celdas x 19..29, y 2..11**, con **53 celdas** con algo dibujado
—no 55—, **172 tiles de 8x8** y **159 colores a 15 bits** (206 a 24). Las
diferencias con lo anotado antes son del redondeo del 65%.

## 3. Los colores entran, y el tram sobrevive

El reparto real no es contra el fondo sino contra **la capa de encima**, que es
donde va: el fondo del mapa 32 usa 58 colores y **se lleva 5 de las 8 paletas**,
así que a la capa de encima le quedan **3 paletas = 45 colores** —de ahí sale el
45—. Con el tram esa capa pasa de 7 a **163 colores**, y `repartir_encima`
—el mismo código del conversor— los baja con **146 fusiones**, usando 2 paletas.

**Se ve bien**: el tram es casi todo gris y marrón desaturado, así que las
fusiones caen entre vecinos. Las capturas están en `/extras/capturas/hovertram/`:
`tram-comparado.png` es el antes y el después a 3x, y `port-320x240.png` tiene el
mismo encuadre que la captura 1 de EasyRPG.

# Lo que no entra en la forma de hoy

La receta del ChipSet **no puede traer esta imagen**, y no por la operación que
falta —`desde_imagen` sería igual que `desde_charset`— sino por el **vehículo**:
el PNG del ChipSet es indexado y tiene 256 entradas.

    ChipSet1, la base del 11              usa 134 índices
    pisando las 55 ranuras altas que hacen falta   quedan 130 libres
    el tram pide, a 24 bits                       204 índices nuevos
    el tram pide, a 15 bits                       148 índices nuevos

130 < 148: **no entra**. Sólo entra si el fork además hace dos cosas que hoy no
hace, y las dos son decisiones, no detalles —`paleta.py` y `techo.py`—:

* **podar el ChipSet a lo que el mapa 32 dibuja.** El 55 es privado del mapa, así
  que lo que el mapa no dibuja es peso muerto: podado quedan **82 índices usados
  y 174 libres**. Pero eso cambia qué es el ChipSet de un fork.
* **redondear el tram a 15 bits antes de escribirlo**, que es lo que baja 204 a
  148. Para la consola no pierde nada —el asignador cuantiza con `>>3` igual—,
  pero deja de ser el arte del juego lo que el fork escribe.

Con las dos, 148 ≤ 174 y entra. **Falta que taro diga si van.**

# Lo demás que quedó medido

* **Las ranuras**: el mapa 32 usa 33 de las 144 altas, y **63..117 son 55
  consecutivas libres**. `passable_upper[0]` del ChipSet 11 es **0x1F**, así que
  las ranuras del tram tienen que llevar 0x1F para no tocar la pasabilidad.
* **La pared de la terraza**: la columna x=19 tiene la ranura alta 18 —flags
  0x00— en las filas 2 a 11, y ahí caen **9 pixeles** de la punta del tram, en
  las celdas (19,4) y (19,5). Los 9 están en la franja x 316..319, que es
  justo la que tapa un sprite parado en la columna 20 —se dibuja en `x*16-4`—,
  así que los dos caminos posibles divergen en esos 9 pixeles: dejarlos afuera
  los pierde siempre, y meterlos con los flags de la pared los dibuja debajo del
  héroe cuando RM2k los dibuja encima.
* **El defecto de los dos pixeles rosados**: al 65% **sobrevive uno solo**, el
  de (199,192) —`(255,39,194)`, casi la clave `(255,33,192)`—, y cae en el pixel
  del mapa (437,159), celda (27,9). El de (199,193) no lo muestrea el vecino más
  cercano y se va solo.
* **La cámara de las capturas**: la 1 está en (256,16) y la 2 en (416,16).

Referencia: `/extras/capturas/hovertram/`, tres capturas de EasyRPG que sacó
taro (el contador de FPS no es del juego).
