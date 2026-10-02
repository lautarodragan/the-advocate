# Qué

**La grilla del mapa se descomprime entera a la WRAM al cargar el mapa, y
vive en `$7E8000-$7EFFFF`**, siguiendo en `$7F8000` si pasa de 32 KB: la
mitad alta de los dos bancos (`GRID` en `tools/runtime/far_ram.s`). El
cartucho la trae en LZ2, en dos flujos, uno por mitad (`lz2_grid` en
`tools/runtime/decompress.s`).

Decidido con taro el 2026-09-26, **como prueba y sabiendo que quizás haya que
revertirlo**.

# Por qué

Las grillas pesaban 278 KB en `release` y en LZ2 pesan 32: es el segundo
ahorro más grande del cartucho después de los tiles. Pero se leen celda por
celda todo el tiempo —cada tira que entra en pantalla, cada pregunta de
pasabilidad— y no se pueden leer comprimidas. Las dos salidas eran partirlas
en trozos de 4×4 deduplicados, que ahorra 214 KB y agrega una indirección en
cada lector de la grilla, o descomprimirlas enteras a la WRAM y dejar el
acceso directo como estaba. La segunda es mejor en todo menos en la RAM, y
**costó cambiar dos lecturas**: sólo `ptr_more` y `ptr_minus` sabían que la
grilla estaba en LoROM, y la mitad alta de dos bancos seguidos de la WRAM
tiene la misma forma que dos bancos de LoROM.

El razonamiento de taro para aceptar el costo: los mapas y los eventos que ya
están en la ROM son una buena muestra de lo que pasa en un juego de RM2k; si
Lashe City entera anda con la RAM que queda, el resto del juego —cerca del 90%
está ahí— también.

# Qué se pierde

* **La mitad de la RAM lejana que quedaba libre**: 32 KB del banco $7E.
  Antes de esto la RAM lejana usada llegaba a `$7E7FFF` y de `$7E8000` en
  adelante no había nada; el día que haga falta más estado de RM2k —más
  variables, más switches, más eventos por mapa, un segundo intérprete— ahí
  era donde iba a ir. Quedan `$7E7805-$7E7FFF` y los huecos de abajo.
* **La mitad alta del $7F la comparte con la pelea** (`SCN_SCENE`), que la
  pisa: en los mapas de más de 32 KB de grilla hay que volver a descomprimirla
  al salir de una pelea. `back_from_battle` la descomprime entera siempre,
  que cuesta lo mismo que al entrar al mapa: 1,7 cuadros de media y 8 en el
  mapa 52, el de 40 KB.
* **Cuadros de carga**: descomprimir la grilla suma a cada cambio de mapa lo
  mismo que arriba. Medido en la ROM sobre los cuarenta mapas de `release`.
* **Un mapa de más de 64 KB de grilla no entra**: el conversor corta. El más
  grande de hoy son 40.000 B (el 52, de 500×40). RM2k llega a 500×500, que
  serían 500 KB: un mapa así no entra de ninguna manera sin trozos.

# Cómo se sabría que hace falta revertirlo

* **`pruebas/herramientas/test_reservas_de_la_wram.py` de ABL falla** si algún
  símbolo del cartucho cae en `$7E8000-$7FFFFF` y no es la grilla, el buffer
  de carga o la escena de la pelea. Es la alarma para quien necesite RAM
  lejana: si falla, no es para agregar el símbolo a su lista, es para leer
  esto. No ve una dirección escrita de dieciséis bits y usada con el banco de
  datos en `$7E`, como `FAR_BATTLE`.
* **`pruebas/rpgmaker/test_carga_descomprimida.py` de ABL compara la grilla entera
  en la WRAM** contra la que dejó el conversor, en cada uno de los cuarenta
  mapas, en snes9x y en bsnes, y **a la vuelta de una pelea** en el mapa 52.
  Un intruso que escriba ahí en esos caminos la hace fallar.
* O que un mapa del juego que falta pida más de 64 KB de grilla, o que lo que
  falta de RM2k no entre en la RAM lejana que queda.

# Cómo se revierte

La grilla vuelve al cartucho, en LZ2 no: sin comprimir, o en trozos de 4×4.

1. En `tools/port/snes_convert.py`, sacar `map_celdas` de
   `CLASES_COMPRIMIDAS` y volver a emitirla con `materiales.guardar(...,
   alinear=2)`: entera no hace falta en un banco, la recorre `ptr_more`.
2. En la ROM, las dos lecturas de `GRID` —`cell_ptr` en `hero.s` y
   `fill_window` en `map_window.s`— vuelven a leer
   `map_table + M_PTR_MAP_CELLS`, y se sacan las dos llamadas a
   `lz2_grid` —en `enter_map_no_events` y en `back_from_battle`—.
3. Se borran `GRID` y su reserva de `far_ram.s`, `lz2_grid` y lo de la
   grilla en `test_carga_descomprimida.py` y `test_reservas_de_la_wram.py`.

Son 246 KB de cartucho de vuelta. El resto de la compresión —los tiles— no
depende de esto: su buffer está en el banco $7F, que la pelea ya usaba.

**Desde el 2026-10-01 la tabla de bloques, su pasabilidad y el bytecode de
los eventos dependen de esto**: viven en la WRAM justo detrás de la grilla, y
`lz2_grid` los descomprime con ella (ver `docs/port/maps.md`). Revertir la
grilla pide también devolverlos al cartucho, sin comprimir: en
`rm2k-snes-mapdata`, sacar `map_ram` y `map_code` de `COMPRESSED_KINDS` y
volver a guardarlos como bloques sueltos con sus etiquetas en el registro y
en la tabla de páginas; y en la ROM, sacar `code_carry_before` y
`code_carry_after`, que sólo existen porque el bytecode se muda.

**Y la pelea le pide prestada la mitad del `$7E`**, también desde el
2026-10-01: ahí descomprime los battlers de la tropa (`SCN_BATTLERS` en
`battle_scene.s`), porque `back_from_battle` ya volvía a descomprimir la
grilla entera. Revertir la grilla no los obliga a irse: la mitad del `$7E`
quedaría libre para ellos solos.
