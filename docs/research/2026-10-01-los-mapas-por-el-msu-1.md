# Los mapas por el MSU-1: hasta dónde llega el cartucho

> **Medido el 2026-10-01 sobre `37ea12fc`**, por Lechuza. Es una foto: los
> números son de ese día y este archivo no se actualiza. Lo que dice cuánto
> le queda **hoy** a cada cartucho es `just espacio`; cuánto tarda el puerto
> de datos, `just msu-puerto`. Las cuentas del juego entero salieron de
> scripts descartables; cómo rehacerlas está al final, en "Cómo se midió".

## Resumen

* **El juego entero, convertido como hoy, son 8.514 KB de datos, 8,3 MB**:
  266 bancos de 32 KB contra los 124 que entran. Es el doble y un poco más
  de lo que tiene el cartucho, y **no entra tampoco en 8 MB** de ExHiROM o de un
  chip con mapeador: confirma, con el número, lo que taro dijo el 2026-09-27.
* **Cuatro de cada diez bytes son música**: 1,4 MB de secuencias y 2,1 MB
  de muestras BRR, 3,4 MB entre las dos. Con MSU-1, la música ya suena de
  las pistas y los efectos de calidad ya vienen del `.msu`: ese peso existe
  sólo para jugar **sin** MSU-1. Otros 1,9 MB son lo que un mapa sube al
  entrar —tiles, colores, grilla, tiles de sprites—, que se puede leer del
  `.msu`.
* **Sacando esas dos cosas, la ROM del juego entero pesa unos 3,0 MB**, y
  entra en los 124 bancos con 0,9 MB libres. Lo que queda en la ROM es lo
  que la CPU lee mientras se juega: las poses, que se suben en caliente; el
  bytecode; los textos; la pelea; las pantallas.
* **Leer un mapa del `.msu` es más rápido que descomprimirlo de la ROM**:
  el puerto da 2,60 MB/s —42 KB por cuadro, medido en snes9x, bsnes y
  mesen-s—, y crudo no hay nada que descomprimir. La carga de un mapa típico
  pasa de unos 5 cuadros a medio; la del más pesado, de 22 a menos de 2.
  **El fundido se acorta, no se alarga**, salvo lo que tarde en buscar el
  cartucho de verdad, que **no está medido**: para eso queda una ROM de
  prueba para el FX Pak.
* **Sin MSU-1 no hay juego entero de ninguna forma.** La recomendación es
  **dos cartuchos del mismo conversor y el mismo runtime**: `release`, como
  hoy, sin MSU-1 y hasta donde entre; y uno nuevo con el juego entero, que
  pide MSU-1. Las fases, al final.

## 1. Cuánto pesa el juego entero

### La cuenta

El juego tiene **328 mapas** en el árbol (`rom/data/maps.json`, los de tipo
mapa). `release` lleva 93. El conversor no puede armar los 328 en una
corrida —ver "Lo que no convierte" abajo—, así que se convirtió en **once
corridas** que se reparten los mapas, cada una con su propio archivo de
proyecto, y se sumó:

* lo que sale **idéntico** en dos corridas que comparten mapas —los tiles de
  un mapa, una pose, un battler, una muestra— se cuenta una vez;
* lo que depende de la corrida aunque el mapa sea el mismo —el bytecode, que
  lleva números de variable y de texto globales; los tiles de sprites, que
  dependen de los candidatos a líder; las tablas de un solo ejemplar— se
  suma por corrida, restando la base que todas llevan;
* las secuencias de música, por nombre de tema.

Hecha sobre `release` sola, la cuenta da sus 3.913.695 bytes exactos, que es
lo que `just espacio` llama 120 bancos usados. (Las muestras son de
instrumentos y de efectos juntas: en `release`, los efectos son 458 KB de
las 925, según `conversor.log`.)

    rubro                                    release      juego entero
    muestras BRR (instrumentos y efectos)     925 KB         2.120 KB
    secuencias de música                      634 KB         1.399 KB   103 temas
    sprites: poses                            473 KB           941 KB
    sprites: tiles por mapa y tablas          239 KB           562 KB
    fondo: tiles y colores                    543 KB         1.494 KB
    grilla, bloques y colisión                162 KB           400 KB
    eventos: bytecode y páginas               204 KB           466 KB
    batalla: battlers, animaciones, fondos    269 KB           547 KB
    textos                                    170 KB           311 KB
    lo demás: pantallas, fuentes, tablas      202 KB           274 KB
    total                                   3.822 KB         8.514 KB
                                           (120 bancos)     (266 bancos)

**La parte fija es chica**: pantallas, fuentes y tablas son 274 KB. Todo lo
demás crece con el contenido, pero de dos maneras distintas:

* **por mapa**: fondo, grilla, tiles de sprites, bytecode y textos. De
  `release` al juego entero crecen de 1.318 a 3.233 KB, unos **8,5 KB por
  mapa** de los 226 que faltan;
* **por lo que el mapa trae**: un tema nuevo, un CharSet nuevo, un enemigo
  nuevo. Las muestras, las secuencias, las poses y la pelea crecen de 2.301
  a 5.007 KB, unos **12 KB por mapa** en promedio, pero en saltos.

En total, **20,8 KB por mapa** nuevo, que es lo que hay que tener a mano para
cualquier "¿entran N mapas más?".

**El bloque de textos llega justo**: los mensajes del juego entero ocupan
unos **255 KB** del bloque de 262.144 que deja el operando de `OP_MESSAGE`
de a 4 bytes. Entra, pero con lo que sume cualquier relleno o cualquier
texto de prueba deja de entrar; ver `todo/los-textos-sin-comprimir.md`.

### Lo que no convierte

**Cinco mapas no entran en la VRAM** con el conversor de hoy, y no es un
problema de espacio del cartucho:

    108 Distant Paradise     462 tiles de fondo, 696 de sprite: no queda lugar
    127                      138 de fondo, 696 de sprite      para la ventana
    148                      614 de fondo, 211 de sprite      de mensaje
    250                      621 de fondo, 211 de sprite
    285                      muestra animaciones de batalla y su caja de 64
                             tiles no entra en el banco de sprites

Los cinco tienen que quedar afuera para que la cuenta corra, y están fuera
de los 8.514 KB: suman poco y no cambian la conclusión. Afuera quedan también
los cinco respaldos inalcanzables que `release` ya excluye (46, 75, 96, 97
y 98).

Y **tres límites del conversor que el juego entero pasa**, que hubo que
esquivar partiendo las corridas:

* **los encuentros**: `rm2k-snes-battle` indexa las tropas de los encuentros
  con un byte, y el juego entero tiene **365**. Es un índice de 16 bits;
* **los candidatos a líder** se calculan sobre todos los mapas del cartucho,
  así que con todos juntos el 207 pide 9 gráficos de la orden 34 —el tope es
  8— y el 288 suma al actor 34, que no tiene CharSet. Cada uno solo convierte;
* **un pánico de `rm2k-snes-audio`**, en `msu.rs:116`, cuando cierto
  conjunto de mapas arma un paquete con un efecto que no tiene tasa en el
  `.msu`: pasa con el 120 y el 122 juntos, y con cada uno solo no. No lo
  seguí; vale una tarea.

Y una corrida, **con `--no-timer`**: con el cronómetro, Yun Town (67) no
entra en las paletas de sprite. Son 16 bytes por mapa.

## 2. Qué se puede leer del `.msu`

### El puerto

El MSU-1 sirve el `<rom>.msu` como un flujo: se escribe una posición de 32
bits en `$2000-$2003`, se espera que baje el bit 7 de `$2000` y se lee
`$2001`, que avanza solo. **Se lee por DMA con el origen fijo** —ya lo hace
`scn_fill` con los fondos de batalla, ver `docs/port/msu-datos.md`—, y el
destino puede ser **cualquiera del bus B**: la VRAM por `$2118`, la CGRAM
por `$2122` o la WRAM por `$2180`. O sea que unos tiles crudos van **del
`.msu` a la VRAM sin pasar por la WRAM** ni por la CPU.

El `.msu` no tiene un tope que importe —es un archivo en la tarjeta—, así
que lo que va ahí va **crudo**: comprimirlo ahorraría tarjeta y costaría
CPU al cargar, que es justo lo que se quiere sacar.

### Qué parte de un mapa

    lo que se sube al entrar            dónde va       ¿del .msu?
    tiles y colores del fondo           VRAM, CGRAM    sí, directo
    tiles de la capa de encima          VRAM, CGRAM    sí, directo
    tiles de los sprites y sus colores  VRAM, CGRAM    sí, directo
    dibujos de la animación del ChipSet WRAM $7F:6000  sí, por $2180
    la grilla (con la colisión adentro) WRAM $7E:8000  sí, por $2180

    lo que la CPU lee mientras se juega
    tabla de bloques y su pasabilidad   ROM            sí, si se copia a la WRAM
    bytecode, páginas, posiciones       ROM            sí, si se copia a la WRAM
    las poses de los personajes         ROM -> VRAM    no: se suben en caliente,
                                                       por DMA en el vblank
    textos, pelea, pantallas            ROM            no al entrar al mapa

**La colisión no es un rubro aparte**: viaja en el bloque (ver
`docs/port/maps.md`), así que viene con la grilla y la tabla de bloques.

**Las poses no pueden venir del `.msu`.** Se suben cuando un personaje
cambia de pose, en el vblank (`decisiones/las-poses-se-suben-en-caliente.md`),
y tenerlas a mano pediría copiarlas a la WRAM al entrar: con 26 NPCs de doce
poses son cientos de KB. Son 941 KB del juego entero y se quedan en la ROM.

### Cuánta RAM hay

La WRAM está **toda repartida**. Jugando `release` en snes9x —el título, la
apertura con A y teletransportes a los mapas 66, 52, 38, 11, 69 y 1— y
anotando qué bytes valen algo distinto de cero en alguna foto:

    región                 tocados     huecos de 256 B o más
    $7E:0000 BSS y pila    7.569 de 8.192    ninguno
    $7E:2000 RAM lejana   19.335 de 24.576   cinco, 1,8 KB entre todos,
                                             más los 2 KB de ANIMB_BUF
                                             (la pelea, que no se jugó)
    $7E:8000 grilla       32.464 de 32.768   ninguno
    $7F:0000 búfer LZ2    20.357 de 24.576   ninguno
    $7F:6000 animación     6.916 de 8.192    ninguno
    $7F:8000 grilla alta  32.336 de 32.768   ninguno

Que la región de la grilla esté tocada entera **no quiere decir que un mapa
la use entera**: la usan también el título y otras pantallas, y la pelea
pisa la mitad del `$7F` —por eso `back_from_battle` vuelve a descomprimir la
grilla—. **Lo que un mapa necesita mientras se juega** es su grilla, y ésa
mide `MAP_BW × MAP_BH × 2` bytes:

    sobre los 319 mapas    mediana    p90       máximo
    grilla                    600 B   5.000 B   40.000 B (mapa 49)
    eventos (bytecode,      1.613 B   4.156 B   13.007 B (mapa 11)
      páginas y tablas)
    grilla + eventos                            43.250 B (mapa 49)

**Ningún mapa pasa de 64 KB con la grilla, el bytecode y sus tablas
juntos**, así que el bytecode y la tabla de bloques de un mapa entran
**detrás de su grilla**, en la misma región. El precio es el de la grilla:
lo que la pelea o una pantalla pisan se vuelve a leer al volver, y del
`.msu` cuesta un tercio de cuadro.

Y el búfer de LZ2 (`$7F:0000`, 24 KB) **deja de hacer falta para cargar un
mapa del `.msu`**: lo crudo va directo a la VRAM.

**Lo que no está medido**: leer el bytecode de la WRAM es más lento que de
la ROM —8 ciclos maestros por byte contra 6 con FastROM—. Afecta sólo a la
lectura del bytecode, no al intérprete entero, pero la carrera y el mapa 11
ya van justos de CPU (ver `wishlist/chips-sa-1-y-s-dd1.md`).

## 3. Cuánto tarda

### El puerto, medido

`just msu-puerto` arma una ROM de 32 KB (`rom/experimentos/msu-puerto/`)
con un `.msu` de 1 MB de bytes pseudoaleatorios, busca, lee 18 tramos de
32 KB por DMA a la WRAM —dos de ellos tras una búsqueda lejos y 16 seguidos,
de a dos DMA pegados— y compara cada tramo con su suma. En los tres cores del
arnés:

    core      tramos malos   32 KB en          o sea
    snes9x    0 de 18        198,6 líneas      2,60 MB/s, 42,2 KB por cuadro
    bsnes     0 de 18        198,7 líneas      2,60 MB/s, 42,2 KB por cuadro
    mesen-s   0 de 18        198,7 líneas      2,60 MB/s, 42,2 KB por cuadro

Es el techo del bus: 8 ciclos maestros por byte son 192 líneas, más el
refresco de la DRAM. Los tres **buscan en el acto**: la espera del bit 7 da
una vuelta.

**Mednafen** (`snes_faust`, el único con MSU-1) tiene la búsqueda lenta: 1 o
2 cuadros cada una, medido el 2026-09-26 con los fondos de batalla
(`docs/snes/emulators.md`).

**El FX Pak no está medido**, y es lo que importa. Su firmware
(`src/msu1.c` de sd2snes) tiene un búfer de 16 KB en dos mitades; cuando la
consola cruza a una mitad, el procesador del cartucho rellena la otra desde
la tarjeta. **No hay contrapresión**: si la consola lee más rápido que el
relleno, lee bytes viejos y nadie se entera. Por eso la ROM de prueba
compara: en la consola, la pantalla sale **verde** si los 576 KB llegaron
bien, **roja** si no y **azul** sin MSU-1. Los 512 KB seguidos son el peor
caso: 64 KB sin respiro, cuatro veces el búfer.

### Lo que alarga el fundido

Con el modelo de costo de `materials.py` —700 ciclos por comando de LZ2 y
60 por byte, del lado alto— sobre los mapas de `release`, contra leer lo
mismo crudo a la velocidad medida:

    sobre los 93 mapas    crudo      hoy (LZ2 de la ROM)   del .msu, crudo
    mediana               17,3 KB     5,0 cuadros           0,40 cuadros
    p90                   45,0 KB    13,2 cuadros           1,04 cuadros
    mapa 66 Lashe Area    62,8 KB    22,3 cuadros           1,45 cuadros
    mapa 52 la carrera    69,4 KB    17,0 cuadros           1,60 cuadros

Y sobre los 319 del juego entero, lo crudo de un mapa tiene mediana de
13,7 KB, p90 de 30 KB y máximo de 69,7 KB (el 52): **ningún mapa pide más
de dos cuadros de puerto**.

**Se acorta**: cuatro cuadros y medio en el mapa típico y veinte en el 66.
A eso se le suma **una búsqueda por mapa** si lo de cada mapa está seguido
en el `.msu` —cero en los emuladores del arnés, uno o dos cuadros en
Mednafen, y lo que diga la ROM de prueba en el FX Pak—, y otra al volver de
una pelea si el bytecode vive detrás de la grilla.

**Si el FX Pak no sostiene 42 KB por cuadro**, se lee de a menos: de a 8 KB
por cuadro —la mitad de su búfer— el mapa más pesado tarda nueve cuadros,
que sigue siendo la mitad de lo que tarda hoy.

## 4. Qué pasa sin MSU-1

Hoy la regla es que **sin MSU-1 el juego anda igual**: lo del `.msu`
reemplaza algo que la ROM ya tiene (`docs/port/msu-datos.md`). Con el juego
entero eso deja de poder cumplirse: la ROM sin MSU-1 tendría que llevar los
8.514 KB.

**Lo que entra sin MSU-1** es lo de hoy: `release` usa 120 de 124 bancos.
Con lo barato que queda (sección 5: unos 7 bancos a la escala de `release`)
son **unos 10 mapas más**, a 20,8 KB por mapa. O sea que **sin MSU-1 se
llega a un tercio del juego**, más o menos hasta donde llega hoy.

### Las opciones

**A. Una sola ROM**, que lleva en la ROM los mapas del principio y del resto
sólo lo que no se puede leer del `.msu`. Sin MSU-1, el juego se corta en la
primera puerta a un mapa que la ROM no tiene, con un cartel. El problema es
el número: lo que no se puede leer del `.msu` —poses, bytecode, textos,
pelea, pantallas, tablas— **del juego entero** son 3,0 MB, así que lo
jugable sin MSU-1 tiene que entrar en 0,9 MB, **música incluida**, y la
música de `release` sola son 1,5 MB. **Sin MSU-1 se llegaría a mucho menos
que hoy**: menos de la mitad de `release`.

**B. Dos cartuchos del mismo conversor**: `release`, sin MSU-1, como hoy; y
uno nuevo —`completo`— con el juego entero, que pide MSU-1: la música sólo
por las pistas, los efectos sólo los de calidad, y lo de cargar los mapas
del `.msu`. El runtime es el mismo, con los dos caminos de carga, y el
conversor elige por mapa de dónde sale.

**C. Sólo con MSU-1**: un cartucho, el completo. Deja a Mednafen con su
módulo por omisión, que es el que taro usa, y al que juegue sin MSU-1.

### Lo que cuesta mantener B

* **Un cartucho más que armar**: hoy `just cartuchos` arma tres en 46
  segundos con el caché.
* **La tanda sigue sobre `release`** y sin MSU-1, como hoy: todo lo que
  `release` lleva se prueba igual.
* **El camino del `.msu` se prueba con goldens que ya existen**: un mapa
  que está en los dos cartuchos tiene que dibujarse **igual pixel por
  pixel** cargado de la ROM o del `.msu`. Los tres cores del arnés tienen el
  puerto de datos, y el arnés ya arma consolas con MSU-1
  (`test_msu_datos.py`).
* **Lo que no cobra nada**: la búsqueda lenta. Igual que hoy con los fondos,
  sólo Mednafen la tiene y ninguna prueba la corre.

## 5. Las alternativas que no son el MSU-1

### Comprimir más con LZ2, sin chip

Hoy van en LZ2 los tiles del fondo, de la capa de encima, de los sprites, la
animación del ChipSet y la grilla. Lo que va crudo, medido sobre `release`
con el `lz2` de las herramientas, por la unidad en que la ROM lo usaría:

    qué                         unidad      crudo       LZ2           zlib -9
    poses                       512 B     484.352   197.082 (41 %)  (40 %)
    tabla de bloques            mapa       99.824    53.945 (54 %)  (39 %)
    pasabilidad de bloques      mapa        6.240     2.289 (37 %)  (37 %)
    bytecode                    mapa      120.300    75.410 (63 %)  (44 %)
    battlers                    battler   126.043    76.920 (61 %)  (45 %)
    animaciones de batalla      bloque     67.696    37.310 (55 %)  (51 %)
    fondos de batalla livianos  fondo      65.536    47.857 (73 %)  (59 %)
    fuente                      bloque     59.280     9.875 (17 %)  (13 %)
    textos                      32 KB     143.114    82.917 (58 %)  (42 %)
    secuencias de música        tema      649.208   369.828 (57 %)  (40 %)
    muestras BRR                muestra   923.292   917.527 (99 %)  (94 %)

**Qué de eso se puede usar**, que no es lo mismo que qué comprime:

* **Las poses no**: se suben en el vblank cuando cambian, y descomprimir
  cuesta unos 60 ciclos por byte; veinte NPCs caminando serían cuadro y
  medio de CPU. Es justo lo que el S-DD1 resuelve, abajo.
* **Las secuencias no**: las lee `irq_music` de la ROM mientras suenan, y
  la más larga mide 68 KB, más que cualquier hueco de la WRAM.
* **Los textos, no con LZ2**: rompe el acceso directo a cada cuadro. Su
  estudio propone DTE (`todo/los-textos-sin-comprimir.md`).
* **Las muestras BRR no comprimen**: ya son un formato comprimido.
* **Lo demás sí**: los bloques y el bytecode descomprimidos a la WRAM al
  entrar al mapa —detrás de la grilla, ver la sección 2—; los battlers, las
  animaciones y los fondos al empezar la pelea, como ya va la grilla; la
  fuente al arrancar.

Llevado al juego entero, lo usable ahorra unos **470 KB, 15 bancos**: la
tabla de bloques 120 KB, el bytecode 100, los battlers 95, las animaciones
de batalla 70, la fuente 50 y los fondos livianos 30. **Contra un faltante
de 142 bancos, no cambia la respuesta**; a la escala de `release`, son unos
siete bancos, que es lo que la sección 4 le suma a lo que entra sin MSU-1.

### El S-DD1

Un descompresor en el cartucho que entrega los bytes **durante el DMA**, sin
CPU: Star Ocean y Street Fighter Alpha 2. Está estudiado entero en
`wishlist/chips-sa-1-y-s-dd1.md` —soporte, mapa de memoria, un compresor
propio verificado contra el decodificador de snes9x—; acá va lo que faltaba,
**contra LZ2 y con los datos de hoy**:

    qué                        muestra                crudo     LZ2        S-DD1
    tiles del fondo, 8 bpp     12 mapas de release   149.440   58 %        57 %
    tiles de sprites, 4 bpp    12 mapas de release    83.040   25 %        24 %
    poses, 4 bpp, de a 512 B   119 de las 946         60.928   41 %        32 %

**En los tiles que ya van comprimidos, el S-DD1 empata con LZ2.** Lo que da
de verdad es **descomprimir sin CPU**, y lo único que hoy no se puede
comprimir por eso son las poses: 941 KB del juego entero que quedarían en
unos 300, **unos 20 bancos**. Y tiene su propio mapeador, que pasa de 4 MB
sin ExHiROM: Star Ocean usa 6 MB.

### El SPC7110 y el SA-1

* **El SPC7110** (tres juegos de Hudson) descomprime de una "ROM de datos"
  por un puerto (`$4800`), y su mapa de memoria es HiROM: 1 MB de programa
  en `$C0-$CF` y la ROM de datos de a ventanas de 1 MB en `$D0-$FF`,
  conmutables (`$4831-$4833`); los juegos llegan a 5 MB (fullsnes, "SNES
  Cart SPC7110 Memory and I/O Map"). Pide pasar el cartucho entero a HiROM.
  **El FX Pak no lo soporta**: `src/smc.c` de sd2snes lo detecta y contesta
  `MENU_ERR_NOIMPL` (clonado en `cf7e21d`, el v1.11.2). Con eso queda
  descartado.
* **El SA-1** no descomprime: es un segundo 65816 a 10,74 MHz. Lo que suma
  en espacio es su mapeador, **hasta 8 MB** en ventanas de 1 MB, y en el
  mapa de memoria mueve la SRAM a la BW-RAM en `$40` y pone en duda el
  FastROM. Está en el mismo estudio de la wishlist.

**El soporte**, del mismo estudio y del firmware clonado:

    chip      FX Pak Pro                      snes9x  bsnes  mesen-s  MSU-1 junto
    S-DD1     sí, desde el v1.10.0            sí      sí     sí       sí en el FX Pak
    SA-1      sí, desde el v1.9.0, hasta 8 MB sí      sí     sí       sí en el Pro (Mk3)
    SPC7110   **no** (MENU_ERR_NOIMPL)        sí      sí     sí       —

Los tres cores tienen los tres chips en el código que está clonado
(`sdd1.c`, `spc7110.c`, `sa1.cpp` en snes9x; `sfc/coprocessor/` en bsnes;
`Sdd1.cpp`, `Spc7110.cpp`, `Sa1.cpp` en mesen-s). **Lo que no se verificó
desde acá** es que los binarios instalados del arnés los traigan
compilados —no se corrió ninguna ROM con chip— ni nada en el FX Pak: eso se
ve armando la ROM con la cabecera del chip y corriéndola, y en el FX Pak
con su menú, que dice el chip que detectó.

### ExHiROM, o un cartucho más grande

**Hasta 8 MB**, y el FX Pak lo soporta (`src/smc.c`, mapeo `$25`). Pero el
juego entero son 8.514 KB de datos más el código, contra 8.192: **no
entra**, y faltan unos 400 KB antes de contar el acomodo. Y cambia cómo
se calcula cada dirección (ver `decisiones/el-cartucho-se-queda-en-4-mb.md`).

### Todo junto

    camino                         lo que gana          ¿alcanza para el juego?
    LZ2 en lo que se puede         ~470 KB, 15 bancos   no
    DTE en los textos              ~100 KB (estimado)   no
    S-DD1 en las poses             ~640 KB, 20 bancos   no; y cambia de chip
    compartir tiles entre mapas    bloqueado por la     no
                                   VRAM (estudio de
                                   gráficos)
    ExHiROM o SA-1, 8 MB           +4 MB                no: faltan ~400 KB
    los mapas por el .msu          1,9 MB               no solo
    la música sólo por MSU-1       3,4 MB               no solo
    los mapas y la música          5,3 MB: ROM en 3,0   **sí**, con 0,9 MB libres
      por el .msu

**Qué habría que revisar de la decisión de 4 MB** si algún día se va por un
chip: dice que "pasar de ahí es ExHiROM", y con el S-DD1 o el SA-1 no lo es
—cada uno trae su mapeador—. Lo que no cambia es la conclusión: ni 8 MB
alcanzan, y con MSU-1 no hace falta pasar de 4.

## 6. La recomendación

**El juego entero va por el MSU-1, en un cartucho propio, y `release` se
queda como está.** Por fases:

**Fase 0 — medir el FX Pak.** `just msu-puerto` y llevar
`rom/build/msu-puerto/msu-puerto.sfc` con su `.msu` a la consola: verde,
rojo o azul. **Cuesta cinco minutos de taro**, y decide si la fase 1 lee a
toda velocidad o de a 8 KB por cuadro. Si sale rojo, vale repetir con una
pausa entre tramos para saber cuánto sostiene.

**Fase 1 — los mapas del `.msu`, en un cartucho `completo`.** El conversor
escribe lo que se sube al entrar a cada mapa —tiles, colores, grilla,
animación del ChipSet— crudo en el `.msu`, en una región fija por mapa,
como los fondos; la ROM, para un mapa marcado, busca y lee por DMA directo
a la VRAM y a la WRAM, en vez de descomprimir. Todo lo demás se queda en la
ROM. **El mismo runtime en los dos cartuchos**; `release` no cambia de
bytes. La prueba: los mapas que están en los dos se dibujan igual por los
dos caminos.

  *Riesgos*: el FX Pak (fase 0); la búsqueda lenta, que como hoy no la
  cobra ninguna prueba; y lo que pise la pelea, que hay que volver a leer.

**Fase 2 — la música sólo por MSU-1 en `completo`.** Sin secuencias ni
muestras de instrumentos en la ROM para los mapas que `release` no lleva, y
los efectos sólo de calidad. Es lo que más pesa (3,4 MB) y es casi todo
quitar. Con esto **entra el juego entero**: 3,0 MB de ROM.

  *Riesgos*: un tema sin pista de MSU-1 no suena
  (`done/todos-los-temas-tienen-pista-de-msu-1.md`); y el reparto de la ARAM,
  que hoy cuenta con las muestras de la ROM.

**Fase 3 — lo que haga falta después, en este orden.** Los límites del
conversor de la sección 1 —el índice de los encuentros, los candidatos a
líder, el pánico del audio— y los cinco mapas que no entran en la VRAM, que
son trabajo de todos modos. Después, si `completo` aprieta: el bytecode y la
tabla de bloques a la WRAM, detrás de la grilla (−0,7 MB de ROM, y más CPU
para leer el bytecode: medirlo en la carrera). El S-DD1 sólo si con todo eso
no alcanza: cambia de chip para ganar 20 bancos.

**Para `release`, sin MSU-1**: lo barato de la sección 5 —LZ2 en bloques,
battlers, animaciones y fuente; DTE en los textos— y el acomodo de bancos
le dan unos siete bancos, diez mapas. Es lo que ya está haciendo Tacuarita
con Tangle Forest, y es el techo de lo jugable sin MSU-1.

## Cómo se midió

* **El espacio de `release`**: `just espacio`, y `rom/build/release/`
  armado con `NO_CACHE` igual que la tanda.
* **El juego entero**: once copias del archivo de proyecto, cada una con
  `[maps] below` en 400, `excluded` con los rangos que no le tocan y los
  cinco mapas que no entran, y `["--no-timer"]` en `flags`; los mapas 1 a 10
  en todas. Cada una se convirtió con `rm2k-snes-cartridges --project <copia>
  --convert-into <dir> --without-tracks release`, y de cada `mapdata.inc` y
  `musicdata.inc` se sumaron los bytes de cada etiqueta (`.byte`, `.word`,
  `.res`…) con la regla de la sección 1. Las corridas fueron: 1 a 119, el
  120, el 122, 123 a 126, 128 y 129, 130 a 139, 140 a 249 sin 148 y 207, 250
  a 351 sin 250, 285 y 288, el 207 y el 288 solos, y la base con los mapas
  1 a 10 y los de prueba. Ninguna linkea —la de 1 a 119 pide 134 bancos—, y
  no hace falta: el tamaño sale de las etiquetas, antes del acomodo.
* **Por mapa**: de los campos de `map_table` de cada corrida (`MAP_TILES`,
  `SPRITE_TILES`, `MAP_BW`…) y de `crudos/`.
* **La RAM**: el arnés (`tanda.partida`) sobre `release` en snes9x, con la
  WRAM leída cada 15 o 20 cuadros.
* **El puerto**: `just msu-puerto`.
* **LZ2**: el `lz2` instalado, por unidad, sobre las etiquetas de
  `release`. **S-DD1**: el compresor de la wishlist de chips, sobre `crudos/`
  y sobre una de cada ocho poses.
* **El tiempo de carga de hoy**: el modelo de `materials.py`, con los
  comandos de LZ2 contados con `lz2 stats` sobre los mismos flujos que arma
  el conversor.
