---
name: "Recortar una imagen en vez de escalarla"
description: "Una opción del motor para que una imagen de pantalla completa se recorte a la ventana de la consola en vez de escalarse; ABL la usa en las cuatro fotos Diff, que son capturas del mapa"
type: feature
assignee: Golondrina
---

De taro, el 2026-10-02 (la tarea del juego está en ABL:
`workflow/tasks/todo/las-fotos-diff-recortadas-y-el-montaje.md`): las fotos
Diff son capturas del mapa a 320x240, y el original las usa para un efecto
de "en vivo a foto". Escaladas a 256 ya no coinciden con el mapa de la ROM.
Recortadas sí, porque la ROM no escala el mapa.

Va encima de `sin-resample` (Corbatita): con `image` en lugar del LANCZOS de
Pillow, las fotos escaladas eligen otros colores al reducirse y la sombra del
árbol pasa de verde a azul. Recortadas no pasan por el escalador. Hornero
propuso esperar a esto antes de mergear `sin-resample`, para que esa versión
no entre nunca, y taro dijo que vaya con lo que le parezca bien. El montaje
del 217 queda para después del piloto del modo 7.
