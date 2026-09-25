---
name: "Ruta: girar sin moverse"
description: "Las órdenes de ruta que giran sin caminar"
---

# Qué

Girar sin moverse en una ruta forzada: `turn_90_degree_right` y sus hermanas.

# Status

Anotado, sin empezar.

# Por qué

**No está afuera por costo sino por dónde arranca el giro.** RM2k gira sobre la
dirección que el personaje ya tenía, y para un evento que todavía no giró ésa es
la que trae su página, que la ruta no lee. O sea que hacerlo no es agregar una
orden: es darle a la ruta la dirección de partida del evento.

Los cuatro giros absolutos —`face_up` y compañía— sí están, y **encarar al
héroe** también: ver "La frecuencia de la ruta, y encarar al héroe" en
`docs/port/events.md`.
