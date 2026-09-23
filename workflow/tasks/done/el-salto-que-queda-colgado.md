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

# Lo hecho, el 2026-09-23

**La causa era la de arriba, tal cual.** El descuento se mudó de `paso_de_ruta`
a `salto_avanzar_heroe`, y lo llama `move_hero` en el mismo lugar donde ya
termina un paso en curso: eso es lo que hace RM2k, donde el que baja el salto es
`Game_Character::Update` —pregunta `IsJumping()` **antes** de mirar si quedan
órdenes, porque estar en el aire no es estar quieto: `IsStopping()` es
`!(IsMoving() || IsJumping())`— y el que lo apaga es
`Game_Character::UpdateMovement`. Con la ruta todavía con órdenes queda
exactamente lo de antes, porque ahí `paso_de_ruta` miraba el salto primero
igual.

Y `hay_rutas` ahora mira `ruta_salto`: es `IsAnyMovePending`, y allá
`MoveRouteFinished` se prende adentro de `UpdateMovement`, o sea al aterrizar.
Va pelado, sin el cuidado que necesita `step_left`, porque el único que pone
`ruta_salto` es `armar_salto_heroe` y a ése lo llama sólo `paso_de_ruta`: del
pad no sale ningún salto.

**Los eventos no lo tenían.** `mover_eventos` les llama a `cuadro_de_ruta_ev`
una vez por cuadro para toda ranura ocupada, sin mirar el contador de órdenes, y
`hay_rutas` ya miraba su `ruta_ev + 13`. Lo sostiene una prueba, para que se
vea si alguien les pone la guarda que tenía `move_hero`.

**Ninguna golden se movió, y eso no es que el arreglo no se vea**: el único caso
de la tanda que pisa el mapa 11 es `en-11`, que entra y nada más —lo usa
`test_paralelos`, sin golden—. El momento que taro ve no lo ejecuta ninguna
prueba, que es el modo de falla de siempre.

## El tirón de cámara, comprobado

Con el arreglo **no queda ningún caso que deslice la cámara más de una fila por
vuelta que no sea el héroe a velocidad 6 más un pan**. Medido sobre los casos
del cartucho de pruebas, 240 vueltas cada uno, contando sólo las vueltas sin
cambio de mapa ni salto de celda: los únicos que pasan de 8 px son
`camara-veloz` y `camara-veloz-x`, con 16 px justos, que es el peor caso que ya
estaba medido.

Lo que apareció midiendo: **el tirón del aterrizaje de golpe no lo reproduce
ningún caso del cartucho**, ni antes ni después del arreglo. Los tirones grandes
de `en-4` y `talan` —256 y 192 px— son teletransportes al mismo mapa, que
escriben `hero_y` y llaman a `fill_window`, así que nunca le debieron una fila a
`stream_map`.

Y de ahí salió lo único que había que cuidar: ese atajo del teletransporte no
toca `ruta_salto`, así que con arco pendiente el héroe se correría hasta 29 px
de donde el teletransporte lo puso, con la ventana recién llena. **No pasa, por
plazos**: el `Teleport` cuesta el fundido —unos noventa ticks hasta que la celda
nueva aparece— y un salto dura once. Quedó el caso
`salto-teleport-en-el-aire` con su prueba, para que se sepa si ese orden deja de
valer.

## Lo que no se hizo

* **El salto del héroe no respeta la velocidad.** `SALTO_VELOCIDAD` es fijo, el
  de la velocidad 4, mientras los eventos lo sacan de `salto_por_vel` como
  `jump_speed[move_speed - 1]` de RM2k. Un `increase_movement_speed` sobre el
  héroe le cambia el paso y no el salto. Ya estaba, y este arreglo no lo toca.
* **taro no lo jugó todavía.** Lo que se corrió es `just pruebas`.

# Jugado

taro lo jugó el 2026-09-23 con el build de `3e028a0`: el salto ya no queda
colgado.
