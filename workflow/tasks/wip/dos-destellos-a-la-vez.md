---
name: "Dos destellos a la vez"
description: "Kersh se queda azul en la terraza: dos destellos juntos suben una sola paleta"
---

**En la terraza del mapa 32, el Agency Captain —Kersh— se queda teñido de azul
varios mensajes**, hasta el `FlashScreen` de pantalla completa. En RM2k el
destello se apaga solo mientras sigue la conversación. taro lo vio el
2026-09-23 con el build de `3e028a0`: `kersh-blue-{1,2,3}.png` y las tres
`kersh-blue-original-*` de `pruebas-manuales/2026-09-23-3e028a0-snes/`. No es
nuevo.

Son dos `FlashSprite` de `EV0005` casi seguidos: comando 97 sobre el evento 2
—azul, 40 décimas— y comando 101 sobre el 6 —Arden, celeste, 40 décimas—, con
un solo mensaje en el medio.

# La causa, leída en el código

Hay `FLASH_MAX` ranuras de destello (4), pero **un solo `flash_buf` de 32
bytes y un solo `flash_pend`**. `flashes_tick` corre todas las ranuras y cada
una copia su paleta ahí, así que en un cuadro con dos destellos vivos el vblank
sube sólo la del último. Cuando termina el de Kersh, su último cuadro —fuerza
cero, o sea la paleta como estaba— lo pisa el de Arden y no llega nunca a
CGRAM: la paleta de Kersh se queda con el último tinte que sí subió. La arregla
la siguiente subida entera de paletas, que es el `FlashScreen`.

Nació así con `FlashSprite`, en `7340b1a` (2026-09-04): la prueba que lo
acompañó tiene un destello solo, y ningún caso de la tanda tiene dos que se
pisen.
