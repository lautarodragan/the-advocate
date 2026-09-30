---
name: "A quién equipar, desde el menú"
description: "Elegir a quién equipar sobre el menú principal, como Scene_Menu, y no en la pantalla de la elección de actor con la mitad izquierda vacía"
type: feature
assignee: Tatú
---

Apareció el 2026-09-28, mirando la golden `equipo-a-quien` de la elección de
actor (`testing/la-eleccion-de-actor-como-el-original.md`, Ñandú): elegir a
quién equipar usa la pantalla de la elección de actor sin las ventanas del
ítem, y la mitad izquierda queda negra. Antes de ese cambio ya estaba así,
sobre negro y con el ">".

En RM2k no hay una pantalla aparte: `Scene_Menu`, con Equipment, pasa el
cursor al panel del grupo del mismo menú —los comandos siguen a la
izquierda— y A abre `Scene_Equip` con ese actor. Hay que confirmarlo en
easyrpg (`scene_menu.cpp`) y con el RPG_RT con Wine.

taro todavía no la pidió: la anotó Hornero al proponerla.
