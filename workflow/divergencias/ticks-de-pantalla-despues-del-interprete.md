# Qué

**El destello, la sacudida, la cámara corrida, el cartel y la lluvia avanzan
después del intérprete, y en RM2k avanzan antes.** Son
`game_screen->Update()` y `game_pictures->Update()`, que en
`game_map.cpp:1305` van **antes** de `UpdateForegroundEvents`; acá van después.

# Medido

Quedó afuera al ordenar el cuadro como `Game_Map::Update`, el 2026-09-20 —ver
el comentario del lazo en `rom/src/arranque.s`—. Ninguno de esos ticks decide si algo se
mueve ni cuándo, así que **la diferencia es de un cuadro en lo que se ve** y
nada más.

# Cómo se ve hoy

No da rojo. Moverlos es otro cambio y **mueve sus goldens**, así que sale con
su propia bendición.
