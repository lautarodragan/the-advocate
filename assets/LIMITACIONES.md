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


## El que no consigue paleta de sprite usa la de otro, y se ve mal

Un evento dibujado con un tile del chipset es, para la consola, un personaje más
con su paleta, y las paletas de sprite son ocho. Cuando ya no queda ninguna, el
gráfico **no se descarta**: se cuelga de la paleta ajena que menos colores le
falten, y cada color que no está ahí se dibuja con el más cercano por luma.

La decisión es de taro, el 2026-09-08, y su argumento cierra la discusión: *"si
no podemos incluir todos los eventos, el proyecto entero se cae"*. Un sprite con
los colores cambiados es un error que se ve; uno que no se dibuja es una pared
invisible que dispara y cierra el paso, y ya costó una tarde con la puerta que
Core rompe.

**Lo que cuesta, medido antes de decidirlo.** Por gráfico, el porcentaje de sus
pixeles que cambia de color y el salto peor en un canal, sobre 31:

    @tile:BLchp1:112     0%
    Chara2:0            21%, salto 9
    @tile:BLchp1:53     23%, salto 11
    Future1:7           38%, salto 15
    @tile:BLchp1:117    42%, salto 1     ← la puerta del pad de Talan
    Future3:1           49%, salto 17
    @tile:BLchp1:111    70%, salto 13

El caso de la puerta es el que muestra por qué el porcentaje solo no alcanza:
cambia el 42% de sus pixeles pero ninguno se mueve más de 1 sobre 31, así que a
ojo es la misma puerta.

**Qué destraba.** El mapa 8 —la calle a la que da el pad— pedía trece paletas de
ocho y no había reparto posible; hoy entra con seis gráficos prestados, y entre
ellos el save point. El Hover-Tram (mapa 13) pedía once y hoy entra con dos. El
tope real dejó de ser la cantidad de paletas.

**Lo que sigue costando.** El presupuesto de tiles de sprite en VRAM: dibujar
todo llevó al mapa 8 de 192 a 347 tiles, y hubo que rebalancear los cuatro
repartos de VRAM para que entren 400 de fondo y 347 de sprite a la vez. Ver
`LAYOUT_*` en `tools/snes_convert.py`.


## Un evento de una sola página condicionada no se dibujaba nunca

`collect_npcs` mira qué gráficos puede llegar a dibujar un evento y, si es uno
solo y al cargar el mapa no está activo, lo salteaba: no le armaba fila. Pero el
conjunto de estados posibles no es sólo el gráfico de cada página — si la
**primera** tiene condición, puede no haber ninguna activa, y ese "nada" es un
estado más.

taro lo vio el 2026-09-07 con el `TalDoorBottom` del mapa 8: se puede usar y
corre sus comandos, pero no se dibujaba. **No eran dos bugs**: la tabla de
páginas —que dispara— y la de NPCs —que dibuja— son distintas, y el evento
estaba en la primera.

Son **350 eventos en 68 mapas**, y contarlos es una línea. Estuvo sin hacer un
día entero porque destapaba más gráficos de los que entran en ocho paletas; lo
destrabó la sección de acá arriba.


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
