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
* **Lo que ninguna prueba corre**: una pelea con una animación a medio
  dibujar en el mapa, que es lo que cubre la llamada a `anim_buf_clear` en
  `scene_upload`.
