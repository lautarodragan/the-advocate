# Los panoramas

> **Escrito el 2026-10-05 sobre `9b180286`**, por Cardón, con ABL en
> `a94288b`. Es una foto: los números son de ese día y este archivo no se
> actualiza. Cómo rehacer cada cuenta está al final, en "Cómo se midió".

El panorama es el fondo de parallax de RM2k: una imagen detrás del mapa que
se ve por donde la capa de abajo no dibuja, y que se mueve sola o con la
cámara a otra velocidad que el mapa. En el port sale negro. taro, el
2026-10-05: algunos se pueden resolver con parches —el emitter room, la
ventana de la oficina del director—, pero otros "son bastante importantes …
sobre todo cuando sí tienen efecto parallax y se mueven a distinta
velocidad que el mapa": el puente de arriba, el de abajo, el techo de Lashe
City y la intro con Kersh.

El encargo: medir todos los mapas con panorama, hacer andar los dos del
puente —el de arriba con el camino A, el de abajo con el B—, medir el techo
y la intro, y decir lo que cuesta. Sin llevarlo a todo el juego.

## Resumen

* **De los 45 mapas con panorama, a 4 no se les ve nunca y a 9 apenas**
  (una ventana, un hueco), y otros 4 no se mueven contra el mapa: 17 que no
  piden una capa. Ver "Los 45".
* **Andan los dos del puente**, en la rama de Cardón: el de arriba (259) en
  modo 3 con el panorama en BG2 a 4 bits, el de abajo (255) en modo 1 con
  el panorama en BG3 a 2 bits. Se mueven como `Game_Map::Parallax`, y el
  del 259 **cae en el mismo pixel que en el original** —medido contra el
  RPG_RT con Wine—. Las capturas acompañan este estudio en la entrega de
  ese día, `2026-10-05-panoramas`.
* **Lo que limita no es la capa sino los colores y los tiles.** Un
  panorama trae entre mil y cuatro mil tiles distintos y la VRAM le deja
  576 (A) o 768 (B): se agrupan los parecidos (Adeleine, `group_tiles`), y
  se nota en el grano, poco. Y los del RTP tienen celdas de 8x8 con hasta
  50 colores: **a 4 bits quedan en unos 15** y se ven casi iguales; **a 2
  bits quedan en 4** y las nubes se aplanan.
* **Así que el B, tal como está pedido, sirve para el 255 y no para los
  del RTP.** Para los mapas que dibujan algo encima del héroe hay un camino
  mejor casi siempre: **modo 3 con lo de encima dibujado abajo**, cuando
  eso es poco —dos celdas en el techo de Lashe, catorce en los miradores—.
  Y para los que no se mueven, **hornear el panorama en el fondo**, sin
  capa. Ver "Mejor que A y B".
* **La lluvia ya convive**: es de objetos, y no toca ni las capas ni la
  mitad de abajo de la CGRAM. Probado con la intro: llueve sobre el
  panorama. Lo único que hubo que hacer es subirle la prioridad en modo 1.
* **El costo**, con los dos del puente: 41 KB de ROM sin comprimir, 224
  bytes de RAM lejana, unos 100 bytes del banco 0 y 1,6 KB de `FAR2`. Ver
  "El costo".

## Lo que hace RM2k

`Game_Map::Parallax`, en `easyrpg-player`, en sus unidades: la posición del
panorama, `pan_x`, va en 1/32 de pixel, y en pantalla el panorama empieza en
su pixel `pan_x / 32`.

* **Uno que hace loop en un eje** arranca en la posición de la cámara y
  suma lo que la cámara se mueve: como la cámara va en 1/16, el panorama
  va **a la mitad**. Si además se mueve solo, cada cuadro suma
  `-(1 << velocidad)` —o `1 << -velocidad`—: la 1 es 1/16 de pixel por
  cuadro, la 8 son 8 pixeles.
* **Uno que no hace loop** va de su primer pixel al último mientras la
  cámara va de un borde del mapa al otro: `min(w, ancho - 320) * cámara /
  w`, con `w` lo que la cámara recorre. En un mapa de una pantalla no se
  mueve.
* **No tiene color transparente**: el índice 0 se dibuja, a diferencia de
  un ChipSet. Hasta que se cargó así, el 259 salía con una franja de
  puntos negros.
* **La cámara de RM2k no es la de la consola.** RM2k pone al héroe a nueve
  celdas del borde izquierdo y a siete del de arriba
  (`Game_Player::GetDefaultPanX`) en una pantalla de 320x240; la consola lo
  centra en 256x224. El prototipo ubica el panorama **detrás de la cámara
  de RM2k** y lo corre lo que la de la consola está lejos de ésa: así queda
  detrás del mapa donde RM2k lo pone, y una captura del original coincide
  con el pedazo que muestra la consola.
* **`ChangePBG` cambia el panorama a mitad del mapa.** Lo usa una sola
  página del juego, el viaje en el Hover-Tram (13). El prototipo no lo
  hace: sigue aceptado y tirado.

## Una corrección al encargo

El camino A decía "la capa de abajo usa sólo los colores 128 a 255". **La
mitad de arriba de la CGRAM es de los sprites** (`docs/port/cgram.md`): el
fondo de 8 bits podría leer esas entradas, pero tendría que conformarse con
los colores de los personajes. Lo que A reparte es la mitad de abajo, como
hoy entre el fondo y la capa de encima: **el fondo elige primero** las
paletas que necesita y el panorama se queda con las que sobran. En el 259
el fondo tiene 18 colores y al panorama le quedan tres paletas, que le
alcanzan para sus 30 colores sin fusionar ninguno.

## Los 45

Medido con el conversor del prototipo sobre cada mapa, aunque no esté en
`release` ("fuera"). Las columnas:

* **se mueve**: "x ½" es loop con la cámara, a la mitad; "x sola +3" es
  además la velocidad propia; "con la cámara" es sin loop, de punta a
  punta.
* **se ve**: qué parte de la capa de abajo es transparente, o sea por dónde
  asoma el panorama. Cero es que no se ve nunca.
* **encima**: cuántos tiles tiene lo que va encima del héroe; cero es que
  el mapa entra en A.
* **fondo**: tiles y colores de la capa de abajo, sin el panorama.
* **modo**: el que eligió el prototipo: 3 si no hay nada encima, 1 si hay.
* **panorama**: tiles que quedan de los distintos que tiene —contando los
  espejados como uno—, y colores que quedan de los que trae.

| mapa | | tamaño | panorama | se mueve | se ve | encima | fondo: tiles, colores | modo | panorama: tiles de distintos, colores |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Introduction; lluvia | 100x100 | Night1 640x480 | x sola +3 | 23% | 52 | 338, 49 | 1 | 729 de 862, 4 de 58 |
| 2 | Linkage Block | 100x100 | screen 320x240 | y sola +4 | 28% | 63 | 272, 60 | 1 | 725 de 806, 5 de 11 |
| 3 | Emitter Room; parche: emitter | 75x75 | Weird 640x480 | y sola -6 | 0% | 16 | 256, 75 | 1 | 617 de 4800, 4 de 254 |
| 6 | CoreRetro II | 100x100 | Night2 640x480 | con la cámara | 74% | 22 | 78, 39 | 1 | 715 de 1814, 4 de 40 |
| 8 | Lashe City - 34,35 | 75x75 | Planet1 320x240 | con la cámara | 0% | 0 | 400, 63 | 3 | 419 de 938, 17 de 227 |
| 13 | Hover-Tram; ChangePBG | 20x15 | Evening2 640x480 | x sola +5 | 1% | 0 | 42, 22 | 3 | 576 de 1441, 15 de 157 |
| 16 | Running To Work Scene | 75x75 | Evening1 640x480 | con la cámara | 22% | 0 | 332, 62 | 3 | 576 de 1058, 15 de 136 |
| 19 | Talan and the Director; parche: ventana del director | 20x15 | OfficeView 640x320 | con la cámara | 5% | 0 | 134, 51 | 3 | 575 de 1195, 20 de 168 |
| 32 | Sector 27 Warehouse | 50x50 | Dawn1 640x480 | con la cámara | 42% | 4 | 210, 58 | 1 | 726 de 935, 4 de 79 |
| 33 | Escape From 27 Scene | 50x50 | Dawn1 640x480 | con la cámara | 14% | 5 | 222, 54 | 1 | 726 de 935, 4 de 79 |
| 34 | AfterGettingCarCutscene; parche: ventana del director | 20x15 | OfficeView 640x320 | con la cámara | 5% | 0 | 154, 62 | 3 | 575 de 1195, 20 de 168 |
| 43 | Vidcasts (Office); parche: ventana del director | 20x15 | OfficeView 640x320 | con la cámara | 5% | 0 | 154, 62 | 3 | 575 de 1195, 20 de 168 |
| 45 | Security Footage; parche: ventana del director | 20x15 | OfficeView 640x320 | con la cámara | 5% | 0 | 134, 51 | 3 | 575 de 1195, 20 de 168 |
| 51 | Jumping the Bridge | 200x40 | lashepan 640x320 | x sola -4 | 57% | 0 | 217, 58 | 3 | 573 de 3154, 20 de 179 |
| 64 | Leaving Lashe City Scene | 20x15 | lashepan 640x320 | con la cámara | 43% | 0 | 100, 34 | 3 | 559 de 1182, 17 de 133 |
| 76 | Sorbe Mountain | 30x50 | Morning1 640x480 | con la cámara | 0% | 55 | 164, 59 | 1 | 621 de 663, 4 de 89 |
| 82 | Director'sOfficeNextStep; parche: ventana del director | 20x15 | OfficeView 640x320 | con la cámara | 5% | 0 | 134, 51 | 3 | 575 de 1195, 20 de 168 |
| 94 | Missiles On Their Way1 | 20x15 | pan2 640x480 | y sola +8 | 100% | 0 | 1, 0 | 3 | 576 de 947, 17 de 51 |
| 95 | Into The Machine | 50x50 | TasgardePan 640x320 | con la cámara | 50% | 3 | 160, 39 | 1 | 765 de 1084, 4 de 7 |
| 96 (fuera) | Backup | 20x15 | Dawn1 640x480 | con la cámara | 1% | 12 | 96, 60 | 1 | 218 de 232, 4 de 79 |
| 99 | Missiles On Their Way2 | 20x15 | pan2 640x480 | y sola +8 | 100% | 0 | 1, 0 | 3 | 576 de 947, 17 de 51 |
| 104 (fuera) | Overlook Memory | 20x30 | Night1 640x480 | x sola -2 | 40% | 8 | 120, 14 | 1 | 729 de 862, 4 de 58 |
| 105 | Mountain Path | 70x30 | Evening1 640x480 | x sola +2 | 41% | 55 | 72, 44 | 1 | 724 de 1058, 4 de 136 |
| 109 | Paradise Overlook | 20x30 | Night1 640x480 | y ½ | 40% | 8 | 120, 14 | 1 | 417 de 433, 4 de 57 |
| 126 | OverlookAtDay | 20x30 | Morning1 640x480 | x sola +1, y ½ | 40% | 8 | 120, 14 | 1 | 721 de 903, 4 de 89 |
| 167 (fuera) | Outside the Bandit HQ | 20x40 | Evening1 640x480 | y ½ | 0% | 0 | 40, 43 | 3 | 458 de 522, 15 de 136 |
| 175 | Mountain Flashback | 20x15 | Night1 640x480 | con la cámara | 23% | 0 | 101, 12 | 3 | 218 de 217, 15 de 56 |
| 176 | Overlook | 20x15 | Night1 640x480 | con la cámara | 80% | 0 | 19, 21 | 3 | 218 de 217, 15 de 56 |
| 203 (fuera) | Up The Overlook | 20x30 | Night1 640x480 | y ½ | 40% | 8 | 120, 14 | 1 | 417 de 433, 4 de 57 |
| 205 (fuera) | Beach Scene | 20x30 | Night1 640x480 | con la cámara | 10% | 0 | 49, 51 | 3 | 433 de 433, 15 de 57 |
| 224 (fuera) | Overlook Memory; lluvia | 20x30 | Night1 640x480 | y ½ | 40% | 8 | 120, 14 | 1 | 417 de 433, 4 de 57 |
| 227 (fuera) | Leaving Lashe Memory | 20x15 | lashepan 640x320 | con la cámara | 43% | 0 | 100, 34 | 3 | 559 de 1182, 17 de 133 |
| 228 (fuera) | Assassination Memory; parche: ventana del director | 20x15 | OfficeView 640x320 | con la cámara | 5% | 0 | 134, 51 | 3 | 575 de 1195, 20 de 168 |
| 236 (fuera) | Kersh On The Overlook | 20x30 | Night1 640x480 | y ½ | 40% | 8 | 120, 14 | 1 | 417 de 433, 4 de 57 |
| 241 (fuera) | Tram to Prima | 20x15 | PrimaTunnel2 640x480 | x sola -7 | 25% | 0 | 109, 45 | 3 | 576 de 1393, 17 de 63 |
| 255 | Under the Bridge | 75x25 | undrbrdgpan 640x320 | x sola +1, y sola +1 | 56% | 8 | 66, 39 | 1 | 768 de 1760, 4 de 6 |
| 259 | Northern Highway Bridge | 70x15 | seapan 640x320 | con la cámara | 82% | 0 | 16, 18 | 3 | 576 de 1435, 30 de 30 |
| 260 (fuera) | Surl Highway | 70x15 | desertpan 640x320 | con la cámara | 80% | 0 | 21, 10 | 3 | 576 de 1840, 13 de 13 |
| 267 (fuera) | Kersh and the Droid Army | 70x15 | desertpan 640x320 | con la cámara | 80% | 0 | 21, 10 | 3 | 576 de 1840, 13 de 13 |
| 268 (fuera) | Emitter Room; parche: emitter | 20x15 | Weird 640x480 | y sola -6 | 1% | 8 | 128, 60 | 1 | 666 de 2400, 4 de 254 |
| 300 (fuera) | Missiles2 | 20x15 | pan2 640x480 | y sola +8 | 100% | 0 | 1, 0 | 3 | 576 de 947, 17 de 51 |
| 301 (fuera) | The Overlook | 20x30 | Dawn1 640x480 | x sola -1 | 40% | 8 | 120, 14 | 1 | 726 de 935, 4 de 79 |
| 303 (fuera) | Tram to Prima | 20x15 | PrimaTunnel2 640x480 | x sola -7 | 25% | 0 | 109, 45 | 3 | 576 de 1393, 17 de 63 |
| 306 (fuera) | Outside Ship | 20x40 | starpan 640x320 | y sola +7 | 80% | 0 | 109, 41 | 3 | 51 de 50, 15 de 15 |
| 313 | Agency Tram | 20x15 | woodspan 640x320 | y sola +3 | 39% | 0 | 118, 32 | 3 | 25 de 24, 7 de 7 |

Agrupados por lo que piden:

* **No se ven nunca** (0%): 3, 8, 76 y 167. El emitter room grande (3)
  tiene el exterior en un tile negro opaco, no transparente. Nada que
  hacer, salvo que algún evento destape algo.
* **Se ven por un hueco** (5% o menos): la oficina del director —19, 34,
  43, 45, 82, 228: la ventana—, el emitter room chico (268), el Hover-Tram
  (13) y el 96. Son los que taro dijo de resolver con un parche de ABL: el
  emitter como tile o CharSet animado, la ventana de la oficina como
  ChipSet. **Hornearlos** —ver abajo— hace lo mismo sin parche, salvo el
  13, que se mueve solo y cambia de panorama.
* **Quietos** —una pantalla de RM2k, sin velocidad propia—: 64, 175, 176
  (y 227 fuera). No piden capa: se hornean.
* **Se mueven y no tienen nada encima**: 16, 51, 94, 99, 259, 313 (y fuera
  205, 241, 260, 267, 300, 303, 306). Son A.
* **Se mueven y tienen algo encima**: 1, 2, 6, 32, 33, 95, 105, 109, 126,
  255 (y fuera 104, 203, 224, 236, 301). B, o mejor otra cosa.

## Los colores y los tiles

**Los tiles.** Un panorama de 640x320 con grano tiene más de mil tiles
distintos aun contando los espejados como uno —seapan 1435, lashepan 3154,
Weird 4800— y la VRAM le deja 576 en A y 768 en B. Así que los parecidos
se dibujan con uno solo: un k-means sobre los tiles promediados de a dos
por dos, y cada grupo con el que más se parece a los demás, que es lo que
`rm2k-snes-images` ya hacía para las texturas de modo 7. Quedó en Adeleine
como `group_tiles`, porque cambia lo que se ve. En el 259 se nota en el
grano del mar y de las nubes, y nada en la forma: ver
`capitulo-259-llegada.png` en las capturas.

**Los colores.** Los panoramas de ABL tienen pocos —seapan 30, desertpan
13, woodspan 7, undrbrdgpan 6— y entran enteros a 4 bits. Los del RTP son
degradés: celdas de 8x8 con 34 a 50 colores. A 4 bits una celda tiene 15,
así que Adeleine fusiona hasta que entran, y quedan en unos 15 en total;
**se ven casi iguales**, porque son grises y azules vecinos. A 2 bits quedan
en 4 —tres por paleta y el fondo de la pantalla—, y **las nubes se
aplanan**: `rtp-night1-8-4-2-bits.png` y `rtp-evening1-8-4-2-bits.png`,
el original, a 4 y a 2.

Y en B el mapa va a 4 bits, con paletas de 15 por celda, y también
fusiona: el 255 de 39 a 22 —marrones oscuros vecinos, que no se notan—,
la intro de 49 a 20, el emitter de 75 a 19.

## Mejor que A y B

**Modo 3 con lo de encima dibujado abajo.** Cuando lo que va encima del
héroe es poco, se lo dibuja en el fondo y el mapa entra en A. Lo que se
pierde es que el héroe pase por detrás de esas celdas: en el techo de
Lashe son dos (el 33), en los miradores catorce, en el 255 las cadenas.
Medido forzando el modo 3:

| mapa | modo 1: fondo, panorama | modo 3 con lo de encima abajo: fondo, panorama |
|---|---|---|
| 1 Introduction | 20 de 49, 4 de 58 | 55 de 55, 15 de 58 |
| 2 Linkage Block | 20 de 60, 5 de 11 | 69 de 67, 6 de 11 |
| 3 Emitter Room | 19 de 75, 4 de 254 | 78 de 78, 15 de 254 |
| 6 CoreRetro II | 28 de 39, 4 de 40 | 42 de 42, 15 de 40 |
| 32 Sector 27 Warehouse | 24 de 58, 4 de 79 | 60 de 60, 15 de 79 |
| 33 Escape From 27 Scene | 21 de 54, 4 de 79 | 54 de 54, 15 de 79 |
| 76 Sorbe Mountain | 19 de 59, 4 de 89 | 60 de 60, 15 de 89 |
| 95 Into The Machine | 30 de 39, 4 de 7 | 39 de 39, 7 de 7 |
| 96 Backup | 29 de 60, 4 de 79 | 60 de 60, 15 de 79 |
| 104 Overlook Memory | 14 de 14, 4 de 58 | 14 de 14, 15 de 58 |
| 105 Mountain Path | 22 de 44, 4 de 136 | 46 de 46, 15 de 136 |
| 109 Paradise Overlook | 14 de 14, 4 de 57 | 14 de 14, 15 de 57 |
| 126 OverlookAtDay | 14 de 14, 4 de 89 | 14 de 14, 15 de 89 |
| 203 Up The Overlook | 14 de 14, 4 de 57 | 14 de 14, 15 de 57 |
| 224 Overlook Memory | 14 de 14, 4 de 57 | 14 de 14, 15 de 57 |
| 236 Kersh On The Overlook | 14 de 14, 4 de 57 | 14 de 14, 15 de 57 |
| 255 Under the Bridge | 22 de 39, 4 de 6 | 43 de 43, 6 de 6 |
| 268 Emitter Room | 23 de 60, 4 de 254 | 61 de 61, 16 de 254 |
| 301 The Overlook | 14 de 14, 4 de 79 | 14 de 14, 15 de 79 |

(El fondo con lo de encima trae los colores de las dos capas: por eso el 2
termina con más de los que tenía.) Está en la rama —`"mode": 3` en el
pedido de `wally`—, sólo para medir: el cartucho no lo pide todavía. La
comparación a ojo, en `modo1-contra-modo3-con-lo-de-encima-abajo.png`: el
techo (33), la intro (1), el camino de la montaña (105) y el mirador de
día (126), izquierda modo 1, derecha modo 3. Lo que va encima se puede
también dibujar con objetos en vez de en el fondo, si no son muchos por
pantalla —en el 255 son 25, en los miradores 12, en la intro 127—, pero
gasta paletas de sprite, que ya escasean.

**Hornear los quietos.** En un mapa de una pantalla de RM2k sin velocidad
propia el panorama no se mueve contra el mapa: se puede pintar en la capa
de abajo al convertir, y no pide capa ni modo. Lo que cuesta es fondo:

| mapa | panorama | tiles del fondo | colores del fondo |
|---|---|---|---|
| 19 Talan and the Director | OfficeView | 134 → 200 | 51 → 131 |
| 34 AfterGettingCarCutscene | OfficeView | 154 → 213 | 62 → 136 |
| 43 Vidcasts (Office) | OfficeView | 154 → 213 | 62 → 136 |
| 45 Security Footage | OfficeView | 134 → 200 | 51 → 131 |
| 64 Leaving Lashe City Scene | lashepan | 100 → 612 | 34 → 155 |
| 82 Director'sOfficeNextStep | OfficeView | 134 → 200 | 51 → 131 |
| 175 Mountain Flashback | Night1 | 101 → 139 | 12 → 64 |
| 176 Overlook | Night1 | 19 → 215 | 21 → 77 |
| 227 Leaving Lashe Memory | lashepan | 100 → 612 | 34 → 155 |
| 228 Assassination Memory | OfficeView | 134 → 200 | 51 → 131 |

A 8 bits no hay paletas por celda: la oficina se queda con unos 98 de sus
131 colores, contra los 20 que le deja A. Los 612 tiles del 64 no entran
en ningún reparto y pedirían agruparlos. Esto resuelve también la ventana
del director, sin parche.

**Otros dos, sin probar.**

* **El panorama en BG2 a 4 bits y lo de encima en BG3 a 2 bits**, con la
  prioridad de BG3 arriba de todo (el bit 3 de `BGMODE`). El panorama no
  se aplana; lo de encima sí, y tapa la ventana de mensajes, así que hace
  falta un canal de HDMA que apague BG3 en sus líneas. Para la intro, que
  tiene 707 celdas encima, es el que queda.
* **El panorama en BG1 a 8 bits y el mapa en BG2 a 4 bits, con prioridad
  1.** El panorama con todos sus colores, para los fotográficos —la
  oficina, lashepan—, a cambio de la mitad de tiles y del mapa a 4 bits.
  El héroe pasa a la prioridad 2, como en modo 1.

## El prototipo

En la rama de Cardón de las herramientas y en la rama `panoramas` de su
clon de ABL, con `[maps] panoramas = [259, 255]` en `rm2k-snes.toml`. Un
mapa que no está en esa lista convierte como siempre, y un cartucho sin
ninguno sale con el `.inc` de siempre.

**El conversor.** `wally` recibe en el pedido cuántos tiles deja cada modo;
dibuja la capa de abajo transparente donde no hay nada
(`render_over_panorama` en `rm2k-render`) y recorta el panorama a lo que la
consola puede llegar a ver —en el 259, las 240 filas de arriba—. Si el mapa
no dibuja nada encima del héroe va en modo 3: el panorama se lleva las
paletas que el fondo deja, y viajan como las de la capa de encima, que es
lo que el registro sube, tiñe y repone (`background::panorama`). Si
dibuja, va en modo 1: el mapa a 4 bits con sus paletas desde la 2, lo de
encima como siempre, y el panorama a 2 bits en las paletas 4 a 7 de BG3
—entradas 16 a 31—, con el color que más dibuja en el fondo de la pantalla
(`background::mode1`). Voodoo aprendió los 2 bits. `rm2k-snes-mapdata`
tiene dos repartos de VRAM nuevos, que `vram_layout` no da nunca a un mapa
sin panorama, y emite `pano_table`: por mapa, cómo se mueve, sus tiles y su
tilemap. Ver `panorama.rs`.

**El runtime**, `pano.s`:

* **El panorama es un anillo.** Mide 640 y el tilemap 512, así que la
  consola lleva una posición corrida —`PANO_UX`—, que da la vuelta donde la
  dan el tilemap y el panorama a la vez, su mínimo común múltiplo, y la
  escribe tal cual en el registro de scroll. El tilemap tiene las 64
  columnas y 32 filas alrededor, y cada cuadro se escriben a lo sumo una
  columna y una fila, como las del mapa.
* **Dónde va** es `Game_Map::Parallax` con la cámara de RM2k, más la
  distancia a la de la consola. El cociente de los que no hacen loop es
  exacto: un producto de 32 bits y una división larga.
* **Modo 3**: el tilemap del panorama es el de la capa de encima, y la ROM
  no le sube las tiras de esa capa. El scroll de BG2 va en el registro y en
  los tramos del mapa del HDMA de la ventana.
* **Modo 1**: `ppu_init` —por donde pasa toda vuelta al mapa— y la carga
  ponen el modo 1 y BG3; las pantallas que se abren encima vuelven al 3
  (`slot_ppu_on`, `screen_ppu_on`, `target_ppu_on`). Y los objetos suben
  una prioridad, porque en modo 1 el mapa está un escalón más arriba que en
  modo 3: así el orden entre mapa, héroe, capa de encima y ventana es el
  mismo.

**Lo verificado**, con los cartuchos del prototipo:

* **El 259 contra el original**: con el héroe donde llega, la franja del
  panorama que no tapa nada es la de RM2k corrida exactamente a donde la
  pone la fórmula —0 pixeles distintos entre el RPG_RT y el panorama en el
  pixel 320—, y la de la ROM es lo que decidió el conversor en el pixel
  384, que es ése más los 64 que la cámara de la consola está corrida: 0
  pixeles distintos. Lo que difiere del original es lo agrupado.
* **El anillo**: caminando el 259 de punta a punta, y con el 255 moviéndose
  solo, el tilemap que la ROM fue armando columna a columna es igual,
  entrada por entrada, al que arma de cero un teletransporte al mismo
  lugar.
* **Los cuadros perdidos**: ninguno en 600 ticks caminando el 259 ni
  quieto en el 255; 2 en 600 caminando el 255, donde a veces se arman una
  columna y una fila del panorama en el mismo cuadro que una del mapa.
* **La tanda de ABL**, entera: fallan las cinco goldens de los dos mapas
  —las llegadas al 259 y al 255, y las tres del cartel de abajo del
  puente—, y la de los parches, porque el 255 fusiona colores nuevos. Nada
  más se movió. **Las goldens no están bendecidas**: van lado a lado, con el
  original, en las capturas de la entrega.
* **El menú y una pelea desde el 255**, con un caso descartable: las dos
  pantallas se dibujan en modo 3 y al cerrarlas el mapa vuelve al 1 con su
  panorama (`modo1-menu-y-pelea-desde-el-255.png`).
* **Lo que no cubre ninguna prueba de la tanda**: que el panorama se mueva
  —las goldens son de la llegada—, el menú y la pelea de arriba, un
  `ChangePBG`, una imagen grande en un mapa en modo 1, y guardar y
  cargar.

## El techo de Lashe City y la intro

**El techo.** Escapando de los agentes es, por lo que muestra, el
`Escape From 27 Scene` (33), con el mismo depósito que el 32: Dawn1, sin
loop, con la cámara, por el 14% del mapa. Tiene **dos celdas** encima del
héroe, así que el prototipo lo manda a modo 1, y ahí el atardecer queda en
cuatro colores y el mapa en 21 de 54. Con lo de encima dibujado abajo va en
modo 3: Dawn1 con 15, el mapa entero. Es el ejemplo más claro de ese
camino. (Si el techo es el de `Jumping the Bridge` (51) —lashepan, solo a
-4, sin nada encima—, es A: 20 de 179 colores y 573 de 3154 tiles.)

**La intro** (1): Night1 con loop horizontal y velocidad 3, por el 23% del
mapa, con 52 tiles encima del héroe en 707 celdas —127 en una pantalla—.
Va en modo 1: las nubes en 4 grises, el mapa en 20 de 49. Para que las
nubes no se aplanen hace falta el panorama en BG2 a 4 bits y lo de encima
en BG3, que no está.

**La lluvia ya está hecha** (`rain.s`) y **convive con el panorama**: son
objetos, con una paleta de sprite y sus tiles al final del banco de
sprites, así que no toca ni las capas ni la mitad de abajo de la CGRAM. Lo
probé armando la intro con su panorama: llueve encima del cielo
(`intro-con-panorama-y-lluvia-770.png`; no está en la rama, era para
ver). Hubo que hacer una sola cosa: en modo 1 las gotas
suben a la prioridad 3, como todos los objetos. Lo que sí compite es lo
que ya competía: el reparto de modo 1 deja 256 tiles de sprite —la intro
usa 222 con las gotas— y las paletas de sprite, donde hoy las gotas no
entran en el 2 y el 3 y no llueve, con o sin panorama.

## El costo

Con los dos del puente, medido con `just espacio release` de ABL contra el
`release` de su `main`:

* **VRAM**: dos repartos nuevos, en `docs/port/vram.md`. En modo 3 el
  panorama tiene 576 tiles de 4 bits y el mapa queda con 256 de fondo y
  384 de sprites; en modo 1, 768 de 2 bits, y el mapa con 512 de fondo a 4
  bits y 256 de sprites. El 259 y el 255 entran sobrados; un mapa grande
  como el 8 o el 16, con 400 y 332 tiles de fondo, no entra en A tal como
  está, y pide otro reparto o achicar el panorama.
* **ROM**: los tiles y el tilemap sin comprimir. 259: 18 KB de tiles y
  4,7 KB de tilemap; 255: 12 KB y 6,3 KB. Comprimidos con LZ2 como el
  resto bajarían, pero los tiles del anillo se leen del cartucho al
  armarlo y habría que descomprimirlos a la WRAM.
* **RAM**: 224 bytes de la lejana, `$7E7E00` a `$7E7EDF`, entre la tabla
  del crecimiento y `CARRY_MAP`. Hay un `.assert` para que el crecimiento
  no se meta: hoy usa 216 de los 256 que tenía. Nada del banco 0.
* **Banco 0**: unos 100 bytes —los enganches en el vblank, en
  `emit_object`, en la lluvia y en la carga—. El resto, 1,6 KB, en `FAR2`.
* **Por cuadro**: el cálculo de la posición —una división larga por eje si
  no hace loop— y a lo sumo una columna de 32 entradas y una fila de 64; en
  el vblank, 64 y 128 bytes de DMA.
* **El conversor**: `rm2k-render` (la capa transparente), Voodoo (los 2
  bits), Adeleine (`group_tiles`), `wally` (`background::panorama`,
  `background::mode1`, el pedido), `rm2k-snes-mapdata` (los repartos,
  `panorama.rs`, la animación del ChipSet a 4 bits) y `rm2k-snes-convert`
  (la lista del proyecto y el reparto de cada mapa). Ninguno cambia nada
  para un mapa sin panorama, y un cartucho sin ninguno sale con el `.inc`
  de siempre: lo cuidan las pruebas de `rm2k-snes-mapdata`, que comparan
  la emisión entera contra la que escribía el Python.

## Lo que falta para llevarlo a todo el juego

* **Elegir el camino por mapa.** Hoy el prototipo elige solo, por si hay
  algo encima; el modo 3 con lo de encima abajo existe en `wally` pero no
  en el proyecto. Y hornear los quietos, que no está.
* **`ChangePBG`**, para el Hover-Tram: cambiar tiles, paletas y velocidad a
  mitad del mapa.
* **La partida**: RM2k guarda la posición del panorama; la consola no, y al
  cargar arranca de cero.
* **Las decisiones en `parches/`**: lo agrupado y lo fusionado del panorama
  no se escribe ahí, sólo las fusiones del mapa.
* **Lo que no cubre la tanda** —ver arriba— y una prueba que mire el
  panorama moviéndose.
* **El tinte** no llega al color del fondo de la pantalla en modo 1, que es
  parte del panorama del 255.
* **Adeleine**: `try_pack` acepta una celda con más colores que una paleta
  como un grupo propio, y la paleta se desborda en la siguiente. El
  panorama es lo primero que tiene celdas así, y lo esquiva con su propio
  `pack`; si algún mapa de hoy tiene una celda de 16 colores en la capa de
  encima, le pasa. No lo medí.

## Cómo se midió

**Un mapa**, con el `wally` de la rama, aunque no esté en ningún cartucho:

    wally layers --data <dump> --search-dir <juego> --search-dir <rtp> \
        --request pedido.json --out <dir>

con `{"map": N, "map_files": {}, "chipset_files": {}, "baked": [],
"window_colors": 13, "panorama": {"tiles_mode3": 576, "tiles_mode1": 768}}`
—y `"mode": 3` adentro de `panorama` para forzarlo—. En `layers.json`,
`panorama` dice el modo, el recorte, los tiles y colores de antes y de
después; `background`, los del mapa; y `background.png` es la capa de
abajo, con el índice 0 donde asoma el panorama. Los mapas de un cartucho
lo imprimen en el `conversor.log`: "panorama seapan: mode 3, …".

**Lo horneado**: `background.png` sobre el panorama en `(0, 0)`, contando
tiles de 8x8 y colores de 15 bits.

**El original**: el RPG_RT de 2015 con Wine, en una copia del juego con el
arranque en el mapa —`RPG_RT.lmt` reescrito con Ditto— y sin la
automática de llegada, que mueve la cámara.

**Los cuadros perdidos y el anillo**: casos de la tanda descartables,
leyendo `lost_frames`, el estado de `pano.s` en la RAM lejana y el tilemap
del panorama en la VRAM antes y después de un teletransporte al mismo
lugar.
