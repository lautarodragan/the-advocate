---
name: "Ignorar ChangeSystemGraphics, por ahora"
description: "Que ChangeSystemGraphics no deje afuera la página que lo usa: aceptarlo sin hacer nada, como deuda, hasta que se implemente (changesystemgraphics.md, en todo)"
type: feature
agents: [Mulita]
assignee: taro
---

De taro, el 2026-10-05: "ignorar el ChangeSystemGraphics. Dejemos una tarea
en todo para implementarlo, y por ahora no permitamos que su falta de
implementación impida compilar páginas". Destraba el arranque de Sunset Over
Imdahl (mapa 11), con el menú todavía en el System equivocado.

Hecho por Mulita, el 2026-10-05: `CHANGE_SYSTEM_GRAPHICS` (10680) entra en `ACCEPTED_UNDONE` y su rama devuelve `vec![]`; las páginas de tropa pasan por el mismo `compile_page`. Prueba `change_system_graphics_is_accepted_without_emitting`, roja antes. ABL no usa el comando (sin ocurrencias en su `data/`), así que su ROM no cambia. Sunset Over Imdahl: el evento de arranque del mapa 11 ya corre (fundido del título, pantalla negra a los 15 s como el original); a los 30 s el original muestra una imagen y el cartucho sigue negro: no se investigó.
