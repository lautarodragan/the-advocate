---
name: "El 108 con poses compartidas"
description: "Los quietos que ninguna cámara muestra juntos se turnan una ranura de VRAM, sólo en el mapa que no entra sin eso; Distant Paradise (108) entra en release y la demo termina en su llegada"
type: feature
assignee: taro
---

De taro, el 2026-10-01, entre las opciones de
`testing/mundo-7-camino-a-paradise.md` (Puma): la A. El 108 pide 42 ranuras
de pose quieta (15 personajes mirando a 3 o 4 lados) y la VRAM da 24, pero en
pantalla a la vez hay entre 12 y 19. Extiende la decisión de las poses en
caliente (`decisiones/las-poses-se-suben-en-caliente.md`, que ahora lo dice).

Base: `387b1e49`, `abl.sfc` `58fce320…`; mergeado con el `main` de Pirincho
(`4d427f34`).

# Quién se turna con quién

Lo decide `wally` (`plan_sharing` en `map.rs`), con el coloreo en
`rm2k-snes-map-sprites` (`share.rs`). Se turnan los quietos que:

* nadie mueve: ni ruta propia ni `SetMoveRoute` (`movable`), ni animación
  quieta, ni `SetEventLocation`/`SwapEventLocations` de una página del mapa
  o de un evento común —uno de un evento común que mueve "este evento"
  apaga los turnos del mapa entero, porque puede ser cualquiera—;
* no están horneados;
* dibujan **un solo gráfico** en todas sus páginas (las que no dibujan nada
  no cuentan: el que aparece y desaparece se turna igual).

El que muestra una pose que ya tiene un quieto que no se turna usa esa
ranura, como siempre. Los demás se colorean: dos van juntos si muestran la
misma pose o si nunca están los dos en pantalla. "En pantalla" es lo que
`build_oam` no descarta —la caja de 32x32 toca la pantalla de 256x224—, así
que para cualquier cámara dos están a la vez sólo si |dx| < 288 px y
|dy| < 256 px: menos de 18 celdas en x y de 16 en y. Es exactamente el
"margen 1" de Puma (16x14 celdas más una alrededor), y no le agregué otro
margen: la ROM decide con la misma comparación, así que es exacto. Una
ranura donde todos muestran la misma pose queda como una quieta de siempre;
sólo las que tienen más de una van a la ROM.

**Sólo se activa en un mapa que no entra sin eso**: `wally` convierte como
siempre, mira si algún reparto de VRAM entra —los repartos le llegan en el
pedido, `layouts`, de `vram.LAYOUTS`— y sólo si no, vuelve a convertir con
turnos. Los otros mapas salen byte por byte iguales.

El 108 queda en 22 ranuras, 376 tiles de sprite, y entra en "+ambos" (384).
13 ranuras se las turnan 74 quietos, con 32 poses. El cronómetro no va en el
108 —no es un mapa del cronómetro—; si fuera, sus glifos empiezan en la
fila siguiente y serían 411 tiles: no entraría.

# Qué hace el runtime

`tools/runtime/shared_poses.s`, en FAR. Tablas de `share_table`
(`rm2k-snes-mapdata`): `share_maps`, una palabra por mapa, y `share_data`,
con un registro por mapa que se turna (ranuras, evento → ranura y pose,
pose → lugar en `npc_poses`). RAM lejana: `SHARE_N` y `SHARE_OWNER` en
$2590-$259F, 15 ranuras como mucho (`SHARE_MAX`, que el `.inc` asserta).

* `place_npc`: si `SHARE_N` no es cero, `share_want` mira la ranura de la
  fila; si tiene otra pose, encola la suya con `vram_queue` y **la fila no
  se dibuja ese cuadro**, sino el siguiente, con la pose arriba. Si la cola
  está llena, pregunta de nuevo al cuadro siguiente. El que mira al héroe
  está en la ranura del giro y no se mira.
* `load_sprite` llama a `share_load`: cuántas ranuras tiene el mapa y
  "nadie sabe qué tienen". Cubre entrar al mapa y volver de la pelea.
* `build_oam_settled`, en el banco 0: el primer OAM del mapa —entrar, volver
  de la pelea, salto dentro del mismo mapa (`FADE_SAME`), cargar desde el
  título o al encender— se arma con la pantalla apagada, sube la cola y lo
  rearma hasta que no falte nadie. En un mapa sin turnos es un solo
  `build_oam`, como antes.
* `share_boot` pone `SHARE_N` en cero al encender: la RAM lejana arranca con
  basura.

Lo que **no** cubre, y está dicho en el encabezado de `shared_poses.s`: si
dos vblanks seguidos no tienen lugar para poses —una línea de la ventana
subiendo con la cámara corriéndose—, la fila se dibuja antes de que su pose
suba, y ese cuadro muestra la pose anterior. La del héroe y las de los que
caminan tienen el mismo límite.

# El 108 en release, y el fin de la demo

`below = 109`. Del otro lado del 108 está otro capítulo: la escena de la
llegada (108 ev5) salta enseguida al Consejo (110), que encadena el recuerdo
de la montaña (175), la casa de Talan (114), el 108 de noche con la chica
que llora, el mirador (109) y el sueño (122). Nada de eso es barato, así que
el corte es el primero: **el fork del 108 cambia el `Teleport` al Consejo
por el cartel del fin** ("END OF THE DEMO / The Council of Paradise is not
/ in the cartridge yet. / Thanks for playing!") y la vuelta al título. El
fork del 107 se fue: el túnel vuelve a saltar al 108, con su pregunta de
guardar. Lo que faltaría para el próximo corte natural —el salto al sueño
en el mirador (109 ev6)—: el 110, el 175, el 114, el 109 y el 122.

Las 26 páginas del 108 que saltan a 109, 110, 112 a 118, 120, 126, 127 y
150 no compilan: las casas no se abren, como las puertas del mundo cuyo
destino no está. El pueblo, al llegar, está casi vacío: los vecinos tienen
páginas de tandas posteriores (switches 350, 376, 396, 427…).

# Pruebas

En `rom/pruebas/abl/test_paradise.py`:

* `test_recien_llegado[paradise-108-llegada]`: la llegada en (19,19) con la
  escena vista (333), golden y celdas contra `fill_window`, como las otras.
* `test_los_quietos_del_108_se_turnan`: el pueblo lleno (333, 396, 386,
  388), caminando por el camino de la plaza hacia abajo y de vuelta, con
  golden en cada parada. En cada una, cada quieto que se turna y está en
  pantalla tiene que tener en la VRAM los bytes de su pose en el cartucho,
  leídos de las tablas como los lee `share_want`; y alguna ranura tiene que
  haber mostrado dos poses en el camino (la 6: el 79 y el 75).
* `test_el_108_se_turna_al_saltar_dentro_del_mapa_y_al_cargar`: un salto
  `FADE_SAME` de (20,19) a (20,45), y guardar por el menú y cargar ahí.

Y `rpgmaker/test_cores.py::test_los_quietos_que_se_turnan_una_ranura`: la
caminata en snes9x y en bsnes.

**El rojo**: sin el arreglo, el 108 no convierte (con las herramientas
globales: "this map can't carry a message window: it spends 462 background
tiles, 696 sprite tiles"). Con el arreglo y `share_want` devolviendo siempre
"como está", las dos pruebas de los turnos fallan: dos quietos dibujados con
la pose de otro. Además, antes de congelar las goldens comparé la silueta de
cada quieto que se turna y está entero en pantalla contra su cuadro del
CharSet original: coinciden todos.

`test_recorrido_paradise_golden.py` sigue ahora del túnel al 108: contesta
que no a la pregunta de guardar y el cartel sale en el 108. Sus fotos siguen
sin bendecir.

En Rust: `wally` (`tests/shared_slots.rs`: se turnan sólo si no entra, y no
el que algo cambia de lugar), `rm2k-snes-map-sprites` (el alcance y el
coloreo) y `rm2k-snes-mapdata` (`share_table`). Los hashes de
`mapdata/tests/python.rs` se regeneraron a propósito, sobre el árbol
mergeado con Pirincho.

# Lo que no cubre `just pruebas`

* **Volver de una pelea en el 108**: `back_from_battle` sube el banco
  (`share_load`) y `battle_fade_to_map` pasa por `build_oam_settled`, pero el
  108 no tiene encuentros ni peleas de evento, así que ninguna prueba lo
  ejecuta.
* El límite de los dos vblanks sin lugar, de arriba.

# Espacio

`just espacio release`, sobre el árbol mergeado con Pirincho:

                   main (Pirincho)       con el 108
    bancos         —                     64 de 128, 44 libres
    banco 0        1.220 B               1.165 B
    banco 1        —                     3.204 B
    BSS, ZEROPAGE  —                     128 B, 4 B
    textos         —                     112.717 B

El código de los turnos en el banco 0 son unos 55 B (el gancho de
`place_npc`, `build_oam_settled` y dos `jsl`); lo demás va en FAR.

# Verificación

Sobre el árbol mergeado (`abl.sfc` `e1e0d591…`): `NO_CACHE=1 just
cartuchos` y `just cartuchos` con caché dan las mismas huellas; `just
pruebas` 966 en verde (961 + las cinco nuevas), con `test_musica_techos.py`
incluido; `just -f tools/justfile test` 39; `cargo test` de `wally`,
`rm2k-snes-map-sprites` y `rm2k-snes-mapdata`. Antes de sumar el 108 —con
los turnos ya en la ROM y el 108 afuera— `NO_CACHE=1 just cartuchos`
cambiaba sólo las ROMs y el `mapdata.inc`, y `just pruebas` daba 961 sin
mover ninguna golden.

# Goldens

Cinco nuevas, en su commit, sin tocar ninguna existente:
`paradise-108-llegada` y `paradise-108-turnos-{arriba,al-medio,abajo,de-vuelta}`.
Lado a lado en `/shared/capturas/2026-10-01-el-108/`, con un `LEEME.txt`.
**El merge espera el visto bueno de taro.**

# Al mergear

Instalar `wally`, `mapdata` y `cartridge` (`just -f tools/justfile install
wally mapdata cartridge`): `wally` lleva `rm2k-snes-map-sprites` adentro, y
`cartridge` arma con el runtime. Python: cambiaron `map_convert.py` y
`snes_convert.py`, sin archivos nuevos ni renombrados.

# Qué tiene que probar taro

* Del túnel (107) a Paradise: la pregunta de guardar, la escena de la
  llegada y el cartel del fin.
* Caminar el 108 con gente: jugando, el pueblo está casi vacío hasta
  tandas de la historia que no entran; hay que prender 396, 386 y 388 en un
  emulador (o pedirme un caso). Que cada vecino tenga su cara y mire para su
  lado al entrar en pantalla, sobre todo en los bordes.
