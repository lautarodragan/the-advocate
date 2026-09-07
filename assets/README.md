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

**Y esto ya no es una afirmación, es una medición.** El conversor comparte
bloques idénticos desde el 2026-09-07 —ver `Materiales`—, y sobre los mapas de
`demo-apertura` eso ahorra **0,1 KB, todo bloques vacíos**. Tomando en cambio
seis mapas que usan el mismo chipset, el 23:

    mapas 4 y 5    2 tiles iguales byte a byte, de 150 -> 122 iguales como dibujo
    mapas 2 y 4    2 de 139                            ->  91
    mapas 2 y 5    2 de 139                            ->  95
    mapas 3 y 4    1 de 150                            ->  83

O sea que el dibujo se comparte hasta en un 80% y los bytes no se comparten
nunca. Lo que separa una columna de la otra es exactamente la paleta.

Al medirlo hay una trampa que cobró en el camino: los tiles de la consola son
**planares**, cuatro pares de planos de bits intercalados por fila. Renumerar
sus bytes para comparar dibujos sin paleta no compara dibujos —es el mismo
error que `canonico` documenta— y daba 11 tiles compartidos donde hay 122. Hay
que decodificar a pixeles primero.

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


## La ventana de mensaje le estaba cobrando media CGRAM al fondo

El presupuesto del fondo no eran 111 colores: eran **47**, y no por falta de
lugar. BG1 va a 8 bits por pixel y **direcciona CGRAM en directo**, así que no
necesita paletas de 16; sólo necesita que nadie le pise las entradas. Pero se le
daba el bloque que quedaba *debajo* de la paleta de la ventana de mensaje, y esa
paleta era una para toda la ROM: la más baja de las capas de encima de todos sus
mapas. En la ROM de la apertura eso la ponía en la 3, y entonces:

    0        color de fondo de la pantalla
    1..47    BG1  <- lo único que se le daba
    48..63   la ventana
    64..111  paletas 4, 5 y 6: **no las usaba nadie**
    112..127 la capa de encima

En el mapa 7 había **57 entradas tiradas** mientras el fondo fusionaba 13 de sus
60 colores. Los nueve mapas del PoC fusionaban 97 colores entre todos.

La solución es mover la ventana a la **paleta 0**, abajo de todo. Ocupa nueve
entradas —el color de fondo más sus ocho colores— y el fondo queda contiguo
desde la 9 hasta donde arranque su propia capa de encima, sin depender de lo que
necesiten los otros mapas. Medido sobre `demo-apertura`:

    presupuesto por mapa    47 -> 55, 71, 87 o 103 según el mapa
    colores fusionados      97 -> 0

Y una propiedad que sale gratis: el tinte de pantalla recorre CGRAM desde donde
arranca el fondo, así que la ventana queda fuera del rango **sin que nadie tenga
que acordarse**. En RM2k el tono se aplica al mapa y no a la ventana.

Al hacerlo hubo un error de conteo que la tanda cobró: los colores de la ventana
se contaban con `sum(1 for w in cram if w)` y daban siete, pero son **ocho**
—uno es negro puro y su palabra de CGRAM es cero—. Con siete reservadas, el
texto se dibujaba con un color que nadie había subido: 79 pixeles en los
renglones de texto. Ahora `convert_ventana` mira el índice más alto que la
ventana usa de verdad y corta si no entra.


## Los sprites tienen su propio problema, y es más duro

Todo lo de arriba es de fondos. Las paletas de **sprite** son otras ocho —siete
con el cronómetro puesto— y ahí no hay margen: cada personaje de RM2k que este
juego usa ocupa **los 15 colores enteros** después de cuantizar. El mapa 8, que
es la calle a la que da el pad de Talan, dibuja diez personajes y no existe
ningún reparto sin pérdida; se probó hasta cinco paletas y no hay.

Y fusionar sale caro. El par más barato de esos diez —`Chara2:0` con
`People1:0`— mueve **920 de 5276 pixeles, el 17,4%**, con un salto de 18 sobre
31 en un canal; el peor par llega al 47%. No es que el heurístico sea flojo:
`merge_least_used` ya fusiona el color menos usado con su vecino más cercano
por luma, y el salto grande sale de encadenar fusiones.

Lo que sí es barato es no dibujar. Cuatro de esos diez aparecen en **una sola
página de un solo evento** —`Future1:6`, `People1:0`, `People4:0` y `savept:0`—
y el último es un punto de guardado, que este port no tiene. Sacar dos entra en
las ocho sin tocarle un pixel a nadie, y el conversor ya sabe no dibujar un
evento cuyo gráfico no entra: hoy corta con error en vez de elegir.


## Compartir tiles entre mapas: la VRAM no da

Medido el 2026-09-07, después de mudar la ventana a la paleta 0. Con el
presupuesto nuevo, que dos mapas del mismo chipset compartan paleta de fondo es
**casi gratis**:

    chipset 1  mapas 4,5   unión 67 colores en 103  -> fusiona 0
    chipset 9  mapas 7,8   unión 77 en 103          -> fusiona 0
    chipset 6  mapas 1,2   unión 64 en  55          -> fusiona 9, y son
                                                       41 pixeles de 5.120.000

Pero compartir **tiles** pide algo más que la paleta: pide un solo pool, porque
la ROM sube el bloque de tiles de un mapa con un DMA contiguo. Y ese pool se
sube entero en cada mapa:

    pool compartido de los mapas 1 y 2     437 tiles de fondo
    el mapa 2 gasta además                 283 tiles de sprite

    reparto con ventana        fondo 384, sprite 448   ->  437 > 384
    reparto alternativo        fondo 480, sprite 256   ->  283 > 256

No entra en ninguno de los dos. Así que el ahorro de 14 KB del par 1–2 es real
en el cartucho e **irrealizable en la consola**: lo bloquea la VRAM, no las
paletas. La ventana de mensaje ya se lleva 8 KB de tiles más 2 de tilemap, y lo
que queda hay que repartirlo entre fondo y sprites.

Lo que sí quedó del trabajo de paletas es la mitad de calidad, que era la más
grande: los nueve mapas del PoC pasaron de fusionar 97 colores a fusionar 8, y
se ve —la sangre de Core en el piso del mapa 2 era marrón y ahora es roja—.


## Lo que sigue

1. ~~**La estrategia de paletas.**~~ Hecha a medias y con un final inesperado:
   la mitad de calidad rindió mucho —97 colores fusionados a 8— y la de ahorro
   de bytes está **bloqueada por la VRAM**, no por las paletas. Ver arriba. Lo
   que sigue vivo de este punto es sólo si aparece más VRAM: qué paletas armar y
   cómo asignarlas, mirando
   estáticamente en qué combinaciones aparecen CharSets con ChipSets y CharSets
   entre sí. Un sprite y el fondo sobre el que camina comparten pantalla, así
   que comparten CGRAM. Hipótesis de taro que vale la pena medir primero: toda
   Lashe City comparte estilo y se parece a los sprites principales, así que
   debería simplificarse mucho.

2. ~~**Separar el material de los mapas en el conversor.**~~ Hecho el
   2026-09-07: los bloques pasan por `Materiales`, tienen nombre propio y el
   mapa guarda a cuál apunta; los idénticos se emiten una vez. Lo que quedó
   claro haciéndolo es que la separación no ahorra nada por sí sola —0,1 KB— y
   que el punto 1 es el que tiene todo el ahorro adentro. Ver arriba.

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
