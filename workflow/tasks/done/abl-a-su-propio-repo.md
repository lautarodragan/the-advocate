---
name: "ABL a su propio repo"
description: "Fase 1 del juego de pruebas: todo lo de ABL —rom/, su justfile, sus pruebas y goldens, sus parches, su parte de docs/ y workflow/— a un repo aparte, nacido de cero; este repo queda con las herramientas y el runtime"
type: refactor
assignee: taro
---

De taro, el 2026-10-02, con el plan de
`docs/research/2026-10-02-el-juego-de-pruebas.md` (Leñatero, fase 1):
"empezaría por asegurarme de que todas las cosas de ABL existan en un solo
lugar. Es más, creo que las sacaría del repo y las movería a un repo
propio, y `git init` ahí". Sin `git filter-repo`: "seguimos teniendo el git
log acá, y lo que va a quedar del lado de ABL debería ser muy poco". El repo
nuevo nace de cero con los archivos de hoy.

El riesgo que señaló Leñatero: entre esta fase y la 2 el motor se queda sin
pruebas de ROM propias. Por eso la fase 2 va enseguida.

# La clasificación (Ñandú-petiso, 2026-10-02, antes de mover nada)

El criterio es el de `testing/decisiones-y-divergencias-por-repo.md`: va con
ABL lo que es de este juego —su contenido, sus pruebas, sus recetas, sus
experimentos, lo que decide qué lleva su cartucho—; queda lo que valdría
para cualquier juego portado con las herramientas, aunque se haya
encontrado o medido sobre ABL. **Mixto** quiere decir que va a los dos: se
copia y cada repo se queda con lo suyo, o se copia entero si partirlo es
criterio que no me toca.

## Los archivos sueltos

| qué | a dónde | porqué |
|---|---|---|
| `rom/` entero | ABL, **a la raíz** | `rom/` ya es la raíz de ABL desde la mudanza del 2026-09-29: en un repo propio no hace falta el escalón. `rom/X` pasa a ser `X` |
| `justfile` de la raíz | se va, y no pasa a ABL | sólo importaba `rom/justfile`; en el repo nuevo `rom/justfile` es el de la raíz. Acá no queda nada que importar: ver abajo |
| `tools/assembly/entregar.py` | ABL, a `entregar.py` | es de ABL (`abl-entregar`), como dice `tools/README.md` |
| `DITTO.md` | **queda** | el estudio lo daba por de ABL; leído, es por qué el conversor lee el volcado y no el binario, y el estado de esa decisión: es de las herramientas (lo cita `tools/justfile`, `decisiones/data-es-la-vista-resuelta.md` es de herramientas). Lo de ABL —qué hay en su `data/`— ya está en `rom/data/README.md` |
| `README.md` | mixto | cada repo el suyo: el de ABL, el juego original, `just datos`, cómo se arma; el de acá, la arquitectura del runtime |
| `AGENTS.md` | mixto | cada repo el suyo; el ambiente se describe en los dos, porque es el único archivo de cada uno que puede nombrarlo |
| `CLAUDE.md` | mixto | la misma forma en los dos |
| `.gitignore` | mixto | cada uno con lo suyo |
| `.git-blame-ignore-revs` | queda | nombra commits de esta historia |
| `.idea/`, `.claude/` | quedan | configuración del IDE y de Claude Code de este checkout |

## docs/

| archivo | a dónde | porqué |
|---|---|---|
| `docs/README.md` | mixto | cada repo el suyo |
| `docs/jetbrains.md` | queda | el annotate a través del corte de `main.s` |
| `docs/port/*` | queda | salvo `pipeline.md` |
| `docs/port/pipeline.md` | mixto | el diagrama es de las herramientas; las rutas `rom/…`, `$ABL_GAME_DIR` y las dos recetas, de ABL |
| `docs/rpgmaker/chipsets.md` | queda | |
| `docs/rpgmaker/rtp.md` | mixto | qué es el RTP y cómo se extrae, de las herramientas; los chipsets y charsets que usa ABL, de ABL |
| `docs/snes/*` | queda | |
| `docs/research/graficos-de-rm2k-a-snes.md`, `el-mapa-de-las-herramientas-de-python.md`, `las-herramientas-hoy.md`, `2026-10-01-el-sistema-de-imagenes.md`, `2026-10-02-el-juego-de-pruebas.md` | quedan | de las herramientas; el del juego de pruebas es el plan de este repo |
| `docs/research/inspeccion-integral-del-repo.md` | ABL | según la tabla de Hornero |
| `docs/research/2026-10-01-el-juego-entero-sin-msu-1.md` | ABL | cuánto pesa ABL entero y qué recortes pide su cartucho |
| `docs/research/2026-10-01-los-mapas-por-el-msu-1.md` | ABL | hasta dónde llega el cartucho de ABL; su ROM de prueba (`experimentos/msu-puerto/`) ya es de ABL |

## workflow/decisiones/ y divergencias/

La tabla de `decisiones-y-divergencias-por-repo.md` (Hornero) vale como
está; lo que se agregó o cambió después:

| archivo | a dónde | porqué |
|---|---|---|
| `decisiones/README.md` | mixto | cada repo el suyo |
| `decisiones/la-camara-corrida-de-la-reja-es-del-juego.md` | ABL | según la tabla |
| `decisiones/el-trueno-va-entero-y-paga-la-lluvia.md`, `las-herramientas-se-separan-de-abl.md`, `un-caso-largo-en-cero-no-prueba-nada.md` | mixto, copia | según la tabla |
| `decisiones/el-cartucho-pasa-a-8-mb.md` | mixto, copia | reemplazó a `el-cartucho-se-queda-en-4-mb.md`, que la tabla daba por mixta: ExHiROM es del runtime, que ABL lo necesite es de ABL |
| `decisiones/el-juego-se-juega-sin-msu-1.md` | mixto, copia | nueva; la regla es para ABL, y el motor la sigue mientras ABL sea el único juego |
| `decisiones/primero-el-juego-entero-despues-la-calidad.md` | mixto, copia | nueva; lo mismo |
| `decisiones/rm2k-plus.md` | mixto, copia | nueva; para las herramientas es qué son, para ABL es que lo que pida va al motor |
| `decisiones/call-event-a-un-cuerpo-compartido.md`, `las-imagenes-grandes-en-modo-1.md` | quedan | nuevas; del conversor y del runtime |
| `divergencias/*` | quedan, todas | según la tabla, y las cuatro nuevas (`la-entrada-a-la-pelea-en-mosaico`, `la-velocidad-del-heroe-con-l-y-r`, `lo-que-las-imagenes-en-sprites-no-modelan`, `lo-que-las-imagenes-grandes-no-modelan`) son del runtime. ABL no lleva `divergencias/`: su `AGENTS.md` apunta acá |

Las copias van sin tocar: partir la prosa de una decisión mixta es
criterio de taro.

## workflow/ el resto

| qué | a dónde | porqué |
|---|---|---|
| `workflow/README.md` | mixto | cada repo el suyo |
| `workflow/ESTADO.md` | mixto, copia | congelado y de sólo lectura; tiene de los dos |
| `workflow/tasks/tasks.nu` | mixto, copia | el script de las tareas |
| `workflow/tasks/done/` | **queda entero** | es registro, como el `git log`, y la historia se queda acá (taro, 2026-10-02) |
| las tareas de `todo/`, `testing/` y `wishlist/` | por tarea, abajo | |

**A ABL** (el resto queda): las que trabajan sobre su contenido, sus
pruebas, sus recetas o sus experimentos, o deciden qué lleva su cartucho.
Un error del motor encontrado en un mapa de ABL queda acá: el arreglo vive
en el runtime o el conversor.

* `todo/`: `cobertura-del-msu-1`, `el-audio-en-dos-pasos-lossy`,
  `el-mundo-y-lo-que-sigue`, `las-fotos-diff-recortadas-y-el-montaje`,
  `las-goldens-del-recorrido-vipers`, `las-goldens-pendientes-del-recorrido`.
* `testing/`: `el-cartucho-a-8-mb` (la ROM de prueba es de
  `experimentos/`), `el-comun-35-y-la-radio`,
  `el-contador-de-fortitude-no-se-ve`, `el-hp-de-los-enemigos-y-el-trueno`,
  `el-juego-entero-sin-msu-1-cuenta`, `el-piloto-del-modo-7`,
  `eventos-de-tropa-en-la-pelea` (los sistemas de batalla de los
  personajes de ABL), `just-video-con-jugadas`, `la-guarda-de-los-bancos`
  (la prueba vive en ABL), `las-pruebas-sin-agujeros-callados`,
  `los-mapas-por-el-msu-1`, `maqueta-del-menu-en-alta-resolucion`,
  `rom-de-prueba-del-menu-en-modo-5`, `una-fuente-para-la-alta-resolucion`,
  `mundo-1-el-66-entra` a `mundo-7-camino-a-paradise`.
* `wishlist/`: `caso-propio-para-la-escena-del-ascensor`,
  `partir-test-comandos-golden`.

`testing/las-pruebas-sin-opcodes.md` (Cotorra) toca las dos mitades y queda
acá, con la mitad de Rust, y `testing/el-juego-de-pruebas.md` y
`decisiones-y-divergencias-por-repo.md` también: son el plan de este repo.

# Lo hecho

## El repo nuevo

`/shared/abl-snes`, con `git init`, autor `taro <taro@taro.codes>` en su
`.git/config`. Los commits, en orden:

1. `bdd0d83` **A Blurred Line, desde abl-snes en 817037ee**: los 2075
   archivos de la clasificación, sin tocar un byte, con `rom/X → X` y
   `tools/assembly/entregar.py → entregar.py`. Comprobado blob por blob y
   con su modo contra `git ls-tree -r 817037ee`: ninguno distinto.
2. `6f79c2b` el `.gitignore` con las rutas de allá.
3. `574427f` **los paquetes de Python, preguntados a la suite**:
   `pruebas/arnes/suite.py` corre `rm2k-snes-python-path` y pone lo que
   contesta en `sys.path`; lo importan `lugares` y los scripts que no pasan
   por él. `pytest.ini` y `video.py` dejan de nombrar `tools/`.
4. `63c57f7` sin la guarda `_herramientas_del_checkout`, y `entregar`
   llama a `./entregar.py`.
5. `e2aef83` `consola.RAIZ` es la raíz del juego y no la de las
   herramientas.
6. `c32b9ba` un comentario mío que nombraba Python: lo cobró
   `test_el_justfile_no_nombra_python`.
7. `bc55f57` `test_el_dbg_nombra_los_fuentes_relativos_a_la_raiz` acepta los
   `.inc` del cartucho con ruta absoluta: ver "Lo que quedó".
8. `6d2d783` **`entregar.py` con dos repos**: el build se llama
   `<fecha>-<commit de ABL>-<commit de las herramientas>`, mira cambios sin
   commitear en los dos, saca `tools/runtime/` del checkout de las
   herramientas y el LEEME dice los dos commits.
9. `3e4d196` README y AGENTS.md con la mitad de ABL.
10. `d6053f5` `docs/`, `workflow/` y el `justfile`: rutas y nombres de allá.

`CLAUDE.md` vino igual: tiene la misma forma, y el texto vale tal cual.

## Este repo

1. `be6fafa8` **`rm2k-snes-python-path`** (`tools/common/python_path.py`),
   instalado como symlink por `_install`; `abl-entregar` deja de
   instalarse, y el `find` de `abl-*` limpia el que quedó en el global.
2. `d356bfb7` **los borrados, sólo borrados**: 2059 archivos.
3. `4ffb90b2` **la prosa**, guiada por el diff del anterior.

## Las decisiones que tomé

* **ABL encuentra `common` y `emulator` preguntándole a un ejecutable**,
  `rm2k-snes-python-path`, desde Python (`arnes/suite.py`). Las otras dos
  del estudio, descartadas:
  * un `PYTHONPATH` exportado por el `justfile` de ABL: un backtick de
    `just` **no ve el `PATH` que el mismo `justfile` exporta** —probado con
    just 1.58—, así que tomaría el global aunque haya un `bin/` local
    adelante; se evaluaría en cada receta; y el `justfile` de ABL no nombra
    Python, que `test_lado_de_abl.py` cuida;
  * paquetes instalados con pip o un `.pth`: estado global que un worktree
    no puede tapar con el suyo, y un paso de instalación más.
  El ejecutable es un symlink al checkout del que se instaló, el mismo del
  que los binarios toman el runtime.
* **`rom/` va a la raíz del repo nuevo**, y no a un `rom/` adentro: la
  decisión del 2026-09-29 ya lo hacía la raíz de ABL.
* **El `justfile` de la raíz se va, y no pasa a ser el de `tools/`**:
  `tools/justfile` encuentra lo que instala con `justfile_directory()`, que
  importado desde la raíz sería la raíz. Se corre con `just -f
  tools/justfile`, o con `just` parado en `tools/`, como hasta hoy.
* **`DITTO.md` se queda acá**: ver la clasificación.
* **La guarda de los worktrees de ABL se va**: las herramientas encuentran
  el proyecto desde el directorio donde corren, y ya no hay scripts de
  Python en el global que armen en el `build/` de otro checkout.
* **`tasks/done/` queda entero acá**, como registro.

## La verificación

* **La ROM, desde `/shared/abl-snes`**: `NO_CACHE=1 just cartuchos` sobre
  un `build/` que no existía —62 s— da `abl.sfc` =
  `35c765009320d43664d4604bc6b456db7f0b4332638dc52d761a573c5ffd7349`, el de
  la base. **Los 1424 archivos de `build/`** —los tres cartuchos, las 51
  pistas de MSU-1, `parches-manual/`— salen iguales a los del `rom/build/`
  del checkout principal, menos los tres `.dbg`, que nombran los `.inc`
  generados con ruta absoluta (abajo).
* **`just pruebas` allá: 993 en verde**, 95 s, sobre el último commit.
* **`just -f tools/justfile test` acá: 32 en verde**, después de los
  borrados y después de la prosa.
* **`just entregar` allá**, con `SHARED=<un directorio del scratchpad>`
  para no tocar `/shared/builds`: dejó
  `builds/2026-10-02-bc55f57-d356bfb7/` con el `abl.sfc` de siempre, su
  `.dbg`, el `abl.msu`, `tools/runtime/` y el LEEME con los dos commits.
  **No se corrió contra `/shared` de verdad**: borra los builds viejos.
* Todo eso se corrió con las herramientas globales más
  `rm2k-snes-python-path` del worktree adelante en el PATH, porque el
  global todavía no lo tiene.

## Al mergear

* **`just -f tools/justfile install-scripts`** desde el checkout principal:
  instala `rm2k-snes-python-path` y borra el symlink de `abl-entregar`.
  Sin eso, el arnés de ABL corta diciendo que falta. No hay Rust que
  reinstalar.
* **El `rom/` del checkout principal queda en disco**: `rom/build/` (1,7
  GB), `rom/pruebas/snapshots/` y lo que haya sin trackear. Con el
  `.gitignore` nuevo, `git status` lo va a mostrar. No lo borré —es el
  ambiente—: se borra cuando ABL se arme desde `/shared/abl-snes`.
* Con eso, `just pruebas` en `/shared/abl-snes` con las globales es lo que
  verifica un cambio en `tools/`.

## Lo que quedó, para la fase 2

* **El motor sin pruebas de ROM**, como dijo Leñatero: está escrito con
  todas las letras en el README y en `AGENTS.md`.
* **`/shared` es un CIFS**: sin symlinks, así que el `install-local` de las
  herramientas no puede dejar su `bin/` en `.herramientas-locales/` de ABL.
  Para correr ABL con las herramientas de un worktree de acá, va su
  `tools/.local-tools/bin` adelante en el PATH (está en los dos
  `AGENTS.md`). Sin bits de ejecución propios: un script nuevo se marca
  con `git update-index --chmod=+x`. Y sin mayúsculas.
* **Un worktree de ABL para un agente de las herramientas**, para no armar
  en el `build/` del checkout que se juega: `git -C /shared/abl-snes
  worktree add <dir>`. No lo probé.
* **Los `.inc` de un juego fuera del checkout van absolutos en el `.dbg`**
  (`under`, en `assemble.rs`, a propósito). Mesen2 no los ve desde un build
  entregado, como antes; abriendo la ROM desde el `build/` de ABL tampoco,
  y antes sí. Se arregla corriendo `ca65` con rutas relativas al proyecto
  para lo generado, si hace falta.
* **`test_perillas_repetidas.py`, de ABL, recorre los `.py` del checkout
  de las herramientas** (`project.tools()`): sigue andando, pero es una
  prueba de allá que mira código de acá.
* **`convert.rs` busca imágenes también en `suite::root()`**, la raíz de
  este repo, y `render_map.py` de ABL lo copia: desde que ABL no está acá,
  ahí no hay nada que encontrar. No lo toqué: cambia lo que lee el
  conversor.
* **Los comentarios del runtime y de los crates que citan `rom/…`** —en
  los `.inc` que emite el conversor, entre otros— quedan, según la
  decisión de las herramientas.
* **La versión de la suite que declara el juego**, que la decisión pide: con
  dos repos es lo que ata las goldens de ABL a un motor, y hoy no existe.
* **`test_lado_de_abl.py`** sigue entero: en el repo nuevo nombrar `tools/`
  es nombrar otro repo, y tiene tres archivos en su lista que lo nombran
  en la prosa.
