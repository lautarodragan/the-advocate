---
name: "Lo que quedó del dominio de los mapas"
description: "Los cabos sueltos que dejó Mara al pasar los mapas a Rust"
type: refactor
assignee: taro
---

De `testing/rust-el-dominio-de-los-mapas.md` (Mara, 2026-09-30):

- que `rm2k-snes-events scan` conteste los blancos de ruta de cada página,
  así `movable_events` sale de Python;
- los repartos de VRAM (`tools/port/vram.py`) en un solo lado: hoy los leen
  las pantallas y la emisión;
- la regla de los colores del cronómetro está dos veces: `timer_colors_of`
  en Python y `timer_colors` en `extras.rs`;
- sacar `voodoo` de la huella de `cartridge`: el conversor ya no corre el
  binario, la etapa de mapas lo usa como biblioteca (entra por el binario
  de `rm2k-snes-maps`);
- decidir si `rm2k-snes-maps layers` se queda: hoy sólo lo usan sus
  pruebas;
- el camino de los translúcidos tramados (`TRANSLUCENT_MODE=dither`) está
  portado pero ningún cartucho lo ejercita;
- los avisos de clippy de los tres crates.

Fuera del encargo: los repartos de VRAM (`vram.py`) quedan como están —son
de la emisión, y Cardón, que pasa la pelea a Rust, puede necesitarlos—.

## Hecho (Ceibo, 2026-09-30)

Base: `968af650`. Cada punto en su commit; la ROM y todo `rom/build/`
—1032 archivos, con el script de huellas de Mara— iguales después de cada
uno, con `NO_CACHE=1 just cartuchos`.

### 1. Quién camina sale de Python

`rm2k-snes-events scan` —y `compile`, que arma los mismos registros—
contesta en cada página `route_targets`: los eventos a los que su código
manda una ruta, recorriendo el bytecode (`instructions`, al lado de
`size_of` en `compile.rs`). La regla de quién se mueve —las rutas, la ruta
propia, los quietos que animan con su tope de cuatro, los que giran— pasó
a `rm2k-snes-maps`, en `moves.rs`: el pedido lleva los registros del scan
tal como salieron (`pages`) y los que manda a caminar una página de prueba
(`also_walk`), y la respuesta trae `movable`, `animates_still` y
`turning`, que `map_convert` lee para la tabla de NPC. Se fueron
`movable_events` y `ANIMATES_STILL_MAX` de `sprites.py` y
`events.route_targets`.

Cómo se verificó: antes de borrar el Python, `map_convert` comparó lo que
contestaba la etapa contra `movable_events` en cada mapa de los tres
cartuchos (102 llamadas) con un `assert`: iguales todas. Las pruebas de
`events` comparan contra hashes del Python viejo que no se regeneran, así
que `route_targets` se saca antes de hashear y tiene su prueba, con los
valores contrastados contra la regla de Python; `moves.rs` tiene las suyas
(sin juego).

### 2. Los colores del cronómetro, en un solo lado

La máscara de qué entradas de su paleta toman los dígitos —la que
`upload_timer_pal` vuelve a subir sin tinte— la calcula la etapa
(`timer_mask`, en `extras.rs` de `rm2k-snes-map-sprites`, sobre las
paletas como terminan) y viaja en `sprite.timer_mask` de `map.json`;
`snes_convert` la emite tal cual. Se fueron `timer_colors_of` de
`obj_extras.py` y `Skin.timer()` de `window.py`, que ya no los llamaba
nadie. Quedan en `obj_extras.py` las constantes de dónde se dibuja el
cronómetro, que son de la emisión (`mapdata.py`).

El pedido `draw: timer` de `rm2k-render system` quedó sin llamadores del
lado de Python; no se tocó, porque es de otro crate y no estorba.

Cómo se verificó: la tabla `timer_mask` de los `mapdata.inc` tiene
máscaras distintas de cero en 93 de los 102 mapas de los tres cartuchos, y
salió igual; `rom/build/` entero igual.

### 3. `voodoo` sale de la huella

`CONVERTER_TOOLS` de `cartridge` lista los binarios que el conversor
**corre**; `voodoo` ya no lo corre nadie —los mapas y las pantallas lo usan
como biblioteca, y entra en la huella por sus binarios—. Cómo se verificó
que ningún camino lo corre: leyendo, todos los `shutil.which` y
`stage.run` de `tools/` y todo `process::Command` de los crates (ninguno
nombra a `voodoo`); y corriendo, `NO_CACHE=1 just cartuchos` con un
`voodoo` falso primero en el PATH que anota y sale con error: no se llamó
nunca, y `rom/build/` salió igual.

### 4. `rm2k-snes-maps layers` se queda

Decidido que se queda. Lo que cuesta es poco: la entrada de la línea de
comandos y `layers::run`, cuatro líneas sobre las mismas funciones que usa
`map` (`draw`, `blocks`, `write`). Lo que da: es la única manera de
convertir las capas de **un** mapa sin armar el pedido entero —líderes,
respuesta del compilador, cartucho—, para mirar qué decidió Adeleine de
ese fondo solo; y las pruebas de línea de comandos del crate ejercitan por
ahí el dibujo de las capas —directorios de búsqueda, celdas pintadas,
errores— con un pedido de tres campos. Sacarlo obligaba a reescribirlas
contra `map`, que mezcla todo lo demás. Quedó dicho en su README.

### 5. clippy en los tres crates

`cargo clippy -p rm2k-snes-map-background -p rm2k-snes-map-sprites -p
rm2k-snes-maps --all-targets` sin avisos de los tres. Lo que queda son
avisos de `ditto` y `rm2k-rules`, que son dependencias y no se tocaron.
Tipos con nombre para las respuestas de tres funciones, los recorridos de
paletas y de filas por referencia, el `entry` del caché de opacos del
horneado, los módulos de prueba al final del archivo y `is_multiple_of` en
las pruebas. Mismo comportamiento: `rom/build/` igual y `cargo test -p` de
los tres en verde.

### 6. Los translúcidos tramados (`TRANSLUCENT_MODE=dither`): sólo anotado

No se agregó nada. Lo medido: `TRANSLUCENT_MODE=dither NO_CACHE=1 just
cartuchos` arma los tres cartuchos sin quejarse; la ROM de `release` sale
distinta (`271ffcede687…`) y las de prueba iguales, porque no llevan
eventos translúcidos. O sea que el camino anda de punta a punta, pero nadie
miró cómo se ve.

Lo que ninguna prueba cubre es chico: el `~trama` de `Drawer::draw` en
`sheets.rs` —quince líneas: dibujar la hoja base y vaciar los pixeles que
`drops` dice— y `drops` con sus cinco tramas. **Vale la pena una prueba
del crate**, sin juego, que dibuje un `~trama` sobre un CharSet inventado
y mire qué pixeles quedaron; cuesta poco y cubre todo lo que es del
camino. **Un cartucho no vale la pena**: el modo existe para comparar las
dos salidas en el mismo árbol, `release` no lo usa, y un cartucho más es
tiempo de cada `just cartuchos` para un camino que no se juega. No la
agregué porque el encargo pedía anotarlo; si taro dice que sí, es una
prueba en `rm2k-snes-maps`.

**Una trampa que encontré de paso**: ni `TRANSLUCENT_MODE` ni
`DITHER_PATTERN` entran en la huella de los cartuchos. Armar con una de
ésas y después sin ella deja la ROM tramada dada por buena hasta que algo
más cambie: para volver hay que borrar los `sello.txt` (o armar con
`NO_CACHE=1` y los sellos borrados, que es lo que hice). No lo arreglé:
es de `cartridge` y del proyecto, y conviene decidir antes si el modo se
queda.

## Cómo quedó verificado

Con los scripts de huellas de Mara, copiados a `<scratchpad>/ceibo/`:
`NO_CACHE=1 just cartuchos` con los sellos borrados, y el sha256 de todo
`rom/build/` —1032 archivos, menos el caché, los `.o`, `sello.txt` y
`conversor.log`; el `.dbg` sin `mtime`— contra la base de `968af650`,
armada con los binarios locales de este worktree. Iguales después de cada
uno de los cinco commits. Las ROMs:

* `release/abl.sfc` `cdcc323197ee6c66d82b1304ce20c3c37f4124d13a6867e851fd13226046b7df`
* `tests/special/prueba.sfc` `15e4f331fe8ff8123803ae3819a2212a5b84d71cd0a053b7261a9188bbab84b9`
* `tests/encounter-every-step/prueba.sfc` `dc83ed698b348032514dbb76eaf5f535b6296944075fcba786087533ed5b8a4b`

Después de mergear `main` (`be94c1d8`, la pelea de Cardón) las tres ROMs
siguen iguales; cambian sólo los tres `.dbg`, por los comentarios del
runtime que trajo ese merge.

Las tandas sobre el árbol mergeado: `just pruebas`, 878 pasan; `just -f
tools/justfile test`, 49. `cargo test -p` de `events`, `map-background`, `map-sprites`, `maps` y
`cartridge`, en verde.

## Al mergear

* Instalar en el global `events` —el scan contesta `route_targets`—,
  `maps` —lee `pages` y `also_walk`, y devuelve quién se mueve y la
  máscara del cronómetro— y `cartridge` —la huella sin `voodoo`—: `just -f
  tools/justfile install events maps cartridge`. **Tienen que ir juntos
  con el Python**: el `map_convert` nuevo le manda a la etapa un pedido
  que la vieja no entiende, y la vieja le contestaba sin `movable` ni
  `timer_mask`.
  `map-background` y `map-sprites` son bibliotecas: entran con `maps`.
* No mueve la ROM ni las goldens. Los cartuchos se rearman una vez, porque
  cambia la huella.
