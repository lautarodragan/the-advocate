# Eventos

Cada página de evento que se puede compilar viaja en el cartucho como
**bytecode**, y ese bytecode tiene tres dueños que no se pisan:

    tools/snes/protocol/events.toml  lo declara: cada opcode, su número y los bytes que lleva
    tools/rm2k-snes/events/          lo emite: `rm2k-snes-events`, en Rust;
                                     `compile_command`, un caso por comando de RM2k
    tools/runtime/interpreter*.s     lo ejecuta: `run_code` y un `.proc op_*` por opcode

**El intérprete lo lee de la WRAM, no del cartucho**, desde el 2026-10-01:
viaja en LZ2 y se descomprime con la grilla, detrás de ella (ver
`docs/port/maps.md`). Como el mapa siguiente ocupa ese lugar, una página que
sigue corriendo después de un `Teleport` a otro mapa —una cinemática que salta
y sigue hablando, y cada caso de la tanda— se lleva su bytecode a
`CODE_CARRY`, y la ruta forzada del héroe se copia entera: ver
`code_carry_before` en `tools/runtime/decompress.s`. Los saltos adentro de una
página son relativos a donde empieza, así que mudarla es mover un puntero.

De `tools/snes/protocol/events.toml` salen generados `tools/port/event_opcodes.py`,
`tools/rm2k-snes/events/src/opcodes.rs` y `tools/runtime/event_opcodes.inc`; ver
`tools/snes/protocol/README.md`, que está en inglés porque ahí adentro no se sabe
nada de este juego. El compilador está en inglés por lo mismo, y su README dice
qué recibe y qué contesta; el conversor lo llama dos veces, por
`tools/port/compiler.py`. Hasta el 2026-09-29 era `tools/port/events.py`, que
quedó con las constantes y los modelos que leen los demás. **Un opcode nuevo se declara ahí y en
ningún otro lado**: antes el número lo elegía el compilador y le llegaba al
intérprete adentro de `mapdata.inc`, y así dos ramas eligieron el mismo sin que
git viera nada.

**Del lado de la ROM, un opcode nuevo es su `.proc` y nada más.** El despacho
de `run_code` es un `jmp (tabla, x)` y la tabla la emite el mismo
generador —la macro `EVENT_HANDLERS` de `event_opcodes.inc`, con
`--jump-table`—, con una regla para el nombre: el manejador de `OP_X` se llama
`op_x`, y si no existe la ROM no ensambla. Eso pide que los números de
`events.toml` sigan contiguos desde 0, y el generador se niega si quedan huecos.
Hasta el 2026-09-25 el despacho era una cadena de `cmp`/`bne`/`jmp`, un
eslabón por opcode, y era el punto donde chocaban dos ramas que agregaban uno
cada una.

**Una página se emite sólo si todos sus comandos se pueden ejecutar.**
`compile_page` corta —`Stop::Cannot`— y el evento se queda sin código:
ejecutar la mitad de un script dejaría al juego en un estado que no existe, y la
comparación no lo vería: la golden es una captura de la propia ROM. Por lo
mismo, un evento con una condición que no sabemos evaluar queda entero afuera:
sin saber qué página está activa, correr la equivocada es peor que no correr
ninguna.

De ahí sale la única clase de error que se arregla **desde afuera** y no tocando
código: una página que teletransporta a un mapa que el cartucho no lleva no se
emite, y el evento se dibuja, se pisa y no hace nada. Por eso el conversor
nombra los mapas que le faltan a cada página que se cae por esto: es la única
razón de las veinte que se arregla sumando el mapa a la ROM.

Los códigos de comando con que el conversor decide todo esto salen de
`tools/rpgmaker/event_codes.json`, que se saca de liblcf y de ningún otro lado.
Cuando se pusieron de memoria —en el filtro que reconocía puertas, que ya no
existe— tres estaban mal, y dos de ésos eran `PlayBGM` y
`ChangeSpriteAssociation`: el filtro aceptaba como puertas eventos que cambian
la música y el sprite del héroe. **La comparación no puede ver esa clase de
 error**, porque una lista equivocada compila una ROM equivocada y la golden es
la captura de esa ROM. Se revisa leyendo contra liblcf, no corriendo.

## Las mecánicas que no son un opcode

Lo que el intérprete necesita alrededor: quién dispara una página, cuál está
activa, quién le cierra el paso a quién, y qué pasa mientras la pantalla está en
negro. Otra vez, el porqué está en el comentario de cada rutina.

**La mecánica la hace la ROM, y la tabla dice dónde.** Hubo un tiempo en que
cada una de estas líneas estaba escrita dos veces, en ensamblador y en Python,
y la segunda columna era el otro programa; ese programa ya no existe. Lo que
queda del lado de Python es el conversor, que compila lo que la rutina después
lee: las páginas, las rutas, las paletas, los glifos. Cuando hay algo así, la
tercera columna lo nombra; cuando la mecánica es entera de la consola, no hay
nada que nombrar y va un guión.

Y lo que **no** va más acá: una función de Python que no llame nadie, dejada
como "la definición escrita" de lo que hace la ROM. Es documentación con forma
de código, no se ejecuta, ninguna prueba la toca, y envejece sin que nadie se
entere. El porqué de cada mecánica va en el comentario de su rutina.

| Mecánica | en `tools/runtime/` | quién la compila, o quién la mide |
| --- | --- | --- |
| Pisar un evento, y pisarlo al final de una ruta forzada —una puerta es eso: una página de contacto con un `Teleport` adentro— | `try_touch`, `action_in_cell` | — |
| Hablarle a un evento con la tecla de acción | `try_action`, `queue_by_action` | — |
| Una página esperando turno es un bit por evento, no una cola | `mark_waiting` | — |
| Qué página está activa, congelada hasta el refresco | `pick_pages`, `apply_pages` | — |
| Las rutas propias de la página, y la velocidad que traen | `page_routes`, `animate_ev_route` | `route::own`, en el compilador |
| La frecuencia de la ruta, y encarar al héroe | `step_route`, `toward_hero`, `after_step`, `after_turn` | `wait_after_step`, `wait_after_turn` |
| La frecuencia se sube y se baja a mitad de una ruta (las órdenes 30 y 31) | `step_route` | `route::min_frequency`, en el compilador |
| Las diagonales, y hacia dónde dejan mirando | `cell_allowed_diag`, `face_diagonal` | — |
| Cambiar el gráfico a mitad de una ruta (la orden 34) | `load_route_graphics`, `refresh_npc` | `Graphics`, en el compilador |
| La colisión con los eventos | `cell_blocked`, `event_crossable` | — |
| El gráfico sigue a la página, y el tile manda sobre el terreno | `page_graphic`, `pass_with_event`, `fit_npc` | `drawable_npcs` |
| Los eventos dibujados con un tile del chipset | `load_npcs` | `drawable_npcs`; la hoja la dibuja `rm2k-render charset`, pedida por `Charsets` en `tools/render/render_map.py` |
| Los que además son opacos y fijos: horneados en el mapa y sin fila que dibujar | `build_oam` saltea la fila escondida | `bakeable_events` |
| El fundido de los teletransportes, con el mapa cargando adentro del negro | `start_fade`, `fade_tick` | `fade_ramp`, y las constantes `FADE_*` |
| El tope de teletransportes encadenados | `JUMPS_MAX` y sus usos | lo cobra `rom/pruebas/rpgmaker/test_saltos.py` |
| La pantalla se prende en el vblank y en ningún otro lado | `flush_video` | — |
| La ventana de mensaje, clavada abajo por HDMA | `build_hdma`, `msg_start`, `msg_ptr_next` | `rm2k-snes-screens`, que la arma con `rm2k-render` como biblioteca, y `Messages` en el compilador |
| El texto compuesto en caliente, con los glifos ya pre-renderizados | `message_tick`, `compose_char`, `prime_line` | `font_prerender` en `rm2k-snes-screens` |
| El arranque dura siempre lo mismo | `BOOT_FRAMES` | lo corre `Partida` en `rom/pruebas/arnes/consola.py` |
| Los cuadros perdidos se cuentan | `count_lost` | los lee `Partida.cuadros_perdidos` de la WRAM |
| La música no espera al lazo: va en una IRQ vertical | `irq_music`, `IRQ_LINE` | — |

Lo que hace que el lazo entre en un cuadro —FastROM, los glifos precompuestos,
la tabla de productos del destello, la lluvia más barata— no cambia qué se
dibuja ni cuándo, y por eso se comprueba sin tocar nada más: las goldens y las
pruebas dan igual.
