---
name: "Reducir el README"
description: "taro está reescribiendo README.md a mano para que sea mucho más corto"
type: docs
assignee: taro
---

taro lo está reescribiendo a mano desde el 2026-09-25. **Mientras esté en
`wip/`, nadie más toca `README.md`**: lo que haya que cambiarle se anota acá
abajo y lo resuelve él.

Anotado para él:

* `README.md` enlaza a una sección "El MSU-1" (`#el-msu-1`, en el índice de
  arriba) que no existe, y el docstring de `tools/audio/msu.py` la cita.
* El flag `--inicio` se sacó el 2026-09-25: la línea de `README.md` que lo
  menciona ("sigue existiendo para las recetas") se va.
* El párrafo "Cómo se suelta una nota" (~líneas 851-853) dice que "el valor por familia está en `sdsp.py`": desde el 2026-09-25 las envolventes salen del SoundFont y las familias se fueron.
* "Cómo está armado", en el audio (~líneas 777-785): "en la consola sólo un
  intérprete de un stream de escrituras" ya no es así desde el 2026-09-26 —el
  stream es por nota y el 65816 lo expande a escrituras: ver "el formato por
  nota" en `tools/audio/snes_music.py`—. Lo del driver del SPC700, que espera
  pares (registro, valor), sigue valiendo: el driver no cambió.
* Los dos párrafos al final de "las muestras de percusión" (~líneas 890-898):
  "La percusión se lleva además una segunda voz del DSP" y "Con el reparto de
  voces por cobertura, que es el mismo código de `md_music.py`" dejaron de ser
  ciertos el 2026-09-26: las ocho voces son de todos los canales y se reparten
  nota a nota (`assign` y `_victima` en `tools/audio/snes_music.py`); la
  batería va primero a las voces 6 y 7 pero no las tiene fijas, y
  `share_voices`/`coverage` se fueron. Cuánto tiempo-nota se pierde lo
  imprime el conversor por tema.
  Desde el 2026-09-26, también: el orden en que eligen voz las notas de un
  mismo cuadro es `_orden_del_cuadro` (golpes primero, uno por familia; lo
  melódico por nivel dividido por su lugar en el acorde).
* "Lo que sí queda de ellas son los números de `sdsp.py`" (~líneas 962-966):
  el techo por voz ya no es uno solo desde el 2026-09-26. `sdsp.AIRE` es el
  máximo, y el tema que con él recortaría va con el suyo, medido por `just
  techos` y versionado en `parches/auto/musica/techos.toml` (ver
  `leer_techos` en `tools/audio/snes_music.py`).
* "Varios temas en el cartucho" (~líneas 130-200) quedó viejo entero el
  2026-09-26, con el presupuesto por paquete (el paso 6 de
  `tasks/todo/la-calidad-de-la-musica.md`): ya no hay recorte de aportantes
  —todos los temas aportan todas sus muestras—, `build_bank`, el reparto de
  sobrantes, la percusión "con lo que sobre" y `--banco-entero` se fueron, y
  "Por qué el límite sigue estando" es justo lo que se cambió: ahora cada
  muestra tiene el presupuesto de su peor paquete. El porqué que queda está
  en `workflow/decisiones/un-solo-banco-de-muestras.md` y en `Banco`
  (`tools/audio/snes_music.py`). El enlace a
  `workflow/wishlist/presupuesto-de-muestras-por-paquete.md` apunta ahora a
  `workflow/tasks/done/`.
* "Lo que sí cuesta caro es el arranque" (~línea 217): el arranque ya no sube
  el banco por el IPL; sube el driver y el directorio, y el paquete del mapa
  de arranque por el comando 3. `BOOT_CUADROS` bajó de 112 a 40 el
  2026-09-26 y ya no está dimensionado sobre el techo: ver
  `workflow/decisiones/el-arranque-esta-dimensionado-para-el-paquete-de-arranque.md`.
