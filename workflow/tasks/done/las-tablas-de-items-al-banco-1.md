---
name: "Las tablas de ítems y temas, fuera del banco 0"
description: "El banco 0 de release quedó en 95 B: las tablas que crecen con cada mapa nuevo (ítems, temas) se mudan, como dice el plan del mundo"
type: refactor
assignee: taro
---

Después de Yun, Drust y Paradise (2026-10-01), el banco 0 de `release`
quedó en 95 B libres. Lo que crece ahí con cada mapa son las tablas de ítems
y de temas; el plan del mundo (`todo/el-mundo-y-lo-que-sigue.md`, hito 5)
ya decía mudar las de ítems al banco 1. Zorro contó 19 lecturas en el
runtime.

## Lo medido antes (2026-10-01, Pirincho, sobre `387b1e49`)

`just espacio`: banco 0 de `release` **95 B**, de `test-special` 1.003 B, de
`test-encounter-every-step` 1.047 B. `TABLES` en `release` son 1.441 B, y en
`test-special` 551 B. La diferencia, etiqueta por etiqueta (con el `.dbg`:
cada etiqueta del segmento hasta la siguiente):

    item_id          328 vs  44   +284   (.word por ítem)
    item_price       328 vs  44   +284   (.word por ítem)
    item_type        164 vs  22   +142
    item_use         164 vs  22   +142
    slot_face_block   29 vs  15    +14
    slot_block_lo/hi/bk  42 vs 34  +8 cada una

Lo demás no cambia entre cartuchos. Así que lo que crece con el contenido son
**las cuatro tablas de ítems, 6 B por ítem**: `release` lleva 164 ítems y
`test-special` 22. Las de los temas no están en `TABLES`: de la música sólo
queda en el banco 0 el prólogo del DSP (`dsp_init_reg`/`dsp_init_val`), fijo.
Las `slot_block_*` crecen con las caras y las ventanas del menú, no con los
mapas.

Las lecturas, con `grep` de cada nombre en `tools/runtime/`: `item_id` 11
(cuatro ya con `f:`, tres en la tienda con Y), `item_use` 5, `item_type` 1,
`item_price` 1 (con Y). Ninguna prueba ni script lee estas tablas por nombre.

## Lo hecho

Seis commits, uno por tabla (las `slot_block_lo/hi/bk` juntas: son una sola
tabla de punteros partida en tres). Todas van a `RODATA` con su `.block`, y
cada lectura pasa a `f:`:

    item_id          11 lecturas: 7 cambiadas (4 ya tenían f:); las 3 de la
                     tienda indexaban con Y y ahora indexan con X
    item_use          5
    item_type         1  (un cmp)
    item_price        1  (ti_price, que indexaba con Y)
    slot_block_*      6  (slot_block_upload y slot_rect_upload)
    slot_face_block   2  (slots.s y menu.s)

En la tienda, `ti_item`, `ti_can`, la del listado y `ti_price` devuelven X = k
como antes; ya no dejan 2k en Y, y ningún llamador la leía (los procs que las
llaman terminan en un `jmp` al bucle). Cada commit con `just pruebas` en 961 y
las goldens sin moverse, y con los hashes de `tests/python.rs` de
`rm2k-snes-mapdata` regenerados, porque el `.inc` cambia a propósito.

`just espacio`, antes y después:

    banco 0   release 95 B -> 1.220 B; test-special 1.003 -> 1.238;
              test-encounter-every-step 1.047 -> 1.234
    banco 1   3.423 B -> 3.405 B en los tres (los f: de la tienda y las
              ranuras caen ahí)

`TABLES` pesa ahora **lo mismo en los tres cartuchos, 302 B**: lo que queda no
depende de mapas, ítems ni actores. **Un mapa nuevo ya no cuesta banco 0**:
sólo lo cuesta el código nuevo del runtime. Lo que todavía difiere entre
cartuchos en el banco 0 son 18 B de `CODE`, por los flags de `test-special`,
no por el contenido.

`NO_CACHE=1 just cartuchos` sale con el mismo `abl.sfc` que el armado con
caché (`1b606408…`); sólo cambian `.o` y `.dbg`, por las mtimes.
`just -f tools/justfile test`: 39. `cargo test -p rm2k-snes-mapdata`: en verde.
`test_musica_techos.py` y `test_cores.py` pasan dentro de `just pruebas`.

**Al mergear**: `just -f tools/justfile install mapdata`. El runtime cambió
(`tools/runtime/`), pero el ensamblador global arma con el del checkout
principal, así que con el merge alcanza.
