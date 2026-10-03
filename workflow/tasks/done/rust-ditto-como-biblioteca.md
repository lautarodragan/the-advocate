---
name: "Rust: Ditto como biblioteca, y las reglas de RM2k"
description: "Un solo lugar en Rust que lee el volcado de data/ con tipos (la biblioteca de Ditto), y un crate rm2k-rules con las reglas de rpgmaker/rm2k.py; rm2k-render y rm2k-snes-battle dejan de leer el JSON a mano"
type: refactor
assignee: taro
---

Paso previo al compilador de eventos en Rust, charlado con taro el
2026-09-29. Hoy `rm2k-render` (`source.rs`) y `rm2k-snes-battle`
(`game.rs`) leen el JSON del volcado a mano, cada uno con sus tipos; el
compilador de eventos y el resto del conversor van a necesitar mucho más.

Lo decidió Hornero:

- **La biblioteca de Ditto es el único lugar en Rust que sabe leer el
  volcado**, con tipos para lo que se usa. Ditto ya es biblioteca, pero con
  un modelo genérico dirigido por el esquema de liblcf.
- **Las reglas de RM2k van a un crate aparte, `rm2k-rules`**, en
  `tools/rm2k/`: lo que hoy hace `tools/rpgmaker/rm2k.py` (pasabilidad,
  capas, poses, gráfico de una página, translúcidos). Ditto es el formato;
  las reglas, lo que el formato significa.
- `rm2k-render` y `rm2k-snes-battle` pasan a usarlos.

## Los tipos: los que Ditto ya genera, no unos nuevos

La pregunta era si escribir tipos a mano —sólo lo que se usa— o generarlos
del esquema. **Ya estaban generados**: son los structs con los que Ditto
arma el binario, `src/schema/mod.rs`, del esquema de liblcf. Lo medido:

- el esquema: **61 structs, 994 campos, 69 enums**, con la vuelta al
  binario 330 de 330;
- lo que leían los dos consumidores: `rm2k-render`, 7 campos de 2 structs
  (`Map` y `Chipset`); `rm2k-snes-battle`, unos 20 de 5 (`Actor`,
  `Parameters`, `MapInfo`, `Encounter`, `Rect`);
- lo que lee `rpgmaker/lcf.py`, que es lo que va a necesitar `events`:
  **192 nombres de campo distintos**, y además `db.decode()` —toda la
  sección de animaciones, campo por campo— y todos los términos. O sea que
  escribirlos a mano era, para empezar, más de 192 campos, y una segunda
  copia del modelo que mantener al paso del esquema.

Lo único que les faltaba para leer la vista resuelta, que es `rom/data/`,
era que un enum se pueda leer como número: el `Deserialize` derivado sólo
aceptaba el nombre. El generador ahora escribe uno que acepta el nombre,
`{"Other": n}` y el número (`lcf::EnumRepr`). Son +1.300 líneas generadas
en `schema/mod.rs`, ninguna a mano.

`ditto::dump::Dump` abre un volcado de cualquiera de las dos vistas: la
base entera, una sección sola, el árbol, un mapa con sus capas; y
`read_map` un mapa por ruta, para el de un fork. `pack` lee por ahí
también. Sobre `rom/data/`, en release: la base entera 109 ms, los actores
solos 1,4 ms, el árbol 1,8 ms, los 328 mapas 82 ms.

**Un campo que falta vale el default del formato**, no es un error: es lo
que significa que falte en el volcado exacto, y los tipos son los mismos.
Hacer que la vista resuelta exija todos los campos se puede —recorriendo
`schema::description`— y no se hizo: nadie lo necesitó.

## Qué quedó en `rm2k-rules`

`tools/rm2k/rules/`, sobre los tipos de Ditto, sin saber de la consola:

- `chipset`: los bloques de ids, `chip_index`, `terrain_of`, la tabla de
  pasabilidad por id, dónde está cada pieza en el dibujo;
- `passability`: los bits, las caras de pared, una celda, un mapa, y qué
  tile va delante del héroe;
- `animation`: el agua y los tiles animados;
- `charset`: la geometría y la pose;
- `event`: la página con la que arranca una partida, qué dibuja una
  página (`Graphic::CharSet` o `Graphic::Tile`), qué capa choca, qué
  animación es continua, el translúcido a 160, lo que un tile impone a su
  celda;
- `actor`: la curva de experiencia de `Game_Actor` y `add_exp`;
- `tree`: las zonas de encuentro de un mapa, los pasos, y el fondo de
  pelea y la canción que hereda del árbol.

Lo que en el Python es del port no vino: `@tile:`, el tramado y el
horneado, los CharSets opacos, las condiciones que entiende la ROM, dónde
arranca el héroe, `collect_npcs`.

Las dos copias las ata `rm2k/rules/tests/python.json` —entradas y lo que
el Python contestó—: `tests/python.rs` exige que el Rust conteste eso, y
`tools/tests/test_rm2k_rules.py` que el Python lo siga contestando. El
agua y las zonas no tienen función en Python y se miden en
`tests/rules.rs` contra el fuente de easyrpg; las zonas además las cobran
los hashes de `rm2k-snes-battle`.

## Qué se borró de los consumidores

- `rm2k-render`: de `source.rs`, el lector a mano del JSON y de la grilla
  del `.tiles` (queda `find_resource` y la conversión a su `Map`); de
  `layers.rs`, la tabla de pasabilidad y los `0x30`/`0x10`; de
  `chipset.rs`, los ids y las posiciones de las piezas, que ahora salen
  de `rm2k-rules`.
- `rm2k-snes-battle`: `game.rs` entero salvo `Game`, que ahora son los
  `Actor` de Ditto y un `rm2k_rules::tree::Tree`; de `experience.rs`, la
  curva; de `encounters.rs`, `zones`, `Zone` y `DEFAULT_STEPS`.

## Lo que va a necesitar `events` y todavía no está

- **Adivinar el texto en Shift-JIS**: `lcf.text` rearma los cuatro
  textos de la base que no son cp1252. No es regla del formato ni de
  RM2k; necesita decidir dónde vive y un decodificador (`encoding_rs`).
- **Los forks**: el Python aplica `rom/parches/manual/` —mapas, mapas
  nuevos con su nodo, ChipSets que se agregan— al leer. La biblioteca lee
  el volcado como está y `read_map` lee un mapa por ruta; aplicar el fork
  es del que llama, como hoy con la petición de `rm2k-render`.
- **`REFIT_TEXTS`**: el Python rearma las cajas de texto al leer los
  comandos; es del port y va a tener que ser una etapa.
- `rm2k-snes-cartridges` todavía lee `maps.json` a mano, para el tipo de
  cada nodo (`cartridges.rs`). No estaba en el encargo.
- Las reglas de `lcf.py` que no se copiaron: `Item.equippable_by`, el
  `hit` de `Enemy`, `critical_hit_chance or 30`, `targets_enemies`,
  `troop_exp`, `leader`. Son chicas y ninguna la usa todavía el Rust.

## Verificación

Corrido el 2026-09-29, sobre `d1f579a8`+prosa, con `ditto`,
`rm2k-render` y `rm2k-snes-battle` de la rama instalados en el `bin/`
local:

- `NO_CACHE=1 just cartuchos`: los 999 archivos de `rom/build/` —`.sfc`,
  `.msu`, `.pcm`, `.inc`, el `.dbg` sin mtime— iguales byte por byte a
  los de la base, armada antes de tocar nada;
- `rm2k-render --map` sobre los 328 mapas de `rom/data/`: los 827 PNG
  iguales a los del binario de antes (el conversor usa `--request`, que lo
  cubre lo de arriba);
- `just datos-vuelta`: 330 iguales, y la vista resuelta que escribe es
  `rom/data/` sin una diferencia;
- `just pruebas`: 874; `just -f tools/justfile test`: 84 —las 83 y
  `test_rm2k_rules.py`—;
- `cargo test` de rm2k-rules, rm2k-render y rm2k-snes-battle; Ditto con
  `DITTO_CORPUS` y el lote largo: 330 de 330 por archivo y por árbol, y
  las dos vistas del juego entero leídas a los mismos valores.

## Al mergear

Reinstalar en el global lo de Rust que cambió: `just -f tools/justfile
install ditto rm2k-render battle`. `rules` es biblioteca y va adentro de
los dos últimos.
