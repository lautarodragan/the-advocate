---
name: "Mundo 1: el 66 entra"
description: "El hito 1 de el-mundo-y-lo-que-sigue: el mapa del mundo en release, con el quinto reparto de VRAM, el fondo en dos flujos de LZ2 y el fin de la demo al pisar Sorbe"
type: feature
---

# Qué

El hito 1 de `todo/el-mundo-y-lo-que-sigue.md`, que tiene todo lo medido
antes. Sale de `2be61a9`.

* **El quinto reparto** al final de `LAYOUTS`, `LAYOUT_VENTANA_FONDO_TECHO`:
  256 sprites, 544 tiles de fondo en `$1000`, ventana_map en `$5400`, tilemap
  en `$5800`, 128 de encima y 256 de ventana.
* **El fondo de más de 32 KB en dos flujos de LZ2**: `partes_comprimidas` lo
  parte en tramos de `LZ2_TOPE_FONDO`, y `lz2_fondo` (en `descomprimir.s`)
  descomprime y sube uno antes de descomprimir el otro. El tope ahora se cobra
  **por flujo** (`controlar_flujos`), y también cuántos flujos lee la ROM: con
  un fondo de tres, o un flujo que se pasa de su lugar, el conversor no arma.
* **El 66 en `release`**, por `AGREGADOS` de `cartuchos.py`: subir `MENOR_A`
  a 67 metería al 65, que es una carpeta.
* **El fin de la demo** pasa del fork del 64 (borrado) a un fork del 66: el
  evento 10, la entrada de Sorbe Village, muestra "END OF THE DEMO" y vuelve
  al título.
* **`Comment` se saltea al compilar**, que estaba en el hito 2 y hubo que
  adelantar: sin el fork, la página de la despedida del 64 no compilaba, y su
  único comando que no compilaba era la nota "LYS" que el autor dejó detrás del
  `Teleport` al mundo (medido con `culpables.py` de `mundo-plan`). Ningún otro
  mapa de los dos cartuchos tiene un `Comment`: el recuento de páginas de
  `test-special` sale igual.

# Hecho y comprobado

* **El conversor solo no cambia nada**: con el `snes_convert.py` del primer
  commit sobre una copia de `2be61a9`, `release` y `test-special` salen byte
  por byte iguales (`cmp` de `abl.sfc`, `prueba.sfc` y `abl.msu`). Ningún mapa
  cambia de reparto ni de flujos.
* **`test_carga_descomprimida.py`** ya recorre todos los mapas de `release`,
  así que mira el fondo de dos flujos del 66 en snes9x y en bsnes. Y una prueba
  nueva, `test_un_fondo_de_dos_flujos_no_se_sale_del_buffer`, escribe un
  testigo en `GRILLA_ALTA`, carga el 66 y mira que siga ahí. **Se vio fallar
  con el error puesto**: sobre la misma copia de `2be61a9` con el 66 metido a
  lo bruto (el quinto reparto y sin el tope del fondo, como la variante `m0p2`
  del plan), el testigo sale pisado.
* **`test_mundo.py`**, nueva: el 66 recién llegado (golden
  `mundo-66-llegada`, `celdas_mal_dibujadas` en cero) y una pelea pedida con
  `ENC_PIDE` que Kersh gana y vuelve al mapa (golden
  `mundo-66-despues-de-pelear`, celdas en cero). Talan solo, con lo que tiene
  al empezar la partida, pierde contra el lobo.
* **El recorrido de la carrera** sigue de la despedida al mundo, camina de
  (71, 29) a Sorbe (75, 10) con los encuentros apagados y termina en el cartel
  nuevo. Sus capturas de `pruebas/snapshots/playthrough/carrera-*/` no están
  bendecidas, como antes.

# Espacio

Medido con el método de `AGENTS.md` sobre lo que dejó `just cartuchos`:

    release        75,6 %   banco 0 261 B   banco 1 8.185 B   BSS 138   ZEROPAGE 4
    test-special   19,2 %   banco 0 1.073 B banco 1 9.977 B   BSS 138   ZEROPAGE 4

El banco 0 **ganó** 37 bytes en los dos: el DMA de los tiles del fondo se mudó
de `load_map` a `lz2_fondo`, en el banco 1.

# Deuda

* **La pelea en el mundo sale sin fondo.** El cartucho lleva tres fondos de
  batalla y el mundo usa otros cinco terrenos (plains5, desert1, forest5,
  forest6, mroad2). Es la pregunta 6 del plan; la recomendación es dejarlo para
  después del hito 3. No se resuelve acá.
* Las demás entradas del mundo no hacen nada —sus destinos no están—, y
  `DaliaGoingToTasgarde` (ev14) no compila por `ChangeEncounterSteps`, que es
  del hito 2.

# Qué tiene que probar taro

* Terminar la carrera y la despedida: tiene que aparecer en el mundo con los
  mensajes de Talan ("Outside Lashe City at last…"), y poder caminar.
* Caminar por el mundo y pelear: los encuentros son por zona, cada 65 pasos.
  Al volver de la pelea el mapa tiene que estar bien dibujado. La pelea sale
  sin fondo, y eso es sabido.
* Pisar Sorbe Village, arriba a la derecha del punto de llegada: el cartel de
  fin de demo y la vuelta al título.
* Guardar en el mundo: la paralela 26 prende el guardado con el switch 236,
  que pone la despedida. No lo mira ninguna prueba.
