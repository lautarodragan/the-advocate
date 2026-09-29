---
name: "Rust: el piloto del conversor, las tablas de pelea"
description: "El primer dominio del conversor en Rust: el crate rm2k-snes-battle con las tablas de experiencia y encuentros (battle_tables.py), llamado por el Python por el PATH, con las ROMs byte por byte iguales"
type: refactor
assignee: Surubí
---

Paso 4 del camino a Rust, con lo que se charló con taro el 2026-09-29:

- el conversor se migra **por etapas**, con el Python orquestando y
  llamando a cada etapa de Rust por el PATH, como `rm2k-render` y
  `rm2k-snes-audio`;
- en Rust queda **un crate por dominio**, porque Cargo no permite ciclos
  entre crates y así la frontera la hace cumplir el compilador; el
  orquestador (`rm2k-snes-convert`, más adelante) no tiene lógica de ningún
  recurso;
- el piloto es chico a propósito para fijar la forma: `battle_tables.py`
  (experiencia y encuentros) va a `tools/rm2k-snes/battle/`, el crate
  `rm2k-snes-battle`, que después va a recibir el resto de la pelea.

## La forma que quedó fijada (Surubí, 2026-09-29)

Es la plantilla de los dominios que siguen. Está en el README del crate,
en inglés, que es donde la va a buscar el que arme el próximo:
`tools/rm2k-snes/battle/README.md`, "One stage of a converter".

- **Un crate por dominio, con biblioteca y ejecutable**:
  `tools/rm2k-snes/battle/`, paquete `rm2k-snes-battle`, binario
  `rm2k-snes-battle`, nombre de proyecto `battle` para `install` e
  `install-local` (es el directorio: `_install` lo busca como
  `<capa>/<nombre>`). Capa `rm2k-snes`, porque emite tablas para ca65.
- **Lee el juego él mismo, del volcado de Ditto** (`--data`, el
  directorio con `maps.json` y `db/`), sólo los campos que usa y con
  tipos propios chicos: `src/game.rs`. Un campo que falta es un error que
  lo nombra, igual que en `lcf.py`. **Se reemplaza por Ditto como
  biblioteca cuando exista**; hasta entonces no se copia el modelo entero.
- **Lo que el volcado no dice viene en un pedido** (`--request`, un JSON):
  lo que decidió el cartucho —qué actores pelean, qué mapas lleva y su
  tamaño, los pasos forzados de un cartucho de prueba— y lo que el
  proyecto parchea encima del volcado —los nodos del árbol de los mapas
  nuevos, que en ABL es el cuarto de debug—. El pedido lleva decisiones y
  parches, nunca datos que el volcado ya tiene.
- **La lógica de otro dominio entra como dato, no como código**: qué
  actores pueden pelear es del grupo, y llega como lista; qué tropas lleva
  el cartucho es de las tropas, y vuelve como lista para que el Python
  las pida con `troops.request`, en el mismo orden que antes.
- **Escribe pedazos del `.inc`, uno por archivo, y un JSON** con lo que el
  resto de la conversión necesita (`--out`): `experience.inc`,
  `encounters.inc` y `battle.json`. El Python los intercala donde
  estaban; no sabe dónde se arma un cartucho.
- **Dos códigos de salida**, como `rm2k-render`: 1 si la respuesta es no
  (no entra, el volcado está roto), 2 si la llamada está mal.
- **Sus pruebas no necesitan el juego**: `tests/python.rs` arma uno chico
  y compara contra los sha256 de lo que daba el Python;
  `tests/command_line.rs`, el binario visto de afuera.

Del lado de Python, **el que llama es el orquestador**: `snes_convert.py`
corre la etapa una vez, en el lugar donde antes corría
`rom_encounters`, y le pasa el resultado a `mapdata.emit`. No queda un
módulo envoltorio por etapa.

## Lo que usaba de otros módulos

- De `events.py`: `ENC_DEFAULT_STEPS`, `ENC_RATE` y las filas de
  `ENC_TABLE` son **constantes**, y se trajeron. `enc_base`,
  `enc_step_thresholds` y `encounter_zones` **son de este dominio** —los
  encuentros— aunque vivan en `events.py`, y se reimplementaron. Las de
  Python **se quedan**: las usan el modelo `Encounters` de las pruebas,
  `battle_scenes.py` (`encounter_zones`) y `test_encuentros.py` /
  `test_pasos_de_encuentro.py`, que comparan la ROM contra ellas. Así que
  una divergencia entre las dos copias la cobra la tanda.
- De `experience.py`: `max_level`, `exp_for`, `exp_list`, `next_exp`,
  `initial_level` e `initial_exp`, reimplementadas. **No se borra nada de
  `experience.py`**: `menus.py` usa `initial_level`, `initial_exp` y
  `next_exp`, y las pruebas de la ROM usan todo el resto (`add_exp`,
  `troop_exp`, `exp_list`, `max_level`, `EXP_MAX`).
- `troops.request` (de `battle.py`, las tropas) queda en Python: ver
  arriba.
- `lcf.CURVES`, el orden de las seis curvas, es del formato: constante.

## Lo que se encontró

- **`enc_base` de un mapa con `encounter_steps` 1 da 65536**, que no
  entra en el `.word` de `enc_base`: el Python lo emitía igual y el Rust
  también, porque la prueba fija lo que daba. Ningún mapa de ABL tiene 1;
  un `--test-encounters 1` rompería el ensamblado. Queda anotado, no
  arreglado: es un cambio de salida.
- **Nada de esto va al caché en disco**: las tablas se calculan en cada
  conversión, así que la clave del caché no tiene por qué llevar el
  binario. La huella de los cartuchos sí: `CONVERTER_TOOLS` en
  `tools/rm2k-snes/cartridge/src/cartridges.rs`.
