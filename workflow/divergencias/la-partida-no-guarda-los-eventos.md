# Qué

RM2k guarda, en cada ranura, el estado de todos los mapas que visitaste: dónde
quedó cada evento, qué página tenía activa. La partida de la ROM **no lleva
dónde quedaron los eventos**; lo que guarda lo dice `partida_tabla` en
`tools/runtime/bank1.s`, y nada más.

Al cargar, cada mapa vuelve a poner sus eventos donde dice el cartucho, igual
que al entrar por una puerta. Los switches sí vuelven, así que las páginas
activas son las correctas: una puerta abierta sigue abierta si lo que la abre
es un switch, y vuelve a su lugar si lo que la movió fue un `MoveEvent`.

Las ranuras son cuatro y no quince: ver `SRAM_RANURAS`.

# Medido

Guardar las posiciones serían `EV_MAX * 8` bytes por mapa visitado, o sea otra
clase de savefile.

# Cómo se ve hoy

No se ve mientras nadie guarde en medio de una escena que movió eventos y no
prendió switches.
