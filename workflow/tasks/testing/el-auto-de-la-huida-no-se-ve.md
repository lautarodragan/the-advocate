---
name: "El auto de la huida no se ve"
description: "Con una automática corriendo, el refresco completo sólo mira las automáticas"
---

**Después de elegir el auto en el techo, la cinemática del mapa 4 corre con la
pantalla negra**: se ven los textos y no el auto. En RM2k el fondo también es
negro, pero el auto está, animado. taro lo vio el 2026-09-23 jugando el build de
`3e028a0` —`pruebas-manuales/2026-09-23-3e028a0-snes/talan-arden-car-escape.png`—,
y no es nuevo.

El auto es `EV0002` o `EV0003` del mapa 4: `BLVehicles/2`, con la página
condicionada a 130 (rojo) o 131 (azul) **y** 132, que prende el mapa 33 antes
de la elección. La cinemática es la página 4 de `EV0001`, una automática que
también pide el 132.

# La causa, medida

Arrancando el cartucho de pruebas en el mapa 4 con 130 y 132 prendidos
—`en-4`—, los dos autos quedan con `npc_buf + 14` en cero y
`eleg_por_ev` en `$FFFF` para los eventos 1 y 2: **ninguna pasada de refresco
miró sus páginas**, ni la de la carga del mapa ni una forzada después.

Es `elegir_con_filtro`: para decidir entre el filtro corto (`$80`, sólo
automáticas) y el completo (`$E0`) hace `ldx solo_auto` con X en 16 bits, y eso
lee también `auto_n`, el byte de al lado. Con alguna automática activa `auto_n`
no es cero, X tampoco, y la pasada completa filtra como la corta: los eventos
que sólo tienen ruta propia o gráfico por página no eligen página nunca
mientras dure la automática.

Nació en `348cf58` (2026-09-06). Dos líneas más arriba la misma función lee
`solo_auto` con `lda`, en 8 bits, así que el `ldx` no está puesto a propósito.

**No es de este mapa**: le pasa a cualquier refresco con una automática
corriendo, que en una cinemática es lo normal.

# El arreglo

`solo_auto` se lee con `lda`, antes que la página. Con eso, en el mismo
arranque de `en-4` con 130 y 132, el evento 1 elige su página (`$A0`) y el 2
queda escondido (`$FFFD`): **el auto rojo aparece, y anima** —cambia de pose
cada diez cuadros—. El azul no, que es lo que corresponde.

Y como la página de prueba de cada caso de la tanda **es una automática**,
todos los refrescos de la tanda corrían con el error puesto: el arreglo puede
mover goldens que no tienen nada que ver con autos. El primero que apareció es
`destello-compartido-2`: el héroe ya no destella junto con el evento 4.

**No movió ninguna golden**: `just pruebas` en verde con el arreglo. Lo
de `destello-compartido-2` que se ve arriba no era esto sino el caso de la otra
tarea, que destellaba al héroe y le cambiaba al conversor el reparto de paletas
del mapa 6: ver `dos-destellos-a-la-vez`.

Lo cuida `pruebas/rpgmaker/test_refresco_con_automatica.py`, que arranca en
`en-4` con 130 y 132 y mira que el rojo se dibuje y el azul no. Se la vio en
rojo contra el `main.s` de antes del arreglo: las dos filas en cero.

Lo que **no** se corrió: la huida jugada entera, desde el techo. La prueba
llega al mapa 4 con los switches puestos a mano.
