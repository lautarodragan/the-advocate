---
name: "Los sonidos adentro de las rutas"
description: "El conversor descarta los efectos de sonido que una ruta forzada pide entre pasos"
type: feature
---

Visto el 2026-09-26 midiendo el mapa 3: la escena de evilrhys pide una
docena de sonidos adentro de rutas forzadas (Decision1, Blow1 a Blow6, Shot2,
Switch1), y el conversor los descarta a propósito (`RUTA_SONIDO` en
`tools/port/eventos.py`: leer su comentario y `git blame` para saber por
qué). En RM2k suenan cuando la ruta llega a ese paso.

Mirar cuántas rutas del juego lo usan, qué haría falta en la ROM (la ruta
tendría que poder disparar un efecto en el paso: ver cómo lo hace
`sonido_de_codigo` para las páginas) y si los efectos ya están en el paquete
del mapa (lo están si la página también los pide).

# Hecho

2026-09-27, en `testing/carrera-3-lo-que-se-ve-y-se-oye.md`: la orden 35
suena en los `MoveEvent`, sobre el héroe y sobre los eventos. En el mapa 3 no:
los efectos de la escena de `evilrhys` no entran en su paquete. Qué mapas
ganaron efectos y cuáles no, y por qué, está allá y en
`SE_DE_RUTA_SIN_PAQUETE` (tools/audio/snes_music.py).
