---
name: "ChangeFaceGraphic en las deudas declaradas"
description: "ChangeFaceGraphic compila a nada pero no está en ACCEPTED_UNDONE, así que page_debts no avisa que la cara se pierde"
type: bug
agents: [Codex]
assignee: Codex
---

Lo encontró Aguará el 2026-10-06 armando el tablero contra RM2k: la rama
de `ChangeFaceGraphic` en `compile_command` da `Ok(vec![])`, pero el código
no está en `ACCEPTED_UNDONE` —la lista tiene 8—, aunque la tarea
`testing/las-caras-y-los-escapes-de-espera.md` y el commit 73b263a3 dicen
que entró. Además, el comentario de esa rama remite a
`todo/las-caras-y-las-esperas.md` sin decir dónde vive hoy.

taro, el 2026-10-06: la primera tarea de Codex, para probar el circuito.
