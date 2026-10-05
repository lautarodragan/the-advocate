---
name: "ChangeExp y ChangeLevel"
description: "El compilador no tiene ChangeExp ni ChangeLevel, y una página con un comando que no compila se cae entera: las puertas del mapa de debug no pueden dar experiencia"
type: feature
agents: [Hurón, Carpintero]
assignee: Carpintero
---

Lo encontró Hurón el 2026-10-04, al agregar las puertas de Paradise y de
después de Fortitude (`workflow/tasks/*/dos-puertas-mas-en-el-mapa-de-debug.md`,
en ABL). Con los dos comandos, cada puerta podría dejar los niveles que
tendría alguien que jugó: después de Fortitude, Talan 3, Arden 4, Saldra 5,
AG7-17 6; en Paradise, Talan 7, Arden y Saldra 7, AG7-17 8. Fijarse si el
juego mismo los usa en algún lado.
