---
name: "El mapa de las herramientas de Python"
description: "Grafo de dependencias, responsabilidades y qué es agnóstico a ABL en los .py de tools/, con un plan por partes para separar herramientas y juego en dos repos"
type: docs
assignee: taro
---

De taro, el 2026-09-28: "me gustaría retomar el refactor de las
herramientas hechas en python. [...] Me gustaría entender el grafo de
dependencias entre los distintos archivos python, qué responsabilidad tiene
cada cosa, y qué es agnóstico al ABL y qué no. Uno de los siguientes pasos
que quiero encarar es dividir el repo en dos: las herramientas por un lado,
todo agnóstico a cualquier juego, y un repo dedicado a A Blurred Line. Ese
proyecto no va a ser completamente trivial y lo tendremos que encarar por
partes. Este plan nos va a ayudar a ello."

Es investigación y plan, no código. **El resultado es
`docs/research/el-mapa-de-las-herramientas-de-python.md`**: taro lo tiene que
leer, y sobre todo contestar las preguntas de su §5, que son las que deciden
por dónde se empieza.

Relacionadas: `todo/las-responsabilidades-de-snes-convert.md` y
`wishlist/un-juego-golden-y-dos-repos.md`.

# Bitácora

* 2026-09-28, Quebracho. `main` mergeado en el worktree (`e314ff7b`). El
  grafo sale de un script de AST descartable (en el scratchpad): aristas
  `import` (a nivel módulo), `lazy` (adentro de una función o del
  `if __name__`) y `ruta` (un literal que *es* la ruta de otro `.py`). La
  primera versión contaba como `ruta` cualquier texto que nombrara un `.py`
  —docstrings, `help=`— y daba un solo ciclo de treinta módulos: ruido. Con
  el literal entero como ruta quedan dos aristas reales: `cartuchos` corre
  `snes_convert.py` como subproceso, y `snes_convert` mete en la clave del
  caché el hash de `rm2k`, `render_map`, `chipset` y `asignador`.
* Primer hallazgo contra `tools/README.md`: los ciclos no son los tres que
  dice. Hay una sola componente fuerte en `port/` de seis módulos
  (`eventos`, `batalla`, `pantallas`, `imagen`, `titulo`, `experiencia`),
  más `snes_convert`↔`pantalla_completa` y, abajo de todo, `lcf`↔`fork`.
  `batalla`↔`pantallas` no es directo: pasa por `eventos`. Y los imports que
  violan las capas salen de dos archivos nada más: `ensamblado/cartuchos.py`
  (importa de `port/`, `audio/` y `rpgmaker/`) y `rpgmaker/fork.py`
  (importa de `render/`, adentro de funciones).
* Repartí la lectura de la clasificación agnóstico/ABL en cinco lecturas
  paralelas: `snes_convert`, `eventos`, el resto de `port/`, las capas de
  abajo, y lo que no es Python.
* Las cinco lecturas coincidieron en lo grueso: **ninguna sección de
  `snes_convert` ni de `eventos` es de ABL**. Lo de ABL escrito en el código es
  el contenido de `cartuchos.py`, las tablas de audio de `snes_music.py`
  (269-417) y unas veinte perillas. Comprobé contra el código cada gancho que
  el research cita por línea (grep de cada constante). Lo que ata el repo a
  ABL es la forma del árbol: once módulos calculan la raíz desde `__file__`.
* El script del apéndice D del research es una versión limpia del que usé.
  Lo corrí sobre este mismo commit y da la misma tabla y las mismas aristas
  que el original (diff vacío, salvo un encabezado).
* `tools/README.md` decía tres ciclos que ya no eran así; lo corregí en su
  propio commit, apuntando al research.

## Lo que decidió taro

El 2026-09-28, sobre el resumen del research: ver
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`, que tiene
también las tres preguntas que quedaron abiertas (cómo consume ABL a las
herramientas, `cartuchos.py`, y qué decisiones y divergencias van a cada
lado). El research no se tocó: es una foto.
