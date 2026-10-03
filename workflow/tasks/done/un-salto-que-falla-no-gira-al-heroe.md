---
name: "Un salto que falla no gira al héroe"
description: "RM2k fija la dirección del salto antes de ver si puede caer; la ROM sólo si puede"
type: bug
assignee: taro
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

# Lo hecho (Guanaco, 2026-09-30; el cierre, Hornero)

Lo escribe Hornero con el informe de Guanaco: a Guanaco el clasificador de
auto mode le negó leer este archivo, y también regenerar los cuadros que
quedaban.

**Confirmado en easyrpg** (`Game_Character::Jump` y `UpdateMoveRoute`),
para el héroe y los eventos: `Jump` fija la dirección —y el `facing` si no
está trabado— antes de `MakeWay`. Si el salto falla y la ruta no se puede
saltear, RM2k lo reintenta y el giro queda; si se puede saltear, RM2k
restaura la dirección y el `facing`. La ROM recibe toda ruta forzada como
salteable y no las distingue, así que gira siempre: de las 410 rutas
forzadas del juego con un salto, sólo 6 son salteables y ninguna es del
héroe. El comentario del código lo dice. **No se confirmó con el RPG_RT
bajo Wine**: pedía armar un mapa de RM2k con el salto bloqueado.

**El arreglo** (`7fd79fa6`, `tools/runtime/oam.s`): en `build_hero_jump` y
`build_ev_jump` el giro va antes de `can_fall`, y el de eventos mira además
el bit de dirección trabada (+18 `$08`). Salió un segundo error al escribir
el caso trabado: la ROM giraba a un evento trabado aunque el salto cayera
bien. Se arregló en el mismo commit.

**Las pruebas** (`rom/pruebas/rpgmaker/test_salto_bloqueado.py`), las cuatro
contra el borde del mapa 6: el héroe (quedaba mirando arriba en vez de a la
izquierda), Kersh (abajo en vez de arriba), Kersh trabado con un salto que
cae (a la derecha en vez de abajo) y Kersh trabado con uno que no cae, que
ya pasaba. Las tres primeras, en rojo antes del arreglo.

**Las goldens**: el droide del mapa 2 (EV0040) tiene la dirección fija
mirando arriba y salta hacia abajo; la ROM lo dejaba mirando abajo después
de cada salto y ahora sigue mirando arriba. Cambian doce cuadros de
`bloqueo`, `droide` y `droide-tapado`, sólo en el droide: tres en
`915a4801` (Guanaco) y nueve en `255c7252` (Hornero, mirados uno por uno).
El antes y el después están en `/shared/capturas/2026-09-30-salto-que-falla/`.
**El merge espera el visto bueno de taro.** (El mensaje de `915a4801` dice
que esos tres son todo lo que cambia, y el de `7fd79fa6` nombra sólo tres
cuadros: los dos se quedaron cortos.)

**Al mergear**: nada de Rust que instalar. La ROM se mueve, así que puede
hacer falta volver a medir los techos de la música; `test_musica_techos.py`
pasó en la rama.

**Lo que queda**: la divergencia de las rutas salteables, donde RM2k
restaura el `facing` y la ROM no; y lo mismo con un `move_*` bloqueado de
un evento: la ROM deja el giro y RM2k lo deshace. No se tocó.
