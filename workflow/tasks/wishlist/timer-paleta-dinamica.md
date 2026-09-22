---
name: "La paleta del cronómetro"
description: "Reservarla sólo mientras el cronómetro corre"
---

# Qué

Mejora timer: reservar la paleta sólo cuando el timer está corriendo, liberarla cuando no.

# Status

Anotado, sin empezar.

# Por qué

Hoy el conversor reserva la paleta de los dígitos en **todos** los mapas del
cartucho cuando el cronómetro está puesto, porque en RM2k el cronómetro es
global: una vez arrancado sigue visible en cualquier mapa al que vayas, así que
estáticamente no se sabe dónde hace falta.

Lo que cuesta, medido el 2026-09-20 sobre `abl`: el **mapa 18 se queda sin
gotas de lluvia** por no tener paleta libre después de reservar la del
cronómetro. Otros siete mapas ya estaban sin gotas por otras razones.

Es trabajo de la ROM, no del conversor: reservar y liberar al arrancar y parar
el cronómetro, con lo que eso implica para lo que ya está dibujado con esa
paleta.
