### ShowPicture

El cartel de "One year previously" es el único `ShowPicture` que el port hace.

Es el caso fácil del sistema de imágenes: 
- aparece una sola vez, entre dos fundidos, 
- sobre un mapa de un solo tile, 
- así que no le pelea VRAM ni colores a ningún ChipSet ni CharSet. 

Lo que hay que tener a mano para tocarlo:

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
