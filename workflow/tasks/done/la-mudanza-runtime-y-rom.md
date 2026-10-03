---
name: "La mudanza: el runtime a tools/, ABL adentro de rom/"
description: "rom/src pasa a tools/runtime; data/, parches/, pruebas/, pytest.ini y el justfile de ABL pasan adentro de rom/, con las ROMs byte por byte iguales"
type: refactor
assignee: taro
---

Decidido por taro el 2026-09-29 (ver
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`): se distingue
el runtime genérico del proyecto A Blurred Line. La raíz queda con `rom/`,
`tools/`, `docs/` y `workflow/` (más los archivos sueltos de siempre:
`AGENTS.md`, `CLAUDE.md`, `README.md`, `DITTO.md`, `.gitignore`…).

Va después del paso 2 del plan (`comun/proyecto.py`, Tipa, `e257bca3`), así
que mover cada carpeta es cambiar una línea ahí. Hornero decide los detalles
con la autorización de taro para decidir sin esperarlo.

- `rom/src/` → `tools/runtime/`
- `data/` → `rom/data/`, `parches/` → `rom/parches/`, `pruebas/` →
  `rom/pruebas/`, `pytest.ini` → `rom/pytest.ini`
- el `justfile` de la raíz → `rom/justfile`
- `rom/build/` se queda donde está.

## Lo hecho (Algarrobo, 2026-09-29)

Cuatro commits: `3b3f8db6`, sólo `git mv` y no arma; `78a5d27e`, lo que lo
hace andar; `1bf580f3`, la prosa; `539ba681`, cinco comentarios que la
pasada mecánica de la prosa cambió adentro de strings que el conversor
escribe al `.inc`, y que vuelven a decir `rom/src/` (ver abajo).

- **`proyecto.py`**: `runtime()` cuelga de `herramientas()`, y una función
  nueva, `abl()` —`rom/`—, de la que cuelgan `build`, `data`, `parches` y
  `pruebas`. `raiz()` sigue siendo la del repo: ahí corren `ca65` y `ld65`,
  y contra ella se escriben las rutas de los `.inc` y los `.dbg`. Por eso
  los `.inc` salen iguales y los `.dbg` cambian sólo en el nombre de los
  fuentes. `entregar` se acomodó solo: su `RUNTIME` sale de `proyecto`, y
  `HUELLA_MSU` da el mismo texto porque `rom/build/` no se movió.
- **`ensamblar.py`** mira el directorio del fuente que arma, así que la
  negativa pasó sola a `tools/runtime/`. Probado con un `mapdata.inc`
  vacío ahí: se niega.
- **`.gitignore`**: `rom/pruebas/snapshots/`. `.git-blame-ignore-revs` se
  queda en la raíz y sin cambios: `git blame` lo busca ahí, y sus commits
  valen para todo el repo.

## Las decisiones, y por qué

**Desde dónde se corren las recetas de ABL: desde la raíz, igual que
antes, o desde `rom/`.** La raíz tiene un `justfile` de dos líneas que sólo
hace `import "rom/justfile"` con `set working-directory := "rom"`. Así:

- taro sigue escribiendo `just cartuchos`, `just entregar "…"` y
  `mednafen rom/build/release/abl.sfc` desde la raíz, como siempre;
- las recetas corren paradas en `rom/` las llame quien las llame —desde la
  raíz, desde `rom/`, desde `rom/pruebas/abl/`, o con `-f` desde `/tmp`—,
  así que sus rutas son relativas a ABL y no al repo;
- el de la raíz no tiene recetas ni nombra `tools/`, y ninguno de los dos
  `justfile` de abajo sabe que existe: es del repo, y el día que se parta
  se borra.

Descartado: `mod rom`, que obliga a escribir `just rom cartuchos`, y que
taro corra desde `rom/`, que cambia su costumbre y el comando de `mednafen`.

Un detalle que costó: importado, `justfile_directory()` es la raíz, no
`rom/`. `rom/justfile` usa `source_directory()`, que es el suyo en los dos
casos. Probado en un árbol de juguete antes de tocar el repo.

**El `bin/` local: `herramientas-locales <destino> [proyectos…]`, con el
destino obligatorio.** Ninguno de los dos lados puede saber dónde vive el
otro, así que lo dice el que consume. `rom/justfile` busca el suyo en
`rom/.herramientas-locales/`, y su guarda, cuando no está, da el comando
entero con rutas absolutas —sale de `git rev-parse --show-toplevel` y de
`source_directory()`—, así que se puede pegar desde cualquier directorio.
Un destino relativo es relativo a donde se corrió `just`
(`invocation_directory()`), no a `tools/`. `tools/justfile` busca el suyo
en `tools/.herramientas-locales/`, para que `protocolo` y sus pruebas usen
el `protocol` del worktree si alguien lo modifica. Obligatorio y no con un
valor por omisión porque `herramientas-locales lz2` sería ambiguo.

**Las rutas en la prosa de `rom/` son desde `rom/`**: `build/release`,
`pruebas/`, y el runtime como `runtime/<archivo>.s`, sin `tools/`, que es
lo que cobra `test_lado_de_abl.py`. Afuera de `rom/`, desde la raíz del
repo.

## Verificado

- **ROMs**: `SIN_CACHE=1 just cartuchos` antes de tocar nada (desde la
  raíz) y después del segundo commit (desde la raíz): de los 1001 archivos
  de `rom/build/` —sin `cache/`, `.o` ni `sello.txt`—, iguales todos salvo
  los dos `.dbg`. `abl.sfc` `7a3c6483…6a66552`, `prueba.sfc`
  `fb6db844…ae2d877`, `abl.msu` `905decd2…6b83cee`, y los `.pcm` y los
  `.inc` generados, iguales. Los `.dbg` difieren en 95 líneas `file` cada
  uno y en nada más, y la única diferencia es `rom/src/` → `tools/runtime/`
  en el nombre.
- **Y otra vez al final**, `SIN_CACHE=1 just cartuchos` desde `rom/` sobre
  los cuatro commits, contra lo de antes de la mudanza: iguales todos salvo
  los dos `.dbg`, que suman al cambio de nombre el `size` de los 16 `.s`
  cuyos comentarios tocó la prosa, y nada más.

  **Esa corrida fue la que cazó el error de la prosa**: la primera vez,
  después de `1bf580f3`, los cuatro `.inc` generados salían distintos. La
  pasada mecánica había cambiado `rom/src/` por `tools/runtime/` en cinco
  strings de `snes_convert.py` y `snes_music.py` que son comentarios que
  el conversor escribe al `.inc`. La decisión dice que lo emitido no se
  toca todavía, así que volvieron a `rom/src/`, con un comentario al lado.
  Ninguna prueba compara los `.inc` contra los de antes: sin esta corrida,
  habría pasado.
- **Tandas**: `just pruebas` desde la raíz, 866 antes y después; desde
  `rom/`, después de la prosa, 866. `just -f tools/justfile pruebas`, 117.
- **`test_lado_de_abl.py`**: sin tocar el código. Calcula su raíz tres
  carpetas arriba de sí misma, que ahora es `rom/`, y sus rutas relativas
  —`justfile`, `parches`, `data`, `pruebas`, `pytest.ini`— siguen
  apuntando a lo mismo. Las 23 excepciones son las mismas: `rom/pytest.ini`
  nombra `../tools`, y ya estaba en la lista.
- **Desde otros directorios**: `just espacio release` desde
  `rom/pruebas/abl/`; `just -f <raíz>/justfile parches-check` y `just -f
  <raíz>/rom/justfile cartuchos` desde `/tmp`; `just parches` deja el árbol
  igual; `pruebas/arnes/video.py --help` desde `rom/`.
- **La guarda**: este worktree sin `bin/` se niega, y el comando que da,
  pegado desde `/tmp`, arma el `bin/` y deja pasar. Sin destino,
  `herramientas-locales` dice su uso; con uno relativo, lo arma relativo al
  directorio desde donde se corrió.
- **Mesen2**: armé lo que dejaría `just entregar` en un directorio del
  scratchpad —`abl.sfc`, `.dbg`, `.msu` y el `git archive` de
  `tools/runtime/`— y corrí la búsqueda de Mesen2 reimplementada (al lado
  del `.dbg` y subiendo): encuentra los 95 fuentes y le faltan
  `mapdata.inc` y `musicdata.inc`, igual que antes. Desde
  `rom/build/release/` en el clon encuentra los 97.
- **`git blame -C --diff-algorithm=histogram`**: de `tools/runtime/` en
  `HEAD` contra `rom/src/` en `4ab92fd0`, línea por línea, el mismo commit
  en las 4223 líneas de `main.s`, `heroe.s`, `interprete.s`, `batalla.s`,
  `registros.s`, `paquete_de_audio.s` y `event_opcodes.inc`. Y `blame` sin
  opciones sobre `rom/pruebas/arnes/consola.py`, igual en sus 1133.

**No se corrió**: `just entregar` de verdad, `datos`, `datos-vuelta`,
`techos`, ni `video` más allá del `--help`.

## Qué tiene que hacer taro en el host

- **Nada para correr las recetas**: `just cartuchos`, `just pruebas`, `just
  entregar "…"` siguen andando desde la raíz. También andan desde `rom/`.
- **La ROM sigue en `rom/build/release/abl.sfc`.** `rom/build/` no se movió,
  y las pistas de MSU-1 de `/shared/msu/` siguen valiendo: la huella es la
  misma.
- **`just -f tools/justfile herramientas` no hace falta volver a correrlo.**
  Los symlinks del global apuntan a los `.py` de `tools/`, que no se
  movieron, y esos scripts leen las rutas de `proyecto.py`, que es el nuevo
  apenas se mergea. Rust no cambió.
- **Los builds que entregue `just entregar` desde ahora traen
  `tools/runtime/`** al lado del `.dbg`, en vez de `rom/src/`. Mesen2 lo
  encuentra igual.
- **El IDE**: si JetBrains tenía marcado `rom/src/` o `pruebas/` como
  carpeta de algo, hay que marcar `tools/runtime/` y `rom/pruebas/`.
- **Sub-agentes**: el comando de arranque cambió —`just -f tools/justfile
  herramientas-locales rom/.herramientas-locales`—, y está en AGENTS.md.
  Los worktrees viejos con `.herramientas-locales/` en su raíz dejan de
  usarlo: la guarda se niega y da el comando nuevo.
