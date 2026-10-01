---
name: "LZ2 donde va crudo"
description: "Comprimir con LZ2 lo que hoy va crudo y se sube al cargar: la tabla de bloques, el bytecode, los battlers, las animaciones de las cinemáticas, la fuente y los fondos de batalla livianos; unos 470 KB en el juego entero, sin perder nada"
type: feature
assignee: Quirquincho
---

Fase 1 del plan de `docs/research/2026-10-01-el-juego-entero-sin-msu-1.md`
(Tucu-tucu), medido por Lechuza en
`docs/research/2026-10-01-los-mapas-por-el-msu-1.md`, sección 5. De taro,
el 2026-10-01, después de pasar a 8 MB
(`decisiones/el-cartucho-pasa-a-8-mb.md`). Las poses y las secuencias de
música no se pueden: se leen mientras se usan, y por qué está en el estudio.

## Cómo va (Quirquincho, 2026-10-01)

Base: `cd3dce0d`, `abl.sfc` en `ccdf1191…`. Cada paso, con `NO_CACHE=1 just
cartuchos`, `just pruebas` y `just -f tools/justfile test`; el tiempo de
carga con el método de `_cargar` en `test_carga_descomprimida.py` —los
cuadros de hardware de la vuelta del lazo que cargó— sobre los 97 mapas de
`release`, y la pelea con `SCN_FRAMES` en el caso `pelea-en-52`.

### 1. La tabla de bloques y su pasabilidad: hecho

Se pueden: la CPU las lee sólo por `blocks_ptr`, `blocks8_ptr` y `pass_ptr`,
punteros de 24 bits que `enter_map` arma desde el registro. Viven ahora en
la WRAM **detrás de la grilla**, en un tercer flujo de LZ2 pegado a los dos
de la grilla (`map_ram` en `materials.rs`): `lz2_grid` lo descomprime donde
terminó el segundo, y por eso vuelven solas con `back_from_battle`. El
registro trae las direcciones de la WRAM, que calcula el conversor; la ROM
no las calcula, y `test_carga_descomprimida.py` mira que coincidan y que el
contenido sea el de `crudos/N.map_ram.bin`, al cargar cada mapa y a la vuelta
de la pelea del 52.

* En `release`: 119,2 KB crudos, 61,7 KB en LZ2 (el reporte del conversor).
  `just espacio`: de 62 bancos de datos a 61, y los huecos de 7.406 B a 0.
* Carga: +39 cuadros sobre los 97 mapas, +0,4 de media, mediana 0, máximo
  +2. La pelea no cambia.
* Ninguna golden se movió; las dos tandas en verde.
* Los hashes de `tests/python.rs` de `rm2k-snes-mapdata` cambiaron a
  propósito: son los bytes del cartucho.

### 2. Los battlers: hecho

Se pueden, pero no "al empezar y listo": la CPU los vuelve a leer **durante
toda la pelea** —`scene_tick` redibuja a los que siguen vivos encima de un
enemigo borrado, y un enemigo oculto se dibuja cuando aparece—, así que
tienen que quedarse en la WRAM. Van a la mitad de la grilla en el `$7E`
(`SCN_BATTLERS = GRID`): la pelea no lee el mapa, y `back_from_battle` ya
descomprimía la grilla entera. `scn_battlers_load` descomprime los battlers
distintos de la tropa —los de `SCN_PAL_BAT`— uno detrás del otro y anota
dónde cayó cada uno por ranura de paleta (`SCN_BAT_PTR`, `$7E6650`); el
conversor corta si los de una tropa pasan de 32 KB (en `release`, la más
pesada son 15 KB). `scn_terrain`, que lee la grilla, corre antes.

* En `release`: los huecos de `just espacio` pasan de 0 a 62.525 B (147 KB
  de battlers crudos).
* La pelea del droide en el 52 compone en 11 cuadros en vez de 10; los mapas
  no cambian. La entrada a la pelea es a negro, así que no se ve.
* `test_reservas_de_la_wram.py` deja pasar `SCN_BATTLERS`, y la decisión de
  la grilla lo dice.

### 3. Las animaciones de batalla (las de las cinemáticas): hecho, cuadro por cuadro

Se pueden, pero no "al empezar la pelea", como decía el estudio: las dibuja
`ShowBattleAnimation` **en el mapa** —las páginas de tropa no lo compilan— y
`anim_frame_build` las arma en el lazo principal, con la pantalla prendida.
Cada cuadro va en su propio flujo de LZ2 y se descomprime cuando toca en uno
de dos lugares de `LZ2_BUFFER` —libre en el mapa una vez cargado—, el que no
tiene el cuadro anterior, cuyos tiles se borran primero. La pelea pisa
`LZ2_BUFFER`, así que `scene_upload` llama a `anim_buf_clear`.

**Probé primero la animación entera en un flujo**, descomprimida al armar su
primer cuadro: ahorraba más —67.696 B a 28.171, contra 37.354 cuadro por
cuadro—, pero el primer tick de la animación tardaba hasta 4 cuadros de
hardware (la 148, de 13,7 KB) y 2 la mayoría: el mapa se frenaba al empezar
cada animación. Cuadro por cuadro, medido sobre las 21 animaciones de
`release` en el mapa 6 con el método de `test_animacion_cuadros.py`, ningún
tick pasa de un cuadro.

* En `release`: 67.696 B crudos, 37.354 en LZ2. `just espacio`: de 61 bancos
  de datos a 60.
* `test_animacion_cuadros.py` arma cada cuadro de cada animación por el
  camino del juego y lo compara con la cuenta sin comprimir.
* **Se me escapó un camino**, y lo arreglé en un commit aparte: volver del
  menú, de la tienda, de las ranuras o de una pelea pasa por `back_to_map`,
  que sube los tiles del mapa por `LZ2_BUFFER` y pisa el cuadro anterior;
  borrarlo leía tiles de fondo como números de la caja, dejaba tiles viejos
  y escribía más allá de `ANIMB_BUF`. `back_to_map` llama ahora a
  `anim_buf_clear` (en vez de `scene_upload`), y
  `test_la_caja_vuelve_entera_del_menu` lo cobra: en rojo sin el arreglo
  (cuadros 4 y 5 de la 148), en verde con él.

### 4. Los fondos de batalla livianos: hecho

Se pueden: la CPU lee el respaldo liviano una sola vez, en `scn_double`, que
lo agranda a los dos búferes de la escena al empezar la pelea. Ahora se
descomprime antes a la mitad de la grilla en el `$7E` (`SCN_BATTLERS`), y
los battlers se descomprimen después, encima: `scn_battlers_load` se mudó de
antes de `scn_backdrop` a después. La tanda corre sin MSU-1, así que el
camino del respaldo es el que miran las goldens y `test_batalla_escena_dibujo.py`.

* En `release`: 73.728 B crudos (18 fondos de 4 KB), 55.331 en LZ2. Los
  huecos de `just espacio` pasan de 27.331 B a 45.728.
* La pelea del droide compone en 12 cuadros en vez de 11 (10 en la base), a
  negro.

### 5. El bytecode de los eventos: hecho, con lo que sigue corriendo en otro mapa

Se lee de la ROM mientras corre —`[code_ptr], y`—, así que va a la WRAM:
detrás de la tabla de bloques, en un bloque de LZ2 propio que nombra la tabla
`map_code` (puesto pegado a la grilla, dos mapas con la misma grilla y otros
eventos dejaban de compartirla: eran 6 KB). La tabla de páginas apunta a la
WRAM. Los saltos de una página son relativos a donde empieza.

**El problema era lo que sigue corriendo después de un `Teleport` a otro
mapa**: el mapa nuevo pone su bytecode en el mismo lugar. En `release` son
282 páginas que siguen después de saltar (contado sobre el volcado, con los
`CallEvent` adentro), y además **cada caso de la tanda** empieza saltando y
sigue. Y la ruta forzada del héroe apunta al bytecode de la página que la dio
y sigue caminando en el mapa nuevo (`Game_Player::PerformTeleport` no la
corta). Lo que se hace:

* `code_carry_before`, al empezar `enter_map_no_events` y con el mapa viejo
  todavía en `map_current`: si la página en primer plano está en el bytecode
  de ese mapa, su puntero se muda a `CODE_CARRY` (en `LZ2_BUFFER`, arriba de
  los cuadros de la animación de batalla); y la ruta del héroe, si apunta al
  banco del bytecode, se copia entera a `ROUTE_CARRY` (`$7E7F00`, 256 B).
* `code_carry_after`, al final de la carga y de `back_to_map` —que sube los
  tiles por `LZ2_BUFFER`—: descomprime ahí el bytecode del mapa acarreado
  (`CARRY_MAP`, `$7E7EF0`).
* Lo demás que apunta al bytecode no sobrevive al cambio de mapa: las
  paralelas, las rutas de los eventos y la línea de tiempo de la animación
  empiezan de nuevo con el mapa nuevo.

La primera versión olvidaba `back_to_map`: con el menú, las ranuras o una
pelea en el medio de una página acarreada, la página leía tiles de fondo.
Lo cobraron siete pruebas de la tanda —`test_guardar_golden.py`,
`test_curar.py`, `test_experiencia_dibujo.py`—, y destapó el mismo error en
la animación de batalla (el commit aparte de arriba).

* En `release`: 124,7 KB de bytecode, 80,2 en LZ2. `just espacio`: de 60
  bancos de datos a 59, y los huecos de 45.728 B a 25.045 —44.853 B menos—.
* Carga: +0,4 cuadros de media sobre los 97 mapas, +6 en el 4 (que en
  `release` lleva los 262 casos). Acarrear cuesta otra descompresión adentro
  del fundido.
* La carrera, que es lo más justo de CPU, no pierde cuadros por leer el
  bytecode de la WRAM (8 ciclos por byte contra 6): manejando, el 49 pierde
  35 cuadros en 976 ticks antes y después, el 52 5 y 4, el 54 0 y 1.
* `test_carga_descomprimida.py` mira el bytecode en la WRAM contra
  `crudos/N.map_code.bin` y `map_code` contra dónde quedó;
  `test_la_ruta_del_heroe_sigue_entera_en_el_mapa_nuevo` mira la copia de la
  ruta, que ningún caso corre.
