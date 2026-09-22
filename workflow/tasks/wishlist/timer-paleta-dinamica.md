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

Lo que costaba, medido el 2026-09-20 sobre `abl`: el **mapa 18 se quedaba sin
gotas de lluvia** por no tener paleta libre después de reservar la del
cronómetro. **Hoy no cuesta nada ahí**: desde que el público del Auditorio se
horneó en su ChipSet, al mapa 18 le sobran paletas y llueve. Los otros siete
mapas sin gotas —el 2, 3, 8, 9, 10, 13 y 17— lo están por otras razones, así
que esto hoy no le devuelve la lluvia a ninguno; lo dice el conversor al armar
`abl`, con un aviso por mapa.

Es trabajo de la ROM, no del conversor: reservar y liberar al arrancar y parar
el cronómetro, con lo que eso implica para lo que ya está dibujado con esa
paleta.
