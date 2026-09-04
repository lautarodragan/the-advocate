# El port a Super Nintendo

Dibuja el mapa y reproduce su tema. Empezó como una rama aparte del port a Mega
Drive, para ver si la SNES se acercaba más al original; la respuesta fue que sí,
y el port a Mega Drive se mudó a su propio repo. Las comparaciones con él que
aparecen más abajo se quedan porque explican por qué las cosas son como son.

## Por qué

El sonido de la Mega Drive quedó lejos del MIDI de la PC, y no por falta de
voces sino por el método: el YM2612 es síntesis FM y el MIDI de Windows XP lo
tocaba un sintetizador **por muestras**. La SNES también es por muestras, así
que el problema deja de ser "imitar un piano con cuatro operadores" y pasa a ser
"comprimir estas muestras", que es mecánico.

De paso: 15 bits de color contra 9, y 8 paletas contra 4. Los 108 colores de los
seis CharSets del Auditorium entran sin fusionar ninguno.

## Veredicto

Probado en emulador: **suena mucho mejor que la Mega Drive y cerca del
original**, con muestras que todavía son ondas de un ciclo generadas en Python.
Esa era la pregunta que motivaba la rama, y la contesta a favor de la SNES.

## El mapa

Va en **modo 3, con 8 bits por pixel**. Ahí cada pixel del fondo es un índice
directo a CGRAM y no hay paleta por tile, así que el problema que dominaba el
conversor de la Mega Drive —repartir los colores en grupos tales que ningún tile
necesite dos— simplemente no existe.

    modo 1 (4bpp, 8 paletas):  60 colores -> 28
    modo 3 (8bpp):             60 colores -> 60, sin fusionar

No era evitable de otra forma: Map0007 tiene tiles de 16, 17 y 19 colores, y
ésos no entran en una paleta de 15 por más paletas que haya. Cuesta el doble de
VRAM por tile, 64 bytes en vez de 32; con 92 tiles son 5,8 KB de los 64.

El resultado se verifica pixel por pixel contra el render de Python, a 15 bits,
que es la profundidad real de la consola:

    Map0007: 0 pixeles distintos de 57344

En la Mega Drive esto no se podía hacer: los 9 bits obligaban a fusionar
colores, así que sólo se podía comparar por forma. Acá la comparación es exacta.

Eso destapó un detalle del hardware que a ojo era invisible: **el PPU muestra la
línea `vofs+1` en el primer scanline**, no la `vofs`. Con el scroll en 0 el mapa
quedaba corrido una línea. Las dos imágenes se veían idénticas y diferían en el
50% de los pixeles.

## La cámara

El scroll es por hardware: mover la cámara es escribir dos registros. Lo único
que hay que cuidar es no salirse del mapa.

El tilemap del PPU se arma con "pantallas" de 32×32 celdas encadenadas en VRAM,
y no van una al lado de la otra en memoria: cada una ocupa sus 1024 celdas
seguidas.

**Cómo se verifica.** Cada dirección se mantiene apretada hasta que la cámara
choca contra el borde. Dónde tiene que quedar no se estima: es exactamente el
ancho del mapa menos el de la pantalla, que el conversor emite como `CAM_MAX_X`
y `CAM_MAX_Y`. Si la ROM se moviera de más, de menos, o no frenara, la
comparación falla.

    centro   (0,0)    0 pixeles distintos de 57344
    derecha  (64,0)   0
    abajo    (0,16)   0
    esquina  (64,16)  0

Que llegue justo a 64 y 16 prueba a la vez el movimiento y el tope.

## Los mapas que no entran

El tilemap del PPU no pasa de 64×64 celdas y encima hay que repartirle la VRAM
a los tiles, así que la ventana que le queda son **64×32 celdas: 512×256
pixeles**. Los mapas del juego llegan a 1000×80. De 335 mapas, 94 no entran.

La ventana no se desplaza: se la trata como un **toro**. La celda `(mx, my)` del
mapa vive siempre en la ranura `(mx mod 64, my mod 32)`, y el scroll por
hardware da la vuelta solo porque 1024 —el máximo del registro— es múltiplo de
los 512 que mide la ventana. Cuando la cámara cruza el borde de una celda, sólo
hay que reescribir la columna o la fila que acaba de entrar; la que sale está 32
columnas o 4 filas afuera de la pantalla y nadie la mira mientras se la pisa.

De ahí sale una propiedad cómoda: **no hace falta llevar la cuenta de qué parte
de la ventana está al día**. Como la ranura de cada celda es fija, escribir de
más nunca puede pisar algo que se esté viendo, y la inducción cierra sola desde
el llenado inicial.

Las tiras se arman en RAM fuera del vblank y se suben cuando empieza el
siguiente, igual que OAM. Una columna sale de un DMA por capa —el PPU puede
avanzar de a 32 palabras tras cada escritura, que es justo lo que mide una fila
del tilemap— y una fila sale de dos, porque las dos pantallas de 32×32 no son
contiguas en VRAM.

### El mapa no se guarda como tilemap

Expandido no entraría en el cartucho: 1000×80 celdas por dos bytes son 156 KB,
más que la ROM entera. Lo que se guarda es la **celda de 16×16 de RM2k**, que es
la unidad con la que el juego fue dibujado y que se repite muchísimo.

    mapa 52, 1000x80 celdas    tilemap expandido   160.000 B
                               grilla de bloques    40.000 B + 1.744 B de tabla

El bloque lleva sus cuatro celdas de fondo, sus cuatro de la capa de encima y su
pasabilidad, todo junto. En todo el juego el máximo son 512 bloques distintos.

Que la pasabilidad viaje en el bloque **borró la tabla de colisión entera** —un
byte por celda, hasta 20 KB. Y no es un atajo: dos celdas que se dibujan igual
podrían tener permisos distintos si vinieran de tiles distintos del ChipSet, así
que la pasabilidad va en la clave con la que se deduplica y esas dos se separan
solas.

Dónde está el héroe dentro de la grilla tampoco es un índice sino un **puntero
que se mueve con él**, una celda o una fila por paso. Así nunca hay que
multiplicar ni armar una dirección de 24 bits desde cero, que en LoROM es
incómodo porque los bancos no son contiguos.

### El reparto de la VRAM lo decide el conversor

Las 64 KB no se reparten como uno quiera: la base de los tiles de los sprites va
de a 16 KB, la de cada fondo de a 8 KB y la de cada tilemap de a 2 KB. Con los
dos tilemaps clavados al final quedan 56 KB para los tres bancos de tiles, y las
granularidades dejan exactamente dos cortes posibles:

    ancho    fondo 512 tiles (32 KB) | sprites 512 (16 KB) | encima 256 (8 KB)
    fondo    fondo 640 tiles (40 KB) | encima 256 (8 KB)   | sprites 256 (8 KB)

Ninguno sirve para todos los mapas: el que más tiles de fondo gasta necesita
620, y Lashe City necesita 320 de sprite. Cuál toca lo decide el conversor
—junto con los valores ya armados de `OBSEL` y `BG12NBA`— y viaja en el `.inc`.
La ROM no elige nada.

### El reparto de CGRAM, también

Las 256 entradas de CGRAM se parten al medio: la mitad de arriba es de los
sprites. La de abajo la comparten el fondo, que va en 8 bits y direcciona CGRAM
en directo, y la capa de encima, que va en 4 bits y por lo tanto cuenta su
índice dentro de una paleta de 16.

Ese corte estaba clavado en dos paletas para la capa de encima y 95 colores para
el fondo, y **27 mapas no entraban** —los tres primeros del juego entre ellos—
mientras el fondo dejaba colores sin usar. Al medirlo aparecieron dos causas que
se veían como una sola:

    la capa de encima pide 3 paletas    7 mapas
                            4           5
                            5           1
                            6           2
                            7           6
    un tile suelto con más de 15 colores   1 mapa

La segunda no la arregla ningún reparto: un tile de 17 colores no entra en una
paleta de 15 por muchas que haya. Se arregla fusionando, que es lo que la Mega
Drive ya hacía con el fondo.

Ahora el corte lo decide el conversor mapa por mapa, y **el fondo tiene la
primera opción**: se queda con las paletas que necesita para los colores que
realmente usa, y la capa de encima se lleva las que sobren —hasta las que pida,
nunca más— y fusiona si no le alcanzan. Va en ese orden porque son 300 mapas
cuya capa de encima pide una o dos paletas contra un puñado que pediría siete:
servir primero al de encima le sacaría colores al fondo en todos para que unos
pocos no fusionen.

    Map0007   fondo 60 de 111 disponibles | encima 1 paleta desde la 7
    Map0001   fondo 49 de  63             | encima 4 paletas desde la 4
    Map0348   fondo 95 de  95             | encima 2 desde la 6, 27 fusionados

Los tres primeros mapas del juego entran ahora sin fusionar un solo color.

Que las dos capas se conviertan juntas no es comodidad: el corte no lo puede
decidir ninguna por su cuenta, así que `convert_layers()` es el único lugar
donde está escrito. Antes cada llamador convertía una y después la otra, y que
las tres copias del orden coincidieran era cuestión de suerte —justo la forma de
error que ya nos había aflojado la comparación una vez.

## Varios mapas en la ROM

Un mapa solo no es un juego. Todo lo que antes era una constante del `.inc` —el
tamaño, las bases de VRAM, dónde arranca el héroe, los punteros a cada tabla—
pasó a ser un campo del registro del mapa en `mapa_tabla`, y la ROM carga el que
le digan con `cargar_mapa`.

Los desplazamientos de cada campo los emite el conversor. La ROM sólo los
nombra, así que agregar un campo no deja ningún número que actualizar de este
lado.

**Las tablas del mapa ya no entran en el banco 0.** La de bloques llega a 8 KB
—512 bloques por 16 bytes— y con varios mapas no hay dónde ponerlas. Se leen
desde donde estén con un puntero de 24 bits, o sea `lda [ptr],y`, que fue lo que
obligó a agregarle direccionamiento indirecto indexado a `w65.py`. Buscando
dónde meterlo apareció que `lda [ptr],y` se ensamblaba como `lda [ptr]` sin
avisar: el sufijo se separaba y la rama de los corchetes lo descartaba.

La de NPCs es la excepción y se copia a la RAM: `build_oam` la recorre con un
índice y en cinco desplazamientos distintos, así que con un puntero saldría el
triple de instrucciones en el lazo que se ejecuta 128 veces por cuadro. Copiarla
cuesta un lazo por carga de mapa y entran 127, que es el tope que impone OAM; el
mapa con más NPCs del juego tiene 89.

### Las puertas

De los 959 teletransportes del juego, **265 son puertas**: una página cuyo único
trabajo es mudarte, sin variables ni condiciones ni diálogo. De ésas, 263 se
disparan con "toca el héroe" y son las que la ROM usa. Se pueden hacer sin
intérprete de eventos, y son las que convierten un mapa suelto en un mundo.

Las otras 694 están adentro de cinemáticas y piden el intérprete.

Qué comandos pueden acompañar a un teletransporte sin que deje de ser una
puerta se decide con un criterio, no a ojo: **que no ejecutarlos no se vea en la
pantalla que comparamos**. Un fundido, una espera y un sonido se saltean y la
imagen final es la misma; un cambio de música o del gráfico del héroe, no.

La primera versión de esa lista puso los códigos de memoria y tres estaban mal.
Dos de los que creía inofensivos eran `PlayBGM` y `ChangeSpriteAssociation`, así
que el filtro aceptaba como puertas eventos que cambian la música y el sprite
del héroe. **La comparación no puede ver ese error**, porque la referencia usa
la misma lista: las dos partes coinciden en hacer lo mismo mal. Los códigos
salen de `tools/event_codes.py`, que se genera desde liblcf, y de ningún otro
lado.

La ROM mira la tabla de puertas al **terminar** el paso, no al empezarlo, que es
lo que hace RM2k: el evento se dispara cuando el héroe ocupa la celda. Si hay
puerta, se apaga la pantalla, se carga el mapa entero y se lo deja donde la
puerta dice. RM2k también funde a negro al cruzar, así que el parpadeo no
desentona.

Una puerta a un mapa que no entró en el cartucho se descarta en la conversión.
En la consola sería un salto al vacío, y es mejor que no haga nada a que haga
cualquier cosa; el conversor dice cuántas quedaron afuera.

### El arranque de verdad

El juego no empieza donde las pruebas lo ponían. Empieza en **Map0004, `Blank
(Leave START here)`**, una habitación vacía cuyo único trabajo es disparar un
evento y teletransportar —el patrón clásico de RM2k—. Esa habitación no tiene ni
una celda abierta por los cuatro lados, así que la heurística que elegía "el
tile abierto más cercano al centro" no tenía dónde poner a nadie.

Ahora, en el mapa donde el juego arranca, la posición sale del LCF. En los demás
sigue saliendo de la heurística, porque a ésos se llega por teletransporte y de
dónde entrás depende de por dónde viniste. La regla vive en `inicio_del_mapa()`
y la usan el conversor y la referencia: si cada uno eligiera por su cuenta, la
comparación estaría midiendo dos cosas distintas.

### El intérprete de eventos

RM2k tiene unos 130 comandos de evento. La ROM entiende siete —prender y apagar
switches, esperar, teñir la pantalla, teletransportar, cambiar el grupo, caminar
una ruta forzada y mostrar un mensaje— y resuelve las páginas como RM2k: de cada
evento gana **la de número más alto cuyas condiciones se cumplen todas**.

La regla que hace que eso sea seguro es una sola: **una página se emite sólo si
todos sus comandos se pueden ejecutar**. Si aparece uno que no modelamos, la
página no se emite y el evento no hace nada. Ejecutar la mitad de un script
dejaría al juego en un estado que no existe, y la comparación no lo vería porque
la referencia haría lo mismo mal. Por lo mismo, un evento con una condición que
no sabemos evaluar —un ítem, un cronómetro— queda entero afuera: sin saber qué
página está activa, correr la equivocada es peor que no correr ninguna.

De las 519 páginas automáticas del juego, 42 se compilan enteras con este juego
de comandos, y 31 sobreviven además al filtro por evento. Pero **29 de esas 31
no hacen nada**: todos sus comandos son de los que se aceptan sin ejecutar
porque no ejecutarlos no se ve. Las que hoy hacen algo son dos, y conviene
tenerlo presente antes de creerle a un número grande:

    mapa 3  Emitter Room               prende dos switches
    mapa 4  Blank (Leave START here)   dos switches, tinte y teletransporte

La segunda es la que abre el juego, y es la única del juego entero que ejercita
el tinte y el teletransporte por evento.

El tinte de pantalla no se podía saltear. En las puertas el fundido termina y la
pantalla vuelve; acá se tiñe y después se teletransporta, así que el mapa de
destino se ve teñido. En una consola con paleta eso no es un efecto de pantalla
sino una transformación de la paleta: la cuenta es `canal * valor / 100` con
enteros, que la consola hace con sus unidades de multiplicación y división y
Python repite igual. Y como el tinte es estado del juego y no del mapa, se
vuelve a aplicar cada vez que se carga uno; con el tinte neutro la cuenta deja
los colores donde estaban, así que el camino es siempre el mismo.

El intérprete está escrito dos veces —en `main.s` y en `tools/eventos.py`— pero
el bytecode es uno solo, así que lo que se ejecuta de los dos lados es el mismo
programa.

**Cómo se lo mira:**

    just snes-evento     # mapas 4 y 1 en la ROM, arrancando en el 4
    just snes-play       # y con sonido, en una ventana

El mapa 4 es una habitación negra y vacía cuyo único trabajo es prender dos
switches, teñir la pantalla y teletransportar. Lo que se ve al arrancar es el
mapa 1 ya teñido de azul, sin haber tocado una tecla: el tinte es `(0, 0, 100)`,
o sea rojo y verde a cero y azul intacto.

Los dos mapas tienen que estar en la ROM. Un teletransporte a un mapa que no
entró no se puede compilar, y entonces la página entera no se emite: con el mapa
4 solo, la pantalla se queda en negro, y eso es correcto.

**Cómo se verifica.** La referencia entra a los mapas como entra la ROM: para
al héroe donde lo dejó la puerta o el teletransporte que lo trajo, le corre los
eventos automáticos del mapa, y si una página pide mudarse repite el ciclo con
el mismo tope de ocho vueltas que la consola. Los switches y el tinte viven en
un estado que sobrevive a los mapas, porque de eso depende qué página queda
activa en el siguiente.

El tinte se aplica al final, sobre la imagen ya compuesta. En la consola no es
un efecto de pantalla sino una transformación de CGRAM, y como cada pixel del
fondo, de la capa de encima y de los sprites sale de una entrada de CGRAM,
teñir cada color del render da lo mismo —siempre que la cuenta se haga sobre
los 15 bits y no sobre los 24 del PNG, que redondearían distinto—.

Eso es `just snes-evento`, y está en `snes-hitos`:

    mapas 4 y 1 en la ROM, arrancando en el 4
    la consola contra la referencia: 0 pixeles distintos de 57344

En una sola comparación entran la selección de página, los dos switches, el
tinte, el teletransporte, y que el héroe quede tapado por la capa de encima en
la celda donde lo deja.

Antes de que existiera, este camino no lo ejecutaba **ninguna** prueba, y tenía
cuatro errores. Los tres primeros encadenados, cada uno tapando al siguiente:

1. `poner_switch` pisaba `Y`, que es el cursor del bytecode del intérprete. Las
   dos páginas que hacen algo empiezan prendiendo switches, así que el bucle
   leía el opcode siguiente de un byte cualquiera del medio de la página y
   cortaba ahí. Ninguna de las dos pasaba de su primer comando.
2. El lazo de `tenir_paleta` llevaba la cuenta de colores en `X`, que adentro
   del lazo es el índice de las tres tablas de canal. Al llegar al `cpx` valía
   el azul del color anterior, así que el lazo no terminaba y la consola se
   colgaba.
3. El azul se corría cinco lugares en vez de diez, y salía en los bits del
   verde. La pantalla se teñía de verde en lugar de azul.

Y el cuarto, que apareció recién cuando hubo una referencia contra la cual
comparar: el héroe se dibujaba **por encima** de la capa que tiene que taparlo.
La prioridad de un objeto son los bits 5 y 4 del byte de atributos, así que el
valor va corrido cuatro lugares, y `$20` no es prioridad 1 sino 2 —que en el
orden del modo 3 está adelante de BG2 1 y no atrás—. Estaba escrito igual de
mal en el conversor y en la ROM, o sea que las dos partes coincidían y sólo se
veía parándose debajo de la capa de encima. Ninguna caminata lo hacía: todas
terminan contra un borde del mapa.

Los cuatro se ven apenas se corre la página, y no se ven de ninguna otra forma.
La lección es la de siempre en este repo, pero al revés: acá el problema no fue
que la referencia y la ROM se equivocaran igual, sino que **no había ninguna
referencia que ejecutar**.

### La ventana de mensaje

La ventana vive en BG2, en la mitad de arriba del banco de tiles que comparte
con la capa de encima: del índice 0 al 255 cae el de encima y del 256 al 511 la
ventana. Su paleta es la que queda justo debajo de la de encima, y se la paga el
fondo: se lo aprieta en las que quedan y fusiona lo que no entre. Relevados los
328 mapas, 290 no fusionan nada y los 38 que sí van de 1 a 16 colores, que es el
techo —una paleta—.

**El tilemap de BG2 se scrollea con la cámara, y la ventana no puede.** No es un
caso raro: en `game_player.cpp` de easyrpg `UpdateMoveRoute` corre **antes** del
guard de `IsMessageActive`, o sea que una ruta forzada del héroe sigue caminando
con el mensaje en pantalla y la cámara lo sigue. En este juego hay 186 páginas
donde eso pasa y la primera está en el mapa 1; y hay 25 páginas paralelas con
`PanScreen`, que también corren.

Se probó primero **seguir el scroll** —escribir las celdas de la ventana en las
posiciones que en *ese* cuadro corresponden a la franja de abajo— y **no
funciona**, por una razón que no es de implementación: el tilemap se dibuja en
celdas de 8 pixeles y la cámara se mueve de a 2, así que una ventana estampada
en celdas cae a `camara_x mod 8` pixeles de donde va. Medido con la cámara
moviéndose sólo en horizontal, y comprobado corriendo la referencia esos mismos
pixeles:

    camara_x 720, resto 0    238 pixeles de diferencia
    camara_x 722, resto 2   2627
    camara_x 724, resto 4   2717
    camara_x 726, resto 6   3198

O sea: **un cuadro de cada cuatro por eje**. Y aparecían dos problemas más —la
franja hay que reestamparla entera en cada cruce, no la columna que entra, y la
fila que sale de la franja no la redibujaba nadie—. El detalle está en
ESTADO.md; el intento vivió tres commits.

**Lo que sí funciona es HDMA**, que era la opción que se había descartado por
2 KB de VRAM que no había. El DMA de siempre transfiere todo de una; el HDMA es
el mismo hardware disparado **una vez por scanline**, así que un registro del
PPU puede valer una cosa arriba de la pantalla y otra abajo. De la línea 0 a la
143 BG2 es la capa de encima del mapa, con la cámara; de la 144 a la 223 es un
tilemap propio de la ventana, de 32x32, con el scroll clavado:

    canal 1   BG2SC          qué tilemap dibuja BG2
    canal 2   BG2HOFS/VOFS   con qué scroll

Cada canal lee una tabla de la RAM con entradas `[cuántas líneas][valor]`. Las
144 líneas de arriba van en dos tramos porque el contador de una entrada es de
7 bits y no llega a 144, y las dos llevan justo lo que `flush_video` ya escribía
en los registros, así que arriba de la ventana no cambia nada.

Lo que esto compra, además de que sea exacto: el tilemap de la ventana **no lo
toca nadie más**, así que se escribe una sola vez al cargar el mapa —320 celdas
seguidas, un solo DMA— y abrir un mensaje es prender el HDMA y cerrarlo es
apagarlo. Ni una escritura de VRAM en el medio, ni un cuadro en negro, y
`redibujar_franja` dejó de existir.

El único cuidado: al apagar el HDMA hay que devolverle a `BG2SC` el tilemap del
mapa, porque el HDMA lo dejó apuntando al de la ventana en la última línea que
escribió.

**Los 2 KB salen de los sprites.** Relevados los 318 mapas que convierten, el
que más gasta usa 380 tiles de sprite de los 512 que el reparto le da, así que
bajarlos a 448 no le saca nada a nadie y deja libre la palabra $1C00, que es
múltiplo de 1024 y por lo tanto una base válida de tilemap. En el reparto para
mapas con mucho fondo los 2 KB no pueden salir de ahí —esos mapas usan hasta
320 tiles de sprite— y salen del fondo: 480 tiles en vez de 512.

### El texto se compone en caliente

Una página de mensaje ya compuesta son unos 240 tiles de 4bpp, o sea 7,5 KB, y
el juego tiene 18.808 líneas de texto: emitir una ventana por mensaje no entra
ni cerca en 256 KB. Así que la ROM lleva la fuente y arma los tiles ella, que es
lo que hace FF6 con su `InitDlgVWF` y su buffer de diálogo en la WRAM.

**La medición que lo volvió barato.** RM2k dibuja cada glifo usando sus pixeles
como máscara sobre un bloque de 16x16 del System —de ahí el degradé de las
letras— y leído así pide muestrear el bloque pixel por pixel. Medido, no: **cada
fila del glifo toma un solo color**, y la sombra es un color plano. O sea que
todo el color se reduce a doce bytes, uno por fila, más uno para la sombra.

El banco de tiles de la ventana se reparte así:

    0 .. 11     la ventana vacía, deduplicada: marco y fondo estirado
    12 .. 251   el área de texto, 30 celdas de ancho por 8 de alto

Las 240 del área de texto **no se deduplican**: cada celda tiene su tile fijo,
porque la ROM las reescribe y no puede andar buscando repetidos. De ahí sale el
tope de **39 caracteres por línea**: con 40 la sombra del último se pasa a la
celda 31 y harían falta ocho tiles más de los que hay. Truncar a 39 pierde el
1,58% de los caracteres del juego, contra el 1,09% de truncar a 40.

Componer un renglón es cebar el buffer con el fondo de la ventana —un DMA de la
ROM a la RAM, que va por la ventana que la WRAM tiene en el bus B— y escribirle
los glifos encima. Lo que hace rápida la escritura es que los planos 0 y 1 de
una fila son **bytes vecinos** en el formato de la consola, y los 2 y 3 también:
duplicando la máscara a los dos bytes de la palabra, cada par de planos sale de
una sola escritura de dieciséis bits, y son cuatro por fila de glifo en vez de
dieciséis. Y la celda que la máscara no toca se saltea entera, que en la mitad
de las fases es la mitad del trabajo.

**El presupuesto por cuadro está medido y no elegido.** Se componen 5
caracteres por vuelta del lazo. No es una optimización: si una vuelta se pasara
del cuadro, `wait_vblank` agarraría el siguiente y el héroe caminaría más lento
que en la referencia, que es una diferencia que ninguna captura muestra. Medido
sobre `snes-anclada`, que es el único caso donde el héroe camina con un mensaje
abierto: con 5 y con 6 no se pierde ningún cuadro, con 8 se pierde uno. Va en 5
por margen, porque la vuelta cuesta distinto en cada mapa.

Lo que cuesta: un mensaje de 51 caracteres tarda unos 15 cuadros en aparecer y
uno de cuatro renglones llenos tardaría unos 36. En RM2k tampoco desentona: allá
la ventana se abre con una animación.

**De dónde sale el texto: el operando del opcode.** `OP_MENSAJE` lleva un
desplazamiento de 16 bits dentro del bloque `mensajes`, que es de la ROM entera
y no del mapa. El conversor lo arma mientras compila las páginas —cada
`ShowMessage` deja su texto y se lleva su desplazamiento— y lo deduplica, que en
el juego entero son 2477 cuadros distintos de 2895.

Dieciséis bits alcanzan porque el bloque tiene que entrar **entero en un banco**
de 32 KB, y eso no es una casualidad de tamaño: lo lee `lda [msg_ptr], y` con un
puntero que el compositor incrementa de a un byte y que **no arrastra al byte de
banco**. Por eso el conversor lo emite con `.bloque`, que rellena hasta el banco
siguiente si no entra, y por eso `msg_empezar` puede sumarle el desplazamiento
al byte bajo y nada más. Si algún día no entra, lo que hay que agrandar es el
puntero, no el operando.

**Lo que no compila y por qué.** El texto de este juego usa dos códigos de
escape de RM2k: `\|`, que es una pausa de un segundo, y `\^`, que cierra el
cuadro sin esperar a que el jugador apriete nada. Son 35 líneas en 17 páginas, y
las dos cosas son tiempo, no texto. Una página que los use **no compila**:
dibujarlos como dos letras se vería, y borrarlos calladito sería peor, porque
con `\^` la ROM quedaría esperando un A que RM2k nunca pidió y la página
pasaría a durar lo que tarde el jugador. Cuando el compositor sepa pausar y
autocerrar, esto se cae solo.

Y llevar ventana es una decisión explícita del conversor, **`--con-ventana`**,
que `--mensaje-de-prueba` implica. Cuesta 8 KB de VRAM y una paleta, así que una
ROM que no la lleve no tiene dónde dibujar un mensaje y sus `ShowMessage` no
compilan: el opcode lo habilita la ventana, no al revés.

El ciclo son tres piezas y ninguna corre donde uno esperaría:

* `op_mensaje` deja el pedido y **corta el cuadro**. La página queda bloqueada:
  `eventos_tick` ve `msg_abierto` y vuelve sin ejecutar nada.
* El flanco de A la desbloquea —`pad_a` contra `pad_a_ant`, que es el
  `Input::IsTriggered` de RM2k: sostener el botón no dispara de nuevo— y la
  página sigue **en ese mismo cuadro**.
* `mensaje_de_evento` atiende el pedido al final del cuadro, con la pantalla
  apagada. Tiene que ser así: estampar la ventana son 640 bytes de tilemap y
  redibujar la franja al cerrar son 2560, y eso no entra en un vblank. Está
  medido, llamando a `redibujar_franja` de más a propósito sobre `snes-heroe 7`:
  cada cuadro deja 532 pixeles de basura, cada 8 cuadros 262, cada 64 cuadros 0
  y una sola vez 0. Que la basura escale con la frecuencia y no con el contenido
  es lo que dice que el problema es el presupuesto del vblank.

Y hay un detalle que cuesta descubrir: `mensaje_de_evento` empieza vaciando las
tiras que dejó `stream_map` en ese mismo cuadro. `redibujar_franja` arranca
poniendo `col_addr` y `row_addr` en cero, así que sin eso la columna o la fila
que la cámara acababa de destapar se perdería.

**Con un mensaje en pantalla el pad no mueve al héroe**, y la ruta forzada sí.
No es una inconsistencia: son dos lugares distintos de easyrpg.
`UpdateNextMovementAction` llama primero a `UpdateMoveRoute` y recién después
vuelve si `Game_Message::IsMessageActive()`, así que la ruta camina y el input
no. Un paso ya empezado se termina igual, porque en RM2k no se frena a mitad de
celda.

**Cómo se verifica.** `just snes-ventana` compara el dibujo —marco, fondo,
fuente, sombra y paleta— contra la referencia, en cinco mapas elegidos por
cómo les pega el reparto de paletas y de VRAM; el 269 está porque es el único de
la tanda que usa el reparto para mapas con mucho fondo, o sea el que pone el
tilemap de la ventana en otro lado. `just snes-cerrar` compara todo lo demás,
con la misma forma que `snes-espera`: dos cuadros con margen, uno antes y uno
después de apretar A.

    cuadro  60   la ventana en pantalla y la página frenada: sin teñir
    cuadro 400   la ventana borrada y el tinte puesto

Los dos cuadros difieren en 52637 pixeles de 57344, así que la prueba tiene de
dónde agarrarse. Con una dirección —`snes-cerrar 7 200 cerrar-right right`—
además se mantiene la cruceta apretada, y el cuadro 60 mide que el héroe no se
haya movido ni girado.

Cada mitad se verificó rompiéndola a propósito, que es la única forma de saber
que la prueba mira lo que dice mirar:

    sin `redibujar_franja` al cerrar   el cuadro 400 se va a 15789 pixeles
    sin bloquear la página             el cuadro 60 se va a 36848
    sin el guard del pad               el cuadro 60 de `right` se va a 22658

Es la única prueba que ejercita `redibujar_franja`, que hasta que existió el
opcode era el único pedazo de código del repo que no corría nadie.

Y que la ventana no se mueva con la cámara lo prueba `just snes-anclada`: una
ruta forzada en el mapa 6 con el mensaje abierto, que es el único caso en que la
cámara se mueve durante un mensaje —con el pad bloqueado, lo otro no existe—.
Los cuatro cuadros están elegidos por el resto de la cámara contra 8, que es
justo lo que hundía al intento anterior:

    cuadro  21   camara_x 722, resto 2   antes 2627 pixeles, ahora 0
    cuadro  23   camara_x 726, resto 6   antes 3198, ahora 0
    cuadro  50   camara_y 700, resto 4   antes 5964, ahora 0
    cuadro 130   la ruta ya bajó doce celdas   antes 11705, ahora 0

Y que el texto salga **del juego** y no de un flag lo prueba `just snes-texto`,
que es lo único que corre ese camino. Todo lo demás de la ventana usa
`--mensaje-de-prueba`: tres líneas inventadas en una página inventada, que
prueban el dibujo, el bloqueo y el cierre pero no que un `ShowMessage` compile
ni que el operando encuentre su texto.

El mapa 255 se eligió midiendo. Tiene una página automática **sin condición de
switch** —o sea que corre al entrar— cuyo código entero es esto:

    07 0000     OP_MENSAJE @0     "BRIDGE OVER THE RIVER LASHE" y tres líneas
    07 7c00     OP_MENSAJE @124   otras cuatro
    01 5003 01  el switch 848

De ahí salen las tres cosas que ninguna otra receta mira. El **desplazamiento**:
el segundo mensaje está en el 124, así que si el operando se ignorara se vería el
primero dos veces. Los **cuatro renglones**, contra los tres del mensaje de
prueba. Y el **encadenado**: al apretar A el primero se cierra y el segundo se
abre en el mismo cuadro, que es la regla que los dos lados escriben por separado.

Los cuadros 60 y 400 dan 0 de 57344, y **entre ellos difieren en 2869 pixeles**,
todos en las filas de la ventana: si el A no avanzara al segundo mensaje serían
cero y la receta daría verde sin probar nada.

### Cómo se verifica

La ROM la corre un core de libretro manejado desde Python con `ctypes`
—`tools/retro.py`—, no un emulador con ventana. `retro_run()` avanza **un cuadro
exacto**, la cruceta se contesta cuadro por cuadro y el framebuffer sale del
callback ya en 256x224. No hay servidor X, ni capturas de pantalla, ni recortes,
ni un solo `sleep`.

Eso no es sólo velocidad —la tanda pasó de 19m30s a medio minuto—, es lo que
hace que la prueba signifique algo. Antes decía "apretá derecha ocho segundos,
seguro alcanza": cuántos cuadros se emulaban en esos segundos dependía de la
carga de la máquina, y una máquina ocupada dejaba al héroe corto de la pared y
disparaba la comparación sin que nada estuviera roto. Ahora N cuadros son N
cuadros.

Y los cuadros tampoco se eligen. La referencia camina celda por celda hasta
chocar, así que sabe cuántas son; el paso del héroe son dieciséis pixeles a
`WALK_SPEED = 2` por cuadro, o sea ocho cuadros por celda. `snes_expect.py`
escribe ese plan y `snes_correr.py` lo lee. El único número puesto a mano es el
margen: ocho cuadros, una celda, porque la ROM llega uno o dos después —el pad
se lee una vez por cuadro y el primero se pierde—. Cruzar una puerta lleva
dieciséis, porque obliga a cargar el mapa entero y eso la referencia no lo
modela: medido, siete cuadros.

**Andan los tres cores instalados —snes9x, bsnes y mesen-s— y los tres dibujan
el mismo cuadro a 15 bits**, que es la precisión a la que se compara: 0 pixeles
de 57344, medido en el mapa 7 a los 180 cuadros. Que tres emuladores
independientes coincidan es lo que vuelve creíble a cualquiera de ellos. Los
tres tardaron en andar por errores del frontend y no de ellos —bsnes ignora los
datos de la ROM y abre el archivo él mismo, mesen-s quiere los callbacks después
de `retro_init` y un directorio de sistema—; el detalle de qué pedía cada uno
está en el docstring de `tools/retro.py`.

Se elige con `CORE`: `CORE=bsnes just snes-heroe 7`. La tanda corre en snes9x
porque es 23 veces más rápido —2747 cuadros por segundo contra 121—, y bsnes
entra por `snes-bsnes`, dos casos que cuestan veinte segundos. Antes de todo
esto había un `MOTOR=mednafen` que corría la tanda por el camino viejo, y se
sacó: mantenía cinco ramas y los segundos elegidos a ojo, y no lo corría nadie.
Un camino que ninguna prueba ejecuta es, en este repo, la manera en que
sobreviven los errores.

`just snes-hitos` corre seis mapas, uno por cada cosa que puede romperse:

    73, 18, 119   los que cerraron los hitos anteriores: tienen que seguir en cero
    6             recorre 100 celdas por los dos ejes: la ventana da tres vueltas
    8             Lashe City, que además pide el otro reparto de VRAM
    52            1000x80, con 40 KB de grilla que cruzan el corte de banco
    1             el primero del juego: la capa de encima se lleva 4 paletas
    348           el caso opuesto: el fondo usa 95 y encima fusiona 27

Más dos paradas quietas en el borde de abajo del mapa 1, que van de a pares
porque se equivocan para lados opuestos, y dos casos de varios mapas: uno que se
carga desde un registro que no es el primero de la tabla —con el índice 0 el
desplazamiento es cero y cualquier cuenta mal hecha da bien por casualidad— y
una puerta cruzada de punta a punta.

El evento del mapa 4 va dos veces, con una tabla de dos mapas y otra de cuatro.
Un teletransporte compilado guarda **el índice en la tabla**, no el número de
mapa, y con la tabla de dos ese índice es 1: el desplazamiento es un solo
`MAPA_STRIDE`, que es la cuenta que más fácil sale bien por casualidad. Con la
tabla `[4,7,19,1]` el mismo salto compila a 3. Bajarlo a mano a 2 —o sea,
mandar la ROM al mapa 19— mueve 55336 de los 57344 pixeles.

Lo que eso **no** prueba es la convención con la que se arma la tabla: el mapa
de `--map-id` primero y después los de `--mapas` sin repetir. Está escrita igual
en el conversor y en la referencia a propósito, porque si no compararían dos
mundos distintos, y por eso mismo equivocarla los equivoca a los dos juntos y la
comparación sigue dando cero. Ese lado se revisa leyendo, no corriendo.

Y tres más para las prioridades de objeto contra la capa de encima, que es por
donde ya se coló el cuarto error. `snes-evento` deja al héroe tapado, pero
entero: los 768 pixeles de su sprite están debajo de la capa, así que un héroe
que directamente no se dibujara daría la misma pantalla. Las dos paradas en la
celda (66,40) del mapa 1 son la misma escena con un solo bit distinto —ahí la
capa tapa 512 de 768 y la silueta tiene que partirse en el lugar exacto—:
primero con el héroe en prioridad 1, debajo, y después con `snes-encima`, que lo
sube a prioridad 2 y lo pone adelante. Entre las dos referencias hay 284 pixeles
de diferencia, así que el par no puede dar cero por casualidad.

Y una ruta forzada, `snes-ruta`, que es la única prueba que compara al héroe
**mientras** camina un guión y no donde termina. La diferencia importa: los dos
errores que destapó —los dos de la referencia, no de la ROM— eran del contador
de cuadros del ciclo de animación, y ninguno de los dos se ve en el cuadro
final, donde el héroe ya está parado. Compara cuatro cuadros de una ruta de doce
celdas con esperas en el medio, elegidos de modo que cada error conocido dé rojo;
el comentario de la receta dice cuáles y por qué. Corre en el mapa 6 porque es
mudo: para comparar un cuadro intermedio hay que saber cuántos cuadros de más
lleva la ROM en el arranque, y sin música son 10 —con música, 44—.

La prioridad 2 es la que llevan los eventos marcados "above", y no hay forma de
ejercitarla con los eventos del juego. Se relevaron los 335 mapas: **hay
exactamente uno con gráfico en esa capa**, el Package del mapa 261 en la celda
(59,1), y la capa de encima de ese mapa termina en x=938 mientras que su sprite
arranca en x=940. Por dos pixeles no se tocan, y donde no hay capa de encima las
prioridades 1 y 2 dibujan lo mismo. Por eso la prueba pasa por el héroe, que es
el mismo byte de atributos y el mismo `emit_object`: lo que se verifica es el
orden del hardware, no quién lo pide.

El Package igual entra en la tanda, con el héroe en (59,2). Ahí los dos sprites
se pisan y el Package tiene que quedar adelante aunque el héroe esté más abajo
en la pantalla, que es la regla de RM2k de ordenar primero por capa y recién
después por Y. Tratarlo como un NPC común mueve 79 pixeles.

Qué mapa elegir para eso no se adivina mirando el tamaño —uno enorme lleno de
paredes frena en la tercera celda—, así que `tools/snes_recorrido.py` camina
todos los mapas con las mismas reglas que la ROM y dice cuánto se recorre en
cada dirección.

Y no todo se llega caminando. Una caminata termina siempre contra un borde del
mapa, que es justo donde la cámara queda pegada; hay estados que sólo se ven en
el medio. `just snes-parado MAPA TX TY` planta al héroe en una celda elegida y
compara sin caminar, que además no depende de cuántos segundos se mantenga la
cruceta. Así se reprodujo el error de la banda de OAM.

**Dónde recortar la captura se le pregunta a X, no a los pixeles.** Se captura
el display entero de Xvfb y hay que quedarse con los 256x224 de la consola. La
primera versión buscaba el primer pixel distinto del fondo del servidor, que es
negro —y el mapa 1 es casi todo negro. En cuanto los sprites dejaron de
dibujarse envueltos arriba, el recorte se deslizó 93 líneas y la comparación
falló por algo que no tenía nada que ver con la ROM. Ahora `screenshot.sh` le
pide la geometría de la ventana a X y se la pasa a `snes_crop.py`.

Buscar esa ventana tiene su propia trampa: `xdotool search --name` no la
encuentra, porque sin gestor de ventanas mednafen publica `_NET_WM_NAME` y
`search` mira `WM_NAME`. Hay que enumerar y preguntarle el nombre a cada una.

## El personaje

Las poses de RM2k son de 24x32 y la SNES no tiene ese tamaño de objeto: el más
chico que las cubre es 32x32, así que se rellena con transparente a los costados
y se pierde una cuarta parte de los tiles. Son 192 tiles, 6 KB.

Y los sprites son **siempre de 4 bits por pixel**: no hay un modo 3 para ellos
como para el fondo. Talan tiene 36 colores y entran 15, así que acá sí hay que
fusionar. Cambia el 9,7% de sus pixeles, con un desvío máximo de 9,9 sobre 31
por canal.

**Cómo se verifica.** Se camina en cada dirección hasta chocar contra el borde
del mapa, y ahí la posición es exactamente el tamaño del mapa menos una celda.
La animación también queda predecible porque la ROM sólo anima cuando la
posición realmente cambia: contra el borde el personaje mira hacia allá pero no
camina en el lugar, que además es lo que hace RM2k.

`snes_expect.py` arma en Python lo que la consola debería mostrar —el mapa, la
cámara siguiendo al héroe, y el héroe en su pose parada con los colores ya
fusionados— y se compara pixel por pixel.

    parado    héroe en (160,112)  cámara (40,8)    0 pixeles distintos
    derecha   héroe en (304,112)  cámara (64,8)    0
    izquierda héroe en   (0,112)  cámara  (0,8)    0
    arriba    héroe en   (160,0)  cámara (40,0)    0
    abajo     héroe en (160,224)  cámara (40,16)   0

Encontró dos cosas que a ojo no se veían:

**Una entrada de CGRAM de menos.** El sprite emite 16 colores —el transparente
más los 15— pero la constante decía 15, así que el último nunca se subía y
quedaba en negro. Eran 14 pixeles de un gris apenas distinto.

**El noveno bit de la X.** La X de un objeto tiene nueve bits y el noveno vive
en la tabla chica de OAM. Sin él, el héroe pegado al borde izquierdo —que en
pantalla queda en -8— se leía como positivo y el sprite saltaba al otro lado de
la pantalla.

## La colisión

Toda la lógica de RM2k vive en `tools/rm2k.py`, fuera del conversor y de esta
consola: que
cruzar de una celda a la de al lado pide permiso a las dos —la de origen tiene
que dejar salir por ese lado y la de destino dejar entrar por el opuesto—, que
la capa alta manda sobre la baja salvo que sea decorado, y que las caras de
pared se cruzan siempre. La consola sólo lee los cuatro bits ya resueltos, que
desde el hito del redibujado viajan adentro del bloque de 16×16 en vez de en una
tabla aparte.

El movimiento también cambia: **RM2k no mueve al personaje libremente.** Se
compromete a una celda vecina y recorre sus 16 pixeles sin poder frenar. Por eso
el estado es la celda más cuántos pixeles faltan del paso en curso, y mientras
falten no se acepta otra dirección.

    parado     héroe en (160,112)   0 pixeles distintos de 57344
    derecha    héroe en (224,112)   0     frena en la celda 14 de 19
    izquierda  héroe en  (48,112)   0     en la 3
    arriba     héroe en  (160,80)   0     en la 5
    abajo      héroe en (160,160)   0     en la 10

Que frene en celdas interiores y no en los bordes del mapa es lo que dice que la
tabla se está mirando de verdad.

## Las tablas van en el banco 0

`lda tabla, x` direcciona **el registro de banco de datos**, no el banco donde
esté la tabla. Ese registro vale 0 al arrancar y nunca lo tocamos, así que una
tabla en otro banco se lee del lugar equivocado — sin ningún error, con bytes
que casualmente están ahí.

Pasó con la tabla de colisión: la ROM leía su propio código como si fuera
pasabilidad, y el personaje no se movía. Y pasaba desde antes con las tablas de
`ppu_reset`, que viven en el mismo segmento: **ese arreglo estaba funcionando a
medias.** Lo que sí funcionaba eran las escrituras directas —apagar el HDMA, los
scrolls— y los borrados por DMA, que llevan el banco explícito. Alcanzó para que
la corrupción de pantalla desapareciera, y por eso no se notó.

Ahora hay un segmento `TABLAS` que el enlazador pone en el banco 0. Todo lo que
la CPU recorra con un índice tiene que estar ahí.

Y lo que no entre en un banco no puede recorrerse con un índice, punto: la
grilla de celdas llega a 40 KB. Ésa se lee con un puntero de 24 bits, y ahí
aparece la otra cara de LoROM: **un banco sólo tiene sus 32 K de arriba**, así
que pasarse del `$FFFF` no lleva al `$0000` del banco siguiente sino a su
`$8000`. Dos rutinas de diez líneas, `ptr_mas` y `ptr_menos`, son las únicas que
saben eso; todo lo demás las usa y se olvida del tema.

## Cómo está armado

El audio lo maneja el **SPC700**, un procesador aparte con sus propios 64 KB. El
65816 no puede tocar el DSP: sólo hablarle al SPC700 por cuatro puertos. Al
encender, el SPC700 corre una ROM interna con un protocolo de carga; se lo usa
para meterle las muestras y un driver, y después ese driver se queda esperando
pares (registro, valor) que le pasa el 65816.

Eso deja el mismo reparto que en la Mega Drive: **toda la lógica en Python, y en
la consola sólo un intérprete de un stream de escrituras.** El driver del SPC700
son **20 bytes**.

    rom/src/main.s      65816: arranque, carga al SPC700, reproductor
    rom/snes.cfg        enlazado LoROM de 32 KB
    rom/record.sh       corre la ROM sin pantalla y graba el audio a WAV
    tools/spc700.py      ensamblador de SPC700, porque no hay uno empaquetado
    tools/brr.py         codificador del formato de muestras de la SNES
    tools/sdsp.py        registros del DSP y el banco de timbres
    tools/snes_music.py  el MIDI del mapa a muestras y stream
    tools/snes_check.py  compara lo que suena contra el MIDI
    tools/wavtone.py     mide la frecuencia de un WAV, para un tono suelto

## El banco de muestras

Que la SNES reproduzca muestras cambia el problema por completo. En el YM2612
cada timbre había que construirlo con cuatro operadores y nueve parámetros cada
uno, a ciegas. Acá el timbre **es** una grabación.

Y las grabaciones salen del **Microsoft GS Wavetable Synth**, que es el
sintetizador con el que este juego se compuso y se escuchó. Microsoft le licenció
a Roland un subconjunto reducido del Sound Canvas en 1996; no es un SC-55, es
exactamente esto. O sea que el port no se aproxima a un banco parecido: muestrea
del que produjo el sonido original.

Eso encaja exacto con el problema: los MIDIs de ABL especifican programas de
General MIDI y el SoundFont tiene una grabación por programa. Mapeo directo, sin
elegir nada a ojo.

Y que sea un banco *reducido* resulta ser una ventaja técnica grande. Sus
muestras son diez veces más cortas que las de un SoundFont completo como FluidR3
y ya vienen a 22 kHz, así que **el banco entero entra en ARAM sin remuestrear
nada** — y remuestrear era, por lejos, lo que más calidad costaba. Con FluidR3
el piano había que bajarlo de 32 kHz a 8230; ahora no se toca.

    PIANO64      5940 B      STRNG71B     6417 B      RDCYM60B     5076 B
    HARP_57A     2142 B      SOLKK60A     1386 B      CHH__60A       756 B
    CABA_60       621 B      MARCS60        648 B

Los ocho a 22 kHz, su tasa original. En total **23 KB de los 64**, con 42 libres.
El banco anterior usaba 52 KB y remuestreaba todo.

Tres detalles que deciden si suena bien o suena mal:

* **El loop tiene que caer justo en un bloque de BRR.** El DSP vuelve al
  principio de un bloque de nueve bytes, o sea cada 16 muestras. No se redondea
  y se espera: se elige primero cuántas muestras va a tener el loop y de ahí sale
  la tasa real.
* **El loop no se acorta.** FluidR3 los elige largos (casi un segundo en el
  piano) porque adentro hay batido entre cuerdas. Cortarlo mete una periodicidad
  audible, así que cuando falta lugar se baja la tasa, no el largo.
* **Los cuatro filtros de predicción del BRR**, que con las ondas de un ciclo
  daban igual y con audio real no:

        instrumento     sólo filtro 0        los cuatro
        piano          12,2% / 0,6%        10,4% / 0,3%
        arpa           12,6% / 2,1%         1,7% / 0,0%
        cuerdas        15,5% / 1,5%         3,6% / 0,4%

  (error de pico y medio, en porcentaje de la amplitud). Al piano lo que le
  queda es el ataque, que por definición no se predice.

## Cómo se suelta una nota

El release del ADSR del DSP **no se puede configurar**: al escribir KOF la
envolvente cae a cero en unos 8 ms. Eso se oye como un corte seco, y era lo que
más llamaba la atención una vez que las muestras fueron reales — sobre todo en
el piano, que debería resonar.

Así que las notas no se sueltan con KOF. Se apaga el bit de ADSR del registro
$x5, con lo que pasa a mandar GAIN, y a GAIN se le pide una caída exponencial
cuya velocidad sí se elige. La envolvente sigue desde donde estaba, así que la
nota se apaga en vez de cortarse. Es la técnica estándar de la consola.

El valor por familia está en `sdsp.py` y se elige de oído, como el resto del
banco: el piano y la campana resuenan (11 y 9, unos 300-400 ms), el órgano y los
vientos cortan casi con la nota (17, unos 130 ms).

El orden en el stream es lo que evita un caso especial: el release se escribe
**antes** que la preparación de la nota siguiente. Si en el mismo cuadro la voz
vuelve a arrancar, su setup pisa el ADSR1 y el GAIN queda sin efecto, que es
exactamente lo que corresponde.

KOF queda usado una sola vez en todo el tema: para callar todo al final.

## La percusión

Era lo que peor sonaba, y por lejos: el generador de ruido del DSP con la
frecuencia cambiada por golpe. Ahora cada golpe tiene su grabación, del kit
estándar de General MIDI —banco 128 del SoundFont, donde cada tecla es un
instrumento distinto en vez de una altura distinta—. El tema de prueba usa
cinco: bombo, charles cerrado, ride, cabasa y maracas.

Dos decisiones acá:

**Se recorta a medio segundo.** El ride de FluidR3 dura 2,6 segundos y el
charles cerrado 0,7, casi todo cola que se apaga. Enteros costarían más que
todos los melódicos juntos; se cortan y el resto lo hace la envolvente del DSP,
que es para lo que sirve.

**El presupuesto se reparte por brillo, no por uso.** El primer intento repartió
por cuántas veces suena cada golpe, y salió al revés de lo que hacía falta: el
bombo suena cien veces y no tiene un solo agudo, se llevó 24 kHz; el ride suena
dieciséis y es todo agudo, quedó en 4 kHz y sonaba a lata. Ahora se le mide el
centroide espectral a cada muestra —la energía de las diferencias entre muestras
consecutivas contra la energía total, que es la misma cuenta sin necesidad de
una FFT— y la tasa sale de ahí:

    bombo       brillo    473 Hz  ->   4000 Hz
    charles     brillo   9218 Hz  ->  17002 Hz
    ride        brillo   8012 Hz  ->  14780 Hz
    cabasa      brillo  11012 Hz  ->  18448 Hz

Con el mismo total de bytes. La percusión se lleva además una segunda voz del
DSP: con una sola, un bombo y un charles que caen en el mismo cuadro se pisan, y
en un patrón de batería eso pasa todo el tiempo. Cuesta un punto de cobertura
melódica (90% a 89%) y se nota mucho menos que perder la mitad de los golpes.

Ocho voces, todas iguales, contra las nueve de la Mega Drive —seis de FM
decentes y tres de onda cuadrada—. Con el reparto de voces por cobertura, que es
el mismo código de `md_music.py`, se reproduce el **90%** del tiempo-nota del
tema de prueba contra el 95% de la Mega Drive.

## Toolchain

**Dos cosas: `python` y `mednafen`.** Las dos están en pacman y en apt. No hace
falta ningún contenedor para compilar ni para verificar.

Llegar ahí costó escribir dos ensambladores propios, y por la misma razón las
dos veces: **nada clonado de internet ni compilado de fuentes sin revisar.**

    tools/spc700.py   el SPC700 no tiene ensamblador empaquetado en ningún lado
    tools/w65.py      el 65816 sí (cc65), pero no en los repos de Arch

El segundo es el interesante, porque había alternativa: clonar cc65 y
compilarlo. Se descartó porque eso mete código sin auditar en la misma caja
donde viven el repo y las credenciales, que es justo lo que se quería evitar.
`w65.py` reemplaza a `ca65` **y** a `ld65` — el layout de la ROM es fijo, así
que emite el binario directo, sin enlazador.

Que se pueda confiar en él no es una promesa. Ver más abajo.

## Cómo se verifica el ensamblador

`just snes-validar` ensambla el mismo fuente con las dos cadenas y compara los
32.768 bytes. Es la única cosa que todavía usa el contenedor, y sólo para eso:
`ca65` es el patrón contra el que se mide.

    main.s:     271 bytes de instrucciones — idénticas
    cobertura:  281 bytes de instrucciones — idénticas

Lo segundo hace falta porque lo primero no alcanza. La ROM del proyecto tiene
271 bytes de instrucciones y 32 KB de datos y relleno: un empate ahí prueba poco,
y sobre todo no toca las sesenta entradas de la tabla de opcodes que `main.s`
nunca usa. Una entrada sin probar es una trampa para el día que alguien la use.
Así que `tools/w65_coverage.py` genera un fuente sintético con **cada mnemónico
en cada modo de direccionamiento que la tabla declara** — 71 mnemónicos, 143
instrucciones — y se compara eso también.

Correrlo cada vez que se toquen las tablas. Mientras dé idéntico, `w65.py` es
correcto para todo lo que el proyecto puede expresar.

## Cómo se verifica la ROM

`mednafen -soundrecord` vuelca lo que sale del DSP a un WAV. Sobre eso hay dos
medidas, ninguna de las cuales necesita escuchar.

Para un tono suelto alcanza con la frecuencia: `wavtone.py` la saca por
autocorrelación, y si se pidió un La de 440 tiene que dar 440.

    tono de prueba: 440.4 Hz medidos contra 440 pedidos, 1 cent de diferencia

Para un tema entero eso no sirve, porque suenan varias notas a la vez. Así que
`snes_check.py` lo hace al revés: del MIDI ya sabemos qué notas deberían estar
sonando en cada momento, así que en vez de preguntarle al audio qué frecuencia
tiene se le pregunta cuánta energía tiene en esa frecuencia. La prueba está en
que además se mide un **señuelo** un cuarto de tono más arriba, que no cae en
ninguna nota: si el mapeo de alturas estuviera mal, el señuelo tendría tanta
energía como la nota buena.

    tema 11h035: 57 de 60 ventanas con la nota por encima de su señuelo (95%)

Cuánto de lo que falta es culpa nuestra lo dice `just snes-referencia`, que
toca el mismo MIDI con FluidSynth en la PC —el mismo SoundFont del que salen
nuestras muestras— y lo mide con la misma vara:

    FluidSynth en la PC:  59 de 60 ventanas (98%)
    nuestra SNES:         57 de 59 ventanas (97%)

O sea que estamos **a una ventana de la referencia**, contra el mismo
sintetizador y con el mismo banco. Sin ese número un 97% no significa nada:
podría ser el máximo alcanzable o podría faltar mucho.

La medida es ciega en los graves, y conviene saberlo: a 87 Hz el señuelo cae a
1,3 Hz de la nota y la ventana de análisis resuelve 11,7 Hz, así que ahí empatan.
Sirve de los medios para arriba.

Y hay un corrimiento que no se puede suponer: la ROM tarda **1,31 s** en
arrancar, porque sube el banco entero al SPC700 por el protocolo de la ROM
interna, que va byte por byte con acuse. Hoy son 0,64 s con el banco de 23 KB;
con el de 48 KB que usábamos antes era 1,40. La primera vez que se midió con muestras reales el puntaje bajó a 80%,
y no era el audio: era la búsqueda de corrimiento, que sólo miraba el primer
segundo y alineaba las ventanas con las notas equivocadas. Ahora se busca dónde
empieza a haber señal y se afina alrededor.

También se controla el pico del WAV. El DSP suma las ocho voces y recién después
aplica el volumen general, sin limitar en el medio: la primera versión saturaba
(pico 32768 clavado) y hubo que bajar el techo por voz. Los números de `sdsp.py`
salen de medir, no de la teoría, porque la teoría supone que todas las voces
pican juntas y en fase y eso no pasa nunca.

## Trampas del hardware

Todas éstas costaron horas y ninguna da error: la consola hace algo distinto de
lo que uno pidió, en silencio. Están acá porque van a volver.

**Un DMA de tamaño cero transfiere 65536 bytes, no ninguno.** Un mapa sin capa
de encima mandaba una paleta vacía y arrasaba CGRAM entera, paletas de sprites
incluidas. Cualquier tamaño que salga de un conteo tiene que garantizarse
distinto de cero.

**CGRAM y VRAM sólo aceptan escrituras con el PPU sin dibujar.** Obvio dicho
así, y sin embargo mordió dos veces el mismo día, las dos cuando el intérprete
de eventos se mudó de `cargar_mapa` —donde la pantalla estaba apagada— al lazo
principal, donde no. Un teletransporte cargaba el mapa nuevo y no llegaba nada a
la VRAM: se seguía viendo el viejo, como si el salto no hubiera ocurrido. Y un
tinte entraba **a medias**: quedaban teñidos la capa de encima y un sprite, y el
resto no, según qué escritura pescara el vblank.

Lo segundo no lo vio la tanda: snes9x acepta esas escrituras y mednafen no. Lo
encontró taro jugando, dos veces seguidas.

**La RAM arranca con basura, y el emulador rápido la arranca de otra manera.**
Ésta es la trampa que hace invisibles a las otras: una variable que nadie
inicializa puede dar verde en las 60 comparaciones y fallar en hardware real.
Pasó con `ruta_n`/`ruta_i`, que sin poner en cero hacían creer a `move_hero`
que había una ruta forzada pendiente, y el héroe no leía el pad nunca. La tanda
entera estaba verde.

Acá decía "snes9x llena la WRAM de ceros al encender", y **no es cierto**. Se
midió el 2026-09-04 con `msg_abierto`: sin su `stz`, `snes-cerrar` se cae en las
doce corridas de snes9x, y da igual dónde caiga la variable —se probó pegada a
`port0` y al final de BSS—. O sea que snes9x tampoco deja esos bytes en cero.

Lo que sí se sostiene es más fino, y conviene tenerlo escrito porque cambia
cuándo hay que desconfiar: lo que snes9x deja es **siempre lo mismo**, así que
esconde los errores que un patrón fijo esconde y no los otros. Medido el mismo
día, con el error de `ruta_n`/`ruta_i` puesto de vuelta a mano y diez corridas
por core:

    snes9x   0 de 10 en rojo
    bsnes    2 de 10

O sea que sea cual sea el valor que snes9x deja ahí, hace que `ruta_i < ruta_n`
dé falso las diez veces, y el error desaparece. `msg_abierto` no tiene con quién
empatar: alcanza con que no sea cero y se ve siempre. La regla práctica no
cambia —toda variable se inicializa— pero la razón sí: no es que snes9x sea
benévolo, es que es previsible.

Contra eso está `snes-bsnes`, que corre dos casos con `bsnes_entropy=High`:
bsnes llena la WRAM de basura, como la consola. Comentando esas dos líneas de
`main.s` y corriendo veinte veces el mapa 7, la basura rompe el cuadro 11 veces
de 20 —con `Low`, 3; con `None`, ninguna—. O sea que no lo agarra siempre, pero
lo agarra la mitad de las veces y sin que nadie tenga que jugar. Con la ROM sana
las veinte corridas dan el mismo cuadro, así que esto no vuelve inestable a la
tanda.

La carga de mapa se arregla apagando la pantalla, como ya hacía `cruzar_puerta`.
Para el tinte se intentó primero diferirlo a `flush_video`, que corre en el
vblank, **y no alcanza**: `aplicar_tinte` arma tres tablas de canal de treinta y
dos entradas y sube tres paletas por DMA, y eso se pasa del vblank. El resultado
era un tinte a medias distinto en cada intento —una vez la capa de encima y un
sprite; otra el fondo teñido, el héroe en negro y los NPCs sin tocar—. La única
forma que aguanta es apagar la pantalla, igual que para cargar un mapa: cuesta
un cuadro en negro, que en RM2k tampoco desentona porque el motor original funde
a negro en las transiciones.

**Un bloque de cero bytes no es un bloque.** La subida al SPC700 va por el
protocolo del IPL —dirección, un puerto en no-cero, el índice—, y con cero bytes
del otro lado nadie contesta: la ROM se queda esperando el handshake. Pasaba con
cualquier mapa sin música, que son la mayoría. Lo peor era el síntoma: el
cuelgue es *después* de encender la pantalla y dibujar el mapa, así que la ROM
tenía toda la pinta de andar y lo único raro era que el héroe no se movía. Es la
misma familia que el DMA de tamaño cero, y la misma lección: cualquier cantidad
que salga de un conteo hay que garantizarla distinta de cero antes de usarla.

Su primo: **un stream de música vacío colgaba `music_frame`**, porque al llegar
al final vuelve a empezar y lo primero que encuentra es otro final. Los dos
estuvieron escondidos mientras `musicdata.inc` lo generaba una receta aparte y
siempre tenía un tema de verdad; aparecieron el mismo día, apenas el conversor
empezó a emitir la música del mapa.

**Un DMA no sigue el mapeo de LoROM.** Su dirección de origen se incrementa
linealmente, y el byte que sigue a `$02FFFF` no es la ROM del banco 3 sino la
RAM. Un bloque que cruce ese límite se sube bien hasta ahí y basura después.
`w65.py` tiene `.bloque N` para rellenar hasta el banco siguiente, y el
conversor lo declara antes de cada bloque. Ese relleno es lo que terminó
obligando a pasar el cartucho de 128 a 256 KB: los datos entran, lo que no entra
es el acolchado de bloques de 25 y 42 KB.

**Un puntero de 24 bits tampoco lo sigue.** El byte que sigue a `$01FFFF` está
en `$028000`, no en `$020000`: un banco de LoROM sólo tiene sus 32 K de arriba.
Cualquier tabla que no entre en un banco —la grilla de celdas llega a 40 KB—
tiene que avanzarse con esa corrección. Está en `ptr_mas` y `ptr_menos`.

**`lda tabla, x` direcciona el banco de datos, no el banco de la tabla.** Ese
registro vale 0 y no lo tocamos, así que todo lo que la CPU recorra con un
índice tiene que estar en el banco 0 — de ahí el segmento `TABLAS`.

**Los registros de scroll comparten un único latch entre todos los planos.**
Escribir BG1 bajo, BG2 bajo, BG1 alto, BG2 alto mezcla los valores. Hay que
completar cada registro antes de pasar al siguiente.

**El PPU muestra la línea `vofs+1` en el primer scanline**, no la `vofs`. Con el
scroll en 0 el mapa queda corrido una línea.

**La X de un objeto tiene nueve bits**, y el noveno vive en la tabla chica de
OAM. Sin él, un sprite en `-8` se lee como positivo y salta al otro lado.

**La Y de un objeto tiene ocho, y la pantalla 224 líneas.** Los valores 224 a
255 quedan ambiguos, y el PPU los resuelve siempre para el mismo lado: los lee
como "un poco más arriba del borde de arriba" y dibuja el objeto envuelto. Un
NPC que se iba por abajo se guardaba con una Y de esa banda y reaparecía arriba
—primero los pies, después entero— antes de desaparecer.

La ambigüedad no se puede sacar, y encima hace falta: es la que hace que un
objeto en `y = -31` muestre su última línea en la línea 0. Lo que no puede pasar
es que le llegue un objeto que de verdad está abajo, así que el descarte de
`emit_object` va en 224 y no en 256. La cuenta de la X es la misma y va en 256.

Ninguna de las caminatas del arnés lo tocaba: todas terminan contra un borde del
mapa, y ahí la cámara está pegada y los NPCs no quedan nunca en esa banda. Por
eso `snes-hitos` ahora incluye una parada quieta en (75,88) del mapa 1, donde
hay cuatro NPCs justo debajo del borde.

**La consola lee los controles sola al empezar el vblank, pero no arranca en el
mismo ciclo.** Preguntar sólo "¿terminó?" pasa de largo y lee registros a medio
armar; hay que esperar a que empiece. Y si antes se hace algo largo —el DMA de
OAM— se llega con la lectura ya terminada y esperar su arranque cuesta el cuadro
siguiente entero.

**OAM sólo se puede escribir en el vblank, y armarla lleva tiempo.** Con treinta
personajes no entra armarla y subirla en el mismo vblank: se sube la del cuadro
anterior apenas abre, y se arma la del siguiente después.

**El ancho de A y de X/Y es estado, y el ensamblador lo cree.** Las directivas
`.a8` y `.a16` no describen: mandan. Un `cruzar:` puesto justo debajo de un
camino que terminaba en `.a8` hereda ese estado aunque se llegue ahí por un
salto con A en 16 bits, y entonces un `and #$00FF` sale con un byte de operando,
el CPU lee dos, y se come la instrucción siguiente. La pantalla queda negra y no
hay ningún error. Toda etiqueta a la que se salte desde otro ancho tiene que
declararlo.

Y la misma trampa del otro lado: `tax` con X de 16 bits transfiere los dos bytes
del acumulador, incluido el alto, que con A en 8 bits nadie tocó y trae lo que
dejó la operación anterior. Una cuenta de direcciones hecha en 8 bits y cerrada
con `tax` funciona mientras ese byte alto sea cero.

**La prioridad de un objeto son los bits 5 y 4 del byte de atributos**, no los
0 y 1: `vhoopppN`. Escribir `$20` creyendo que es prioridad 1 da prioridad 2, y
en el modo 3 el orden es `objetos 3 / BG1 1 / objetos 2 / BG2 1 / objetos 1 /
BG1 0 / objetos 0`, así que ese lugar de más cruza justo la capa de encima. El
sprite se sigue viendo, sólo que del lado equivocado de una capa.

Los dos valores viven en un solo lugar, `tools/snes_convert.py`: el de cada NPC
va armado dentro de su byte de atributos y el del héroe llega a la ROM como
`HERO_PRIORITY` en `mapdata.inc`. Tenerlos también escritos en `main.s` era la
duplicación de siempre —dos lados que se pueden equivocar igual— y así fue como
este error sobrevivió a la primera comparación.

**Un `jsr` te devuelve `X` e `Y` como se le da la gana.** No hay convención de
llamada acá: cada rutina usa los índices para lo suyo. Cuando un registro es un
cursor que tiene que sobrevivir a una llamada —el del bytecode del intérprete lo
es— hay que guardarlo con `phy` en el que llama, y el que llama es el único que
sabe que hace falta.

**La consola arranca con lo que dejó el programa anterior.** El emulador arranca
en cero. Hay que escribir los 43 registros del PPU, no sólo los que se usan, y
cortar el HDMA antes que nada.

**En una línea no entran más de 34 tiles de 8x8 de sprite.** Un objeto de 32x32
aporta cuatro, así que a partir de nueve personajes juntos se pierden los
últimos. No tiene arreglo; se declara y se excluyen esas líneas de la
comparación.

## Lo que falta

* **Que un NPC frene al héroe.** En RM2k los eventos de la capa del héroe
  bloquean el paso; la ROM todavía no lo mira. La tabla ya trae el dato.
* **Los teletransportes que siguen sin resolverse.** Los que están adentro de
  cinemáticas con variables y condiciones que todavía no modelamos. El del mapa
  donde el juego arranca ya no: es automático, entra con los cinco comandos que
  la ROM entiende, y `Blank (Leave START here)` ahora se sale solo.
* **Cambiar la música desde un evento (`PlayBGM`).** Decidido dejarlo afuera el
  2026-09-03, y aceptado igual: una página que lo use compila, y la ROM sigue
  con el tema que venía sonando. No es una equivalencia sino una deuda, y está
  en `ACEPTADOS_SIN_HACER` de `tools/eventos.py` con ese nombre a propósito.

  Cuesta caro porque la ROM sube **un solo banco de muestras** al SPC700 al
  arrancar: cambiar de tema en caliente pide varios bancos en el cartucho y
  volver a subir en mitad del juego, con la pantalla andando. Es una feature de
  audio, no un comando más.

  Lo que se pierde no se ve en la pantalla que se compara, que es el criterio
  por el que se acepta. Pero sí se oye, y hay un segundo efecto que conviene
  tener presente: `snes-check` compara el audio contra el MIDI **del mapa**, así
  que en un mapa donde una página cambia el tema esa prueba estaría midiendo
  contra el tema equivocado. Hoy no pasa —ninguna página que compile usa
  `PlayBGM`— y el conversor avisa por pantalla en cuanto pase.

* **La cinemática de apertura.** El mapa 4 prende el switch 20, que es la
  condición de la página que abre el mapa 1: el enganche ya funciona, y si esa
  página se pudiera correr, arrancaría sola. No se puede por la regla de todo o
  nada: la condición pide `actor` —que el héroe 10 esté en el grupo, y todavía
  no hay grupo— y le faltan comandos. De los cuatro que le faltaban, `PlayBGM`
  ya se acepta y `MoveEvent` caminando también, desde el 2026-09-03; quedan
  `WeatherEffects` y `ChangePartyMembers`.
  Mientras tanto el héroe queda parado adentro del caño, que es donde RM2k
  también lo deja: ahí no camina nadie, sigue el script.
* **Lo que le falta al juego entero, medido.** De las 489 páginas automáticas
  con comandos, hoy compilan enteras **71** —eran 16 antes de que los cuadros de
  texto compilaran—. Y esto es cuántas pasarían a compilar con cada comando
  hecho, contando una ROM que lleve la ventana —`just snes-destraba`—:

      MoveEvent de otro evento  +40      WeatherEffects         +0
      FlashSprite               +23      FullHeal               +0
      PlaySound                  +6      ChangeItems            +0
      ControlVars                +4      CallEvent              +0
      TintScreen con saturación  +4
      ConditionalBranch          +3
      ChangeEventLocation        +1
      PanScreen                  +1
      FadeOutBGM                 +1

  Puestos los trece juntos se llega a **305 de 489**. Y lo que seguiría cortando
  después de todos ésos lo encabeza `ShowBattleAnimation` con 22, seguido de
  `ShowChoice` con 12 y de los 11 cuadros de texto con códigos de escape.

  **Este número no es el que estaba escrito acá antes, y la diferencia importa.**
  Lo de antes contaba qué comando corta **primero** cada página —ShowMessage
  144, CallEvent 98, MoveEvent 60— y eso no es lo que se destraba: una página
  cortada por un cuadro de texto puede estar cortada además por otras cuatro
  cosas. Con el número bueno, la conclusión sobre los cuadros de texto se
  sostuvo —eran +55, y hechos dieron exactamente eso— pero las de abajo cambian
  de lugar, y `MoveEvent` sobre otro evento pasó de +3 a +40 al hacerlos: eran
  las mismas páginas, contadas detrás del corte que ya no está.

  Dos trampas que costaron una medición mal hecha cada una, y que están
  anotadas en `tools/destraba.py` para no volver a pisarlas:

  * RM2k emite un `ShowMessage` y después un **`ShowMessage_2` por cada línea
    de más** del mismo cuadro. Contándolos aparte, los cuadros de texto
    parecían destrabar tres páginas y no cincuenta y cinco.
  * `CallEvent` aceptado sin hacerlo daba **+97**, que es falso: el evento
    común llamado tiene que compilar él también, y los de este juego se cortan
    casi todos en `FullHeal` y en `ControlVars`. Hecho de verdad destraba cero
    hasta que esos dos existan.

  Puestas todas juntas se llega a 314 de 489, y lo que sigue cortando después
  es una cola larga: `ShowBattleAnimation` 23, `ShowChoice` 13,
  `ChangeScreenTransitions` 10, `JumpToLabel` 8.

  Y una nota que sigue valiendo: de las páginas con `MoveEvent`, la mayoría
  mueve **otro evento** y no al héroe, o sea que piden que los NPCs caminen, que
  es una feature aparte de la ruta forzada que ya anda.
* **Componer el texto del mensaje en caliente.** Es lo que separa al opcode que
  ya existe de que esas 144 páginas compilen: hoy la ROM lleva una sola ventana
  ya compuesta por el conversor, porque una por mensaje son 7,5 KB y no entran.
  Hace falta la fuente en la ROM y armar los 240 tiles desde el 65816, como hace
  FF6 con su `InitDlgVWF` y su buffer de diálogo en la WRAM. Ver "La ventana de
  mensaje".
* **El mapa entero en un cartucho.** Los 328 mapas suman 3,7 MB y LoROM llega a
  4, así que hoy entra un puñado por ROM y se elige al compilar. La salida
  probable es compartir los tiles entre los mapas que usan el mismo chipset:
  son 43 chipsets para 328 mapas.
* **Mapas con más de ocho personajes distintos.** Los sprites van en 4 bits y
  hay ocho paletas para ellos, una por CharSet. Yun Town usa diez y Sorbe
  Village once, así que no convierten. Los dos venían tapados detrás del
  problema de las paletas de la capa de encima, que ya está resuelto.
* **El ataque y el decaimiento** siguen saliendo de las ocho familias de
  `sdsp.py`, elegidas a ojo cuando el banco era sintético. El SoundFont trae los
  suyos por instrumento y todavía no se leen. (El release ya no: ver arriba.)
* **Una muestra por instrumento.** Un piano real está multi-muestreado cada
  pocas notas; nosotros tomamos la del do central y transponemos. En los
  extremos del teclado eso se nota.
