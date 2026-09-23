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

# El arreglo

**Una paleta por ranura**, en la RAM lejana: `FAR_FLASH_PAL`, $6900 a $69FF,
reservado el 2026-09-23 —en la BSS quedaban 75 bytes y hacían falta 96 más—.
Lo que está pendiente de subir va en el byte +7 de cada ranura de `flash_ev`,
que estaba libre: la entrada de CGRAM de su paleta, que nunca es cero porque
las de sprite arrancan en la 128. El vblank sube todas las pendientes. Salen de
la BSS `flash_buf`, `flash_pend` y `flash_pend_cgadd`: 34 bytes.

Lo cuida `test_destellos_encimados`, con el caso `destellos-encimados`: el
evento 1 destella diez décimas, y dos décimas después el 4 destella treinta. En
el tick 90 el 1 tiene que verse como en el tick de llegada. Se la vio en rojo
contra el `main.s` de antes.

Dos cosas que costaron y conviene saber:

* **La comparación tiene que ser contra el tick de llegada**, no contra uno de
  después de los dos destellos: con el error el primero **no vuelve nunca**, así
  que el final también está teñido y la primera versión de la prueba pasaba con
  la ROM rota.
* **Destellar al héroe en el mapa 6 cambia el reparto de paletas del mapa
  entero**: la primera versión del caso lo hacía, y se movieron las goldens de
  `grafico`, `grafico-heroe`, `sprite-actor` y `destello-compartido` —con
  cualquiera de los dos `main.s`—. Por eso el segundo blanco es el 4.

Con todo, `just pruebas` en verde y ninguna golden se movió.
