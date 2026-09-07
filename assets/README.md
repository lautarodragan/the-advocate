# Los gráficos y el sonido, de RM2k a la SNES

Esto es un sub-proyecto aparte del port, y la razón es que el trabajo es de
otra naturaleza. Volcar un `.lmu` a JSON —lo que hace `data/`— es mecánico: el
formato de origen y el de destino dicen lo mismo. Pasar los gráficos de RM2k a
un cartucho de SNES no lo es: hay que **elegir** qué se lleva, con qué paleta y
compartido con quién, y esas decisiones se toman midiendo.

Acá viven las mediciones y la estrategia que sale de ellas.

    medir.py    las mediciones, por rubro
    comun.py    lo que comparten: leer el material y contarlo bien

    python3 assets/medir.py sprites     los CharSets, por fotograma
    python3 assets/medir.py fondos      los ChipSets, sólo lo que se usa
    python3 assets/medir.py colores     si alcanza una paleta por chipset
    python3 assets/medir.py resto       backdrops, imágenes, panoramas
    python3 assets/medir.py todo

**Los números de este archivo salen de correr eso.** Si alguno no coincide, el
que miente es el README.


## Cómo contar sin engañarse

Tres formas de medir mal, las tres cometidas antes de llegar a las de acá:

**Los KB del PNG no dicen nada.** Son truecolor y comprimidos. `Panorama` pesa
421 KB en disco y 759 en el cartucho, porque el PNG comprime lo que la ROM no.
La unidad es el **tile de 8x8 a 4 bits**, 32 bytes, que es lo que se guarda.

**El pixel es la métrica equivocada.** Contando cuántos pixeles cubren los 256
colores más usados daba 85%, y suena bien; pero a un tile al que le falta un
solo color no se le dibuja peor, se le dibuja **roto**. Contando *tiles que
quedan enteros*, esos mismos 256 colores sirven para el 40%.

**Hay que contar lo que el juego usa, no lo que hay en la carpeta.** Los juegos
de RM2k arrastran material que nadie referencia —era gratis— y medir sobre los
archivos da números sin sentido: de los 456 personajes de los CharSets, el juego
usa 161; de las 12.096 casillas de objetos de los ChipSets, 3.232.

Y hay que contar el RTP junto con el juego, no aparte: ocho de los panoramas que
los mapas piden viven ahí. Mirando sólo la carpeta del juego daban 571 KB en vez
de 991.

Y dónde buscar las referencias también importa. Las imágenes las piden sobre
todo los **eventos comunes**: mirando sólo los mapas daban 20 de 111 usadas, y
son 97. Los backdrops no los eligen los eventos sino los **terrenos**.


## Lo que la consola regala

Dos deduplicaciones que no cuestan nada porque el hardware ya las hace:

* **Espejado.** El bit de espejo horizontal está en el tilemap y en el OAM, así
  que un tile y su reflejo son el mismo tile. Las animaciones de caminar a
  izquierda y a derecha son la misma.
* **Paleta.** El número de paleta es otro campo, así que dos dibujos iguales con
  colores distintos comparten los tiles. **Un recoloreado no cuesta un byte de
  gráfico.**

Y una tercera que aparece sola: un **autotile** de RM2k no es una celda de la
imagen sino una *combinación de bordes* que el motor arma de un bloque chico,
y cada bloque genera hasta 50 combinaciones. En la SNES esa composición la hace
el tilemap gratis, apuntando cuatro celdas a cuartos que ya están. Medido:

    autotiles    3460 ids -> 1936 tiles de 8x8 = 0,56 por id
    capa baja    1620 ids -> 3619              = 2,23
    capa alta    1612 ids -> 3801              = 2,36

Cuatro por id sería no compartir nada.


## Cuánto pesa el juego

    grillas de mapa      818 KB    2 bytes por celda, 418.635 celdas
    sprites              450 KB    1201 fotogramas distintos
    colisión             409 KB    1 byte por celda
    tiles de fondo       287 KB    9199 tiles de 8x8, compartidos entre chipsets
    tablas de bloques   ~152 KB    escalado del mapa 1
    música              ~860 KB    estimado, 43 temas
    ------------------
    total              ~2,9 MB     y un cartucho LoROM llega a 4

El arte que todavía no dibuja nadie, y que hace falta para que el juego sea el
juego —taro fue explícito: sin batallas el proyecto no tiene sentido—:

    Panorama   991 KB   los 19 que los mapas piden, de 27
    Picture    604 KB   las 97 referenciadas, de 112
    Backdrop   494 KB   los 21 que nombran los terrenos, de 70
    Monster    301 KB   sin filtrar por uso
    Battle     218 KB   sin filtrar
    FaceSet    168 KB   sin filtrar
    ------------------
    arte      2,7 MB    (los tres últimos son cota de arriba)

Sumado, ~5,6 MB contra 4 de techo. **Comprimir no es la condición para que el
juego entre; es lo que hace lugar para el arte.**


## La paleta, que es el problema de verdad

Deduplicar tiles entre mapas sólo sirve si las paletas coinciden. Hoy el
conversor cuantiza **por mapa**, así que dos mapas que comparten un chipset
reciben paletas distintas y el mismo dibujo termina siendo bytes distintos. La
deduplicación no es un problema de empaquetado: es uno de paletas disfrazado.

Pero la paleta **global** era la pregunta equivocada. La CGRAM se recarga al
cambiar de mapa, y los tiles sólo hace falta compartirlos entre mapas del mismo
chipset. Medido por chipset, sobre los ids que cada uno usa de verdad:

    el más chico 17 colores, mediana 65, el más grande 206
    entran en los 111 de la capa de fondo:  33 de 42
    entran en 256:                          42 de 42
    llevando el chipset entero:              9 de 42

La última fila es la que muestra por qué filtrar por uso no es un detalle de la
medición sino la condición de que la idea funcione.

**El precio no son bytes.** Una paleta por chipset es más exigente que una por
mapa, porque un mapa usa un subconjunto del chipset: un mapa que hoy entra
holgado con 63 colores pasaría a compartir una de 150, y se va a ver **peor que
hoy**. Ése es el costo real de deduplicar, y es artístico.


## Lo que sigue

1. **La estrategia de paletas.** Qué paletas armar y cómo asignarlas, mirando
   estáticamente en qué combinaciones aparecen CharSets con ChipSets y CharSets
   entre sí. Un sprite y el fondo sobre el que camina comparten pantalla, así
   que comparten CGRAM. Hipótesis de taro que vale la pena medir primero: toda
   Lashe City comparte estilo y se parece a los sprites principales, así que
   debería simplificarse mucho.

2. **Separar el material de los mapas en el conversor.** Que la compilación de
   un mapa guarde **referencias** y no material. Es lo que hace realizable todo
   lo anterior: hoy cada mapa lleva sus propios tiles, y un personaje que
   aparece en 39 mapas se paga 39 veces.

3. **Un spike de análisis estático para descartar mapas enteros.** No
   interpretando todos los estados posibles, que no es practicable, sino al
   revés: elegir mapas candidatos y trazar sus referencias hasta llegar a "para
   ver esto hace falta tal item o tal héroe". La memoria de taro suma como
   heurística. Su propia intuición dice que puede no cambiar nada: los mapas
   descartables son probablemente de prueba y usan tilesets que ya se usan.

4. **Comprimir la grilla**, que es el rubro más pesado. taro recorrió el juego
   entero en el editor y sabe que hay mucho desperdicio: los mapas más grandes
   —el del escape en auto, por ejemplo— usan veinte o treinta tiles del chipset,
   en áreas rectangulares grandes con patrones repetitivos y mucho espacio sin
   usar.

Y un límite que vale para todo lo de arriba: **esto es análisis estático**. Dice
qué está referenciado, no qué se ve jugando. Un evento común puede pedir una
imagen y no ser alcanzable nunca. La salida no es más análisis sino jugar con un
centinela visible en lugar del gráfico, y anotar dónde aparece; eso además
encuentra lo contrario, que ningún filtro estático ve: un `ShowPicture` con el
nombre armado en una variable.


## El horizonte

La idea de taro es que esto termine siendo general: un `migrar-rm2k-a-snes
juego.zip juego.sfc` que funcione sin ajustar tuercas para cada juego. Nada de
lo medido acá es propio de *A Blurred Line* salvo los números: que los CharSets
traen ocho personajes, que los autotiles se expanden, que el material sobra
porque en 1999 sobrar era gratis, valen para cualquier juego de RM2k.
