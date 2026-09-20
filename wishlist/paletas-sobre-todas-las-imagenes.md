# Qué

Calcular las paletas **sobre todas las imágenes del juego a la vez** —CharSets,
ChipSets y texto— unificando los negros y los grises casi iguales que hoy cada
imagen tiene por su cuenta.

# Status

Idea de taro, anotada para no perderla y **sin encarar**. Vivía adentro de "El
acolchado de bloques", en `ESTADO.md`, que es el límite que la motiva y que sigue
ahí.

# Por qué

Es una de las dos ideas que hay para **cuando haga falta apretar assets**: el
impacto visual sería mínimo y lo que se gana es espacio de cartucho, que es lo
que se termina llenando.

Quién decide esto es el asignador, `tools/port/asignador.py`, que es el único
lado donde se decide qué color se pierde: ver "`tools/voodoo/` no decide colores"
en `AGENTS.md`. Hacerlo pide mirar el juego entero de una vez y no un cartucho,
que es lo que lo hace distinto de lo que el asignador hace hoy.
