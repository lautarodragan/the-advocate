# Qué

Las celdas que cambian llevan tiles propios, en una corrida por familia: una
para el agua y otra para los tiles animados. Una celda que cambiara con las dos
—agua en la capa baja y un tile animado en la alta— pediría todos los cruces de
dibujos y no dos corridas, así que **Voodoo la rechaza** y el conversor no arma
la ROM. RM2k la dibuja sin problema.

Ver "Animations" en `tools/snes/voodoo/README.md`.

# Medido

El 2026-09-09, cero celdas así en los 328 `.lmu` que trae el juego.

# Cómo se ve hoy

No se ve: en *A Blurred Line* no hay ninguna. Es una de las que hay que mirar
si esto se apunta a otro juego, y ahí corta con la celda en el mensaje en vez
de emitir un dibujo que acierta la mitad del tiempo.
