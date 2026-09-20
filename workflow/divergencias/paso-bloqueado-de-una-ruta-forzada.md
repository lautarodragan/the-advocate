# Qué

**Un movimiento bloqueado de una ruta forzada se saltea**, y RM2k lo
reintentaría para siempre —`UpdateMoveRoute` con `skippable` apagado—.

Es una decisión de modelo vieja y declarada, en `tools/port/eventos.py`: una
prueba colgada no dice nada.

# Medido

Hasta el 2026-09-20 ninguna golden la ejercitaba. Con el cuadro reordenado, la
ruta del héroe de `droide-tapado` arranca un cuadro más tarde, el paso hacia
arriba cae justo cuando el droide ocupa la celda, y el paso se pierde: **el
héroe termina una celda más abajo que antes**, y no hay tick que empareje la
captura —probado de -12 a +12—.

# Cómo se ve hoy

La golden nueva congela eso. Si algún día el bloqueo pasa a reintentarse, **esas
cinco goldens se mueven**.
