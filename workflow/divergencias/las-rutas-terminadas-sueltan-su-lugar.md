# Qué

La ROM tiene doce lugares para las rutas de los eventos —`route_ev`, en la
BSS del banco 0, que está llena—. Hasta el 2026-10-03 un evento que recibía
uno lo tenía hasta el próximo mapa, y el conversor se negaba a armar un mapa
cuyas páginas mandaran a caminar a más de doce eventos distintos.

Desde entonces, **cuando no queda ninguno libre, el primero cuya ruta
terminó** —sin órdenes por dar, sin paso, espera ni salto, sin ruta propia:
`route_busy`— **pasa al evento que lo pide**. El tope es doce moviéndose a la
vez, no doce en todo el mapa. El conversor lo avisa en vez de frenarse. Ver
`reclaim_slot` en `tools/runtime/event_pages.s`.

Lo que el evento pierde con su lugar es lo que RM2k le guarda después de una
ruta: **la velocidad, la frecuencia y las banderas** que la ruta le cambió
—atravesar paredes, la animación fija, el giro bloqueado— vuelven a ser las
de su página. **Hacia dónde mira sí lo conserva**: se escribe en su fila
(+10), que es de donde lo lee el lugar nuevo si vuelve a caminar.

# Medido

Lo pidió la granja de A Blurred Line (127): la celebración hace saltar en su
lugar a Pierson y a los de la profesión que se elige —hasta ocho—, y el baile
que sigue tiene seis más con ruta propia. Son dieciocho eventos distintos con
ruta en el mapa, y nunca más de nueve moviéndose a la vez. Sin esto el
conversor se negaba a armar el 127; con los doce de siempre y sin soltar,
dos de los que pasean en el baile no se mueven nunca (lo cobra
`test_recorrido_granja_golden.py` de ABL, que se vio en rojo así).

Ningún mapa que ya entraba cambia: todos mandan a caminar a doce o menos, así
que nunca se quedan sin lugar libre y `reclaim_slot` no corre.

# Cuándo deja de alcanzar

Un evento al que una ruta le deja la velocidad cambiada, o atravesando
paredes, y que después de que otro le saque el lugar camina por su cuenta o
lo empujan: caminaría con lo de su página. Y un mapa con más de doce
moviéndose a la vez, donde la ruta que no encuentra lugar se pierde sin
avisar, como siempre.
