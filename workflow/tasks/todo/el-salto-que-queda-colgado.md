---
name: "El salto que queda colgado"
description: "Un salto al final de una ruta forzada deja al héroe flotando para siempre"
---

**Un salto del héroe que es la última orden de su ruta forzada no termina
nunca**: el héroe queda flotando a mitad del arco. taro lo vio en el mapa 11,
cuando Talan salta del susto y se queda a mitad de camino mientras habla.

Medido el 2026-09-22, con el caso `camara-salto-colgado` que quedó en el repo
sin prueba: `ruta_salto` se queda en 232 y `hero_y` en 323, con la celda de
destino en `tile_y = 22`, indefinidamente.

La causa: `move_hero` llama a `paso_de_ruta` sólo mientras `ruta_i < ruta_n`, y
`paso_de_ruta` es el único que baja `ruta_salto`. Con el salto como última
orden, el contador ya llegó al final y nadie lo termina. Y `hay_rutas` tampoco
mira `ruta_salto`, así que un `ProceedWithMovement` pegado atrás no lo espera.

**196 de las 410 rutas con salto del juego terminan en el salto**, así que no
es un caso de borde.

Hecho es: el salto termina, el héroe aterriza, y hay una prueba que lo mira.
