---
name: "Un salto que falla no gira al héroe"
description: "RM2k fija la dirección del salto antes de ver si puede caer; la ROM sólo si puede"
type: bug
assignee: Guanaco
---

Apareció leyendo la reja del mapa 12 —el evento 1 de (1,47)— para
`pruebas/abl/test_recorrido_vipers_otras_ramas_golden.py`, y **no se ve en
ningún caso cubierto**: ahí el héroe ya mira hacia abajo cuando el salto falla.

En easyrpg, `Game_Character::Jump` fija la dirección —y el `facing`, si no
está trabado— **antes** de llamar a `MakeWay`, así que un salto que no puede
caer deja al personaje mirando hacia donde quiso saltar. En la ROM,
`armar_salto_heroe` sólo llama a `direccion_del_salto` en `se_puede`: si
`puede_caer` dice que no, el héroe queda mirando como estaba.

Además RM2k, con la ruta sin "saltear si no puede", **reintenta** el salto; la
ROM lo saltea, y eso sí es a propósito —el comentario de `paso_de_ruta` lo
dice—. Lo que falta es sólo el giro.

Hecho es: un caso con un salto bloqueado hacia un costado distinto del que
mira el héroe, que compruebe `hero_dir` después, visto en rojo antes del
arreglo. Hay que ver también los saltos de eventos, que tienen su propio
armado.
