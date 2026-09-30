---
name: "Rust: Adeleine"
description: "tools/port/adeleine.py (qué colores se pierden y cómo se agrupan en paletas) como crate propio en tools/snes/, al lado de Voodoo, con las ROMs byte por byte iguales"
type: refactor
assignee: taro
---

De taro, el 2026-09-29: empezar por Adeleine a Rust. Ya decidido
(`workflow/decisiones/las-herramientas-se-separan-de-abl.md`): Adeleine es
un crate propio en `tools/snes/`, al lado de Voodoo y no adentro, porque
Voodoo no decide colores (AGENTS.md). No sabe nada de RPG Maker: colores,
tiles y el límite de 16 por paleta. Es el paso antes de que `rm2k-render`
sume los CharSets.

## Lo hecho (Tucán, 2026-09-29)

Tres commits:

1. **El orden de try_pack** (`3a8e381f`), solo porque **cambia la ROM**.
   `try_pack` dejaba los empates entre teselas del mismo tamaño en el orden
   del `set` de Python, que es el de los hashes de CPython. Dentro de
   `reduce_colors` ese set se rearma en cada fusión, así que en Rust sólo
   se reproducía emulando las tablas de hash de CPython. Ahora el empate se
   desempata por los colores. Medido registrando cada llamada de un
   `NO_CACHE=1 just cartuchos`: cambian 6 de 62 `try_pack` y 5 de 11
   `reduce_colors`. Todos son otro reparto de colores entre las paletas de
   la capa de arriba, con ni un pixel distinto, menos el mapa 3: antes
   fusionaba 2 colores (6 pixeles de 3684) y ahora entra sin fusionar.
   Cambian las capas de arriba de los mapas 1, 2, 3, 10, 32, 79 y 255, y
   las dos ROMs. **taro: mirar el mapa 3.**
2. **El crate** (`c5e22f0b`): `tools/snes/adeleine/`, con biblioteca y el
   ejecutable `adeleine merge|pack|reduce --request <json> --out <dir>`.
   `port/adeleine.py` queda como el lado de Python y lo llama con
   `stage.run`. Las salidas quedan byte por byte iguales a las del commit 1.
3. La prosa (`cecdb6e1`).

**Lo que quedó en Python:** `luma_distance`. Los llamadores no piden una
decisión, sino el color más cercano de una paleta, adentro de un `min()`,
y lo llaman unas 40.000 veces por build. Se va cuando migren `sprites.py`
y `menus.py`. También se quedaron `CELL`, `tile_colors` y la memoización
de `merge_least_visible`: se piden unas 1.900 fusiones y sólo unas 200 son
distintas. Cada subproceso cuesta entre 2 y 5 ms, y el Python tardaba unos
2 s en total.

**Al mergear:** `just -f tools/justfile install adeleine cartridge`.

**Las tandas.** `just -f tools/justfile test` pasa entera, y también
`cargo test -p adeleine` y `-p rm2k-snes-cartridge`. `just pruebas` da
**4 rojos, y los 4 vienen del commit 1**: con el Python de `5dc54ff7` y
los mismos binarios, `dcbest` pasa.

* `test_caminando[3-down-avances3]` y `test_escena[talan]`: 4 pixeles
  cada una, en el mapa 3. Pasan de (16, 56, 65) a (24, 64, 82): son los
  pixeles que ya no se fusionan.
* `test_los_parches_versionados_…`: `0003.toml` ya no lista las dos
  fusiones.
* `test_el_tema_no_recorta_en_su_pico[dcbest]` recorta 2 muestras. Correr
  `just techos` reescribe media tabla: aires, huellas de la mezcla de seis
  temas y el encabezado, que ahora sale en inglés. No lo commiteé: es más
  grande que este cambio.

Si el orden nuevo se acepta, hay que correr `just parches` y
`just techos`, y reemplazar las dos goldens. Si no se acepta, el port a
Rust no puede ser byte por byte igual en `reduce`.
