---
name: "Las herramientas encuentran el proyecto"
description: "Las herramientas dejan de saber que ABL vive en rom/ y de leer ABL_*: buscan rm2k-snes.toml hacia arriba, sus rutas salen del archivo, y el ambiente llega por flags"
type: refactor
assignee: taro
---

Lo que queda para que `tools/` no sepa nada de dónde ni cómo está ABL, después
de `testing/el-archivo-de-proyecto.md` (Molle). Lo decidió Hornero, con la
autorización de taro del 2026-09-29 para decidir sin esperarlo:

- **Las herramientas encuentran el proyecto como cargo encuentra el suyo**:
  buscan `rm2k-snes.toml` hacia arriba desde el directorio actual, o lo
  reciben por `--proyecto <dir>`. `proyecto.abl()` desaparece.
- **Las rutas del proyecto** (`data/`, `parches/`, `build/`, lo que haga
  falta) **las declara el archivo**, relativas a él. El runtime no: es de
  las herramientas.
- **El ambiente llega por flags** (`--game-dir`, `--rtp-dir`,
  `--soundfont`…), como dejó escrito Molle en su tarea; `rom/justfile`
  traduce `$ABL_GAME_DIR` y las demás. Las herramientas no leen ninguna
  `ABL_*`.

## Cómo va (Timbó, 2026-09-29)

La red de cada commit: `SIN_CACHE=1 just cartuchos` antes de tocar nada y
después de cada uno, con los sha256 de todo `rom/build/` —el script de Molle,
con el mismo criterio: sin `cache/`, `.o`, `sello.txt` ni `conversor.log`, y
los `.dbg` sin `mtime`—.

1. **Encontrar el proyecto.** `proyecto.directorio()` busca `rm2k-snes.toml`
   desde el directorio actual hacia arriba la primera vez que alguien lo
   pide, y `proyecto.fijar()` lo fija sin buscar. `--proyecto` lo lee cada
   ejecutable con `desde_la_linea_de_comandos`, que toma sólo ese flag
   antes del `parse_args` de su `main`: `cartuchos` y `entregar` leen el
   archivo al importarse, así que en ésos va antes que nada. Si no lo
   encuentra, `NoHayProyecto` —un `SystemExit`, así el ejecutable corta con
   el mensaje y sin traza— dice desde dónde buscó.
   - **Nada se calcula al importar.** Las constantes que salían del proyecto
     —`lcf.DATOS`, `fork.MAPAS`/`NUEVOS`/`CHIPSETS`/`DEL_JUEGO`,
     `chipset_del_fork.GENERADO`, `snes_music.TECHOS`, `cache_disco.DONDE`,
     `techos.MEDIDA`— pasaron a ser funciones o a calcularse adentro de la
     que las usa. Si no, importar el conversor desde `tools/` —lo que hacen
     las pruebas de las herramientas— buscaría un juego. La prueba de
     `test_perillas.py` que lo cuidaba ahora corre parada en un directorio
     vacío, y al final pide el proyecto para ver que no había uno.
   - **`parches.py` recibía la raíz del repo** y le sumaba
     `rom/parches/auto/`: ahora sus funciones reciben el directorio de lo
     automático (`proyecto.parches_auto()`), y los mensajes nombran las
     rutas relativas al directorio actual.
   - **El conversor corre parado en la raíz del repo** —ahí están las rutas
     relativas que terminan en el `.dbg`—, así que `cartuchos` le pasa
     `--proyecto`.
   - **Las pruebas de ABL fijan el proyecto por su ubicación**:
     `pruebas/arnes/lugares.py`, que importan primero `conftest.py`,
     `consola.py` y `video.py`.
   - `render_map` sigue buscando recursos también en `proyecto.raiz()`: es
     de 2026-08-31 (`00d96428`, cuando el RTP podía vivir en el repo) y hoy
     no encuentra nada ahí, porque la raíz no tiene carpetas de RM2k. No es
     llegar a ABL, así que no se tocó.
2. **`[paths]` en el archivo**, con claves en inglés y relativas a él:

       [paths]
       data = "data"
       patches = "parches"
       build = "build"
       cases = "pruebas/casos"

   `proyecto.build()`, `data()`, `parches()` y `casos()` las leen de ahí.
   Lo de adentro de `parches/` (`manual/`, `auto/`) y de `build/`
   (`release/`, `tests/`, `cache/`, `techos/`) sigue siendo de las
   herramientas: es la forma que le dan ellas, no una decisión del juego.
   - **Qué entra y qué no, con el criterio del encargo: es del archivo si lo
     lee una herramienta.** `cases` entra aunque viva en `pruebas/`, porque
     la lee `rm2k-snes-cartridges`. Las goldens y los snapshots no: sólo los
     leen las pruebas de ABL, que los saben por su propia ubicación, en
     `pruebas/arnes/lugares.py` (`GOLDENS`, `SNAPSHOTS`).
     `proyecto.pruebas()`, `goldens()` y `snapshots()` desaparecen.
   - `test_perillas_repetidas.py` no mira `[paths]`: sus valores son nombres
     de carpeta, y las herramientas usan `parches/auto/` como forma del
     directorio de cada cartucho. Armar a mano una ruta del juego con esas
     palabras lo cobra `test_proyecto.py`, que mira rutas.
3. **El ambiente por flags**, con el plan de Molle: `comun/ambiente.py` es
   **un solo lugar que se configura**. Cada ejecutable suma los flags de lo
   que usa (`ambiente.argumentos`) y los fija (`desde_argumentos`); el resto
   de las herramientas lee de ahí. `recursos.GAME_DIR`, `recursos.RTP_DIR` y
   `snes_samples.SOUNDFONT` siguen existiendo, pero se resuelven al leerlos
   con un `__getattr__` de módulo, y sin fijar fallan con
   `FaltaElAmbiente`, que dice qué flag falta. Se eligió esto y no pasar el
   valor por parámetro porque se leen adentro de unas cuarenta funciones
   —lo que contó Molle—: con esto cambiaron las doce firmas que los tenían
   de default (`game_dir=GAME_DIR` pasa a `None`, que se resuelve adentro),
   y ninguna más.
   - Los flags: `--game-dir`, `--rtp-dir`, `--soundfont`, `--reemplazos`
     (el de `rm2k-snes-msu`, que ya existía), `--cache` y
     `--test-cartridges` en la suite; `--compartido` en `abl-entregar`.
     Los valores se guardan absolutos, porque el conversor corre parado en
     otro directorio que el que lo llamó.
   - **Sin valor por omisión**, salvo el caché y los cartuchos de prueba,
     que tienen su lugar adentro del `build` del proyecto y el flag sólo los
     mueve. Los reemplazos de MSU-1 son opcionales: sin `--reemplazos`,
     cada pista sale de su MIDI.
   - `rm2k-snes-cartridges` le pasa al conversor lo suyo con
     `ambiente.como_flags` (`AL_CONVERSOR`), y `rm2k-snes-volume-ceilings`
     toma esos mismos.
   - **`rom/justfile` traduce.** Exporta `ABL_GAME_DIR`, `ABL_RTP_DIR`,
     `ABL_SOUNDFONT` y `SHARED` con los mismos valores por omisión de
     antes, y `ABL_CACHE` y `CARTUCHOS` vacías si no están; arma
     `al_conversor` y `al_armar` y se los pasa a cada receta que corre una
     herramienta. Los reemplazos, que no tenían variable, quedan como
     `reemplazos_msu` del `justfile`. `datos` y `datos-vuelta` usan la
     exportada en vez de repetir el valor.
   - **Las pruebas de ABL leen las variables ellas**, en
     `pruebas/arnes/lugares.py`, y fijan `ambiente` con eso: son las que
     exporta el `justfile`. Sin ellas —un `pytest` suelto sin las
     variables— cortan diciendo cuál falta, en vez de tener una segunda
     copia de los valores de la máquina. `test_hover_tram.py` dejó de
     repetir el suyo.
   - **Dos pruebas de las herramientas leen un SoundFont de verdad**
     (`test_musica_stream.py`, las envolventes): antes caían en el de
     `ABL_SOUNDFONT` por omisión. Ahora lo reciben en `SOUNDFONT`, como
     Ditto su corpus en `DITTO_CORPUS`, y sin la variable se saltean con un
     mensaje. `just -f tools/justfile pruebas` da 120 y 2 salteadas; con
     `SOUNDFONT=…`, 122.
   - `snes_convert.args_game_dir` arranca en `None` y `_juego()` cae en el
     del ambiente: las pruebas llaman a `lideres_posibles` sin pasar por
     `main`.
4. **La red: `test_ninguna_herramienta_sabe_de_abl`**, en
   `tools/pruebas/test_proyecto.py`, al lado de la de Tipa porque comparte
   cómo se lee una variable de ambiente. Falla si un `.py` de `tools/` lee
   cualquier variable `ABL_*`, o escribe `rom/` como pedazo de ruta: un
   string sin blancos que empieza por `rom/` o tiene `/rom/`. No mira la
   prosa —docstrings, `help=`, los mensajes, que llevan blancos— ni la
   sección `[rom]` del archivo de proyecto, que es un nombre de clave. Y
   `proyecto.py` deja de ser la excepción de la de Tipa: ya no tiene los
   valores de la máquina.
   - Mostrado que falla: con `os.environ.get("ABL_GAME_DIR")` agregado a
     `comun/ambiente.py` y `"rom/data/maps"` a `rpgmaker/fork.py`, las dos
     pruebas dan rojo y nombran archivo y línea; sacados, verde.
5. **La prosa**, en su commit: `tools/README.md` ("Cómo encuentran el
   juego"), `AGENTS.md` (los valores de la máquina los pone `rom/justfile`,
   y cómo correr acá las dos de `SOUNDFONT`), `README.md` y los índices de
   las dos carpetas de pruebas.

## Qué cambia para taro en el host

**Nada en las recetas ni en las variables**: `just cartuchos`, `just build
release`, `just pruebas`, `just espacio`, `just parches`, `just techos`,
`just entregar` y `just video` se llaman igual, y `ABL_GAME_DIR`,
`ABL_RTP_DIR`, `ABL_SOUNDFONT`, `ABL_CACHE`, `CARTUCHOS` y `SHARED` apuntan
a lo mismo, con los mismos valores por omisión —ahora en `rom/justfile`—.
Lo que cambia:

* **Un script de la suite corrido a mano**, fuera de `just`, ya no cae en
  los valores de esta máquina: hay que pasarle `--game-dir` y los demás, y
  correrlo desde adentro de `rom/` o con `--proyecto`. Corta diciendo qué
  falta.
* **Un `pytest` suelto** de las pruebas de ABL necesita las variables
  puestas; por `just` las pone el `justfile`.
* **`just -f tools/justfile pruebas`** saltea dos si no se le pasa
  `SOUNDFONT`.

## Verificado

* `SIN_CACHE=1 just cartuchos` y los sha256 de `rom/build/` antes de tocar
  nada y después de cada commit que toca lo que arma (1, 2 y 3) y al final:
  **995 archivos iguales**, con los `.sfc`, `.msu`, `.pcm`, `.sym` y los
  `.inc` adentro. Las dos pistas que salen de un reemplazo salieron de él
  las dos veces.

      7a3c6483…a6552  build/release/abl.sfc
      905decd2…6cee   build/release/abl.msu
      fb6db844…0617   build/tests/special/prueba.sfc
      d9e96eab…1578   build/tests/special/prueba.msu

* `just pruebas`: 867, en cada commit y al final.
  `just -f tools/justfile pruebas`: 132 y 2 salteadas, y 134 con
  `SOUNDFONT`. Eran 122: las diez nuevas son las de la red del paso 4.
* Sin ABL: `rm2k-snes-cartridges --lista` desde `/tmp` corta con "no
  encontré un rm2k-snes.toml en /tmp ni en ninguna carpeta de más
  arriba…"; desde `rom/data/maps/` encuentra el proyecto; con `--proyecto`
  desde `/tmp` andan `rm2k-snes-cartridges --lista`, `rm2k-snes-patches
  --check` y `rm2k-snes-space release`. El conversor sin `--game-dir` corta
  con "falta --game-dir…".
* A mano: `just espacio release`, `just parches-check`, `just techos
  --medir`, `rm2k-snes-msu` sobre `release`, y `video.py --help` con y sin
  las variables.
* `test_lado_de_abl.py` no se tocó.
* `main` no se movió desde `9e276429`: no hubo nada que mergear.

## Lo que no se hizo

* **`just entregar` no se corrió**: se miró su línea con `--dry-run`.
  Tampoco `just techos` entero —escribe la tabla—, sólo `--medir`.
* **`raiz()` sigue en dos lugares que no son para llegar a ABL**: el
  directorio donde corren el conversor y `ca65` —de ahí salen las rutas
  relativas del `.dbg` y de los `.inc`, y cambiarlo cambia el `.dbg`—, y la
  búsqueda de recursos de `render_map`, que no encuentra nada ahí. Cuando
  las herramientas sean otro repo, las dos hay que pensarlas.
* **El pre-parseo de `--proyecto`** existe porque `cartuchos` y `entregar`
  leen el archivo al importarse. Si dejan de hacerlo, alcanza con el
  `parse_args` de cada `main`.
* **La forma de adentro de `build/` y de `parches/`** —`release/`,
  `tests/`, `manual/`, `auto/`— sigue siendo de las herramientas. Si otro
  juego quisiera otra, serían más claves de `[paths]`.
