---
name: "El HP de los enemigos escondido, y el trueno del despegue"
description: "Esconder los HP de los enemigos como RM2k (con flag para depurar) y grabar el tema de batalla con y sin Thunder9 para que taro decida"
type: feature
assignee: Ombú
---

Dos cosas chicas de la pelea, del 2026-09-28.

**El HP de los enemigos.** RM2k no lo muestra nunca y ABL no tiene cómo verlo
(lo midió Tero: `testing/el-menu-como-rm2k.md`). taro aceptó la propuesta:
esconderlo por defecto con un flag de armado, `CON_HP_DE_ENEMIGOS = False` en
`cartuchos.py`, como `CON_MAPA_DE_DEBUG`. Hoy lo dibuja `ba_renglon` en
`rom/src/batalla.s`; en `pantallas.py` está anotado como decisión propia.

**El trueno del despegue.** La página de turno 1 de las tropas 102 y 104 pide
Thunder9, y no suena porque meterlo en el paquete de la pelea le baja al tema
de batalla seis instrumentos de ~14 a ~11,5 kHz y el BRASS64 de 16,3 a 10,8
(lo midió Ceibo: `testing/eventos-de-tropa-de-release.md`). Se decide
escuchando.
