---
name: "Tiles animados"
description: "Las dos familias de tiles animados del ChipSet"
---

### El agua se mueve, y cuesta un DMA de 1664 bytes

RM2k anima dos familias de tiles del ChipSet, con relojes distintos y sin que
el mapa tenga nada que decir al respecto: los autotiles de agua A/B/C, que
recorren tres dibujos cada 24 cuadros en el ciclo 0,1,2,1, y los "tiles
animados", cuatro dibujos cada 6. Las dos cuentas son `TilemapLayer::Draw` de
easyrpg, `tilemap_layer.cpp:289`, y las dos cadencias por defecto —el
`animation_type` y el `animation_speed` del ChipSet— son las que tiene este
juego entero: de sus 52 ChipSets sólo dos las pisan, y ninguno de los dos lo usa
un mapa del port.

**Cómo se hace: pisando el dato del tile, no el tilemap.** Un mapa de 100x75
celdas tiene 30000 entradas de tilemap y sólo unos pocos tiles distintos que se
mueven: en el mapa 5 son **26 tiles de 8x8** de los 157 del banco, en el 2 son
7 de agua más 12 animados, en el 3 son 8 y en el 6 son 2. Así que animar es
volver a subir esos tiles y no tocar nada más — y el conversor los deja **en una
corrida contigua al final del banco**, para que un paso sea un DMA solo: 1664
bytes en el mapa 5, 128 en el 6.

Para que eso sea correcto hacen falta dos cosas más, y las dos las decide
`convert()`:

* **Un tile que se anima no se comparte con una celda quieta.** Si se
  compartiera, pisarlo haría parpadear también a la quieta. Medido: en los
  cuatro mapas no hay una sola colisión, así que separarlos no cuesta tiles.
* **El espejado se prueba sobre los dibujos juntos.** El PPU espeja el tile, no
  cada dibujo por su cuenta, así que dos celdas comparten tile sólo si las
  cuatro orientaciones coinciden en *todos* los dibujos.

Y la paleta se reparte contando los colores de todos los dibujos: el agua del
mapa 5 trae tres colores que no están en el dibujo que se ve al entrar, y sin
ellos el paso 1 no se podría escribir.

**En la consola no gasta un byte de RAM.** No por elegancia: la BSS estaba en
7680 de 7680 y la página directa en 255 de 256, así que no había dónde poner ni
un contador ni un puntero para `lda [puntero], y`. En qué punto del ciclo va
cada familia sale de **dividir `vueltas` por su cadencia con el divisor del
hardware**, y el resto de esa misma división dice si este tick es el del cambio,
que es lo único que hay que preguntar para saber si hace falta el DMA. Dónde
están los tiles y los dibujos lo trae `anim_tabla`, que arma el conversor con
la dirección de VRAM ya resuelta.

Lo que se paga es que `vueltas` es de dieciséis bits: cada dieciocho minutos la
cuenta da la vuelta y el ciclo se saltea un dibujo. Está declarado en
`assets/LIMITACIONES.md`, y no lo alcanza ninguna prueba: dieciocho minutos son
mucho más de lo que corre el caso más largo.

**Y el reloj de la ROM no es el tick de la partida.** Adentro del negro de un
teletransporte el mundo está congelado y el tick no avanza, pero la consola
sigue dando vueltas al lazo: son 70 por fundido. La cuenta que valía era el
tick más `FUNDIDO_TOTAL` por cada fundido, y sin eso la escena de Core y
Manta se iba un dibujo desde el primer teletransporte. Los dos contadores que
la llevaban eran de la referencia y se fueron con ella; del lado de la ROM
quedan `FUNDIDO_TOTAL` y `fundido_tick`, que es donde los 70 pasan.
