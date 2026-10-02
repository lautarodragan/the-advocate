---
name: "Las imágenes grandes, en BG1 en modo 1"
description: "Fase 3 del sistema de imágenes: las que tapan la pantalla con el mapa oculto (las fotos Diff, las instrucciones del 49 y del 285, GTest4 con ondas, el final del 309) en BG1 pasado a modo 1 mientras se muestran"
type: feature
assignee: taro
---

Fase 3 de `docs/research/2026-10-01-el-sistema-de-imagenes.md` (Jilguero),
opción E. Lo decidió taro el 2026-10-01:
`decisiones/las-imagenes-grandes-en-modo-1.md`. Las fotos Diff (212 a 216),
que en RM2k se achican con un zoom, se muestran con un fundido: la SNES no
escala sin modo 7. Lo que pasa en esas escenas, con capturas del original:
`/shared/capturas/2026-10-01-escenas-diff/` (Bandurria).

Hecha por Aguilucho, desde `main` en `83c7e3ee`, con `main` mergeado en
`635c3704` (los comunes automáticos y el `CallEvent` compartido, de
Picaflor). **Espera el visto bueno de taro a las goldens** —un commit sólo
de goldens— y a la elección del montaje del 217, y que la juegue: el
cartel de la carrera del 49 está en `release`.

## El diseño

**El plano lo elige el conversor** (`tools/port/picture.py`): una imagen
que no entra en los objetos va a BG1 si va con la pantalla, o si va con el
mapa y tapa la pantalla entera —las fotos del 212 al 216—. El hovertram del
32, pegado al mapa con la escena alrededor, sigue sin dibujarse: en BG1 se
llevaría el mapa entero mientras hablan. Las grandes **son del cartucho y
no de cada mapa**: van en una tabla, `big_table`, y la misma imagen en dos
mapas es una.

**La conversión** es `rm2k-snes-images background`: la imagen dibujada
donde la pone su `ShowPicture`, en un lienzo del ancho de la pantalla —más
alto si pasa por arriba o por abajo y los tiles alcanzan, para que
`MovePicture` la pueda subir: las instrucciones del 285—; Adeleine reparte
los colores en siete paletas de quince (la 0 es de la ventana) y Voodoo
corta los tiles de 4 bits. Los tiles van **crudos** en el cartucho, y el
tilemap en LZ2: ver abajo.

**El runtime** (`tools/runtime/big_picture.s`, banco 1): mostrarla apaga la
pantalla, manda los tiles por DMA desde el cartucho a `$0000`-`$3FFF` y el
tilemap a `$4000` —el mismo lugar en los seis repartos, ver
`docs/port/vram.md`—, muda el tilemap de la ventana a `$4800`, vacía el de
la capa de encima y pasa a modo 1 con BG1 y BG2, sin sprites. La ventana de
mensaje, que es BG2, queda igual, encima. Borrarla vuelve al modo 3 con la
misma recarga que la vuelta de la pelea (`big_back_far`, en `picture.s`).
Mientras está, el vblank no sube poses, tiras del mapa, la animación del
ChipSet ni el tinte.

* **Tono y transparencia** son la paleta, con las tablas del tinte; la
  transparencia **oscurece**, porque abajo sólo hay negro. La saturación
  sale gratis de `build_palette`: la del 288 y el 208 está.
* **El zoom que achica es un fundido** a negro, en el tiempo del zoom.
* **`MovePicture` la sube o la baja** con el scroll de BG1: la consola
  calcula la esquina como RM2k, con la mitad del alto de la imagen que está.
  De costado no se mueve.
* **Las ondas**: un canal de HDMA (el 4) sobre `BG1HOFS`, con dos tablas en
  el banco `$7F` que se turnan para no escribir la que se está leyendo.
  Exactas con `WaverBlit` de easyrpg-player: profundidad, fase de 8 por
  cuadro, período de 32 líneas de RM2k. Lo que una onda trae de más allá
  del costado, para una imagen más ancha que la pantalla (`GTest4`), son
  sus bordes espejados; para una que no (`ShipFlash`), negro, como RM2k.

**Cuánto cuesta**, medido: mostrar una, dos o tres cuadros de pantalla en
negro; borrarla, catorce. Los tiles iban en LZ2 al principio, y descomprimir
treinta kilobytes —y después el bytecode llevado de otro mapa, que vive en
el mismo buffer— eran diez: por eso van crudos (unos 200 KB los nueve; el
cartucho tiene 43 bancos libres).

## Qué escenas se dibujan

    49    EscapeInst         release: el fork del 49 se borró, ver abajo
    212   PhoneCallDiff      caso de prueba, con el fundido
    213   SurlBroDiff        caso de prueba
    214   SurlGravesDiff     caso de prueba
    216   ThreeRubbleDiff    caso de prueba
    285   AdvoInstr          caso de prueba: sube 93 líneas en 4 s
    309   ABLEndBox8         caso de prueba: sube y baja de negro
    208   GTest4             caso de prueba: ondas 6 -> 1 -> 4, y 8 saturada
    267   GTest4             es la segunda del 208, con otro mensaje
    288   ShipFlash, GTest4  caso de prueba: saturadas, ondas 2
    217   el montaje         caso de prueba: las dos opciones, abajo

Los mapas del 207 al 217, el 285, el 288 y el 309 no están en el cartucho;
cada caso de `rom/pruebas/casos/imagen-grande-*.json` copia los comandos de
su escena en una página que salta al mapa 12. El 32 (`hovertram2`) sigue
afuera, a propósito: ver el diseño.

**El fork del 49 se borró** —`rom/parches/manual/mapas/Map0049.*`—, como
decía su README: cambiaba el cartel por dos mensajes porque la ROM no tenía
dónde dibujarlo. Ahora corre la página del juego, con su `KeyInputProc`. El
recorrido de la carrera fotografía el cartel una vez (`01-el-cartel`) en vez
de dos, y sus fotos pendientes se renumeraron.

## El montaje del 217

Cuatro fotos al 50 % cada seis cuadros, con un destello blanco. Las dos
opciones, capturadas cuadro por cuadro en
`/shared/capturas/2026-10-02-imagenes-grandes/montaje-217/`:

* **Las fotos**, que es lo que hace hoy el conversor: cada una se carga con
  la pantalla apagada, así que son **cinco cuadros de foto y tres de
  negro**, sin el blanco —el destello no se ve sobre la imagen—. Al 50 %
  sobre negro es la foto a medio color, que es lo que muestra RM2k sobre el
  mapa en negro.
* **Sólo los destellos**, sin las fotos: el 217 en negro con un blanco que
  se apaga cada seis cuadros. Para elegir ésta haría falta que el conversor
  deje afuera las imágenes de ese mapa.

Lo que no se probó: las cuatro fotos **a la vez** en la VRAM, a la mitad
de tamaño (128x112, unos 224 tiles cada una, 896 las cuatro), cambiando sólo
el scroll de una a otra: entrarían sin apagar la pantalla, pero pide que el
conversor sepa que se muestran juntas.

## Las pruebas

`rom/pruebas/rpgmaker/test_imagenes_grandes_golden.py`, contra goldens:
cada escena en dos o tres momentos, el cartel del 49 con la página del
juego, y **la vuelta**: una imagen puesta y borrada sobre Sorbe Village —el
reparto que más pisa, con el tilemap del fondo debajo de la imagen—, que
tiene que quedar igual pixel por pixel, a 15 bits, al mismo caso sin la
imagen en el mismo tick. **Vista en rojo** sacando `fill_window` de
`big_back_far`: 9.727 pixeles.

`test_cores.py` suma tres: una foto a mitad del fundido, las ondas y la
vuelta, en snes9x y bsnes.

`cargo test`: el compilador (`a_big_picture_goes_up_scrolls_fades_and_comes_down`),
la conversión (`background::tests`) y el tilemap con sus bordes espejados
(`rm2k-snes-mapdata/tests/big_pictures.rs`).

**Cambian a propósito los dos hashes de `rm2k-snes-mapdata/tests/python.rs`**:
el `.inc` lleva la sección de las imágenes grandes, siete renglones de más
aunque no haya ninguna.

## Las goldens

En su commit aparte, sólo goldens: veintitrés nuevas, ninguna movida. Lado
a lado con el original del RPG_RT con Wine —y para las fotos, con las
capturas de Bandurria— en `/shared/capturas/2026-10-02-imagenes-grandes/`.
**El merge espera el visto bueno de taro.**

Lo que se ve distinto del original, anotado en
`divergencias/lo-que-las-imagenes-grandes-no-modelan.md`: el fundido en vez
del zoom, el marco negro de las instrucciones del 285, los bordes espejados
de las ondas de `GTest4`, los 105 colores, y los cuadros en negro al
mostrar y al borrar.

## Para mergear

* **Reinstalar en el global**: `just -f tools/justfile install images events
  mapdata cartridge`. Lo de Python no agregó ni renombró ningún script.
* **Los opcodes**: `OP_BIG_SHOW` (`0x3D`) y `OP_BIG_MOVE` (`0x3E`), que
  reemplazaron los `OP_RESERVED_3D` y `_3E` de Picaflor al mergear `main`;
  `0x39` a `0x3C` siguen reservados.
* **Números de hoy**, sobre el árbol mergeado: `just pruebas` da **1000**
  (988 de `main` más 12 nuevas), `just -f tools/justfile test` **39**,
  `cargo test` de events, images y mapdata en verde. `NO_CACHE=1 just
  cartuchos` y el armado con caché dan los mismos tres cartuchos; `abl.sfc`
  es `6643d2c1…`. `test_musica_techos.py` siguió en verde.
* **Espacio**, `just espacio` sobre `release`: banco 0 con 1.063 B libres,
  **banco 1 con 131 B** —el código de las imágenes grandes está ahí, y los
  comunes de Picaflor también—, 43 bancos de datos libres.
* **La RAM lejana**: la que me tocaba, `$2570`-`$257F`, es el final de
  `FAR_PAIR_LIST`. Uso `$25E0`-`$25EF`, entre la música y
  `FAR_SPEED_BONUS`. Y en el banco `$7F`, mientras hay una imagen grande,
  `BIG_PAL` y las dos tablas de las ondas en `$7F6000`-`$7F64FF`, sobre los
  dibujos de la animación del ChipSet, que la carga del mapa repone:
  `test_reservas_de_la_wram.py` los nombra.
* **El canal 4 de HDMA** es de las ondas: ningún otro código lo usaba.
