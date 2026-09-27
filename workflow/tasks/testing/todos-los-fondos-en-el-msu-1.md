---
name: "Todos los fondos de batalla en el MSU-1"
description: "Cada fondo del juego en el .msu en alta calidad; en la ROM sólo los que entran, y los demás comparten uno de reemplazo en baja calidad"
type: feature
---

De taro, el 2026-09-27, al ver que las peleas del mundo (66) salían en negro
porque el cartucho no lleva sus cinco terrenos:

- **Todos los fondos de batalla del juego van al `.msu`**, en alta calidad,
  estén o no en los mapas del cartucho. Con eso la parte del `.msu` dedicada
  a fondos queda fija: se sabe qué sector exacto ocupa, y no se mueve cuando
  entra un mapa.
- **En la ROM, cada pelea cuyo fondo no entra usa un mismo fondo de
  reemplazo**, uno de los que ya hay, en baja calidad. No negro: negro
  confunde.
- **Con MSU-1, cada pelea muestra su fondo correcto**, aunque no esté en la
  ROM.

Ver `docs/port/msu-datos.md` y `testing/msu-1-los-fondos-por-el-puerto-de-datos.md`
para cómo se leen hoy. Hay que medir cuánto pesan todos los fondos del juego
en el `.msu` y decidir el orden (por id del fondo, así el sector de cada uno
no depende de qué mapas entran).

# De dónde saca RM2k el fondo de una pelea

De easyrpg-player, no de memoria: `CommandEnemyEncounter` (el parámetro
`[2]`: 0 "del lugar", 1 el que nombra el comando, 2 un terreno, de RM2k3),
`Game_Map::SetupBattle` (sube por el árbol mientras el nodo diga "el del
padre"; sólo el tipo 2 trae nombre) y `Spriteset_Battle` (sin nombre, el
fondo del terreno de la celda del héroe). O sea que **llegar a la raíz sin un
tipo 2 también es "el del terreno"**, y el port lo trataba como "sin fondo".

Medido sobre el juego el 2026-09-27 (script descartable):

* `EnemyEncounter`: 51; 49 nombran fondo (14 nombres distintos) y 2 piden el
  del lugar, en el 105 y en el 141. **Ningún `ChangeBattleBG`** en todo el
  juego (mapas, comunes, tropas).
* Árbol: 58 nodos con fondo propio (24 nombres), 24 con el del terreno, el
  resto heredan.
* Terrenos: 30, 21 con fondo (19 nombres).
* **La unión son 45 fondos, y existen todos**: 32 en el juego y 13 en el RTP
  (`Cave1`, `Castle`, `Swamp` y los de los terrenos genéricos). Hasta hoy
  `escena._abrir` no buscaba en el RTP; ahora sí, sólo para los fondos.
* Los terrenos del mundo, por celda del 66: forest5 (16), river5 (21), mroad2
  (15), plains5 (20), desert1 (19), plains6 (25) y Galaxy (1). No son los
  cinco que decía el plan: forest6 es el 17, que el 66 no pisa. En la llegada
  (71, 29) es plains6. El 158 y el 210 también son de terreno.

# Qué se hizo

* **El número de un fondo** es su lugar en la lista de los 45 ordenada por
  nombre sin mayúsculas (`escena.fondos_del_juego`). No depende del
  cartucho. Un byte alcanza con margen: `$FE` es "del lugar" y `$FF` el liso.
* **El `.msu`, versión 2**: la cabecera y el índice rellenos hasta `$10000`,
  y desde ahí el fondo k en `$10000 + k × $8200` (tiles; colores `$8000` más
  adelante; el resto relleno hasta el sector de 512). Los efectos detrás del
  último lugar. Documentado en `docs/port/msu-datos.md`.
* **En la ROM**: `escena_tropa_fondo` y `escena_mapa_fondo` llevan números
  del juego; `fondo_terreno` (por terreno) y `fondo_respaldo` (por número,
  cuál de la ROM se dibuja sin MSU-1). `esc_terreno` lee el terreno bajo el
  héroe como `op_terrain`. `ESC_FONDO` es el número del juego y el nuevo
  `ESC_RESPALDO` ($7E664B, en el tramo de la escena) el de la ROM.
* **El reemplazo es `ABLBackdropSJ08`**, el de los Rat Tracks: una cueva de
  roca gris, el único de los tres que no dice dónde se está (el del droide es
  una nave con la Tierra en un monitor; el de los Back Alleys, una calle con
  carteles). Ya lo lleva `release`, así que no cuesta nada.

# Las cifras

* `.msu` de `release`: 3.347.116 B, con los 45 fondos y 212 efectos. La
  región de fondos son 45 × 33.280 = 1.497.600 B desde `$10000`. Antes, con 3
  fondos, los fondos eran unos 99 KB.
* Cada fondo que la ROM lleva son 16.416 B (tiles y colores) más 8 de
  punteros.
* **Tres en la ROM (lo que queda) contra sólo el reemplazo**, medido
  armando `release` de las dos maneras: 75,6 % contra 74,8 %, o sea 32.848 B
  (dos respaldos). Banco 0, BSS y ZEROPAGE, iguales en los dos.
* **Recomendación: que sigan los tres.** El criterio de taro es que sin
  MSU-1 se vea algo razonable: con los tres, las peleas que ya andaban —el
  droide, Sector 27 y 30, los Rat Tracks— siguen con su fondo; con sólo el
  reemplazo, el droide pelea en una cueva. 32 KB son un banco, y el día que
  el espacio apriete es una línea: `escena.FONDOS = (REEMPLAZO,)`.

# Lo que no escala del formato de hoy

* **Los números de fondo son de 8 bits**: 45 de 254 posibles. Sobra.
* **`msu_fondo_pos` crece 8 B por fondo** (360 B) pero va en un banco
  generado, no en el 0. Las tablas nuevas también (31 + 45 B).
* **El índice del `.msu` tiene tope** en `$10000`: 8.190 entradas. Con 90 de
  fondos quedan unas 8.100 para efectos; `armar` se niega si se pasa.
* **`se_msu_altura`, la tabla de alturas de los efectos**, es la que no
  escala: el plan del mundo la mide en 33,8 KB con el capítulo entero, y
  `escribir_msu` se niega a pasar de un banco. No es de esta tarea: es por
  paquete × sonido y crece con el audio, no con los fondos.

# Pruebas

* `test_msu_una_pelea_del_mundo_lee_su_terreno_o_el_reemplazo` (nueva, en
  snes9x y bsnes): pelea en la llegada al 66. Sin `.msu`, `ESC_FONDO` es el
  número de plains6 calculado del juego (tile → terreno del ChipSet → fondo
  del terreno) y el fondo limpio de la WRAM es el reemplazo liviano, no
  ceros: golden `msu-mundo-rom`. Con `.msu`, `ESC_MSU` en 1 y el limpio es
  plains6 de calidad: golden `msu-mundo-msu`.
* `test_msu_la_rom_sabe_donde_esta_cada_fondo`: además, cada fondo en su
  lugar fijo, `MSU_FONDOS_N == FONDOS_JUEGO == 45`, y la región de fondos
  byte por byte igual en el `.msu` de los dos cartuchos.
* `test_batalla_escena_dibujo`: los colores del respaldo se leen con
  `ESC_RESPALDO`.
* `test_escena_una_pelea_del_lugar_usa_el_fondo_del_mapa` (nueva): el caso
  `pelea-113` pelea con el fondo "del lugar" en el 60, que nombra
  `SJBackdropABL01`; `ESC_FONDO` es ése y el limpio es el reemplazo.
* **Verificado** con `just cartuchos` y `just pruebas` sobre esta rama antes
  del merge: todo en verde, y **ninguna golden vieja cambió**. Las únicas
  nuevas son `msu-mundo-rom` y `msu-mundo-msu`.
* Lo que **no corre ninguna prueba**: el terreno bajo el héroe con una
  `TileSubstitution` puesta (la búsqueda de `esc_terreno` está copiada de
  `celda_sustituida`, que la tanda sí ejercita por `op_terrain`), y un mapa
  de un solo terreno que pida el del terreno (la rama de `TERRENO_PLANO`).

# Lo que cambia a propósito

Sin MSU-1, las peleas que antes salían en negro porque su fondo no estaba en
la ROM ahora salen sobre el reemplazo: el mundo, el 158 y el 210 (terreno), y
en `release` también las de los mapas que nombran un fondo que la ROM no
lleva, como el Warehouse de Sector 27 (`SJBackdropABL01`). Y dos cosas que el
port hacía distinto de RM2k y ahora no: un `EnemyEncounter` con el fondo "del
lugar" (el 105 y el 141 del juego, y el caso `pelea-113`) salía sin fondo, y un
mapa que sube hasta la raíz sin nombrar fondo se trataba como sin fondo; los
dos son "el del terreno" en easyrpg. Ninguna golden de la tanda mira esas
peleas.

# Espacio

Medido relinkeando el `.o` de `release` con el mapa de `ld65`:

    release   75,6 %   banco 0 261 B   banco 1 ~8.090 B   BSS 138   ZEROPAGE 4

El banco 0 no cambió: todo el código nuevo es del banco 1 (unos 95 B, en
`escena_subir` y `esc_terreno`) y las tablas van en bancos generados.

# Qué tiene que mirar taro

* **Sin MSU-1 (Mednafen)**: caminar por el mundo desde la llegada y pelear.
  El fondo tiene que ser la cueva gris de los Rat Tracks, en 16 colores, y
  **no negro**. Las peleas de siempre —el droide, Sector 27 y 30, los Rat
  Tracks— tienen que verse como antes.
* **Con MSU-1 (el `abl.msu` al lado, en un emulador que lo tenga o en el FX
  Pak)**: la misma pelea en el mundo tiene que mostrar **el terreno que se
  pisa**: pradera en la llegada (plains6), bosque (forest5), montaña (mroad2),
  desierto (desert1), según la celda. Las peleas de siempre, con el fondo de
  calidad.
* **Decidir** si los tres fondos siguen en la ROM (lo recomendado) o si
  todos pasan a reemplazo más MSU-1, que ahorra 32 KB y pone al droide en la
  cueva sin MSU-1.
* El `.msu` pasó de unos cientos de KB a unos 3,3 MB (los 45 fondos son 1,4
  MB): copiarlo entero al lado del `abl.sfc`.
