---
name: "Las flechas se repiten en el menú"
description: "Sostener una flecha en el menú mueve la selección sola después de una espera, como Input::IsRepeated de RM2k"
type: feature
assignee: Tala
---

De taro, el 2026-09-28: "al mantener presionada una flecha direccional
dentro del menú, luego de ~1s, debería empezar a mover la selección
continuamente en esa dirección, a un ritmo de ~10 items por segundo
(revisar el código de easy rpg para confirmar)".

easyrpg (`src/input.cpp`): `start_repeat_time = 23` y `repeat_time = 4`, en
cuadros. La primera vez se dispara al apretar, después al cuadro 23 y de ahí
cada 4: `press_time == 1 || (press_time >= 23 && press_time % 4 == 0)`. Son
~0,38 s y 15 por segundo, no ~1 s y ~10: falta confirmarlo contra el RPG_RT.
