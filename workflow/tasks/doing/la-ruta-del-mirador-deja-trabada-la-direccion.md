---
name: "La ruta del mirador deja trabada la dirección del héroe"
description: "A velocidad 3, la escena del sueño en el mirador (mapa 109) corta la ruta del héroe antes de que destrabe la dirección, y Talan queda sin poder girar"
type: bug
agents: [Hurón]
assignee: Hurón
---

Lo encontró Hurón el 2026-10-04 (`workflow/tasks/*/dos-puertas-mas-en-el-mapa-de-debug.md`,
en ABL). La ruta del héroe del 109, evento 6, traba la dirección y la
destraba al final; a velocidad 3 —la del juego desde la carrera— la ruta se
corta antes del destrabe, la traba queda y la velocidad termina en 4. Con
la dirección trabada Talan no puede girar hacia Emily en su casa. A
velocidad 4 la ruta termina, y por eso el recorrido del primer día, que
corre a 4, no lo ve. La prueba de la puerta de Paradise destraba a mano,
con un comentario para sacarlo cuando esto se arregle. Falta ver qué hace
RM2k: si la ruta se corta en el original también, o es nuestra.
