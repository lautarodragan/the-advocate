---
name: "Herramientas locales por worktree"
description: "Un bin/ propio de cada worktree, adelante en el PATH de just, en lugar de ejecutable.py; Rust se compila sólo si el agente toca ese proyecto"
type: refactor
assignee: taro
---

De taro, el 2026-09-29, después del paso 1 (`testing/el-justfile-no-sabe-que-existe-python.md`):
el problema es el que `npm link` intenta resolver, con N sub-agentes en
paralelo que modifican las herramientas seguido. Lo acordado:

- cada worktree tiene un `bin/` propio, ignorado por git, que el `justfile`
  pone adelante en el `PATH` si existe: lo que no está ahí sale del global;
- Python se linkea entero (los ocho ejecutables), porque no cuesta nada y
  cada script resuelve sus módulos desde su checkout real;
- Rust se instala ahí **sólo para el proyecto que el agente modifica**. De
  taro: "es importante que ningún subagente corra una compilación de Rust
  innecesaria. Son costosas";
- `tools/comun/ejecutable.py` se va: resolvía lo mismo de forma implícita;
- al mergear, el que mergea vuelve a instalar en el global sólo lo de Rust
  que la rama tocó.

## Lo hecho (Espinillo)

* `just herramientas-locales [proyectos…]` arma `.herramientas-locales/bin/`
  en el worktree: los ocho scripts siempre, y `cargo install --root` sólo de
  los proyectos nombrados. Sin nombres no compila nada; un nombre que no es
  proyecto corta antes de compilar. Se niega en el checkout principal
  (`git-dir` igual a `git-common-dir`).
* El `justfile` exporta `PATH` con ese `bin/` adelante si existe
  (`path_exists`). En `main` no existe.
* `just herramientas [proyectos…]`: con nombres, sólo esos de Rust más los
  symlinks de Python; sin nombres, todo, como antes.
* Las dos usan `_instalar`, que entró en la lista de recetas de las
  herramientas de `test_lado_de_abl.py` con lo que antes estaba adentro de
  `herramientas`.
* `just cuales` imprime qué ejecutable resuelve el checkout para cada una.
* Se fue `tools/comun/ejecutable.py` con sus llamadas; `comun/` volvió a su
  fila en `tools/README.md`.
* AGENTS.md, "Sub-agentes": qué hace el agente al empezar y qué reinstala el
  que mergea.

**El nombre, `.herramientas-locales/`**: en la raíz y no en `tools/`, así que
la huella —que mira `tools/*/*.py`, `rom/src/` y los binarios que resuelve el
PATH— no lo recorre, y la prueba del grep tampoco —mira `parches/`, `data/` y
`pruebas/`—. Oculto, porque no es parte del árbol. Adentro queda lo que
`cargo install --root` deja: `bin/`, `.crates.toml` y `.crates2.json`.

**Sin el `bin/`, un worktree se niega.** Correría los scripts de `main`,
que arman en el `rom/build/` de `main`: pisaría sus cartuchos sin enterarse.
Lo marcó el coordinador antes de mergear, y se resolvió con
`_herramientas_del_checkout`, de la que dependen `cartuchos`, `build`,
`pruebas*`, `espacio`, `parches`, `parches-check`, `techos`, `entregar` y
`video`. Pasa en el checkout principal (`git-dir` igual al común) y en un
worktree con `.herramientas-locales/bin/`. `herramientas-locales` y `cuales`
no dependen de ella. Medido: sin el `bin/`, `just cartuchos`, `just pruebas`,
`just espacio release` y `just video` salen 1 con el mensaje, y `just
cuales` anda; en el checkout principal la receta sale 0; después de `just
herramientas-locales` —sin Rust— `just cartuchos` arma y `just pruebas` da
973 en verde, con `abl.sfc` y `prueba.sfc` iguales que antes.

**`cargo` fuera de instalar**: sólo lo llaman `herramientas`, `_instalar` y
las `*-pruebas` de Rust, que son sus pruebas. Ningún `.py` de `tools/` ni de
`pruebas/` lo llama (grep).

### Verificado

* **ROMs**: `SIN_CACHE=1 just cartuchos` en este worktree, con su `bin/`
  —los ocho scripts y `lz2` locales—: los 47 archivos de `release/` y
  `tests/special/` con el mismo sha256 que antes del paso 1 (`abl.sfc`
  `7a3c6483…6a66552`).
* **`just pruebas`**: 973 pasan.
* **Resolución**, con `just cuales`:
  * este worktree sin `bin/`: todo en `/usr/local/bin`, sin error;
  * después de `just herramientas-locales`: los ocho locales, Rust global;
  * después de `just herramientas-locales lz2`: `lz2` también local;
  * una copia del `justfile` en un directorio sin `bin/` —lo que ve `main`—:
    todo global.
* `just herramientas-locales foo` corta sin crear el directorio;
  `_no_en_el_principal` corrido en el checkout principal sale 1.
* **Rust se compiló una sola vez**: `lz2`, el más chico (una crate, sin
  dependencias; `protocol` tiene 34 y 837 líneas contra 700).
* El global no se tocó: los symlinks de `/usr/local/bin` siguen apuntando al
  checkout principal, con la fecha de cuando los instaló el coordinador.
  `just herramientas lz2` se probó sólo con `--dry-run`.

**Lo que no se probó**: `just herramientas <proyecto>` de verdad contra el
global, y nada del host (`CARGO_ROOT=~/.cargo`). Tampoco un segundo worktree
real: "desde `main`" se probó con la copia del `justfile`, no corriendo en
el checkout principal, que no se quiso tocar.
