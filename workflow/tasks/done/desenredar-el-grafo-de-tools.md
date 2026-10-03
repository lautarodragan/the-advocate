---
name: "Desenredar el grafo de tools/"
description: "El paso 1 del plan del research: romper los ciclos y las violaciones de capa de tools/ moviendo funciones, sin cambiar lógica y con las ROMs byte por byte iguales"
type: refactor
assignee: taro
---

Paso 1 del plan de `docs/research/el-mapa-de-las-herramientas-de-python.md`
(§4), aprobado por taro el 2026-09-28. taro autorizó a Hornero a avanzar con
los pasos mecánicos sin esperar su feedback el 2026-09-29.

Entra: los ítems 1.1, 1.2, 1.3, 1.5 y 1.6 del research, y el 1.7 (partir
`titulo.py`) si todo lo anterior quedó mergeado y en verde.

No entra: el 1.4 (`cartuchos` deja de importar `port/` y `audio/`), porque
qué hacer con `cartuchos.py` es una pregunta abierta de taro (ver
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`).

## Lo hecho (Lapacho)

Un commit por ítem, cada uno mudanza sin lógica nueva:

- **1.1** `GAME_DIR`, `RTP_DIR` y `find_resource` a `rpgmaker/recursos.py`.
  `audio/` deja de importar `render/`.
- **1.2** `TILE`, `caja_de_terreno`, `caja_de_comun`, `SPRITE_*` y
  `OFFSET_*` a `rpgmaker/rm2k.py`. `render/charset.py` quedó vacío y se
  borró.
- **1.3** `lcf`↔`fork`: la parte de imagen de `fork` sube a
  `render/chipset_del_fork.py`, la opción que el research prefería. La otra
  —que `fork` reciba el `Map`— cambiaba una firma; ésta es sólo mudanza.
  `rpgmaker/` ya no carga PIL.
- **1.5** Las siete movidas, a cuatro módulos nuevos de `port/` que no
  importan nada del port (salvo `paleta`, que importa `constantes`):
  `reglas`, `constantes`, `color` y `paleta`. Importar `eventos` ya no carga
  PIL, numpy ni `render_map` (medido con `sys.modules`).
- **1.6** `pack_tile`, `cgram_word` y `entry` a `port/formato_snes.py`.
- **1.7, la mitad**: `titulo.py` se corta en `titulo.py` (la pantalla de
  título) y `menus.py` (ranuras, pausa, ítems, elegir a quién). Ninguna
  mitad usa nada de la otra, medido en el AST.
- Prosa: `tools/README.md`, las capas y los ciclos.

Verificado en cada ítem: `SIN_CACHE=1 just cartuchos` da iguales los
archivos de `rom/build/release/` y `rom/build/tests/special/` que se
comparan —el `.sfc`, el `.msu`, las pistas, los `.inc`, el `.sym`, el
`conversor.log`, y los `.dbg` sin los `mtime` de los fuentes—. No se
comparan los `.o`, que llevan adentro los `mtime` de los `.inc` regenerados,
ni `sello.txt`, que lleva la huella de los `.py` y cambia a propósito.
`just pruebas` y `just -f tools/justfile pruebas` en verde en cada commit
desde el 1.3; en el 1.2, sólo la ROM.

El script del apéndice D, sobre el árbol final:

    ## VIOLACIONES DE CAPA
    ensamblado.cartuchos:31 -> audio.muestras_brr [import]
    ensamblado.cartuchos:33 -> port.tiles_bin [import]
    ensamblado.cartuchos:34 -> port.comprimir [import]
    ensamblado.cartuchos:148 -> rpgmaker.lcf [lazy]
    ensamblado.cartuchos:260 -> audio.snes_music [lazy]
    ensamblado.cartuchos:482 -> audio.msu [lazy]
    ensamblado.cartuchos:416 -> port.snes_convert [ruta]

    ## CICLOS
    import + lazy + ruta SCC: ensamblado.cartuchos, port.parches, port.snes_convert

Sin la clase `ruta` no queda ningún ciclo, y todas las violaciones son de
`cartuchos`, que es el 1.4.

### La clave del caché

Entró **un** archivo en la lista de `_version_capas`: `rpgmaker/recursos.py`,
porque `render_map` encuentra el ChipSet con `find_resource`, y ese código
entraba en la clave por vivir en `render_map.py`. Los demás módulos nuevos
no entran: o salen de archivos que no estaban en la lista (`fork`,
`eventos`, `titulo`, `pantallas`, `batalla`), o lo que se cachea no los usa
(`formato_snes`: medido recorriendo en el AST las llamadas de
`capas_convertidas`). La huella de `cartuchos` los cubre sola, con su glob
de `tools/*/*.py`.

### Lo que no entró, y lo que quedó para mirar

- **El 1.4**, por lo que dice arriba.
- **La otra mitad del 1.7: la fuente de los menús aparte.** No es mudanza.
  La fuente de la pantalla de ítems (`pantalla_items`, `texto_de_item`,
  `ITEM_BLANCO`…`ITEM_ROJO`, `ITEM_PRIMER_CARACTER`, `ITEMS_TILES_MAX`) y los
  marcos (`marcos`, `ITEM_MARCO_CGRAM`) están entreverados con la geometría
  de esa pantalla en los mismos bloques de comentario, se llaman `ITEM_*`, y
  `_bloque_de_celdas` lo usan también las ranuras. Separarlos pide decidir
  dónde va cada constante y probablemente cómo se llama: es criterio.
- **`BA_TERMINOS` se fue a `reglas` con `terminos_batalla`**, porque la
  función la recorre. Pero es también el orden en que la ROM lee los
  términos (`ba_vic_mensaje`), así que dónde vive es discutible.
- **`pack_tiles`**, la de numpy, sigue en `snes_convert`: no cerraba ningún
  ciclo. Es candidata al próximo corte de `snes_convert`.
- **Dos comentarios nombran lo viejo** y no se tocaron: el que
  `snes_convert` escribe en `mapdata.inc` ("lo que depende del actor' en
  titulo.py"), porque cambiarlo cambia el `.inc` que se comparaba byte por
  byte, y el de `rom/src/registros.s:39` (`eventos.tenir`, que ahora es
  `color.tenir`), porque `rom/src/` no se tocaba. También nombran lo viejo
  dos tareas de `wishlist/`: `test-declarative-script` e
  `inventario-de-imagenes-en-python`.
- **Tres imports sin usar que ya estaban antes**: `ELEGIR_CURSOR` en
  `pantallas`, `collections` en `imagen` y `load_image` en `snes_convert`.
