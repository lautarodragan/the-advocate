---
name: "La lista de habilidades de la pelea no se desplaza"
description: "La pelea junta 16 habilidades a lo sumo y muestra 14: con más, las otras no se pueden usar, y las dos últimas se eligen sin verlas"
type: bug
assignee: Chingolo
---

Lo encontró Carpintero el 2026-10-04, midiendo el pozo de pares con Talan
sabiendo sus 54 (`workflow/tasks/*/la-lista-de-habilidades-agota-el-pozo.md`).

`ba_skill_list` (`tools/runtime/battle_skills.s`) junta las habilidades que
el actor sabe y la pelea ofrece hasta `BA_SKILL_MAX`, 16, y la pantalla
dibuja `BA_SKILL_ROWS * BA_SKILL_COLUMNS`, 14. El cursor llega hasta la 16
(`mode_skill`, en `battle_run.s`, sólo mira `BA_SKILL_N`), así que las dos
últimas se eligen sin verlas, y de la 17 en adelante no están. RM2k
desplaza la lista.

Para ABL importa: Talan aprende habilidades con su sistema de auras y puede
llegar a saber 54.

Lo que pide: que la lista se desplace como la de ítems (`ba_item_see`,
la ventana de ocho renglones), con la lista entera en `BA_SKILL_LIST` —que
hoy es de 16 y la comparte la elección de acciones de los enemigos— o
juntando sólo la página visible. La capa de texto ya no es el límite: la
pelea tiene 447 pares, una pantalla entera, y una fila que dice lo que otra
decía toma sus tiles.
