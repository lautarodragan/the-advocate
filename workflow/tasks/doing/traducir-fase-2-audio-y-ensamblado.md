---
name: "Traducir las herramientas, fase 2: el audio y el ensamblado"
description: "Los nombres de código de tools/audio y tools/ensamblado al inglés, y las recetas de tools/justfile"
type: refactor
assignee: Pindó
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
