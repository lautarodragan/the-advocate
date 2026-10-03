---
name: "El justfile no sabe que existe Python"
description: "El justfile llama sólo ejecutables del PATH; los .py que se ejecutan pasan a ser ejecutables de verdad, y una prueba con grep cuida que el lado de ABL no nombre tools/"
type: refactor
assignee: taro
---

De taro, el 2026-09-28, como primer paso para separar las herramientas de
ABL (ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md` y
`docs/research/el-mapa-de-las-herramientas-de-python.md`):

> Se me ocurre un primer paso: que justfile no sepa que existe python. ABL
> no puede saber que existe el directorio de tools — solo sabe que existe
> una suite de herramientas disponible en el path. Los archivos de Python
> que son ejecutables se convierten en ejecutables de verdad, con hashbang y
> chmod +x.
>
> Luego podemos tener un test muy simple con grep: si algo en abl matchea el
> path de tools, falla el pipeline.

Medido antes de empezar: el `justfile` tiene 50 líneas que nombran
`python3` o `tools/` (`grep -c "python3\|tools/" justfile`), y 63 archivos de
`pruebas/` importan módulos de `tools/` directamente. Por eso la prueba del
grep arranca con una lista de excepciones para `pruebas/` que sólo puede
achicarse.

## Lo hecho (Espinillo)

Tres commits, en el orden que pide AGENTS.md: lo que se verifica con las ROMs
primero, la prueba y la prosa después, los docs aparte.

### Los ejecutables

Los ocho `.py` que tienen `__main__` pasan a tener hashbang y `chmod +x`, y
`just herramientas` los instala como symlinks en `{{cargo_root}}/bin`, al lado
de los de Rust:

    rm2k-snes-cartridges        tools/ensamblado/cartuchos.py
    rm2k-snes-assemble          tools/ensamblado/ensamblar.py
    rm2k-snes-space             tools/ensamblado/espacio.py
    rm2k-snes-convert           tools/port/snes_convert.py
    rm2k-snes-patches           tools/port/parches.py
    rm2k-snes-msu               tools/audio/msu.py
    rm2k-snes-volume-ceilings   tools/audio/techos.py
    abl-entregar                tools/ensamblado/entregar.py

El `justfile` llama sólo a cinco: `rm2k-snes-convert`, `-assemble` y `-msu`
los usan los otros scripts adentro o se corren a mano, y se instalan igual
porque se ejecutan.

**Los nombres siguen al repo donde va a vivir cada programa.** La suite va a
ser un repo en inglés (lo decidido el 2026-09-28), así que sus ejecutables ya
van en inglés: el nombre es lo que ABL consume, y ponerlo en castellano
obligaría a renombrarlo dos veces —en el `justfile`, en los docs y en el `bin/`
de taro, donde el viejo quedaría colgado—. Los flags siguen en castellano
(`--lista`, `--medir`): ésos se traducen con el código. `entregar` se queda con
ABL según el research (§ la tabla de módulos), así que va con `abl-` y en
castellano. El prefijo es porque el `bin/` es compartido: `espacio`, `parches`
o `msu` sueltos no dicen qué son y pueden chocar con cualquier cosa; con
`rm2k-snes-<TAB>` aparece la suite entera. Los de Rust siguen sin prefijo, y
`protocol` es el que más riesgo de choque tiene: no es de esta tarea.

**Symlinks y no copias**, como pedía el encargo. No encontré razón para copiar.

### La desviación: un symlink apunta a un solo checkout

Con sólo `realpath`, un script corrido desde el PATH usa el checkout del
symlink. En un worktree de sub-agente, `just cartuchos` armaba entonces **las
ROMs de otro árbol, con el conversor de otro árbol y en el `rom/build/` de
ése**, y la tanda del worktree se negaba a correr contra las suyas, viejas.
Rompía a todos los sub-agentes a partir del primer `just herramientas` desde
`main`.

Así que cada script, al arrancar desde el PATH, busca hacia arriba desde el
directorio actual un checkout que tenga su propia copia del mismo archivo, y si
la hay y no es él, hace `execv` de ésa (`tools/comun/ejecutable.py`). El
checkout del symlink queda como el de último recurso: fuera de todo checkout.
Es lo mismo que hace cualquier herramienta que prefiere la versión del
proyecto a la instalada.

`comun/` es la capa que no importa nada; `ensamblado/` la importa sólo al
arrancar como script. `tools/README.md` la baja a una fila propia.

Lo que esto **no** resuelve: si el checkout al que apunta el symlink se borra
—un worktree que se limpia—, los ejecutables quedan colgando hasta volver a
correr `just herramientas` desde otro. Por eso:

> **Al mergear, correr `just herramientas` desde `main`.** Hoy los symlinks de
> `/usr/local/bin` apuntan al worktree de Espinillo.

### `video.py` y pytest

`video.py` es de `pruebas/`, así que no se instala: el `justfile` lo llama por
su ruta, y el `-O` va en el hashbang (`#!/usr/bin/env -S python3 -O`). No hizo
falta ponerlo en ninguna lista de excepciones. `env -S` es de coreutils 8.30 en
adelante.

Las pruebas corren con `pytest` en vez de `python3 -m pytest`; lo único que
agregaba el `-m` era la raíz en el `sys.path`, y nada importa `pruebas.` ni
`tools.` desde ahí. `_xdist` pregunta con `pytest -p xdist --help`, que sale 1
si el plugin no está (medido con un `-p` inexistente: `--version` sale 0 igual,
por eso no sirve).

### La prueba

`pruebas/herramientas/test_lado_de_abl.py`. Qué es el lado de ABL está escrito
arriba de la prueba: el `justfile` salvo las ocho recetas de las herramientas
(`protocolo`, `*-pruebas`, `ditto-vuelta-entera`, `herramientas`), `parches/`,
`data/`, y `pruebas/` + `pytest.ini` con 28 excepciones. Las dos listas sólo
pueden achicarse: falla si aparece uno nuevo y si uno de la lista ya no nombra
`tools/`.

Para que diera verde hubo que cambiar el encabezado que el conversor escribe en
cada parche versionado —136 archivos de `parches/auto/`, una línea cada uno— y
el de `techos.toml`, más los README de `parches/` y `data/` y la prosa de las
recetas de ABL.

Las excepciones de `pruebas/` son de dos clases. Las que arman el camino de los
imports o leen archivos de `tools/` (`pytest.ini`, `video.py`,
`test_repartos.py`, `test_musica_stream.py`, `test_protocolo.py`) se van cuando
las pruebas se separen de las herramientas. Las demás lo nombran en la prosa
—"ver `tools/port/eventos.py`"— y se van al reescribirla.

Lo que la prueba no mira, a propósito: los imports por nombre de paquete
(`from rpgmaker import lcf`), que no dicen dónde está nada.

### Verificado

Ver el mensaje de cada commit. Al final, sobre el árbol mergeado con `main`:

* **ROMs byte por byte**: `just cartuchos` sobre `2bf9ff2c`, antes de tocar
  nada, y `SIN_CACHE=1 just cartuchos` sobre el árbol final: los 47 archivos
  de `rom/build/release/` y `rom/build/tests/special/` —dos `.sfc`, dos `.msu`
  y 43 `.pcm`— con el mismo sha256. `abl.sfc`
  `7a3c6483…6a66552`, `prueba.sfc` `fb6db844…66a0617`.
* **`just pruebas`**, corrido desde el scratchpad con `--justfile`: 973
  pasan, ninguna falla.
* `just herramientas` instala los ocho; los ocho contestan `--help` por su
  nombre desde fuera del repo.
* Desde fuera del repo también: `just espacio release`, `just espacio
  <ruta a abl.sfc>`, `just parches-check`, `just build release`, `just video
  release … quieto:120` (el `-O` del hashbang anda: sin él, `video.py` se
  niega) y `just techos --medir`.
* El re-exec, con un checkout falso en el scratchpad cuyo `cartuchos.py`
  sólo imprime: `rm2k-snes-cartridges` corrido adentro corre ése.
* La prueba del grep, con una línea que viola cada regla puesta a mano y
  sacada después: ver el mensaje de `2aa151be`.

**Lo que no se probó**: nada del host. `CARGO_ROOT=~/.cargo just
herramientas` no se corrió; la receta hace `mkdir -p` del `bin/` y usa rutas
absolutas, así que no debería depender de dónde, pero no está medido. `just
entregar` tampoco se corrió, por encargo: sólo `abl-entregar --help`. Y la
rama de `_xdist` sin el plugin no se ejecutó entera; se midió sólo que `pytest
-p <inexistente> --help` sale 1.

**Para taro**: después de mergear, `just herramientas` una vez, del lado del
host también. Sin eso, `just cartuchos` dice `rm2k-snes-cartridges: command
not found`.
