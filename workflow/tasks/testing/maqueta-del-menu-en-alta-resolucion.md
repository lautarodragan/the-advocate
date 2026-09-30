---
name: "Maqueta: el menú en alta resolución"
description: "Antes de tocar la ROM, cómo se vería el menú de pausa en modo 5 (512 de ancho) con la fuente de RM2k escalada ×1,6, al lado de dos alternativas baratas, para que taro elija mirando"
type: research
assignee: taro
---

De taro, el 2026-09-30. El menú original muestra, por actor, el **título**
(`title` en el LDB: "Agency Capt.", "Fugitive"…) y los **SP**, y el nuestro
no, porque a 256 de ancho no entran. Sumar filas estira cada entrada, puede
pedir scroll y queda feo.

La idea de taro: el modo 5 de la PPU da 512 de ancho. El menú original mide
320, y 320 × 1,6 = 512, así que entraría el menú de RM2k entero al 80 % del
ancho. Lo que no se sabe es cómo se ve la fuente escalada ×1,6: unas
columnas de cada letra salen dobles y otras simples. En modo 5 el texto va
en 4 bits, y las caras irían como sprites, que ya son de 15 colores.

Esto es sólo la maqueta: imágenes para mirar, sin cambiar la ROM.

## Qué se armó (Ñacurutú, 2026-09-30)

Las imágenes están en `/shared/capturas/2026-09-30-menu-alta-resolucion/`,
con un `LEEME.txt` que dice qué es cada una: el original, el menú de hoy, el
modo 5 con tres criterios de escalado, las dos alternativas a 256, cada una
como la muestra un emulador (512x448), una hoja con todas al mismo tamaño
físico y recortes ×4 de la fila de Kersh. Los scripts quedaron en el
scratchpad; se usaron `rm2k-render` (ventanas, cursores, colores del texto,
sombra y caras del juego) y `rm2k-snes-screens render` (el menú de hoy). El
menú a 320 que arman los scripts se comparó contra la captura del RPG_RT:
las posiciones coinciden; lo que difiere es la fuente del RPG_RT, que no es
la Mincho de easyrpg, y los degradés de los 16 bits de Wine.

**Lo que se ve:**

* **×1,6 por posición** (02): se lee, pero cada letra sale distinta según
  la columna donde cae; se nota en los dígitos repetidos ("168/168").
* **×1,6 por glifo** (03): letras parejas —tinta 2,2,1,2,2 y aire 1, 10 de
  avance—, pero 10 es más que los 9,6 que deja la disposición de RM2k, y
  donde RM2k empaqueta justo el texto choca: "HP168" y "/168" quedan
  pegados. Arreglarlo sería mover la disposición.
* **×1,5 por glifo** (04): la que mejor se lee según Ñacurutú. 2,1,2,1,2 + 1
  son 9, exactamente ×1,5: letras parejas, simétricas y sin choques. El menú
  mide 480, así que no hizo falta recortar la disposición: sobran 32 de
  alta, que pueden ir de margen —así está— o ensanchar la ventana del grupo.
* **A** (05): "HP168/168 SP168/168" entra en una línea con dígitos de 4
  (termina en x=238). El título al lado del nombre entra para Core y Manta,
  pero **no para Kersh**: la ROM compone el nombre una letra por celda de 8,
  y "Agency Capt." se pasa 14 px del borde. Ninguna variante a 256 lo hace
  entrar para todos: con el nombre a 6 se pasaría igual.
* **B** (06): título y SP del elegido en una línea abajo del grupo, con los
  SP compuestos como hoy los HP. Entra sin tocar nada de arriba.

**La fuente en 4 bits entra.** Medido sobre los glifos: el color 0 del
System usa 4 colores, el 1 (rojo) 8, el 3 (gris) 8, y la sombra 1. Blanco,
rojo y sombra son 13: una paleta para el panel del grupo, donde un mismo
tile mezcla "HP" y "168"; el gris de lo deshabilitado, otra. El peor bloque
de 16x8 lleva 7 colores.

## Lo que costaría cada una en la ROM (estimado, sin implementar)

Mirando `menu.s`, `slots.s`, `screen_bank.s`, `enter_map.s`,
`screens/src/layout.rs` y `docs/port/vram.md`.

### Modo 5

* **Cambiar de modo es barato.** El menú ya abre con la pantalla apagada y
  sube su banco entero (`menu_upload` → `slot_bank_upload`), y al cerrar
  `back_to_map` rearma el mapa con `ppu_init` + `load_map`. Es un
  `BGMODE = 5` al abrir, y lo de volver ya existe. Dos cosas del modo que
  hay que respetar: en modo 5 **las columnas pares salen de la subpantalla**,
  así que BG1, BG2 y los sprites van en `TS` además de `TM`, o falta la
  mitad de los pixeles; y el modo 5 sin entrelazado sigue en 224 líneas: el
  menú de 240 pierde 16, que salen de la ventana del grupo y del oro (así
  está la maqueta).
* **Las capas cambian de profundidad.** Hoy el menú es modo 3 y todo va en
  BG2 de 4 bits (texto y caras, una paleta por cara) y la barra en BG1. En
  modo 5, BG1 es de 4 bits y BG2 de 2: el texto a BG1, y las ventanas, la
  barra y el cursor a BG2 —las ventanas de ablskin tienen 4 colores con el
  negro, que puede ser el fondo, y la barra y el cursor, uno cada uno—.
* **Las caras, a sprites.** En modo 5 los sprites siguen a 256: cada pixel
  ocupa 2 de alta, en X par, que es lo que se quiere. Una cara de 48x48 son
  36 tiles; tres, 108 tiles, unos 3,5 KB. Los colores son los de hoy: 21 a
  29 por cara, que Adeleine baja a 15, y cada una con su paleta de sprite
  (hay 8; hoy una se usa para el Ex, que en modo 5 pasaría al fondo).
  `menu_exp_paint`/`menu_exp_close` ya cambian y reponen `OBSEL` al entrar y
  salir, así que ese camino existe.
* **El texto no se puede componer como hoy.** Hoy el nombre, el nivel y los
  HP van una letra por celda de 8 (`layout.rs`, "composed one letter per
  cell"), y el Ex en sprites. En modo 5 una celda del tilemap mide 16 de
  alta —dos tiles de 8 lado a lado—, y un glifo mide 9,6, 10 o 9: no cae
  alineado con nada, y dos glifos comparten tile. Hay dos caminos:
  - **Hornear todo en el conversor.** Las órdenes, los términos y "Normal"
    sí, porque son pocos. Los nombres y títulos de los 50 actores con nombre
    suman 548 letras: a 10 de avance y dos filas de tiles son unos 1.400
    tiles, **~44 KB de ROM** sin comprimir. Y los números (HP, SP, Ex,
    nivel, oro) no se pueden hornear: son demasiados.
  - **Una fuente de ancho variable en la ROM** (el "VWF" de los juegos de
    SNES traducidos): la fuente escalada guardada como máscaras de 1 bit
    —95 glifos × 12 filas × 2 bytes, ~2,3 KB— y una rutina que la corre y
    la mezcla en un búfer de tiles de 4 bits en la RAM, con la sombra y el
    color de cada fila del degradé, y lo sube por DMA. Es la opción
    realista: unos cientos de bytes de código nuevo, y con la pantalla
    apagada el costo de CPU no se ve (~150 glifos por menú).
  - Una intermedia para los números: pares de dígitos pre-armados en
    celdas de 16 (100 pares, ~6 KB de VRAM), con los dígitos a 8 de avance
    en vez de 9,6: más angostos que las letras.
* **VRAM.** Medido sobre la maqueta: el texto ocupa entre 515 y 560 tiles
  de 8x8 con algo (**16 a 18 KB**), de los que 413 a 486 son distintos. Más
  dos tilemaps de 2 KB y ~3,5 KB de caras: **unos 25 KB**. Entra en los
  64 KB, pero pisa más que lo que pisa hoy la pantalla de ranuras
  ($2000..$4000, `SLOT_VRAM`/`SLOT_MAP` de `tools/port/vram.py`): hay que
  confirmar que `load_map` repone todo lo que el menú pise, sprites
  incluidos.
* **Riesgo que la maqueta no muestra**: por compuesto o RF, una columna de
  un pixel de alta resolución está al borde del ancho de banda del video
  NTSC y se borronea; por RGB, HDMI o un emulador se ve como la maqueta.
  Algunos emuladores, además, mezclan los pixeles de alta resolución por
  omisión. Conviene que taro lo mire en la SNES con la salida que usa.

**En resumen**: el modo y las caras son baratos porque el menú ya apaga la
pantalla y rearma el mapa; lo caro es el texto, que pide un renderizador de
ancho variable en la ROM.

### Si el mismo camino serviría para otras pantallas

Sí, y es el argumento más fuerte a favor. Una vez que existen el cambio de
modo, la VWF y las caras en sprites, **cualquier pantalla de RM2k entra con
su disposición de 320 entera**: la lista de ítems en dos columnas (hoy una
sola, `layout.rs`: "RM2k's two do not fit"), el equipamiento con sus
parámetros y la lista, las técnicas, la tienda y las ranuras. Cada pantalla
sigue pidiendo su port de disposición, como hoy. Lo que se agrega en las
que tienen lista con scroll: redibujar la fila que entra —dos ítems en dos
columnas son ~80 tiles, 2,5 KB— en el vblank, que entra en lo que el DMA
llega a subir por cuadro.

### A: dígitos angostos

Los dígitos a 4 no caben en una celda de 8 uno por celda: dos comparten
tile. Van en **sprites**, como hoy el Ex (`menu_exp_paint`), con 11 tiles
nuevos (0-9 y la barra). Por actor son 16 sprites más para la línea del HP y
el SP, 48 para tres: con el Ex, que ya usa 15 por actor, van ~93 de 128. Lo
que puede morder es el **límite de 32 sprites por línea**: la línea del HP
(16) y la del Ex (15) se tocan en una fila, la de la sombra, y ahí son 31.
El título: entra sólo cuando es corto —no entra el de Kersh—, y sería texto
por actor horneado o en sprites. Un día de trabajo.

### B: sólo el elegido

La más barata: una línea más con el título —en sprites a 6, como el Ex— y
los SP compuestos una cifra por celda como hoy los HP (`menu_hp_write`). Se
redibuja cuando la barra cambia de actor. Horas, no días.
