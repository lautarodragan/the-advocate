**Usar un ítem de curación desde el menú, fuera de la pelea.**

Reporte de taro del 2026-09-21: el `Cold Sandwich-HP` (medicina, recupera 30 HP)
cura en la pelea y no fuera de ella. Y después de intentarlo, si se vuelve a la
pantalla anterior y se entra otra vez a la selección de personaje sin cerrar el
menú, los gráficos se rompen; cerrar y abrir el menú lo arregla.

Probablemente del mismo lado: el `Pungent Elixir-LIFE` (`ko_only`) no se pudo
usar en Arden con 0 HP ni fuera ni dentro de la pelea. La sospecha, sin
comprobar, es que llegar a 0 HP no pone el estado de caído, y el ítem busca el
estado.

Hecho es: los dos ítems hacen fuera de la pelea lo que hacen en RM2k, la
selección de personaje se dibuja bien al volver, y hay pruebas que lo miran.
