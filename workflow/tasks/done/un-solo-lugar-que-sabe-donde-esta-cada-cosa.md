---
name: "Un solo lugar que sabe dónde está cada cosa"
description: "El paso 2 del plan: comun/proyecto.py junta los once cálculos de la raíz y las rutas derivadas, sin cambiar ningún valor"
type: refactor
assignee: taro
---

Paso 2 del plan de `docs/research/el-mapa-de-las-herramientas-de-python.md`
(§4). Va antes de la mudanza de `data/`, `parches/`, `pruebas/` y el motor
(ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md`): con esto
hecho, mudar una carpeta es cambiar una línea.

Lo decidió Hornero, con la autorización de taro del 2026-09-29 para decidir
sin esperarlo: un módulo `tools/comun/proyecto.py` con una función por
lugar, que devuelve hoy exactamente lo mismo que los cálculos dispersos. El
motor ya se llama `runtime()` ahí, aunque siga en `rom/src/`, para que la
mudanza no tenga que renombrar llamadas.

## Cómo va (Tipa, 2026-09-29)

- `tools/comun/proyecto.py`, en su commit, sin llamadores. Una función por
  lugar: `herramientas`, `raiz`, `runtime`, `build`, `data`, `parches`,
  `parches_manual`, `parches_auto`, `pruebas`, `casos`, `goldens`,
  `snapshots`; y las del ambiente: `juego` (`ABL_GAME_DIR`), `rtp`
  (`ABL_RTP_DIR`), `soundfont` (`ABL_SOUNDFONT`), `reemplazos_msu` (sin
  variable, lo pisa `--reemplazos`), `cache` (`ABL_CACHE`),
  `cartuchos_de_prueba` (`CARTUCHOS`) y `compartido` (`SHARED`).
- `herramientas()` sale de `__file__` y `raiz()` es su padre: el que se
  mude es el que cambia una línea.
- Los scripts que se ejecutan siguen subiendo **dos** carpetas desde
  `__file__`, hasta `tools/`: es el arranque que pone los paquetes en el
  `sys.path`, y sin él no se puede importar `proyecto`. Lo que dejan de
  hacer es subir tres.
- `parches.py` tenía una sola constante para dos cosas: dónde está lo
  versionado en el repo y dónde lo deja cada cartucho en su build. Eran
  iguales por casualidad —el build imita la forma de `parches/`—. Ahora
  `Clase` tiene `directorio` (del repo, sale de `proyecto`) y `en_build`
  (la forma del build, que no se mueve con `parches/`).
- La clave de las capas del conversor (`_version_capas`) suma
  `comun/proyecto.py`: de ahí salen los directorios donde `render_map`
  busca el ChipSet, igual que `recursos.py`.
- La red: `tools/pruebas/test_proyecto.py` falla si un `.py` de `tools/`
  sube tres carpetas desde `__file__`, arma con `os.path.join` una ruta que
  empieza por una carpeta de la raíz (o la pega detrás de la raíz), o lee
  una de las variables de ubicación. Una excepción: la forma del build en
  `parches.py`.

## Lo que quedó afuera, y por qué

- `pruebas/arnes/video.py`: calcula la raíz para armar su `sys.path` antes
  de poder importar nada. Es un script, y el arranque es eso.
- `pruebas/herramientas/test_lado_de_abl.py`, `test_indice.py` y
  `pruebas/abl/test_hover_tram.py`: no importan de las herramientas y no
  empiezan a hacerlo. `test_hover_tram` repite el valor por omisión de
  `ABL_GAME_DIR`, igual que el `justfile`.
- `consola.NUCLEO`: un core de libretro, no una ruta del proyecto.
- `entregar.HUELLA_MSU` sale de `proyecto` y hoy da el mismo texto, pero
  ese texto está copiado en el `LEEME.txt` de las pistas entregadas: cuando
  `rom/build/` se mude, la huella cambia y hay que reentregarlas.
- El script del apéndice D del research pone a `comun` en la fila de
  `rpgmaker`; `tools/README.md` dice cómo correrlo con `comun` abajo.

## Verificado

- `SIN_CACHE=1 just cartuchos` antes de tocar nada y después de migrar:
  997 archivos de `rom/build/` iguales (sin `.o` ni `sello.txt`; los `.dbg`
  sin mtime). Después del comentario de `registros.s`, lo mismo salvo el
  `size` de ese archivo adentro de los dos `.dbg`.
- `just pruebas`: 866. `just -f tools/justfile pruebas`: 117 (109 + 8).
- `rm2k-snes-space` y `rm2k-snes-patches --check` por su nombre desde `/`,
  `just -f …/justfile parches-check` desde `/tmp`, y `--help` de los otros
  seis ejecutables.
- **No se corrió** `just entregar` (se imprimieron sus valores), ni
  `rm2k-snes-msu` ni `rm2k-snes-volume-ceilings` más allá de `--help`.

## Qué mirar

Nada que jugar: la ROM es la misma. Lo que queda es leer el diff.
