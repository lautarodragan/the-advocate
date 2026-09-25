---
name: "Inventario: imágenes a tiles en Python"
description: "Qué conversiones de imagen a tiles siguen en Python y cuáles puede hacer Voodoo"
type: refactor
---

**Contar qué conversiones de imagen a tiles siguen hechas en Python**, y para
cada una, si Voodoo la puede hacer con su contrato de hoy: PNG indexado que
entra, tiles, paleta y tilemap que salen, sin decidir colores.

Voodoo ya convierte la capa de encima de los mapas, desde el paso 8c. Lo que
se sabe que sigue en Python: la escena de la pelea arma sus tiles en
`tools/port/escena.py`. Probablemente hay más —sprites, fuente, ventana,
título, animaciones—, y no están contadas.

Es sólo medición: por cada una, qué hace, si entra en el contrato de Voodoo, si
la ROM sale byte por byte igual pasándola por Voodoo, y cuánto Python se iría.

## Lo medido

Medido el 2026-09-22 sobre `deaf3be`. **Los números son de ese día**: se
rehacen con la sonda y los dos prototipos, que quedaron en
`/extras/scratch/inventario-voodoo/` y no en el repo:

    sonda.py                envuelve cada conversión, deja que haga lo suyo, y
                            pasa sus mismas celdas por `voodoo` para comparar
                            tiles y tilemap. Se corre con los argumentos de
                            `just build release` y no escribe nada del árbol.
    prototipo-menu.diff     el menú del título por Voodoo
    prototipo-titulo.diff   la imagen del título por Voodoo
    comparar.sh             `just build release` + `just cartuchos` y `md5sum -c`
                            contra las cuatro ROMs de `deaf3be`

Las dos capas de los mapas —la de abajo con sus animaciones, la de encima— ya
pasan por Voodoo (`tiles_bin.convertir`, en `_convert_layers` y
`convert_above`), así que no están en la tabla. Todo lo demás que escribe tiles
termina en `pack_tile` de `snes_convert.py`, que tiene **once llamadores**:
ésos son las filas de la tabla, más tres codificaciones que no son tiles.

### Qué le falta a Voodoo, por clase

Lo que sale de la sonda es que las conversiones se parten en tres clases, y la
clase dice más que la fila:

* **Deduplicar con tilemap**, que es el modelo de Voodoo. Difieren en detalles
  que no cambian un pixel: Voodoo **reusa una celda espejada** con los bits de
  volteo del tilemap, y Python no lo hace nunca; y en la pantalla de ranuras y
  en la de ítems Python **comparte un tile entre dos paletas** —deduplica por
  índice, no por color—, y Voodoo a 4bpp exige la misma paleta. Una sola
  entra hoy tal cual: el menú del título.
* **Orden fijo, sin deduplicar**: poses, dígitos del cronómetro, cartel,
  animaciones de batalla, fondo de la escena, la corrida del área de texto de
  la ventana. Ahí cada celda tiene que ser su propio tile, en un lugar que la
  ROM ya sabe —una pose se sube con cuatro DMA de 128 bytes, un cuadro de
  animación son 64 tiles fijos, la escena compone los battlers sobre los 512
  tiles del fondo—. **A Voodoo le falta un modo sin deduplicar**: una celda, un
  tile, en orden de filas, sin tile 0 reservado y sin volteos. No es una
  decisión que se vea —es contabilidad, y `render` seguiría devolviendo los
  mismos índices—, así que no choca con "no decide colores". Dónde va cada
  tile en la grilla de 16 de OAM sigue siendo del llamador, que es lo que dice
  el README de Voodoo en "What is deliberately not here".
* **No son tiles**: los battlers, la fuente y su prerender. Ésos no van a
  Voodoo por ningún modo.

Y uno aparte, sólo de los sprites: **a 4bpp Voodoo rechaza las paletas 8 a
15**, porque un tilemap tiene tres bits de paleta. Los sprites viven justo ahí
—CGRAM 128 a 255—, así que un PNG de sprite con sus entradas de CGRAM de verdad
no entra. La sonda los pasó con índices de 0 a 15, que es lo que `pack_tile`
recibe, pero eso rompe "los índices son entradas de CGRAM". Para los objetos
haría falta que Voodoo sepa que la paleta de un objeto va en OAM, no en un
tilemap.

### La tabla

Ordenada por lo que conviene hacer primero. "Celdas → tiles" es lo que dio la
sonda: cuántas celdas le pasó Python a `pack_tile` y cuántos tiles saca Voodoo
de las mismas. "Python que se va" son líneas de código sin comentarios, blancos
ni docstrings, contadas con `ast`: **neto** donde hubo prototipo, y donde no lo
hubo, las del corte que desaparecería, sabiendo que armar el PNG se come parte.

| # | Conversión | Dónde | Clase | ¿Entra hoy? | Lo que le falta | ROM por Voodoo | Python que se va |
|---|---|---|---|---|---|---|---|
| 1 | Menú del título: las dos variantes con el cursor, un banco | `titulo.menu` | dedup | **Sí** | nada | **Igual** en las cuatro ROMs (prototipo) | −7 neto (18 que entran, 25 que salen) |
| 2 | Imagen del título, 8bpp | `titulo.convertir` | dedup | **Sí**, con `--no-blank-tile` | que `tiles_bin.convertir` pase ese flag | **Distinta**: 496 → 486 tiles, 22 celdas volteadas; `abl` y `juego` cambian. Las 4 goldens de título, **pixel por pixel iguales** | +1 neto (12 y 11); ahorra 640 bytes de ROM |
| 3 | Ventana de mensajes: el marco | `convert_ventana` | dedup | Sí, el marco | nada para el marco | Distinta: la sonda, con la ventana entera, da 11 entradas volteadas | parte de las 29 del corte |
| 4 | Ventana de mensajes: los 240 tiles del área de texto | `convert_ventana` | fijo | No | modo sin deduplicar: 240 celdas dan 3 tiles | — | parte de las 29 del corte |
| 5 | Pantalla de ranuras y menú de pausa, con las caras | `titulo.pantalla_ranuras` + `_bloque_de_celdas` | dedup | Casi | compartir tiles entre paletas; 244 celdas vacías que Python escribe con su paleta Voodoo las escribe 0; los bloques de muchas capas hay que apilarlos en una imagen y volver a cortar el tilemap | Distinta: 344 → 341 tiles (3 volteos le ganan a lo que pierde por paletas), 404 de 3890 entradas cambian | hasta 24 (`_bloque_de_celdas`), compartidas con la 6 |
| 6 | Pantalla de ítems: la fuente en blanco y en gris | `titulo.pantalla_items` + `_bloque_de_celdas` | dedup | Casi | compartir tiles entre paletas: sin eso son 307 → 315 tiles; 10 vacías con paleta | Distinta | ídem 5 |
| 7 | Poses de los CharSets, VRAM y banco del cartucho | `pose_tiles` (`build_characters`, `banco_de_poses`) | fijo | No | modo sin deduplicar **y** paletas de objeto (8 a 15) | — (con el modo, 32.928 celdas; Voodoo hoy las junta en 17.209 tiles con 995 volteos) | hasta 20; el mapeo de colores se queda |
| 8 | Dígitos del cronómetro, 11 glifos de 8x16 | `digitos_del_timer` | fijo | No | modo sin deduplicar, paletas de objeto | — (638 → 522, 87 volteos) | hasta 14 |
| 9 | Cartel del `ShowPicture` | `imagen.celdas` + `cartel_de_imagen` | fijo | No | modo sin deduplicar, paletas de objeto | — (96 → 89) | hasta 19 + 3 |
| 10 | Cuadros de las animaciones de batalla | `animacion.celdas` + `animaciones_asm` | fijo | No | modo sin deduplicar, paletas de objeto | — (15.744 → 1.252 en 246 cuadros) | hasta 13 + 4 |
| 11 | Fondo de la escena de pelea, 512 tiles de 8bpp | `escena.tiles` | fijo | No | modo sin deduplicar | — (1.536 → 1.515 en 3 fondos) | hasta 7 + 4 |
| 12 | Gotas de lluvia, 6 tiles | `gotas_de_lluvia` | fijo | Por casualidad | no hay imagen: los pixeles salen de `eventos.lluvia_pixeles` | Los 22 grupos dan identidad y los mismos bytes, pero porque las 6 celdas son distintas, no por contrato | ~0: habría que fabricar un PNG |
| 13 | Battlers de la escena | `escena.battler_bytes` | no son tiles | No va | máscara y 4 planos por fila, al revés, para que la ROM los superponga | — | 0 |
| 14 | La fuente: 1bpp por fila y las tablas por fase | `fuente_bytes`, `fuente_prerender` | no son tiles | No va | — | — | 0 |

`pack_tile` (9 líneas) se va recién cuando se vaya su último llamador, o sea
con el modo sin deduplicar y las filas 4 y 7 a 11 adentro.

Qué se corrió para cada columna:

* **Filas 1 y 2**: el prototipo aplicado en el árbol, `just build release` y `just
  cartuchos` —los cuatro rearmados, `armado` en los tres de prueba—, y
  `md5sum` contra las cuatro ROMs de `deaf3be`: `abl`, `pruebas`, `chico` y
  `juego`. De ésas, las que tienen título son `abl` y `juego`. Para la 2,
  además, `pytest pruebas/rpgmaker/test_tanda_pantallas.py -k titulo`: 4
  verdes contra las goldens, que se comparan exactas.
* **Las demás**: sólo la sonda, sobre los argumentos de `just build release`. Donde la
  sonda ya da tiles o tilemap distintos, la ROM sale distinta sin armarla;
  donde falta un modo, no hay qué armar.

### Dos cosas que salieron de paso

* **Que el menú salga igual es un hecho de los datos, no del contrato.** Hoy
  ninguna celda del menú es espejo de otra anterior; si un texto nuevo tuviera
  una, Voodoo la voltearía y la ROM cambiaría, con los mismos pixeles.
* **`titulo.render` y `titulo.informe` no tienen llamadores**: `grep` en
  `tools/` y `pruebas/` no encuentra ninguno. Son de la época de la referencia;
  por eso el prototipo de la fila 2 no tuvo que enseñarle volteos a `render`.

### Por dónde empezar

1. **El menú del título**: entra tal cual, la ROM sale igual y se va código.
2. **La imagen del título**: entra con un flag que `tiles_bin` ya casi tiene,
   la pantalla es la misma y ahorra ROM. Cambia la ROM, así que va con las
   goldens del título a la vista.
3. **El modo sin deduplicar en Voodoo**, que es el que destraba la mayoría: 4,
   7 a 11 y al final `pack_tile`. Es trabajo en `tools/voodoo/`, en inglés, y
   para los sprites va junto con las paletas de objeto.
4. **Compartir tiles entre paletas**, para ranuras e ítems. Es lo que menos
   rinde: la cuenta de tiles casi no se mueve y el apilado de bloques en una
   imagen es código nuevo del lado del llamador.
