# Lo que decidimos que este port no hace

Este archivo existe porque el horizonte del proyecto es un `migrar-rm2k-a-snes
juego.zip juego.sfc` que ande sin ajustar tuercas —ver el final de
`assets/README.md`— y varias de las decisiones que tomamos **no son generales**:
funcionan porque *A Blurred Line* es como es. Si mañana alguien apunta esto a
otro juego, acá está lo que hay que volver a mirar, con el número que justificó
cada cosa.

No son deudas ni cosas a medias: son elecciones, medidas, que valen para este
juego. Lo que está a medias vive en `ESTADO.md`.


## Sólo se lleva a VRAM lo que el mapa dibuja, no el ChipSet entero

Un chipset de RM2k expandido son cientos de tiles de 8x8 —el `ChipSet3` da 420
y el `BLchp1` 523, contando sólo los ids que algún mapa del juego usa— y en la
SNES el fondo tiene **384 tiles con la ventana de mensaje puesta**, o 480 en el
reparto alternativo. No entra.

Así que el conversor renderiza el mapa y saca los tiles únicos de lo que se
dibuja: el mapa 1 son 341 y el 2, 278, contra los 420 del chipset que comparten.

**Qué se pierde con esto.** Que dos mapas del mismo chipset compartan sus tiles,
que es lo que ahorraría bytes de cartucho y evitaría recargar VRAM al cruzar de
uno al otro. Medido: el pool compartido de los mapas 1 y 2 son 437 tiles y no
entra en ninguno de los dos repartos.

**Cuándo deja de alcanzar.** Un juego cuyos mapas usen más de ~400 tiles
distintos de fondo no entra, y ahí no hay reparto que lo salve: hay que
recargar VRAM mientras el mapa scrollea, que es un motor distinto del que hay.


## La ventana de mensaje se lleva 10 KB de VRAM, y eso aprieta todo

Son 8 KB de tiles —12 fijos más 240 del área de texto— y 2 KB de tilemap
propio. De los 64 KB de VRAM, eso es lo que hace que al fondo le queden 384
tiles en vez de 512.

Los 240 tiles del área de texto salen de que **el glifo mide 6 píxeles de ancho
y la celda 8**: no alinean, así que cada celda es un tile propio que la ROM
compone pixel por pixel. Es lo que hace Final Fantasy, y se verificó contra su
decompilación antes de descartar alternativas.

**La alternativa que existe y no tomamos**: glifos de 8 px, alineados a la
celda. Ahorraría unos 48 tiles —1,5 KB, o sea 24 tiles de fondo— y bajaría la
línea de **39 caracteres a 30**. Los textos del ABL están escritos para 39, así
que cortarían distinto que en el original.

Queda como plan B por una razón concreta: **ya estamos truncando texto** por la
diferencia de resolución, así que en algún momento va a hacer falta un algoritmo
que rearme los saltos de línea. Hoy cada cuadro de texto es un comando aparte y
cada salto está puesto a mano, así que fusionar comandos consecutivos pide
decidir cuándo es razonable hacerlo —¿cambió quién habla?— y eso puede no ser
determinístico. El día que ese algoritmo exista, pasar a 30 columnas deja de ser
un costo técnico y pasa a ser sólo estético.


## Un evento que no entra en las paletas de sprite no se dibuja, pero ocupa

Un evento dibujado con un tile del chipset es, para la consola, un personaje más
con su paleta, y las paletas de sprite son ocho. Cuando no entra, el conversor lo
deja sin dibujar y **el evento sigue ahí**: cierra el paso y dispara igual.

Desde el 2026-09-07 eso corta la conversión si el evento **cambia de gráfico
entre sus páginas**, porque ésos son mecanismos —una puerta que se abre— y sin
dibujarse dejan una pared invisible; ver `aviso_de_descarte`. Los de una sola
página son adornos y sólo se avisan.

**Cuándo deja de alcanzar.** En este juego cada personaje de CharSet usa los 15
colores enteros y no comparte ninguno, así que un mapa con nueve personajes pide
nueve paletas y no hay reparto posible: es el caso del mapa 8, la calle a la que
da el pad de Talan. Fusionar dos de esas paletas cuesta el **17% de los pixeles**
de esos sprites, con saltos de 18 sobre 31 en un canal. Para un juego con
personajes de menos colores el problema no existe; para éste, la salida es no
dibujar lo prescindible y no fusionar.


## El destello de un evento tiñe la paleta, no el sprite

`FlashSprite` en RM2k tiñe **ese** dibujable. En la consola el tinte es una
transformación de CGRAM, así que tiñe la paleta entera y con ella todo lo que la
comparta. La referencia hace lo correcto —aplica el destello sobre la imagen— y
por eso los dos lados pueden diferir sin que la tanda de pixeles lo vea.

Lo que hacemos es que **nadie comparta la paleta de un líder posible**, porque el
héroe es el que destella en este juego y es el único que se puede saber al
convertir. Ver `pruebas/test_destello_paleta.py`.

**Cuándo deja de alcanzar.** Un juego que destelle sobre un NPC cualquiera va a
filtrar el color a quien comparta su paleta. La solución general sería darle una
paleta propia al que destella, en caliente, y hoy no hay ninguna libre.


## El cronómetro comparte paleta con un personaje

Sus dígitos son dos colores y entran en la paleta de cualquiera que tenga trece
o menos. Reservarle una de las ocho le sacaba eventos al mapa: el 2 perdía la
celda del medio de la puerta que Core rompe.

**Cuándo deja de alcanzar.** Un mapa cuyas ocho paletas estén llenas hasta el
tope; ahí el conversor corta y lo dice.


## Los mapas que el cartucho no lleva hacen que sus páginas no compilen

Un `Teleport` a un mapa que no entró en la ROM hace que esa página no sea
ejecutable, y el conversor lo nombra. Es a propósito: saltar a cualquier lado
sería peor. Con la demo de la apertura eso deja afuera, por ejemplo, la puerta
que sale del pad de Talan, que lleva al mapa 8.

**Cuándo deja de alcanzar.** Nunca, mientras el juego entero entre en el
cartucho. Es una limitación de las ROMs de prueba, no del port.
