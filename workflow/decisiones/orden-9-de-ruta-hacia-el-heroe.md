# Qué

**La orden 9 de ruta, `move_towards_hero`, se camina** desde el 2026-09-12. Las
otras nueve órdenes de movimiento que faltan —al azar, huyendo del héroe, hacia
adelante y los cinco giros en el lugar— **no**.

# Por qué

No es una orden nueva: `UpdateMoveRoute` hace `TurnTowardCharacter(hero)` y
después `Move(GetDirection())`, o sea la 21 y un `move_*` pegados, así que se
resuelve con lo que ya había.

Medido sobre el juego entero: **+33 páginas** —de 2802 a 2835—, y es la única
que rendía. **Las otras nueve suman +1 entre todas**, y por eso siguen afuera.

La cubre `npc-hacia-heroe`. Queda afuera en las **rutas propias de página**, que
son dos del mapa 105 y ninguna prueba llega ahí; ver `ruta_propia`.
