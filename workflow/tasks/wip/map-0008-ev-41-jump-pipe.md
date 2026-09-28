---
name: "Bug en caño en mapa 0008"
description: "Edge case al subirse al caño en Lashe City 34,35"
type: bug
---

Si dejo apretado el auto-fire del emulador (que es más rápido que
el que tenemos implementado directamente en el rom), 
puedo subir y bajar del caño sin apretar ningún otro botón.

El EV0042 triggerea la subida con Action Button. Te deja sobre 
EV0043. EV0043 hace lo mismo, pero para bajar.

Por lo que vi, la subida es irrelevante.
Creo que lo que pasa es que el auto-fire del `A`
triggerea el evento EV0052, que está sobre el caño.
Ese evento se supone que le podés interactuar solo desde
la izquierda, nunca _sobre_ él.

No logré reproducirlo con el auto-fire propio del juego.
Tampoco pude reproducirlo en el juego original.

# Lo hecho, el 2026-09-27

**La sospecha era la buena: es el `EV0052`, y la causa es que la tecla de
acción no miraba la ruta forzada del héroe.** El caño son tres eventos:

    EV0042 (51,22)  capa de abajo, acción: sube y deja al héroe en (55,18)
    EV0043 (55,18)  capa de abajo, acción: baja y lo deja en (51,22)
    EV0052 (52,21)  capa del héroe, acción: sube, encarado desde (51,21)

La página del `EV0043` es **un `MoveEvent` solo**, sin espera: termina en el
mismo cuadro en que arranca y el héroe baja el caño con la página ya cerrada.
La ROM sólo pedía `step_left` en cero para aceptar la A, y entre dos pasos de
una ruta —y en un `wait`, y en el aire— está en cero. En el arnés, con A cada
cuadro, cada dos o cuatro y cuatro desde (55,18): en el cuadro 49 el héroe
está en (52,20) mirando abajo entre dos pasos, la A mira la celda de enfrente,
(52,21), y dispara el `EV0052`, cuya ruta arranca desde ahí y no desde
(51,21): termina en (56,19), arriba del edificio. El autofire de la ROM, de
cuatro y cuatro, cae o no según la fase con que se apriete X.

**RM2k**: `Game_Player::UpdateNextMovementAction` vuelve antes de mirar el
botón si `IsMoveRouteOverwritten()` (`game_player.cpp:297`), y recién después
viene el `IsStopping()` del que cuelga `CheckActionEvent`. La regla de capas
—la celda propia pide otra capa, la de enfrente la del héroe— ya estaba bien.

**El arreglo**: `probar_accion` vuelve sin mirar nada si al héroe le queda
ruta —`ruta_salto`, `ruta_espera`, `ruta_i < ruta_n`, las tres cosas del héroe
de `hay_rutas` sin la del paso, que ya mira quien llama—. `git blame` da
`1410cb87`, que escribió la tecla de acción cuando el héroe no tenía rutas que
sobrevivieran a su página, y su comentario cita sólo el `IsStopping()`.

**Lo que sigue pasando, y es de RM2k**: con el autofire sostenido el héroe
sube y baja para siempre, pero ahora por los eventos que corresponden. La
bajada lo deja parado **sobre** el `EV0042`, que es de otra capa y de acción,
y la A siguiente lo sube (`CheckEventTriggerHere`); la subida lo deja sobre el
`EV0043`, y la A siguiente lo baja. RM2k hace lo mismo con cualquier autofire.

**Otros lugares**: un script aproximado —páginas con un `MoveEvent` sobre el
héroe sin `ProceedWithMovement` detrás, siguiendo la ruta y mirando en cada
parada si había un evento de acción abajo o enfrente— da unas treinta
páginas candidatas en los mapas 8, 9, 95, 261, 278, 279, 343 y 344. Es
aproximado —la celda de arranque de los eventos de la capa del héroe se
adivina— y no hace falta afinarlo: el arreglo es general y las cubre a todas.

**La prueba**: `pruebas/rpgmaker/test_accion_con_ruta.py`, A cada uno, dos y
cuatro cuadros desde el `EV0043`: lo segundo que arranca tiene que ser el
`EV0042` y en (51,22). Sin el arreglo da rojo en las tres —"disparó el evento
de índice 51 con el héroe en (52, 20)"—; con él, verde. La misma aserción
cobra que la A de después de la ruta no se pierda.

## Lo que tiene que probar taro

Con el autofire del emulador sostenido sobre el caño: bajando ya no tiene que
volver a subir a mitad de camino ni aparecer arriba del edificio, en (56,19).
Que suba y baje entero, de punta a punta, sí es lo esperado.
