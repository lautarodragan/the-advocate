---
name: "Rust: el compilador de eventos"
description: "tools/port/events.py (páginas de evento a bytecode) como crate propio en Rust, sobre la biblioteca de Ditto y rm2k-rules, con las ROMs byte por byte iguales"
type: refactor
assignee: Guazú
---

La pieza más cara del conversor, charlada con taro el 2026-09-29: el
compilador de eventos va a un crate propio, porque la frontera es real —de
páginas de RM2k a bytecode, con el protocolo declarado en
`tools/snes/protocol/events.toml`— y porque es lo que más gana con Rust.

Se apoya en lo que ya existe: la biblioteca de Ditto para leer el volcado,
`rm2k-rules` para las reglas de RM2k, y la forma que fijó el piloto de la
pelea (`tools/rm2k-snes/battle/README.md`, "One stage of a converter").
Zorzal dejó anotado lo que falta de ese lado: la adivinanza de Shift-JIS
de `lcf.text`, aplicar los forks de `rom/parches/manual/`, `REFIT_TEXTS`, y
reglas chicas de `lcf.py`.

## Inventario: qué recibe y qué devuelve `events.py` hoy

Medido el 2026-09-29 sobre `64d838fa`, leyendo el módulo entero (5.600
líneas; unas 2.000 de código) y a todos los que lo llaman.

### Lo que recibe

**Del volcado**, por `lcf` —que ya le aplicó el fork de
`rom/parches/manual/` y `REFIT_TEXTS`—:

- las páginas de cada mapa: comandos, condiciones, disparador, capa,
  frecuencia, velocidad, tipo de animación, ruta propia, el CharSet de la
  página activa de cada evento (para `shares_graphic`);
- de la base: los eventos comunes (con `REFIT_TEXTS`) y sus disparadores,
  las páginas de tropa (sin `REFIT_TEXTS`: la ventana de la pelea es otra),
  las animaciones (sus `timings` y cuántos cuadros), los términos de la
  posada y del oro, el audio de la pelea de `System`, qué actores hay (para
  `OP_IF_ACTOR` y `ChangeEquipment`), qué habilidades hay y qué aprende cada
  actor por nivel (para `SKILL_SLOT`);
- **todos los mapas del juego**, no sólo los del cartucho: las ranuras de
  variable y de par (actor, habilidad) salen de barrer el juego entero.

**Del conversor**, que no están en el volcado:

- `REFIT_TEXTS` (`port/texts.py`): las cajas de texto rearmadas para el
  ancho de la ventana. Es una función pura de las líneas de **una** caja;
- `DECORATE_TRANSLUCENT` (`rm2k.decorate_translucent`): el nombre que lleva
  el CharSet de una página translúcida —horneado, con mapa y celda—. Al
  compilador sólo le importa para `shares_graphic` (un destello en una
  animación);
- el orden de los mapas del cartucho (`map_index`) y, por mapa, las
  `Substitutions` de `blocks.py` (qué par de bloques de ROM es cada
  `TileSubstitution`), que se arman **después** de convertir el mapa;
- la imagen del `ShowPicture` que se quedó con el lugar (`Pictures.choose`,
  que convierte PNG con `picture.py` mientras se convierte cada mapa);
- las asociaciones de `ChangeSpriteAssociation` (`sprite_associations`,
  que es del compilador pero corre antes que todo) y los gráficos de
  `--test-graphic` de cada mapa;
- las páginas de prueba de los casos (`rom/pruebas/casos/`, que no vienen
  del volcado) y en qué mapa corre cada una;
- las decisiones de oído del archivo de proyecto: `[sound_effects]`
  `per_map`, `route_effects_left_out` y `troop_effects_in_package`;
- las tropas de los encuentros aleatorios, que contesta
  `rm2k-snes-battle`.

### Lo que devuelve

- por mapa, `map_pages`: un registro por página de cada evento con
  condiciones soportadas —disparador, condiciones, capa, frecuencia,
  velocidad, el bytecode o `None`, la ruta propia, el gráfico, lo que el
  tile impone a la celda, si gira—;
- el bytecode de cada caso, compilado con el contexto de su mapa;
- los registros que llenó al compilar, que el resto del conversor lee:
  `Messages` (el bloque de textos de la ROM, con los de los casos primero),
  `Songs` (temas y efectos numerados, qué pide cada mapa, cuáles son de
  salida, con qué tema salta cada `Teleport`), `Graphics` por mapa,
  `Troops` (qué tropas y con qué fondo), `TroopPages` (el código de las
  páginas de tropa, deduplicado, con su bloque de mensajes aparte);
- `battle_audio`, el cuerpo compilado de cada evento común de equipo
  (`compile_party_common_event`), y las deudas de cada mapa (qué comandos
  acepta sin hacer, para el aviso);
- los índices: `VARIABLE_SLOT`, `SKILL_SLOT`, `PARTY_COMMON_EVENTS`,
  `ANIMATIONS`, `BATTLE_AUDIO`, `ACTOR_EQUIPMENT`, `INN_TERMS`, que leen
  también `mapdata.py`, `animation.py` y las pruebas.

Y no emite `.inc`: lo que llega a `mapdata.inc` lo escriben `mapdata.py` y
`map_record.py` con lo de arriba.

### Quién compila, y con qué contexto

No es una llamada sino **cinco pasadas**, cada una con su contexto, y la
salida de las primeras decide lo que entra en el cartucho:

1. `game_scan.possible_leaders`: todas las páginas de todos los mapas del
   cartucho, cada una con registros vacíos, para saber cuáles compilan y
   quién entra al grupo;
2. `sprites.movable_events`, dentro de `convert_map`: `map_pages` de cada
   mapa con un `Messages` propio y sin temas, para saber quién camina y a
   qué gráfico cambia una ruta —y la numeración de `Graphics` tiene que
   salir igual que en la de verdad, lo cuida un `sys.exit`—;
3. la de verdad, en `snes_convert.main`, mapa por mapa y con todo;
4. las deudas, otra vez las automáticas, con el bloque de textos y nada más;
5. las páginas de tropa, **después** de la pelea, con el mismo `Songs`.

Y las pruebas de la ROM compilan páginas sueltas con Python:
`arnes/datos.py`, `test_paginas.py`, `test_posada.py`,
`test_protocolo_contra_el_juego.py`, `test_musica_paquete.py`.

## La frontera

**Del compilador, y va al crate**: leer las páginas del volcado con Ditto;
`compile_page` y `_compile` enteros —rutas, ramas, elecciones, peleas,
posada, llamadas en línea, celdas fusionadas, el seguimiento del tema de
salida—; los registros que se llenan al compilar (`Messages`, `Songs`,
`Graphics`, `Troops`, `TroopPages`); `map_pages` en lo que es del
compilador; los barridos de variables, pares y asociaciones; y las cinco
pasadas, porque son la misma función con distinto contexto y el contexto
decide el bytecode.

**De otro dominio, y entra en el pedido**:

- `REFIT_TEXTS`: una tabla de las cajas que cambian —las líneas de antes y
  las cajas de después—, que arma `texts.py`. Es "lo que el proyecto cambió
  sobre el volcado", como los nodos del árbol del piloto;
- `DECORATE_TRANSLUCENT`: el nombre de cada página translúcida que lo
  cambia, que arma `rm2k.py`;
- los forks de mapa: la ruta de cada JSON de `rom/parches/manual/`, que el
  crate lee con `ditto::dump::read_map`;
- las `Substitutions`: por mapa, cada `(capa, viejo, nuevo)` con sus pares
  ya resueltos, o `null`. El crate devuelve cuáles pidió, y el Python las
  vuelve a pedir para que `known_keys` —el tope `SUB_MAX`— cuente lo mismo;
- la imagen: qué `ShowPicture` se quedó con el lugar (nombre, número y
  dónde), no la imagen;
- `[sound_effects]` del archivo de proyecto, tal cual;
- los casos: sus comandos y su mapa;
- las tropas de los encuentros, de `rm2k-snes-battle`, que por eso pasa a
  correr antes.

**Se queda en Python**: qué dibuja cada página (`grafico`, `tile_pass`,
el `@tile:` y el horneado son del port y de `rm2k-rules`), que el Python
agrega a cada registro que devuelve el crate; `texts.py`; `ANIMATIONS`,
que es de `animation.py`; y las constantes que emiten tablas de
`mapdata.inc` (`SHAKE_SINE`, `fade_ramp`, la lluvia, `KEY_*`…).

## La propuesta

`rm2k-snes-events`, en `tools/rm2k-snes/events/`, biblioteca y ejecutable,
con la forma del piloto. Dos subcomandos:

- `scan`: las pasadas 1 y 2 y los índices, que corren antes de convertir
  los mapas. Contesta las ranuras de variable y de par, las asociaciones,
  y por mapa qué páginas compilan (para el grupo) y los registros de
  `map_pages` sin temas (para quién camina) con su `Graphics`;
- `compile`: las pasadas 3, 4 y 5. Contesta los registros de cada mapa, el
  código de los casos, `Songs`, `Troops`, `TroopPages`, el audio de la
  pelea, los eventos comunes de equipo y las deudas; y escribe aparte, en
  binario, los dos bloques de mensajes y el código de las tropas.

Los números de opcode salen de `events.toml` con `protocol --rust`.
