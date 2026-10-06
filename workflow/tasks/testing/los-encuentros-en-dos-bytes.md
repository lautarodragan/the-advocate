---
name: "Los encuentros con índices de dos bytes"
description: "Las tablas de encuentros usan un byte por índice y Vampires Dawn tiene 779 tropas y 136 zonas: que entren, en vez de cortar el armado"
type: feature
agents: [Tijereta]
assignee: taro
---

Lo encontró Cardón el 2026-10-06 midiendo Vampires Dawn: con los mapas que
no entraban afuera, `rm2k-snes-battle` falla porque los encuentros no
entran en tablas de un byte (121 registros, 136 zonas, 779 tropas).

taro, el 2026-10-06: "Dale!", con Sonnet.

## Hecho, el 2026-10-06 (Tijereta)

`enc_map` (con `$FFFF` por "sin encuentros"), `enc_zone_init` y
`enc_troop_init` son tablas de palabras; `ENC_REG` es una palabra, en el
noveno byte que ya estaba libre de `$3900`: **no hay RAM nueva**, no se tocó
ningún opcode. Siguen en byte `enc_zone_n` y `enc_troop_n`, los conteos
*dentro* de un registro o una zona, y el conversor corta si alguno pasa de
255. Topes: 8191 registros (`record * 8` en un offset de 16 bits) y 32767
tropas. Ancho fijo y no variable por juego: cuesta unos cientos de bytes.

El tope de un byte era de cuando eran 53 registros, 56 zonas y 322 tropas
(lo dice su comentario): no había decisión que respetar. De las tres sólo
las tropas pasaban de 255 en Vampires Dawn; las otras dos entraban, pero
las pasé igual como pidió el encargo.

Otra tabla con el mismo tope no apareció: `BA_TROOP` y `enc_troop` ya eran
palabras. **Sí apareció un consumidor escondido**: `scene.rs` del conversor
leía el `per_map` del JSON y comparaba con `0xFF`; con `$FFFF` todos los
mapas parecían tener encuentros y el cartucho cargaba fondos de más
(`test_escena_una_pelea_cuyo_fondo_no_esta_usa_el_reemplazo` lo mostró en
rojo). Ahora compara con `NO_RECORD`, escrita dos veces porque `convert`
no enlaza `battle`.

### Medido en Vampires Dawn
Con el clon de Cardón (mapas excluidos) la pelea **pasa**: 102 mapas con
encuentros, 117 zonas y 646 troops (con 23 mapas más afuera). Lo que corta
después, y es del tipo "no entra" que ya degradamos y no toqué: primero los
mapas con más de 104 NPCs en OAM (6, 130, 164, 201, 205, 208, 210, 216, 218,
239, 240, 323, 332, 333, 341, 347, 379, 381, 383, 390, 393, 409, 412, 429,
que excluí en mi clon), y con ésos afuera, el mapa 1: "a stream of anim_tiles
is 27264 bytes and 8192 fit in WRAM". Lo que viene después de eso no lo vi.

### Verificado
- Prueba nueva del crate en rojo antes (300 mapas, `the encounters don't fit
  in one-byte tables`) y en verde después; los dos hashes del texto de las
  tablas cambiaron a propósito, dicho en la prueba. Tests de `battle` y de
  `convert` en verde.
- Tanda de ABL con mis herramientas: 1150 verdes, incluida
  `test-encounter-every-step` (las mismas tropas). Ninguna golden cambia.
  `abl.sfc` pasó de `8bb36b99…` a `aaae70c2…`: las tablas son más anchas y
  el runtime las lee distinto, como se esperaba. La prueba de ABL que leía
  `ENC_REG` de un byte la pasé a palabra (rama `tijereta-encuentros-dos-bytes`
  del clon `/extras/scratch/tijereta/abl2`).
- No cubierto: la pelea con más de 255 troops **corriendo en la ROM**: ninguna
  prueba ejecuta un encuentro con el índice de tropa pasado de 255 (el juego
  de pruebas no tiene tantos). El camino nuevo, `enc_troop_init` como palabra,
  sí lo ejecutan los encuentros de ABL con índices chicos.

Al mergear, reinstalar: `battle cartridge convert`.
