# Eventos

Cada página de evento que se puede compilar viaja en el cartucho como
**bytecode**, y ese bytecode tiene tres dueños que no se pisan:

    tools/protocol/events.toml  lo declara: cada opcode, su número y los bytes que lleva
    tools/port/eventos.py       lo emite: `_compilar`, un caso por comando de RM2k
    rom/src/interprete.s        lo ejecuta: `correr_codigo` y un `op_*` por opcode

De `tools/protocol/events.toml` salen generados `tools/port/event_opcodes.py` y
`rom/src/event_opcodes.inc`; ver `tools/protocol/README.md`, que está en inglés porque
ahí adentro no se sabe nada de este juego. **Un opcode nuevo se declara ahí y en
ningún otro lado**: antes el número lo elegía el compilador y le llegaba al
intérprete adentro de `mapdata.inc`, y así dos ramas eligieron el mismo sin que
git viera nada.

**Una página se emite sólo si todos sus comandos se pueden ejecutar.**
`compilar_pagina` corta con `NoSePuede` y el evento se queda sin código:
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

| Mecánica | en `rom/src/` | quién la compila, o quién la mide |
| --- | --- | --- |
| Pisar un evento, y pisarlo al final de una ruta forzada —una puerta es eso: una página de contacto con un `Teleport` adentro— | `probar_contacto`, `accion_en_celda` | — |
| Hablarle a un evento con la tecla de acción | `probar_accion`, `encolar_por_accion` | — |
| Una página esperando turno es un bit por evento, no una cola | `marcar_esperando` | — |
| Qué página está activa, congelada hasta el refresco | `elegir_paginas`, `aplicar_paginas` | — |
| Las rutas propias de la página, y la velocidad que traen | `rutas_de_pagina`, `animar_ruta_ev` | `ruta_propia` |
| La frecuencia de la ruta, y encarar al héroe | `paso_de_ruta`, `hacia_el_heroe`, `tras_paso`, `tras_giro` | `espera_tras_paso`, `espera_tras_giro` |
| La frecuencia se sube y se baja a mitad de una ruta (las órdenes 30 y 31) | `paso_de_ruta` | `frecuencia_minima` |
| Las diagonales, y hacia dónde dejan mirando | `puede_celda_diag`, `encarar_diagonal` | — |
| Cambiar el gráfico a mitad de una ruta (la orden 34) | `load_ruta_graficos`, `refrescar_npc` | `Graficos` |
| La colisión con los eventos | `celda_bloqueada`, `atraviesa_el_evento` | — |
| El gráfico sigue a la página, y el tile manda sobre el terreno | `grafico_de_pagina`, `pasa_con_evento`, `acomodar_npc` | `npcs_dibujables` |
| Los eventos dibujados con un tile del chipset | `load_npcs` | `npcs_dibujables`, `Charsets` en `tools/render/render_map.py` |
| Los que además son opacos y fijos: horneados en el mapa y sin fila que dibujar | `build_oam` saltea la fila escondida | `eventos_horneables` |
| El fundido de los teletransportes, con el mapa cargando adentro del negro | `empezar_fundido`, `fundido_tick` | `rampa_de_fundido`, y las constantes `FUNDIDO_*` |
| El tope de teletransportes encadenados | `SALTOS_MAX` y sus usos | lo cobra `pruebas/rpgmaker/test_saltos.py` |
| La pantalla se prende en el vblank y en ningún otro lado | `flush_video` | — |
| La ventana de mensaje, clavada abajo por HDMA | `armar_hdma`, `msg_empezar`, `msg_ptr_sig` | `tools/port/ventana.py`, `Mensajes` |
| El texto compuesto en caliente, con los glifos ya pre-renderizados | `mensaje_tick`, `componer_char`, `cebar_linea` | `fuente_prerender` en `tools/port/snes_convert.py` |
| El arranque dura siempre lo mismo | `BOOT_CUADROS` | lo corre `Partida` en `pruebas/arnes/consola.py` |
| Los cuadros perdidos se cuentan | `contar_perdidos` | los lee `Partida.cuadros_perdidos` de la WRAM |
| La música no espera al lazo: va en una IRQ vertical | `irq_musica`, `IRQ_LINEA` | — |

Lo que hace que el lazo entre en un cuadro —FastROM, los glifos precompuestos,
la tabla de productos del destello, la lluvia más barata— no cambia qué se
dibuja ni cuándo, y por eso se comprueba sin tocar nada más: las goldens y las
pruebas dan igual.
