---
name: "El posadero después del bosque no habla"
description: "En el mapa con una casa y un NPC en la puerta, a pocos pasos de salir del bosque en llamas y de pelear con el hover tram, el NPC debería ofrecer posada y tienda, pero no se puede interactuar con él"
type: bug
agents: [Mulita]
assignee: taro
---

De taro, el 2026-10-05: "en el mapa que tiene una casa y un npc en su
puerta, que está a pocos pasos al salir del bosque prendido fuego y haber
peleado con el hover tram, ese npc debería ser interactuable y ofrecerme inn
y shop, pero no puedo interactuar con él".

# Qué es

La salida del bosque (312 ev81 p2) deja al héroe en el 66 (34,56), y a
doce celdas al oeste está la puerta al **348, "Small General Store"**: una
casa con el dueño parado en la puerta, el evento 1 en (9,8).

* **Página 1**, sin condición: **tocar** (trigger 1) y **en la capa del
  héroe**. Es la charla de "I'm just closing up shop", que prende el
  switch 975.
* **Página 2**, con el 975: botón de acción, la elección de la tienda y la
  posada. Ésa ya andaba (`test_elegir.py` la cubre con el 975 prendido).

O sea que lo que no andaba era la página 1, y sin ella el 975 no se prende
nunca y la 2 no se activa. No era la dirección trabada de Hurón: el héroe
llega destrabado.

**Por qué**: `can_trigger` del compilador dejaba sin código toda página de
tocar en la capa del héroe, con el porqué "un evento en esa capa tapa el
paso y nunca se lo pisa". Es cierto para la celda propia
(`CheckEventTriggerHere`), pero RM2k la dispara **desde la de enfrente**
(`CheckEventTriggerThere`), de dos maneras: la A —`CheckActionEvent` mira
primero los de tocar de enfrente— y **chocándolo** —después de un `Move`
que no avanzó, en `UpdateNextMovementAction`—. El runtime no hacía ninguna
de las dos.

# El original

Con Wine (`RPG_RT_2015.exe`), con el juego arrancando en el 348 (9,10), en
un prefijo y un Xvfb propios: un paso arriba y la A, o la flecha sostenida
contra él, y **en los dos casos dice "I'm sorry, I'm just closing up
shop."**.

# El arreglo, en las herramientas

* `rm2k-snes-events`: se va `can_trigger`; una página de tocar compila en
  cualquier capa. Los hashes de `maps` de `tests/python.rs` se movieron por
  eso (el evento 4 del mapa 1 del juego de prueba), dicho en su encabezado.
* Runtime, `action_key.s`: la regla de capas de `queue_by_action` vale para
  los dos disparadores (enfrente, la del héroe; la propia, las otras);
  `try_touch` marca la celda propia; `try_bump` mira los de tocar de
  enfrente; `try_action` lo llama antes de las dos celdas de acción, en el
  orden de RM2k; y `front_cell` es la cuenta de la celda de enfrente que
  antes estaba adentro de `try_action`. `hero.s`: un paso del pad que no
  arrancó llama a `try_bump`.

Sin opcode nuevo (el `0x47` no se usó) y sin RAM nueva.

# Lo que cambia en el resto del juego

Las páginas de tocar en la capa del héroe son 17. En `release`: el 8 ev38
(GangMember1, p4), el 11 ev14 (LTSentry1, p2 y p3), el 69 ev11 p2 y el 114
ev1 p3 (vacías). Fuera de `release`: siete vacías del 131 y el 330 ev10, la
roca que se empuja (`MoveEvent` + `ProceedWithMovement`), que ahora se
empujaría.

**Declarado**: una página de acción o de tocar **vacía** no hace nada en
RM2k —`ScheduleForegroundExecution` vuelve antes, sin girar al evento—, y
acá compila a un `OP_DONE` que lo gira hacia el héroe. Era así con las de
acción; ahora también el 69 ev11 y el 114 ev1 giran al chocarlos.

# La prueba

`pruebas/rpgmaker/test_tocar_de_frente.py`: con la A desde (9,9), la charla,
el 975 y la tienda abierta; chocándolo desde (9,10), la charla y la posada,
que cobra los 100. Rojas las dos con las herramientas globales (ninguna
abre la charla), verdes con éstas.

No se agregó puerta en el mapa de debug: armar el estado de "recién salido
del bosque" a mano es más riesgo que lo que ahorra, y la prueba llega con
`ir_al_mapa`.

# Al mergear

Las herramientas son la rama `worktree-agent-abd20fdcf9df6b578`, commit
`a4fd1514`: reinstalar `events` y `cartridge` en el global (el runtime
cambió). La tanda de ABL entera con ellas: verde, sin goldens movidas.
Capturas del original y de la ROM en `/shared/capturas/2026-10-05-posadero/`.

Lo que taro tiene que jugar: salir del bosque, entrar al 348 y hablarle
al dueño con la A y chocándolo; después, la tienda y la posada. Y de paso
el pandillero del 8 (GangMember1, p4) y el centinela del 11 (LTSentry1),
que tienen páginas así y ahora hablan.
