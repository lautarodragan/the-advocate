---
name: "Rust: la música del conversor"
description: "Lo que el conversor decide de la música y del .msu (music.py, msu_data.py) a rm2k-snes-audio, con las ROMs y el .msu byte por byte iguales"
type: refactor
assignee: Calandria
---

De taro, el 2026-09-30, en la migración del conversor a Rust. `music.py`
decide qué temas pide cada mapa, cuáles pueden estar sonando cuando carga un
paquete, el trabajo que le pasa a `rm2k-snes-audio` y el presupuesto de
cuadros del arranque; `msu_data.py` arma el `.msu` con los fondos de calidad
y los efectos. La música en sí ya es de `rm2k-snes-audio`.

Sale de `main` en el commit que lanza la tarea. Ahí: `NO_CACHE=1 just
cartuchos` da `abl.sfc` `241dc9ad2bf8b43c…`, `special` `63779e111ee18923…`,
`encounter-every-step` `200a0b7355289700…`; `just pruebas` 882,
`just -f tools/justfile test` 49.

## Inventario: qué hace hoy el Python

Leído el 2026-09-30:

| dónde | qué hace |
|---|---|
| `music.rom_songs`, `songs_of_maps` | agrega a los temas del compilador el del mapa de arranque, el del título y el del Game Over —al final, para no renumerar el bytecode— y el propio de cada mapa, del árbol (`Game_Map::PlayBgm`) |
| `snes_convert.main`, 870-955 | los efectos pedidos, y los paquetes: uno por mapa —el propio adelante, el de arranque, los de salida y los aparte separados—, el de la pelea, el del Game Over y el del título |
| `music.separate_songs` | `[music] apart_themes` |
| `music.inherited_songs` | qué tema puede estar sonando cuando carga cada paquete, siguiendo los saltos sin mirar condiciones, menos `[music] jumps_that_never_happen` |
| `music.compile_music` | el trabajo, a `audio-job.json`, y `rm2k-snes-audio compile` |
| `music.boot_frames` y 1010-1024 | que el arranque entre en `BOOT_FRAMES`, que lee de `far_ram.s` |
| `music.write_msu` | el `.msu`: los fondos de calidad y los efectos de calidad; lo que el `.inc` necesita para leerlo, al final de `musicdata.inc`; y `efectos.json` |
| `msu_data` | el formato del `.msu`: `build`, la firma, y `index`/`read`, que usan cuatro pruebas de ABL |
| `tools/tests/test_inherited_songs.py` | la prueba de la herencia, sobre un juego hecho a mano |

## La frontera

**Todo lo de arriba va a `rm2k-snes-audio`, como un subcomando nuevo,
`cartridge`**, con la forma de "One stage of a converter". No es un crate
aparte porque lo que decide es exactamente lo que `compile` recibe: el
trabajo deja de viajar por Python y se arma adentro, y la etapa llama a
`compile` en el mismo proceso. `compile` se queda como está, porque lo usan
el arnés (`musica.py`) y las pruebas del crate.

**El `.msu` va con la música.** Lleva dos cosas —los fondos de calidad y los
efectos de calidad—, y de las dos lo único que tiene que decidirse es el
orden y las tablas de los efectos, que ya son de la música (`msu.rs`). Los
fondos llegan hechos: son bytes que arma la emisión (`backdrop_bytes`, de
`battle_scenes.py`) con los píxeles de `rm2k-snes-images`, y la etapa sólo
los pone en su lugar fijo. El formato va a `src/msu_data.rs`, al lado de
`rm2k-snes-msu`, que arma las pistas del mismo MSU-1.

**Lo que recibe el pedido** —decisiones del cartucho y lo que otros
dominios ya resolvieron—:

* los temas y sonidos que numeró el compilador de eventos, **tal cual los
  devuelve** (`compiled["songs"]`: nombres, sonidos, qué pide cada paquete,
  los de salida y qué tema lleva cada salto);
* los mapas del cartucho por número, en el orden de la tabla, y en cuál
  arranca;
* si lleva título, y si lleva Game Over: el segundo depende de que se haya
  encontrado la imagen, que es de las imágenes;
* los cuadros de descomprimir el mapa de arranque (`materials`, la
  emisión) y `--measure-headroom`;
* los fondos de calidad, como bytes, por número;
* los nodos del árbol que agregó el proyecto, como los recibe
  `rm2k-snes-battle`.

**Lo que lee sola**: del volcado (`--data`), el árbol —la música de cada
mapa, con `rm2k_rules::tree::Tree::music`— y el `System` —el tema del
título, el del Game Over, y todos los `*_music` para numerar las pistas—;
del proyecto, `[music] apart_themes`, `[music] jumps_that_never_happen` y
`[rom] msu_data_signature`; de la carpeta del juego, el RTP y el
SoundFont, lo que ya leía `compile`; y `BOOT_FRAMES` de `far_ram.s`, del
runtime de la suite.

**Lo que devuelve**, en `--out`: `musicdata.inc` (con las tablas del
`.msu` al final, como hoy), `musica.json`, `audio.json`, `audio-job.json`,
`efectos.json` y el `.msu`; Python los pone donde van —el `.msu` en
`--msu`—. Lo que imprime sale con lo que imprime el conversor.

**Lo que queda en Python**: armar el pedido, los bytes de los fondos, los
cuadros de descomprimir y poner los archivos en su lugar. `events.Songs` y
`compiler.songs` quedan sin uso y se borran con lo demás.

**Las pruebas de ABL que leen el `.msu`** dejan de importar `msu_data`: el
binario suma `msu-index` —las entradas de un `.msu`, o que no es uno
válido— y `msu-sign` —la firma de nuevo, para armar "el `.msu` de otro
build"—, y `constants` suma las del formato. Así el formato vive en un solo
lado; el arnés las llama desde `musica.py`, como ya hace con `constants`.
`test_inherited_songs.py` pasa a pruebas del crate, así que
`just -f tools/justfile test` va a dar una menos.

## Diario

* **La base**, en `3afc8199` con `rm2k-snes-audio` y `cartridge` en el
  `bin/` local: `NO_CACHE=1 just cartuchos`, 1032 archivos de `rom/build/`
  (sin caché, `.o`, `sello.txt` ni `conversor.log`; el `.dbg` sin `mtime`;
  los PNG decodificados), sus sha256 y los tres `conversor.log` en
  `<scratchpad>/calandria/musica/`. Las ROMs dan los sha256 de la tarea; el
  `.msu` de `release` da `905decd20b48411f…`.
* **La etapa, entera de una vez**, y salió igual en la primera corrida: los
  1032 archivos iguales, **y los tres `conversor.log` también**, línea por
  línea. Lo que la etapa imprime es lo que imprimía el Python, en el mismo
  orden.
* **`audio-job.json` sigue saliendo**, ahora de Rust, con el formato de
  `json.dump(…, indent=1)`: `pyjson` aprendió el `repr` de un `float`
  (`decompress_frames` lo es), con sus pruebas.
* **Una rareza del log, heredada tal cual**: "battle audio package: N
  song(s), M sound effect(s)" cuenta los efectos del **último** paquete de
  la ROM, que es el del Game Over cuando el cartucho lo tiene, así que dice
  0. Se copió igual para poder comparar el log entero; va arreglado en un
  commit aparte.
* **Las pruebas del crate contra el Python**: un juego chico hecho a mano
  (`tests/cartridge.json`: seis mapas, uno sin páginas, temas de salida,
  temas aparte, un salto que nunca pasa, saltos que llevan su tema y lo que
  entró; con y sin título, Game Over y pelea) y un `.msu` con dos fondos y
  los efectos de tres paquetes. Los sha256 salen de
  `<scratchpad>/calandria/musica/referencia.py`, que corre `music.py`,
  `msu_data.py` y el bloque viejo de `snes_convert.py` sacado con `git show`.
  `test_inherited_songs.py` pasó entera a pruebas de `cartridge.rs`.
