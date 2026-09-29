---
name: "El grupo en la tienda"
description: "Los sprites del grupo y las flechas de 'puede equiparlo' en la tienda, como Window_ShopParty"
type: feature
---

De taro, el 2026-09-28, al aprobar la tienda con ventanas: que quede en la
wishlist.

En RM2k (`Window_ShopParty` en easyrpg), al comprar hay una ventana de 136
por 48 arriba a la derecha con el grupo:
- el charset de cada uno, de frente y caminando en tres cuadros;
- en gris el que no puede equipar el ítem marcado;
- al lado de cada uno, una de las cuatro flechas del System (8x8, cuatro
  cuadros) que dice si el ítem le sube o le baja los parámetros, con la
  cuenta de `CmpEquip`.

Las capturas del original están en
`/shared/capturas/2026-09-28-tienda/original-comprar-arco.png` y
`original-comprar-chaqueta.png`.

La tienda de la ROM (`testing/la-tienda-como-el-original.md`, Aguaribay) no
lo tiene: en 256 de ancho la lista va a lo ancho y "Owned Items" con el oro
debajo, así que esa ventana no tiene dónde ir sin sacarle filas a la lista
de comprar, que ya tiene cinco. Antes de implementarlo hay que decidir de
dónde sale ese lugar.
