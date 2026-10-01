---
name: "Los vehículos giran cuando no tienen que girar"
description: "El hover tram, las naves de la agencia y el auto de la carrera tienen charsets hechos para no rotar, y en la ROM miran hacia donde caminan"
type: bug
assignee: taro
---

De taro, el 2026-09-30, jugando en la SNES: "los vehículos, al moverse, se
ven rotos porque los charsets están editados a medias, diseñados para que
ciertos vehículos no puedan rotar. Creo que hay una opción de los eventos
que les fuerza cierta dirección, y, al estar activada, no miran hacia donde
caminan". Se ve en:

- el hover tram del inicio;
- las naves de la agencia, cuando empieza a sonar Lunar Pyramid;
- el auto de la carrera: "por momentos, puedo cambiarle el color al auto, o
  convertirlo en otro vehículo, apretando las teclas direccionales".

Pista de Hornero: `tools/runtime/oam.s` dice que para el héroe "no
`lock_facing` to look at: `step_route` ignores 26 and 27", es decir que las
órdenes de ruta que traban la dirección no se cumplen sobre el héroe.

# Lo hecho (Coipo, 2026-09-30 y 10-01)

**Los tres casos**, buscados en `rom/data/`:

- **El tram de Lashe City** (mapa 9, EV27 "Hover-Tram"): un evento con
  `animation_type` 4 ("gráfico fijo") mirando a la izquierda y sin ruta
  propia; al subir, un `MoveEvent` forzado lo baja cinco celdas. Es el
  "hover tram del inicio": Lashe City es donde arranca el juego.
- **Las naves de la agencia** (mapa 28, EV11 "Hover2" y EV12 "Hover1"): lo
  mismo, gráfico fijo mirando a la izquierda, bajadas por el `MoveEvent`
  del EV15, el mismo que pone `Lunar_Pyramid`.
- **El auto de la carrera** (mapas 49, 51, 52 y 54, EV1 "RaceController"):
  es **el héroe**, con los actores 19 y 20 en `Future3`, y una ruta forzada
  `13, 26` (o `14, 26`) que traba la dirección y **nunca la destraba**: el 27
  llega recién en el mapa 64. La ROM tiraba el 26 en el compilador, así que
  cada flecha le ponía la fila de esa dirección, que en ese CharSet es otro
  auto.

En total, `scan2.py` (descartable) encontró 13 eventos con página de
dirección fija movidos por una ruta forzada —también Dessen, el Bum de
Sector 30, Emily, los Package, los Canister—, y 35 rutas del héroe con 26,
todas con su 27 en la misma ruta salvo las de la carrera.

**Qué hace RM2k** (easyrpg, `game_character.cpp/.h`): `Move` hace
`SetDirection` y `UpdateFacing`, que con `IsFacingLocked()` no toca el
`facing`; el pad del héroe pasa por el mismo `Move`. `lock_facing` lo ponen
el 26/27 de una ruta (`SetFacingLocked`) y `SetAnimationType` con los tipos
2, 3 y 4 (`IsDirectionFixedAnimationType`). El de la ruta queda puesto
después de la ruta —es un campo de `SaveMapEventBase`, también del héroe,
y nada lo limpia salvo un 27 o el cambio de página de un evento—, y se
guarda en la partida. Los `face_*` de una ruta escriben el `facing`
directo y **sí** giran aunque esté trabado. `Jump` sólo gira si no está
trabado. No se confirmó con el RPG_RT bajo Wine.

**Las pruebas** (`rom/pruebas/rpgmaker/test_direccion_trabada.py`, casos
`traba-heroe`, `traba-heroe-ruta` y `tram-fijo`): el pad no gira al héroe
trabado, el héroe trabado igual camina, la ruta no lo gira hasta el 27, y el
tram con gráfico fijo no gira con la ruta forzada. En rojo antes del
arreglo: la del pad (la flecha abajo lo dejaba mirando abajo), la de la ruta
y la del tram (+8 quedaba en abajo). La de "igual camina" pasaba antes.

**Los lugares que giran a un personaje**, buscados con `grep` de
`sta hero_dir` y `sta route_ev + 8, x`:

- el pad (`hero.s`) y el `move_*` de la ruta del héroe (`hero_route.s`):
  los dos pasan ahora por `try_toward`, que respeta `hero_lock`;
- el 26/27 en la ruta del héroe (`hero_route.s`, `lock_hero`), y el
  compilador ya no los tira (`compile.rs`);
- el salto del héroe (`oam.s`, `build_hero_jump`): mira `hero_lock`, con el
  criterio de Guanaco para los eventos;
- la ranura nueva de una ruta forzada sobre un evento (`event_routes.s`,
  `route_for_event`): hereda el bit de dirección fija de la página activa,
  que el conversor ahora emite también sin ruta propia (`map_record.py`,
  `rm2k.FIXED_DIRECTION`);
- los `face_*` giran aunque esté trabado, como en RM2k; el giro hacia el
  héroe al hablarle ya miraba el tipo de animación (`turns`) y la traba.

**La partida**: RM2k guarda `lock_facing`, la ROM no, a propósito —la única
traba que el juego deja puesta fuera de su ruta es la de la carrera, y entre
los mapas 49 y 64 no hay save point—. Cargar la limpia y el reset la
arranca en cero. Está en el comentario de `hero_lock`.

**Declarado**: con la traba puesta, la tecla de acción mira hacia donde mira
el héroe y no hacia la última flecha, que es lo que haría el `GetDirection`
de RM2k: hay una sola variable para las dos cosas, y ningún caso del juego
aprieta acción trabado.

**Las goldens**: cambian dos, `tram-320` (`test_escena[tram]`) y `tram-620`
(`test_hablar[tram]`), en `bccba0fb`, sólo goldens. El tram baja con la nave
gris de su página en vez del auto azul. Antes y después, y las capturas de
la carrera y de las naves de la agencia antes y después, en
`/shared/capturas/2026-09-30-vehiculos/` (con un `LEEME.txt`). **No se
capturó el original con Wine.** **El merge espera el visto bueno de taro.**

**Commits**: `e90d1d5c` (el arreglo y las pruebas), `bccba0fb` (las
goldens), `c1c9305f` (main mergeado).

**Al mergear**: reinstalar `events` (`just -f tools/justfile install
events`); `cartridge` no cambió. La ROM se mueve: `test_musica_techos.py`
pasó en la rama. No se usó RAM lejana ni opcodes nuevos; BSS gana dos bytes
(`hero_lock`, `found_flags`).
