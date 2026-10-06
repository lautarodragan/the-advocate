---
name: "ChangeFaceGraphic en las deudas declaradas"
description: "ChangeFaceGraphic compila a nada pero no está en ACCEPTED_UNDONE, así que page_debts no avisa que la cara se pierde"
type: bug
agents: [Codex]
assignee: taro
---

Lo encontró Aguará el 2026-10-06 armando el tablero contra RM2k: la rama
de `ChangeFaceGraphic` en `compile_command` da `Ok(vec![])`, pero el código
no está en `ACCEPTED_UNDONE` —la lista tiene 8—, aunque la tarea
`testing/las-caras-y-los-escapes-de-espera.md` y el commit 73b263a3 dicen
que entró. Además, el comentario de esa rama remite a
`todo/las-caras-y-las-esperas.md` sin decir dónde vive hoy.

taro, el 2026-10-06: la primera tarea de Codex, para probar el circuito.

Codex, el 2026-10-06: `git blame` y `git log -S` muestran que no se perdió en
un merge. El commit 73b263a3 agregó la rama y su prueba de compilación, pero
dejó `ACCEPTED_UNDONE` con las mismas seis entradas; los merges posteriores
sólo agregaron otras deudas.

La prueba `change_face_graphic_is_reported_as_debt` dio rojo antes del arreglo:
`page_debts` devolvía `[]` en vez de `[10130]`.

Hecho: `CHANGE_FACE_GRAPHIC` entra en `ACCEPTED_UNDONE`, y el comentario de su
rama sigue la tarea sin depender de la carpeta en la que esté. Verificado con
`just -f tools/justfile crate-test events` y, en un clon de ABL usando la
instalación local de `events`, con `just cartuchos` y `just pruebas`.

La tanda no ejecuta el aviso nuevo: ABL no tiene el comando 10130 en sus JSON.
Sí verifica que el cartucho y el resto de la tanda no cambien; el aviso lo
cubre directamente la prueba unitaria nueva.

Al mergear, instalar `events`.
