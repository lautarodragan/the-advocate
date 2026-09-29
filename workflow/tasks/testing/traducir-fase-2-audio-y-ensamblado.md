---
name: "Traducir las herramientas, fase 2: el audio y el ensamblado"
description: "Los nombres de código de tools/audio y tools/ensamblado al inglés, y las recetas de tools/justfile"
type: refactor
assignee: taro
---

Fase 2 de la traducción de `tools/` al inglés, segunda área: `tools/audio/`,
`tools/ensamblado/` (que pasa a llamarse `tools/build/` o parecido) y las
recetas de `tools/justfile`, con todos sus usos. Van juntas porque
`cartuchos.py` importa del audio.

`ensamblado/entregar.py` (`abl-entregar`) es de ABL y queda en castellano.

Hace falta además una forma de instalar sólo los scripts de Python en el
PATH, sin compilar ni reinstalar Rust: hoy `herramientas` sin argumentos
reinstala los cinco proyectos, y cada renombre de un script pide volver a
enlazar.

## Cómo se hace

De a un módulo por commit, con los scripts de renombre por tokens de
Mburucuyá adaptados —ahora también miran `docs/` salvo `docs/research/`,
que son estudios fechados, y no tocan `musica.json`, `techos.toml` y
demás nombres de archivo que parecen `módulo.atributo`—. Entre commit y
commit: `SIN_CACHE=1 just cartuchos` con las huellas de `rom/build/`
contra las de 2bd3cf64 (995 archivos), las dos tandas, pyflakes y cada
ejecutable corrido por su nombre desde /tmp con `--project`.

## Dónde quedó

- `audio/musica.py` → `audio/music.py`.
- `techos.py` no leía `--project` antes de importar, y fuera del juego
  `rm2k-snes-volume-ceilings --project rom --help` se cortaba: arreglado en
  su propio commit.
- `audio/muestras_brr.py` → `audio/brr_samples.py`, con sus nombres.
- `audio/sdsp.py` y `audio/midi.py`: los nombres; los archivos ya estaban
  en inglés.
- `audio/snes_samples.py`: los nombres.
- `audio/snes_music.py`: los nombres, con los atributos de `Bank`,
  `SoundEffect`, `Constraint`, `Group`, `NoteSetup` y `_Voice`. Quedan en
  castellano, a propósito, las claves de los dicts que arma —`leido["voces"]`,
  `tema["sonidos"]`…—, que leen el conversor y las pruebas y terminan en
  `musica.json`; las etiquetas del driver del SPC700; y lo que va adentro
  del texto de `musicdata.inc`, que tiene que salir igual: nombra todavía
  `lugares_de_efectos` y `build_efectos`.
- `audio/efectos_msu.py` → `audio/msu_effects.py`, con sus nombres. El
  comentario de `tools/runtime/efectos_con_msu.s` que lo nombra queda con
  la ruta vieja: tocar un `.s` cambia el `.dbg`, y el runtime es la última
  área.
- `audio/msu.py`: los nombres, y `--ganancia` pasa a `--gain`.
- `audio/techos.py` → `audio/ceilings.py`, con sus nombres, y `--medir`
  pasa a `--measure`. El symlink de `rm2k-snes-volume-ceilings` cambia de
  destino: el global queda roto hasta reinstalar los scripts.
- `tools/ensamblado/` → `tools/assembly/`, y no `tools/build/`: ver el
  commit. Los comentarios de `tools/runtime/*.s` que la citan quedan con la
  ruta vieja, por lo mismo que el de `efectos_con_msu.s`.
- `assembly/bancos.py` → `assembly/banks.py`, con sus nombres.
- `assembly/ensamblar.py` → `assembly/assemble.py`, con sus nombres, y
  `--simbolos` pasa a `--symbols`.
- `assembly/espacio.py` → `assembly/space.py`, con sus nombres y las
  claves de `measure`, que lee `test_espacio.py`.
- `assembly/cartuchos.py` → `assembly/cartridges.py`, con sus nombres, y
  `--lista` pasa a `--list`.
- Las recetas de `tools/justfile`, al inglés: `herramientas` → `install`,
  `herramientas-locales` → `install-local`, `protocolo` → `protocol`,
  `pruebas` → `test`, `*-pruebas` → `*-test`, `ditto-vuelta-entera` →
  `ditto-round-trip`, `cuales` → `which`. Su directorio local,
  `tools/.herramientas-locales/` → `tools/.local-tools/`; el de ABL,
  `rom/.herramientas-locales/`, es de ABL y queda.
- `install-scripts`: los symlinks de Python solos, al global, sin compilar
  nada. Se niega en un worktree. De paso, la guarda de `install-local` no
  reconocía el checkout principal: comparaba `--git-dir`, absoluto, con
  `--git-common-dir`, que desde `tools/` sale relativo (`../.git`), así que
  nunca eran iguales. Ahora las dos piden `--path-format=absolute`, como la
  de `rom/justfile`.
- `tools/runtime/interprete.s` cita `just protocolo` en un comentario: queda,
  por lo mismo que los otros `.s`.
- Las citas que el script no alcanzó, en su commit, después de un grep de
  cada nombre viejo.

## Para el que mergea

- Los symlinks del global apuntan a rutas que ya no existen —`techos.py`,
  `ensamblado/*.py`—: después del merge, desde el checkout principal,
  `just -f tools/justfile install-scripts`. No compila nada.
- Un worktree que ya tenía su `bin/` lo rearma con `just -f tools/justfile
  install-local rom/.herramientas-locales`: el nombre viejo de la receta ya
  no existe.
- Los dos `memoria.cfg` de `rom/build/` cambian su primera línea —la ruta de
  `banks.py`—; lo demás sale byte por byte igual a 2bd3cf64.

## Términos nuevos para el glosario

- aire de medida → measuring headroom.
- lugar (del directorio de muestras) → place: `effect_places`,
  `SE_PLACES_MAX`. No "slot", que es la ranura.
- copia (de una muestra) → copy: `copies`.
- restricción → constraint.
- viejo (un cartucho) → stale, de "al día / viejo".
- `BANCO`, el tamaño de un banco → `BANK_SIZE`, para no confundirlo con
  `BANKS`.
- pieza del acomodo (`_Unidad`) → piece (`_Piece`).

## Qué queda para taro

Nada que jugar: ningún byte de la ROM cambió. Mirar el diff de
`AGENTS.md` —sólo recetas y rutas, más el punto de qué reinstala el que
mergea— y decidir si el glosario suma los términos de arriba.
