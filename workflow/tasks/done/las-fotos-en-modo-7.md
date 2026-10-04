---
name: "El zoom de las imágenes en modo 7"
description: "Una imagen grande que se achica o agranda con ShowPicture/MovePicture se hace en modo 7, con la textura de 255 tiles parecidos (vq); quieta sigue en modo 1 a resolución completa"
type: feature
assignee: taro
---

De taro, el 2026-10-03, después de ver el piloto en la SNES: "el modo 7 es
definitivamente la forma de encarar las fotos", y eligió la variante 4, la
**híbrida vq**: la foto quieta a resolución completa en modo 1, como hoy, y
al empezar el zoom el modo 7 con una textura de 255 tiles elegidos por
cuantización vectorial. El piloto, lo medido y el costo de llevarlo al
juego: `workflow/tasks/done/el-piloto-del-modo-7.md`, en ABL. Es del motor:
cualquier imagen grande con zoom, de cualquier juego.

Hecha por Chajá, desde `main` en `2c05f8a0`; ABL en un clon, rama
`fotos-en-modo-7` desde `30d916c`.

## El plan

* **La textura sale de la capa del modo 1, no de la foto**: los mismos
  índices de CGRAM (las siete paletas de arriba de la ventana), así que el
  cambio de modo no toca la CGRAM y el tono de la imagen sigue andando en
  modo 7 con `big_palette_build` tal cual. El piloto usaba 239 colores
  propios; acá son los ≤105 de la capa.
* **Quieta, la foto con textura va a `$4000`** (tiles) y su tilemap a
  `$7C00`, 32x32: el modo 7 es dueño de `$0000`-`$3FFF` y la textura se
  sube en el vblank mientras está quieta. Eso pisa la ventana y los tiles
  de BG2: con la foto quieta no puede haber mensaje (en las cuatro escenas
  no lo hay). En modo 7 la mitad de arriba ya no hace falta, y la ventana
  se repone ahí durante el zoom.
* **Al terminar el zoom en 0**, modo 1 con BG1 apagado: los mensajes que
  siguen (el de la viuda, en el 212) ven la ventana. Si termina en otro
  tamaño, se queda en modo 7.
* `irq_music` multiplica con el multiplicador de la PPU, que en modo 7 es
  la matriz: con el modo 7 en pantalla multiplica a mano.
* RAM: los bytes de la imagen en `$7F6500`, dentro de `ANIM_DRAWINGS`,
  que es de la imagen mientras está (como su paleta y sus ondas). Opcode:
  `OP_BIG_ZOOM`, `0x43`.

## Lo hecho

* **El conversor** (`c30ea5b0`): la pasada que junta las imágenes anota a
  qué tamaño lleva cada `MovePicture` a su número; la imagen grande que
  algún movimiento de su mapa lleva a otro tamaño pide su textura a
  `rm2k-snes-images` (`mode7.rs`), que la corta de la misma capa del modo
  1. Va ahí porque comparte la capa y sus entradas de CGRAM, no es un
  formato aparte. k-means sobre los tiles promediados de a 2x2, sembrado
  sin azar, y el medoide de cada grupo. Sólo si la capa entra en la mitad
  de arriba: 960 tiles y 32 filas; si no, se sigue apagando como antes.
  `OP_BIG_ZOOM` (0x43) reemplaza a `OP_BIG_MOVE` para esas imágenes.
* **La ROM** (`e14c8912`, `tools/runtime/big_picture_zoom.s`): quieta en
  $4000/$7C00, la textura subiendo a $0000-$3FFF de a 3 KB por vblank; el
  zoom en modo 7 sin cuadros en negro; la ventana de vuelta en la mitad de
  arriba durante el zoom; zoom a cero → modo 1 con la capa apagada y los
  mensajes visibles. Los sprites están apagados como con cualquier imagen
  grande. Y `irq_music` multiplica con una tabla de cuadrados mientras hay
  modo 7, porque el multiplicador de la PPU es la matriz.
* **ABL**, rama `fotos-en-modo-7` del clon de Chajá: dos casos y una prueba
  nuevos, y las goldens (una cambia: `imagen-grande-foto-140`).

Las cuatro fotos Diff llevan textura —y con ellas el montaje del 217, que
usa las mismas capas—: 16 KB de tiles y 3,5 KB de filas cada una, 78 KB.
Las capas del modo 1: 664 tiles PhoneCallDiff y 897 las otras tres.

## Los números

* `just pruebas` en ABL: **1037** (las 1035 de antes y las dos nuevas).
* `abl.sfc`: `ef1bf110a5e1bf1b…` (antes `35ce63c5…`).
* `just -f tools/justfile test`: 27; `cargo test` de los seis proyectos
  tocados, en verde.

## Qué tiene que ver taro en la consola

Capturas, el video y qué mirar: `/shared/capturas/2026-10-03-modo-7/`,
con su `LEEME.txt`. **La golden `imagen-grande-foto-140` espera su visto
bueno.** En el juego: las escenas del 212, 213, 214 y 216 —el salto al
empezar el zoom, la velocidad, el centro, y el mensaje de la viuda en el
212 después del zoom—.

## Al mergear

* Instalar `bytecode cartridge events images mapdata convert`. 0x41 y
  0x42 van reservados en `events.rs` y en `interpreter.s` para Yaguareté:
  al mergear su rama, sus opcodes reemplazan a los reservados.
* Traer primero la rama de ABL, que sin ella la tanda da rojo en la golden
  del 140.

## Lo que no cubre ninguna prueba

Un mensaje con la foto quieta (no se vería: la ventana no está), un zoom
que vuelve a crecer desde cero, uno que termina en otro tamaño y se queda
en modo 7, y uno que llega antes de que la textura terminó de subir (sube
el resto con la pantalla apagada).
