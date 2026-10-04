# Qué

La pelea no tiene el menú del grupo de antes de las órdenes —Engage,
Automatic, Escape—: cada personaje elige entre **Attack, Special, Defend,
Use Item y Escape**, y Escape va quinta **sólo en una pelea de la que se puede
huir**. Es un agregado de RPG Maker 2000 PLUS, elegido por taro el
2026-10-04.

Huir sigue siendo del grupo, como en RM2k, la elija quien la elija: si sale,
la pelea termina; si falla, se olvidan las órdenes que dieron los de antes
—un ítem elegido, que se gasta al elegirlo, vuelve al inventario—, sale el
mensaje de la huida fallida y el turno es sólo de los enemigos, que es
`ProcessSceneActionEscape` con `eFailure`. Ver `ba_flee_failed` en
`tools/runtime/battle_run.s`.

Se puede huir, como en easyrpg (`args.allow_escape`), de un encuentro al azar
y de un `EnemyEncounter` con `escape_mode` distinto de 0. El de 0 lo dice el
destino de huida de `OP_BATTLE`, `BATTLE_NO_ESCAPE`: ver `compile.rs` en
`rm2k-snes-events`.

# Qué hace RM2k

El menú del grupo aparece al empezar cada turno: Engage pide las órdenes,
Automatic las elige solo y Escape intenta la huida, que en una pelea sin
huida está en gris. Las órdenes de cada personaje son cuatro.

# Lo que no está

* **Automatic**: no hay pelea automática.
* La huida desde el menú del grupo **antes** de que nadie ordene: acá se
  elige desde la orden de un personaje, después de los que ya ordenaron.
  Lo que ordenaron se pierde, igual que en RM2k, donde no llegaron a
  ordenar.

# Medido

Con el RPG_RT de 2015 en Wine, el 2026-10-04, la prueba de pelea con las
tropas 82 y 87: el menú del grupo al empezar cada turno, con Escape en
blanco —la prueba de pelea deja huir siempre—. Dónde están las capturas lo dice la tarea,
`workflow/tasks/*/el-menu-de-la-pelea-como-rm2k.md`.

La tanda de ABL lo cubre en `test_huir_es_del_grupo` —la huida fallida, con
los HP contra el modelo— y en `test_sin_huida_no_hay_escape`.
