---
name: "El justfile de las herramientas"
description: "Las recetas que son de las herramientas se mudan a tools/justfile; el justfile de la raíz queda para ABL"
type: refactor
assignee: taro
---

De taro, el 2026-09-29: el primer paso antes de mover `data/`, `parches/`,
`pruebas/` y el motor (ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md`).
Un `tools/justfile` con lo que es de las herramientas, y el de la raíz
acotado a ABL. Se acerca a tener dos repos sin mover todavía ninguna ruta.

Lo que va a `tools/justfile`, según lo charlado: `protocolo`,
`protocolo-pruebas`, `gunter-pruebas`, `ditto-pruebas`,
`ditto-vuelta-entera`, `voodoo-pruebas`, `lz2-pruebas`, `herramientas`,
`herramientas-locales`, `_instalar` y `cuales`. Lo que pone el `bin/` local
adelante en el `PATH` y la guarda se quedan en el de la raíz. También se
quedan `datos` y `ditto-volcado`, que vuelcan este juego.

De `pruebas/herramientas/`, sólo se mudan a `tools/` las que no necesitan
el juego ni una ROM, confirmado prueba por prueba.

## Lo hecho (Espinillo)

* **`tools/justfile`** con las once recetas de la lista, más
  `_no_en_el_principal`, que es de `herramientas-locales`. Las rutas pierden
  el `tools/` porque `just` corre parado en el directorio del `justfile`;
  lo de afuera se nombra desde ahí: `protocolo` escribe en `../rom/src/`, y
  el `bin/` local se arma en la raíz (`parent_directory(justfile_directory())`),
  que es donde lo busca el `PATH` de la raíz. `tools/justfile` pone el mismo
  `bin/` adelante en su `PATH`, para que `protocolo` use el `protocol` del
  worktree si se lo está modificando.
* **La raíz** se queda con el `PATH`, la guarda, `datos` y `ditto-volcado`.
  No delega en nada.
* **El comando de la guarda es `just -f tools/justfile herramientas-locales`.**
  Anda desde la raíz sin que la raíz importe ni delegue, y `-f` corre la
  receta parada en `tools/`, igual que desde adentro. La otra opción, `cd
  tools && just …`, dice lo mismo en dos comandos. La guarda queda como la
  única receta de ABL que nombra `tools/`: la lista de la prueba pasa de
  nueve a esa sola, y se renombra a `RECETAS_QUE_NOMBRAN_TOOLS`.
* **Un error de la prueba del grep**, arreglado en su propio commit: una
  receta con valores por omisión (`datos DIR="data" …:`) no se reconocía, y
  su comentario quedaba a cuenta de `voodoo-pruebas`, que estaba exceptuada.
  Por ahí se escapaba un `tools/rpgmaker/lcf.py` en el comentario de `datos`.

### Lo que no cerró del todo

* **`ditto-pruebas` y `ditto-vuelta-entera` siguen sabiendo de ABL**: si no
  viene `DITTO_CORPUS`, usan `ABL_GAME_DIR`. Las mudé igual, porque son las
  pruebas de Ditto; pero el corpus es el juego, así que cuando se separen
  los repos alguien tiene que pasárselo. Una receta de la raíz que lo pase
  tendría que llamar a `tools/justfile`, que es lo que la raíz no puede.
* **`tools/justfile` está en castellano**, como el Python de `tools/`: se
  traduce con él.

### `pruebas/herramientas/`: no se movió ninguna

* `test_lz2.py` necesita los cartuchos armados (`tanda.cartucho`): se queda.
* `test_protocolo.py` mezcla: unas corren `protocol --check` y comparan
  módulos, y otras leen los cartuchos (`tanda`) y el juego (`GAME_DIR`).
  Habría que partirla.
* `test_escapes.py` sólo importa `port.eventos` y `port.ventana`: no
  necesita ni el juego ni una ROM.
* Sin mirarlas a fondo, tampoco importan la tanda ni el juego
  `test_temas_heredados.py`, `test_sustituciones.py` y
  `test_musica_stream.py`; `test_lideres.py` usa `datos.DEMO`, del arnés.

No las moví porque no es obvio adónde: `tools/` no tiene carpeta de
pruebas de Python ni un `pytest.ini` propio, y `tools/justfile` no tiene
receta que las corra. Hace falta decidir eso primero (¿`tools/pruebas/`?,
¿en inglés?).

### Verificado

* `just --list` de la raíz: 14 recetas de ABL; `just -f tools/justfile
  --list`: las 10 de las herramientas.
* `just -f tools/justfile protocolo --check`: los dos al día.
* `just lz2-pruebas`, parado en `tools/`: 19 pasan. Fue la única
  compilación de Rust. Las demás `*-pruebas`, `ditto-vuelta-entera` y
  `herramientas` sólo con `--dry-run`.
* Sin el `bin/`, `just cartuchos` se niega con el comando nuevo; ese
  comando lo arma sin compilar Rust, con los symlinks a `tools/` del
  worktree, y `just cartuchos` anda después. `_no_en_el_principal` sale 1
  en el checkout principal.
* `just pruebas` desde la raíz: 973 pasan. `abl.sfc` y `prueba.sfc`
  rearmados, con el mismo sha256 que antes.

**Lo que no**: `herramientas` de verdad contra el global, las `*-pruebas`
salvo `lz2`, y el host.
