# Qué

**La grilla del mapa se descomprime entera a la WRAM al cargar el mapa, y
vive en `$7E8000-$7EFFFF`**, siguiendo en `$7F8000` si pasa de 32 KB: la
mitad alta de los dos bancos (`GRILLA` en `tools/runtime/ram_lejana.s`). El
cartucho la trae en LZ2, en dos flujos, uno por mitad (`lz2_grilla` en
`tools/runtime/descomprimir.s`).

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
**costó cambiar dos lecturas**: sólo `ptr_mas` y `ptr_menos` sabían que la
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
* **La mitad alta del $7F la comparte con la pelea** (`ESC_ESCENA`), que la
  pisa: en los mapas de más de 32 KB de grilla hay que volver a descomprimirla
  al salir de una pelea. `volver_de_batalla` la descomprime entera siempre,
  que cuesta lo mismo que al entrar al mapa: 1,7 cuadros de media y 8 en el
  mapa 52, el de 40 KB.
* **Cuadros de carga**: descomprimir la grilla suma a cada cambio de mapa lo
  mismo que arriba. Medido en la ROM sobre los cuarenta mapas de `release`.
* **Un mapa de más de 64 KB de grilla no entra**: el conversor corta. El más
  grande de hoy son 40.000 B (el 52, de 500×40). RM2k llega a 500×500, que
  serían 500 KB: un mapa así no entra de ninguna manera sin trozos.

# Cómo se sabría que hace falta revertirlo

* **`rom/pruebas/herramientas/test_reservas_de_la_wram.py` falla** si algún
  símbolo del cartucho cae en `$7E8000-$7FFFFF` y no es la grilla, el buffer
  de carga o la escena de la pelea. Es la alarma para quien necesite RAM
  lejana: si falla, no es para agregar el símbolo a su lista, es para leer
  esto. No ve una dirección escrita de dieciséis bits y usada con el banco de
  datos en `$7E`, como `FAR_BATALLA`.
* **`rom/pruebas/rpgmaker/test_carga_descomprimida.py` compara la grilla entera
  en la WRAM** contra la que dejó el conversor, en cada uno de los cuarenta
  mapas, en snes9x y en bsnes, y **a la vuelta de una pelea** en el mapa 52.
  Un intruso que escriba ahí en esos caminos la hace fallar.
* O que un mapa del juego que falta pida más de 64 KB de grilla, o que lo que
  falta de RM2k no entre en la RAM lejana que queda.

# Cómo se revierte

La grilla vuelve al cartucho, en LZ2 no: sin comprimir, o en trozos de 4×4.

1. En `tools/port/snes_convert.py`, sacar `map_celdas` de
   `CLASES_COMPRIMIDAS` y volver a emitirla con `materiales.guardar(...,
   alinear=2)`: entera no hace falta en un banco, la recorre `ptr_mas`.
2. En la ROM, las dos lecturas de `GRILLA` —`ptr_de_celda` en `heroe.s` y
   `fill_window` en `ventana_del_mapa.s`— vuelven a leer
   `mapa_tabla + M_PTR_MAP_CELDAS`, y se sacan las dos llamadas a
   `lz2_grilla` —en `cargar_mapa_sin_eventos` y en `volver_de_batalla`—.
3. Se borran `GRILLA` y su reserva de `ram_lejana.s`, `lz2_grilla` y lo de la
   grilla en `test_carga_descomprimida.py` y `test_reservas_de_la_wram.py`.

Son 246 KB de cartucho de vuelta. El resto de la compresión —los tiles— no
depende de esto: su buffer está en el banco $7F, que la pelea ya usaba.
