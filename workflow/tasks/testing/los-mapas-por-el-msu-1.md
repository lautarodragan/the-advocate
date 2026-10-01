---
name: "Plan: los mapas por el MSU-1"
description: "Ni 6 ni 8 MB alcanzan para el juego entero: cuánto pesa, qué se puede leer del .msu, cuánto tarda cargar un mapa así y qué pasa sin MSU-1, para que taro decida hasta dónde llega el cartucho"
type: research
assignee: taro
---

De taro, el 2026-10-01, al preguntar por más mapas. Ya decidido: el
cartucho se queda en 4 MB (`decisiones/el-cartucho-se-queda-en-4-mb.md`), y
taro dijo el 2026-09-27 que "a este ritmo, ni 6 MB ni 8 MB nos van a
permitir cubrir todo el juego". Los fondos de batalla ya van por el `.msu`
(`docs/port/msu-datos.md`). Esto es un estudio con números, sin
implementar: es lo que define hasta dónde llega el cartucho, y conviene
antes de seguir sumando capítulos. Después se sumó la pregunta de taro por
los chips de descompresión (S-DD1, SPC7110, SA-1).

# Hecho

Lechuza, el 2026-10-01. **El estudio es
`docs/research/2026-10-01-los-mapas-por-el-msu-1.md`**; lo de abajo es lo
que hay que decidir y lo que quedó suelto.

* **El juego entero son 8.514 KB de datos**: 266 bancos contra 124. Tampoco
  entra en 8 MB. Medido convirtiendo los 328 mapas en once corridas.
* **Con los mapas y la música por el `.msu`, la ROM del juego entero baja a
  3,0 MB** y entra con 0,9 MB libres. La música sola son 3,4 MB, y lo que un
  mapa sube al entrar, 1,9.
* **Leer un mapa del `.msu` es más rápido que descomprimirlo**: el puerto da
  42 KB por cuadro en los tres cores del arnés (`just msu-puerto`), y la
  carga del mapa típico pasa de ~5 cuadros a ~0,4; la del 66, de 22 a 1,5.
* **Sin MSU-1 se llega a un tercio del juego**, más o menos lo de hoy.
* **El S-DD1 empata con LZ2 en los tiles** (57 contra 58 %); lo que da es
  descomprimir las poses sin CPU (32 % contra 41 %). **El FX Pak no tiene
  SPC7110** (`MENU_ERR_NOIMPL` en su firmware).

# Lo que taro tiene que decidir

* **Uno o dos cartuchos.** La recomendación es dos del mismo conversor:
  `release` sin MSU-1 como hoy, y uno `completo` que pide MSU-1. La opción
  de una sola ROM deja lo jugable sin MSU-1 en menos de la mitad de hoy.

# Lo que taro tiene que probar

* **La ROM del puerto en el FX Pak** (fase 0 del estudio): `just
  msu-puerto` arma `rom/build/msu-puerto/msu-puerto.sfc` y su `.msu`; en la
  consola, **verde** si los 576 KB llegaron bien, **rojo** si no, **azul**
  sin MSU-1. Decide si la carga lee a toda velocidad o de a 8 KB por cuadro.
  En Mednafen se puede mirar con `-force_module snes_faust`.

# Lo que quedó suelto, para tareas aparte

* **Cinco mapas no entran en la VRAM** (108, 127, 148 y 250 sin lugar para
  la ventana; 285 con la caja de las animaciones de batalla).
* **`rm2k-snes-battle` indexa las tropas de los encuentros con un byte**, y
  el juego entero tiene 365.
* **Los candidatos a líder con todos los mapas**: el 207 pide 9 gráficos de
  la orden 34 (tope 8) y el 288 suma al actor 34, sin CharSet.
* **Un pánico en `rm2k-snes-audio`** (`msu.rs:116`, "no entry found for
  key") con los mapas 120 y 122 en el mismo cartucho.
* **El bloque de textos del juego entero son ~255 KB** de los 256.

# Al mergear

Nada que instalar: no se tocó Rust ni el runtime, y la ROM no cambia. Es
una receta nueva, `msu-puerto`, con su experimento en
`rom/experimentos/msu-puerto/`.
