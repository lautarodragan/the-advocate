---
name: "Traducir las herramientas, fase 2: el runtime y lo que cruza"
description: "Los símbolos, etiquetas y archivos del runtime al inglés, junto con lo que el conversor escribe en los .inc, las pruebas que leen símbolos por nombre, y los datos que quedaron en castellano"
type: refactor
assignee: taro
---

Última área de la fase 2 de la traducción de `tools/` al inglés. Es la más
acoplada: el conversor escribe símbolos en los `.inc`, el runtime los usa
por nombre, y las pruebas de ABL leen los símbolos del runtime por nombre.

Hornero decidió (con la autorización de taro para decidir sin esperarlo)
que acá también van los datos que quedaron en castellano por ser la
interfaz entre dos programas: la línea `; Temas:` de `musicdata.inc` y quien
la lee, las claves de `rm2k.collect_npcs`, la clave `aire_de_medida` de
`techos.toml` (a mano, sin volver a medir), los comentarios que
`patches.py` escribe en `rom/parches/auto/` (con `just parches`), y las
variables `SIN_CACHE`, `TRAMA_PATRON` y `MODO_TRANSLUCIDO`. Lo que va a la
ROM y lo que es del juego no se toca: el `.sfc` sale igual.

## Cómo se hizo

Con un mapeo viejo → nuevo de los ~4300 identificadores del ensamblador
que tenían alguna palabra castellana (runtime y `.inc` generados), armado
palabra por palabra con un diccionario y corregido a mano donde el
resultado no se leía o chocaba. El reemplazo es por token de `ca65`
—código, sin tocar strings ni `.include`— y, en comentarios, sólo lo que va
entre backticks, lleva `_` o está en mayúsculas. En Python y en las
pruebas, sólo adentro de strings y comentarios; una palabra suelta en
minúscula sólo si es la búsqueda de un símbolo (`simbolos["oro"]`,
`.palabra("vueltas")`), porque en un docstring castellano puede ser otra
cosa.

Cada commit se verificó igual:

* `SIN_CACHE=1 just cartuchos` con `rom/build/release` y `rom/build/tests`
  borrados antes: `.sfc`, `.msu`, `.pcm` y todo lo demás de `rom/build/`
  byte por byte igual al de `319a322a`, salvo `.inc`, `.sym`, `.dbg`,
  `memoria.cfg` (el nombre de un segmento) y los volcados
  `crudos/N.map_celdas.bin`, que pasaron a llamarse `N.map_cells.bin` con
  el mismo contenido;
* el `.dbg` de los dos cartuchos: los mismos símbolos, con el mismo alcance,
  valor, tipo y tamaño, cambiando sólo el nombre según el mapeo; el `.sym`,
  las mismas direcciones; los `.inc`, los mismos tokens de código bajo el
  mapeo —que es lo que prueba que el Python emite exactamente el nombre que
  el runtime espera—;
* las dos tandas en verde y pyflakes sin avisos nuevos.

## Hecho

1. Los símbolos globales, de a un subsistema: el intérprete, la pelea, el
   audio, los menús y pantallas, el mapa y lo demás, la memoria (RAM baja,
   RAM lejana, página cero, registros).
2. Los prefijos `BA_` y `TI_` quedan, porque el Python del conversor los
   conserva (`screens.BA_COMMANDS`, `screens.TI_COUNT_BUY`): un primer
   intento los había pasado a `BT_` y `SHOP_`, y un commit los devolvió.
3. Lo que el conversor escribe en los `.inc`, en los dos lados. Los nombres
   que se arman en Python (`M_%s`, `PANTALLA_%s`, `fuente_pre%d`,
   `ranura_bloque_%s`, `BA_TXT_%s` desde `rules.BATTLE_TERMS`) fueron a
   mano; los términos de la pelea pasaron al inglés en `rules.py` y quien
   los lee.
4. Las etiquetas locales y los parámetros de macro.
5. Los que se le escaparon al diccionario (`BA_MQUIEN`, `dest_tab_r`…).
6. `.bloque` → `.block`, `.cruza` → `.crossbank` y el segmento `TABLAS` →
   `TABLES`.
7. Los 82 `.s` con nombre castellano, con `git mv` y sin tocarles una línea;
   la lista de `.include` de `main.s` en el mismo orden. Después, en su
   propio commit, las citas por nombre de archivo en comentarios y
   documentación, y las de módulos de Python con nombre de antes de la fase
   1 (`eventos.py`, `titulo.py`…).
8. Los símbolos que citan AGENTS.md, README.md, tools/README.md, docs/ y
   las decisiones y divergencias de workflow/.

9. Los datos que eran interfaz: la línea `; Temas:` de musicdata.inc
   (`; Songs:`, con `no music` y `none`) y quien la lee; la línea `; --- N:
   mapa M` de mapdata.inc (`map`) y la regex de `consola.mapas_de`; las
   claves del NPC de `rm2k.collect_npcs` (`event`, `speed`, `animates`,
   `changes`, `graphics`, `layers`, `tile_pass`), que las páginas de
   events.py comparten en tres de ellas.
10. Los comentarios que `patches.py` escribe en `rom/parches/auto/`,
    regenerados con `just parches`: los 137 TOML leídos con `tomllib` dan lo
    mismo antes y después, y `just parches-check` pasa. `aire_de_medida` →
    `measuring_headroom` a mano en `techos.toml`.
11. `SIN_CACHE`, `TRAMA_PATRON`, `MODO_TRANSLUCIDO` → `NO_CACHE`,
    `DITHER_PATTERN`, `TRANSLUCENT_MODE`, con sus valores (`baked`/`dither`;
    `checkerboard`, `columns`, `rows`, `five_of_eight`, `three_of_four`).
12. Las columnas que corrieron los renombres (sólo espacios; `git diff -w`
    vacío), y las citas del runtime que apuntaban a nombres de Python de
    antes de la fase 2 o a alias castellanos.

Los protocolos (`events.toml`, `music.toml`) ya estaban en inglés: no hubo
nada que regenerar. Ningún script cambió de nombre: no hace falta
`install-scripts`.

## Lo que queda en castellano, a propósito o para después

* Las otras claves de las páginas de events.py y de `map_info` en el
  conversor (`pagina`, `codigo`, `ruta_propia`, `grafico`, `gira`,
  `frecuencia`, `ordenes`, `cambian`, `aparecen`, `afuera`, `celdas`…),
  y las de los diccionarios de la música (`nombre`, `temas`, `escrituras`,
  `largo`): son internas del Python, de las áreas anteriores.
* Las claves de los TOML de `rom/parches/auto/` y de `techos.toml` (salvo
  `measuring_headroom`), y el encabezado castellano de `techos.toml`, que
  sale en inglés la próxima vez que corra `just techos`.
* Los sufijos de los CharSet (`~trama`, `~horneado`, `~aparte`) y el nombre
  `capas` del caché en disco.
* Las tareas que dicen `SIN_CACHE=1` o nombran rutinas viejas: cuentan lo
  que se corrió ese día.
* Algunas etiquetas locales salieron palabra por palabra y se leen raro
  (`a_faces_a`, `sia_yes`); son locales y no las ve nadie de afuera.
* Los volcados `rom/build/*/crudos/N.map_celdas.bin` ahora se llaman
  `N.map_cells.bin`: el nombre sale del mismo string que la etiqueta.

## `git blame`

El commit que renombra los archivos no cambia nada: `git blame -C
--diff-algorithm=histogram` de cells.s, music.s, battle_scene.s,
interpreter.s, far_ram.s y shop.s da, línea por línea, lo mismo que el de
sus nombres viejos justo antes.

Lo que **sí** cambió es por los renombres de símbolos, y es el límite que
AGENTS.md describe para el corte de `main.s`: cada línea editada parte en
dos el trozo de líneas iguales que la rodea, y los trozos que quedan son
más cortos que el mínimo de `-C`, así que dejan de cruzar el corte y se
quedan en `391930c4` ("Partir main.s"). Medido contra `319a322a`, sobre las
líneas que la traducción no tocó: en shop.s 538 dan el mismo commit y 449
pasaron al del corte; en cells.s, 98 y 179; en far_ram.s, 550 y 4; en
interpreter.s y main.s, todas iguales. `-C3` recupera una parte (cells.s:
197 iguales, 80 al corte); `--ignore-revs-file` con estos commits, no.

