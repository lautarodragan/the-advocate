### El cartel de "One year previously"

Es el único `ShowPicture` que el port hace, y el caso fácil del sistema de
imágenes: aparece una sola vez, entre dos fundidos, sobre un mapa de un solo
tile, así que no le pelea VRAM ni colores a ningún ChipSet ni CharSet. El cómo
está en el README. Lo que hay que tener a mano para tocarlo:

* **Un cartel por ROM**, y quién se queda con la ranura lo decide
  `Imagenes.elegir` mirando todos los mapas en el orden de la tabla, antes de
  compilar nada. Con "el primero que pase" los dos lados podían elegir
  distinto, porque los mapas se compilan en un orden que depende de si la ROM
  lleva ventana.
* **El fundido es de tono y no de transparencia.** Los dos `MovePicture` dejan
  `top_trans` en cero y mueven (r, g, b). Y **la duración viene en décimas**:
  los 35 del primero son 210 cuadros. Eso subió la página del "1 year earlier"
  de 105 décimas a 160, y por eso `test_un_ano_antes.py` pasó de 900 cuadros a
  1200.
* **Quince colores de los 226 del PNG**, y el degradé del resplandor se
  escalona. Es lo cosmético declarado de esta vuelta; falta que taro lo
  confirme jugando.
* **El estado vive en `$7E30E8`, en la RAM lejana**, porque en el banco 0 no
  entraba: la BSS estaba en **7680 de 7680**. Lo que siga pidiendo RAM del
  banco 0 va a tener que aflojar algo.
* **`armar_paleta` deja Y en 32.** Llamarla desde un opcode sin `phy` le mueve
  el cursor al intérprete. Costó el primer rojo y no se veía como un cartel
  roto: la página seguía corriendo, sólo que otra.

**Lo que costaría el sistema entero** está medido y en el README: 34
`ShowPicture` en el juego, 20 carteles distintos, 7 comandos de 34 que el
modelo de hoy sabe hacer, y cinco imágenes de 320x240 exactos que **con objetos
no se pueden hacer** —serían 56 de los 128 de OAM y 32 de los 34 tiles por
línea—. Ésas piden prestarle una capa al cartel, y con eso el mapa se recarga
al borrarlo.

Es lo único que este port dibuja de `ShowPicture`, y el alcance está elegido a
propósito: **un cartel por ROM**. El de la intro aparece una sola vez, entre un
fundido y otro, sobre el mapa 4 —"Blank (Leave START here)", un mapa de un solo
tile— así que no le pelea nada a nadie, y eso lo hace el caso barato del sistema
de imágenes. Lo demás se sigue aceptando sin hacerse; cuánto cuesta el sistema
entero está más abajo.

**Va en objetos de OAM y no en una capa.** En modo 3 las dos capas son del mapa,
y prestarle una al cartel obliga a recargar el mapa al borrarlo: 30 KB de DMA y
dos cuadros negros, que es lo que cuesta `volver_al_mapa`. Con objetos se pone y
se saca sin tocar lo que hay debajo, que además es lo que hace RM2k —la imagen
se compone encima—. Se pagan dos cosas:

* **Quince colores**, los de una paleta de sprite, contra los 226 del PNG. Los
  elige `titulo.reducir`, el mismo de la pantalla de título y por lo mismo: no
  promedia, así que no inventa colores que haya que volver a cuantizar, y no
  depende de la versión de PIL. El degradé del resplandor rojo se escalona, se
  ve, y está declarado.
* **Veinticuatro de los treinta y cuatro tiles por línea** en las veintinueve
  líneas que ocupa: son seis objetos de 32x32 en fila. Ahí entran dos
  personajes más y no más. Cuál sprite descarta el PPU en esas líneas es
  justamente lo que ninguna referencia en Python podía modelar y una captura del
  emulador sí: es la razón por la que las goldens son capturas y no un render.

**La paleta es suya y no la comparte con nadie.** No es por falta de lugar: el
fundido es un tinte de esas quince entradas cuadro a cuadro, así que un
personaje metido ahí se apagaría y se prendería con el cartel. Y va **arriba de
`SPRITE_CGRAM`**, o sea afuera de los rangos que recorren `aplicar_tinte` y
`subir_paletas`: en RM2k las imágenes tienen `affected_by_tint` apagado de
fábrica —`Priority_PictureOld` es 120 contra los 90 de `Priority_Screen`— así
que el tinte de pantalla no las toca, y quedando fuera del rango no hay que
acordarse de saltearlas.

**El fundido es de tono, no de transparencia**, y eso hubo que ir a leerlo:
los dos `MovePicture` de la página dejan `top_trans` en cero y mueven
(r, g, b) entre 0 y 100 con la saturación quieta. La imagen aparece **negra**,
sube a su color y vuelve a negro. En la consola eso es exactamente la cuenta
que el tinte de pantalla ya hacía, `tabla_canal` más `armar_paleta`, sobre
dieciséis entradas en vez de doscientas.

Y **la duración viene en décimas**: `data.time_left = duration * DEFAULT_FPS /
10`. Los 35 del primer `MovePicture` son tres segundos y medio, no medio
segundo, y los 20 del segundo son dos. Hasta que esto se dibujó, esas 55
décimas no costaban nada —el comando se aceptaba sin hacerse y sin su espera—,
así que la página del "1 year earlier" pasó de 105 décimas a 160.

**La posición de RM2k es el centro de la imagen**, no su esquina
—`Sprite_Picture` hace `SetOx(width / 2)`—, y la pantalla de RM2k mide 320x240
contra las 256x224 de la consola. Las dos esquinas del rectángulo pasan por la
misma cuenta y la imagen se lleva al tamaño que queda; escalar el tamaño por su
lado daba 28 de alto donde las esquinas dan 29, y un pixel de diferencia entre
las dos puntas es una comparación que falla. El cartel del "One year
previously" queda entonces en (-13, 149) y mide 186x29: **se sale por la
izquierda**, y eso no es un error nuestro, es lo que el juego muestra.

**Los tiles son de un solo mapa.** Se ponen al final de su banco de sprites,
redondeando a una fila de bloques como los dígitos del cronómetro y las gotas
de lluvia, y por lo mismo: un objeto de 32x32 lee cuatro tiles de cuatro filas
seguidas de la grilla de dieciséis, así que en una fila de bloques entran cuatro
objetos y el quinto arranca 64 tiles más adelante. Seis objetos son dos filas,
128 tiles reservados de los cuales 96 se usan. Que el cartel viva en un mapa y
que se borre al cambiar de mapa son la misma cosa: sin sus tiles en VRAM no
habría qué dibujar, y `erase_on_map_change` viene prendido de fábrica en
`Game_Pictures`.

**Cuál cartel se queda con la ranura lo decide `Imagenes.elegir`**, mirando
todos los mapas del cartucho en el orden de la tabla y **antes de compilar una
sola página**. Con "el primero que pase" bastaba que dos carteles compitieran
para que la elección dependiera del orden en que se compilan los mapas, que a su
vez depende de si la ROM lleva ventana, y eso no se ve como un cartel equivocado
sino como dos streams de bytecode distintos.

**Y el estado vive en la RAM lejana**, quince bytes en `$7E30E8`, al lado del
de la animación de batalla. No es elegante: es que en el banco 0 no entraba
—la BSS estaba en 7680 de 7680— y esto se lee y se escribe unas pocas veces por
cuadro, así que el direccionamiento largo no se nota.

Lo cobra el caso `cartel` de `pruebas/abl/test_tanda_escenas.py`: cinco cuadros
contra su golden, **los cinco en cero**. El de la mitad de cada rampa no es
adorno: es el único que ejercita la interpolación cuadro a cuadro, que es donde
un valor de más o de menos no se vería a ojo.

#### Lo que costaría el sistema de imágenes entero

Medido sobre los 328 mapas del juego, no estimado:

    ShowPicture en el juego                    34, en 23 páginas
    carteles distintos                         20
    páginas que muestran 2, 3 y 4 a la vez     2, 3 y 1
    comandos que el modelo de hoy sabe hacer    7 de 34
    con la pantalla ya teñida a negro          10 de 34

Y lo que cada uno pediría, contado por comando —un mismo comando puede pedir
varias—:

    el color transparente del PNG              21
    pegada al mapa (fixed_to_map)               9
    translúcida (top_trans)                     8
    zoom distinto de 100                        7
    rotar u ondear                              6
    saturación distinta de 100                  5
    la posición desde una variable              2

Lo que esa tabla dice es que **la parte cara no son los carteles**. De los 20
distintos, seis son carteles de texto que entran en un objeto de alto
—`Oneyearprev`, `MeanwhileLashe`, `SevDaysPrev`, `Ready`, `Fortitude` y el
`9` de 16x16— y los otros catorce son ilustraciones grandes, cinco de ellas de
**320x240 exactos**, o sea la pantalla entera.

Una de 320x240 **no se puede hacer con objetos**: escalada son 256x224, que son
8x7 objetos de 32x32 —56 de los 128 de OAM, 896 tiles de 8x8, 28 KB de un banco
de sprites que mide 8 o 16— y en cada una de sus 224 líneas gasta 32 de los 34
tiles por línea, o sea que se lleva puestos a todos los personajes del mapa.
Para ésas hay que prestarle una capa al cartel, con lo que eso implica: el mapa
se recarga al borrarlo. Es exactamente el caso que la nota de `eventos.py` ya
anticipaba, y por eso el atajo de las cinemáticas —teñir a negro antes— vale
para diez de los 34 y no para los otros veinticuatro.

Si algún día se hace completo, el orden que sale de estos números es: primero
**el color transparente** (21 comandos, y es un color menos en la paleta),
después **más de un cartel a la vez** (seis páginas), después **la capa
prestada** para las ilustraciones, y al final el zoom, la rotación y la onda,
que son cinco o seis comandos cada uno y cada uno un sistema.
