---
name: "MSU-1: los fondos por el puerto de datos"
description: "Piloto: los fondos de batalla también en el .msu, y con MSU-1 la ROM los lee de ahí; sin él, de sí misma"
type: feature
---

Idea de taro, el 2026-09-25: usar el **puerto de datos** del MSU-1 para
guardar cosas fuera de la ROM, empezando por los fondos de batalla. Es un
piloto: **probar el mecanismo, no ahorrar espacio todavía**. La condición que
no se negocia es que sin MSU-1 el juego ande igual, porque taro juega en
Mednafen.

## Qué anduvo

El conversor escribe en el `.msu` de cada cartucho los mismos fondos que lleva
la ROM, con una firma del contenido adelante —formato y mecanismo en
`docs/port/msu-datos.md`, referencia en `tools/port/msu_datos.py`—. Al
empezar una pelea con fondo, la ROM mira si hay MSU-1 y si el `.msu` tiene su
firma; si sí, trae los 32 KB por DMA desde `$2001` a los dos búferes de la
WRAM y los colores a la CGRAM, y deja `ESC_MSU` en 1. Si no —sin MSU-1, con
otro `.msu`, vacío, o si el MSU-1 no termina de buscar—, todo sale de la ROM
como antes.

## En qué está verificado

* **Sin MSU-1**: la tanda entera, sin ninguna golden cambiada.
* **Con MSU-1, en snes9x y en bsnes**: `pruebas/abl/test_msu_datos.py`. La
  pelea de Sector 27 se ve igual por los dos caminos, un control con los
  tiles del `.msu` cambiados se ve distinto —que es lo que prueba que la
  imagen salió del `.msu`—, y un `.msu` de otro build o vacío cae a la ROM.
* **mesen-s**: los mismos tres casos, a mano, con el mismo resultado. No va
  en la tanda por el arrastre de estado entre consolas del mismo proceso que
  documenta `test_cores.py`.
* **No verificado: el FX Pak Pro.** Es lo que falta que taro pruebe: con
  `abl.sfc`, `abl.msu` y las pistas en la misma carpeta, entrar a una pelea
  con fondo —la del droide, o un encuentro al azar en Sector 27 o 30— y ver
  que el fondo es el de siempre. Si el fondo sale bien pero la entrada tarda
  más que en un emulador, es la búsqueda en la SD.
* **No lo corre nadie: la espera del bit de datos ocupados.** Ningún
  emulador lo prende; sólo el hardware busca de verdad.
* **No lo cubre la firma**: un `.msu` con la cabecera intacta y los datos
  dañados. La ROM no hashea los fondos al empezar cada pelea.

## Cuánto tarda

Lo mismo por los dos caminos en los tres emuladores: `ESC_CUADROS` da igual
con MSU-1 y sin él, porque el DMA va a 8 ciclos maestros por byte venga de
donde venga y buscar es instantáneo. En el hardware se suman cuatro búsquedas
por pelea —la firma, los tiles dos veces (uno por búfer) y los colores—, que
no están medidas.

## Cómo viaja a taro

`just entregar` copia el `abl.msu` al build, al lado del `abl.sfc`, y
**siempre** a `/shared/msu/`, porque es del build y no de las pistas. Con el
`abl.sfc` de otro build no se rompe nada: la ROM no encuentra su firma y lee
los fondos de sí misma.

## El paso siguiente

* **El respaldo liviano.** Que la ROM lleve una versión más barata del fondo
  —menos colores, o a media resolución y ampliado— y el `.msu` la buena. Ahí
  "se ve igual por los dos caminos" deja de valer: cada camino contra su
  propia golden, y la tanda que corre sin MSU-1 cubre el liviano.
* **Los demás fondos.** El juego nombra una quincena; en el `.msu` no cuestan
  cartucho, así que el respaldo de los que no están en `FONDOS` puede seguir
  siendo el fondo liso.
* **Medir en el FX Pak** cuánto tarda buscar, antes de mover algo que se lea
  en cada cuadro y no una vez por pelea.
* Si se suman otras cosas al `.msu`, la firma sigue cubriendo todo el archivo:
  cualquier cambio en cualquier entrada invalida el `.msu` entero, que es lo
  simple y lo correcto mientras el `.msu` viaje con el build.
