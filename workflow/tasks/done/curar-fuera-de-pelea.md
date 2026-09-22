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

## Dónde quedó, el 2026-09-21

Lo de "hecho es" está, con casos que corren la ROM en
`pruebas/rpgmaker/test_curar_menu.py`. Las causas:

- **El sándwich**: la elección de actor no hacía nada con A sobre una
  medicina, a propósito, desde antes de que los HP fueran estado. Ahora es
  `medicina_usar`, que es `Game_Party::UseItem` entero.
- **El elixir**, lo mismo. La sospecha del estado de caído se descartó:
  `IsDead` de easyrpg mira los HP, así que un caído es un actor en cero HP y
  no hace falta guardar ningún estado. La partida guardada no cambió.
- **Los gráficos**: `ranura_rect_subir` leía el ancho de fila en 16 bits y
  `menu_grupo_pintar` lo escribía en 8. Se rompía con un ítem en gris al final
  de la lista.

Lo que quedó afuera:

- **El elixir en la pelea**: la pelea no ofrece los ítems `ko_only`
  (`batalla.item_usable_en_batalla`), así que ahí taro lo sigue sin poder
  usar. Hacerlo pide que el cursor de blanco de un ítem pueda pararse en un
  aliado caído, que el levantado vuelva a pedir órdenes el turno siguiente y
  cobre la experiencia al ganar, y mover `batalla.py` igual, que es contra lo
  que `test_batalla.py` predice los HP. Es de la pelea, no del menú.
- **La columna de la izquierda de la elección**, que en RM2k dice el ítem y
  cuántos quedan: sigue vacía, como estaba declarado en `titulo.py`.
- **Los usos de un ítem de varios**: se gasta uno por uso, como en los de
  switch. Las medicinas de este juego son todas de un uso.
