---
name: "Las pruebas de las herramientas, en tools/"
description: "Las pruebas que no necesitan el juego se mudan a tools/pruebas/; las de Ditto dejan de caer en el juego de ABL, y ABL comprueba su ida y vuelta con el ditto del PATH"
type: refactor
assignee: taro
---

Sale de lo que dejó abierto `testing/el-justfile-de-las-herramientas.md`
(Espinillo). taro pidió el 2026-09-29 que Hornero decida lo abierto y haga
una primera versión sin esperarlo. Lo decidido:

- **Las pruebas que no necesitan el juego ni una ROM van a `tools/pruebas/`**,
  con un `tools/pytest.ini` propio y una receta `pruebas` en `tools/justfile`.
  Van en castellano, como el Python de `tools/`: se traducen todas juntas.
- **`ditto-pruebas` y `ditto-vuelta-entera` exigen `DITTO_CORPUS`** y no
  caen en `ABL_GAME_DIR`: las herramientas no saben de ningún juego. Sin la
  variable, las que necesitan corpus se saltean, como ya hacen.
- **ABL comprueba que su juego hace la ida y vuelta** con una receta propia
  que usa el ejecutable `ditto` del PATH (`unpack` y `pack`), sin compilar
  nada.

## Lo hecho (Chañar)

El criterio, aplicado prueba por prueba leyéndolas: se muda lo que no lee
`GAME_DIR` ni el RTP, ni `data/`, ni `parches/`, ni un cartucho armado, ni la
tanda. Leer el motor (`rom/src/`) no cuenta, porque viaja con las
herramientas; tampoco el SoundFont, que es material del conversor.

### Qué se mudó a `tools/pruebas/`

**Enteras, con `git mv` y sin tocarlas por dentro:** `test_escapes`,
`test_temas_heredados`, `test_sustituciones`, `test_musica_stream` y
`test_repartos`. Las dos últimas se siguen armando el `sys.path` a mano: sobra,
pero no molesta, y tocarlo complicaba el merge.

**Partidas**, con `git mv` del archivo a `tools/` —la parte más grande— y lo
que necesita el juego a un archivo nuevo en `pruebas/herramientas/`:

* `test_protocolo`: las dos que leen los cartuchos y `GAME_DIR` quedan en
  `test_protocolo_contra_el_juego.py`.
* `test_textos`: las dos que leen `data/` quedan en `test_textos_del_juego.py`.
* `test_ensamblar`: lo de `cartuchos.py` —la huella, el `.dbg` de cada
  cartucho, a cuál va cada caso, la lista de `release`— queda en
  `test_cartuchos.py`. `cartuchos.py` tiene los datos de ABL y su destino
  está abierto, así que sus pruebas se quedan con el juego.
* `test_bancos`: la que lee la tabla de símbolos del cartucho se queda con el
  mismo nombre, porque `rom/src/banco1.s` la cita por ahí.

**Para el que mergee con Lapacho:** los archivos que se mudaron y los nuevos
importan `port.eventos`, `port.ventana`, `port.textos`, `port.snes_convert`,
`port.event_opcodes`, `rpgmaker.lcf`, `render.render_map.GAME_DIR`,
`ensamblado.*` y `audio.*`. Git sigue el renombre de los que se movieron
enteros y de `test_protocolo`, `test_textos` y `test_ensamblar` (este último
lo ve como renombre a `test_cartuchos.py`, por parecido); los cuatro archivos
nuevos de `pruebas/herramientas/` no los sigue nadie: si Lapacho cambió
imports ahí, hay que llevarlos a mano. Con grep de los módulos que movió
sobre `tools/pruebas/` y `pruebas/herramientas/`.

### Qué no se mudó, y por qué

* `test_lz2`, `test_espacio`, `test_reservas_de_la_wram`, `test_parches`:
  leen cartuchos armados.
* `test_encuentros`, `test_paginas`, `test_horneados`, `test_destello_paleta`,
  `test_timer_paleta`: leen el juego (`GAME_DIR`).
* `test_lideres`: usa `datos.DEMO`, del arnés, y el conversor sobre esos mapas.
* `test_fork_mapas`: lee `data/` y `parches/manual/`.
* `test_indice`, `test_lado_de_abl`: son de ABL.
* De `pruebas/rpgmaker/`, ninguna: todas corren la ROM (`partida`) o leen el
  juego. La que más cerca estuvo es `test_musica_reparto`, que no corre ROM
  pero arma `escape_newyork`, un tema del juego. `test_items` tiene un caso
  sin ROM que lee el LDB del juego.

### Lo que salió de más

* **La huella de los cartuchos leía `tools/*/*.py`**, así que las pruebas de
  `tools/pruebas/` dejaban viejos a todos los cartuchos al editarlas. Se las
  saca de la huella, en su propio commit.
* **`tools/pruebas/` tiene su índice y su prueba del índice.** Extender la de
  la raíz la haría nombrar `tools/` desde el lado de ABL, que es lo que
  prohíbe `test_lado_de_abl`.
* **`ABL_SOUNDFONT`**: `test_musica_stream` lee el SoundFont desde esa
  variable, que tiene el nombre de ABL aunque sea material del conversor. No
  se tocó.

### Ditto y `datos-vuelta`

* `ditto-pruebas` usa sólo `DITTO_CORPUS`; sin la variable, las que la
  necesitan se saltean (leído en `tools/ditto/tests/common/mod.rs`, sin
  compilar). `ditto-vuelta-entera` se niega sin ella.
* `just datos-vuelta`, en la raíz: con el `ditto` del PATH, `unpack` y
  `pack`, y `cmp` de cada `.lmu`/`.ldb`/`.lmt`. Corrido una vez: **330
  iguales byte por byte, 0 distintos, en 2 s.** El camino de "distinto" o
  "falta" no se ejercitó.

### Verificado

Sobre `main` en `6072e21e`, que no se movió mientras duró esto:

* **Antes:** `just pruebas`, 973 casos.
* **Después:** `just pruebas`, 866 pasan, en un minuto; `just -f
  tools/justfile pruebas`, 109 pasan, en medio segundo. 866 + 109 = 975: los
  973 de antes, que las particiones no cambian de número porque cada caso
  va entero a un lado o al otro, más los dos de la prueba del índice nueva.
* `abl.sfc` rearmado con el mismo sha256 que antes (`7a3c6483…`): la huella
  cambió, la ROM no.
* `test_lado_de_abl`: la lista de excepciones bajó en cinco
  (`test_musica_stream`, `test_repartos`, `test_temas_heredados`,
  `test_protocolo`, `test_ensamblar`).

**Lo que no se corrió:** `ditto-pruebas`, `ditto-vuelta-entera` y ningún
`cargo test` (sólo `--dry-run`, y `ditto-vuelta-entera` sin la variable, que
se niega antes de llegar a cargo). Tampoco el host.
