# El juego entero sin MSU-1: la cuenta

> **Medido el 2026-10-01 sobre `6a83e2c5`**, por Tucu-tucu. Es una foto,
> como la de Lechuza que continúa
> (`2026-10-01-los-mapas-por-el-msu-1.md`): los números son de ese día y
> este archivo no se actualiza. Lo que dice cuánto le queda **hoy** a cada
> cartucho es `just espacio`. Las cuentas del juego entero salieron de
> scripts descartables; cómo rehacerlas está al final, en "Cómo se midió".

La pregunta es de taro, después de leer el estudio de Lechuza y de decidir
que el juego entero se juega sin MSU-1
(`decisiones/el-juego-se-juega-sin-msu-1.md`): *"si pasamos a 8 MB y
optimizamos un poco los recursos, comprimimos todo lo que podemos
comprimir, y tal vez bajamos la calidad de alguna que otra cosa en ROM sin
MSU-1, ¿podríamos llegar?"*

## Resumen

* **En 4 MB no entra, de ninguna forma.** Con todo lo de este estudio
  —cada compresión, cada recorte de calidad, el S-DD1 en las poses y sin
  las imágenes— quedan unos 4.300 KB contra los 3.968 de datos que tiene el
  cartucho. Lo que sobra no es un recorte más: es el juego.
* **En 8 MB entra, y sin bajar la calidad de nada.** El juego entero con
  lo que faltaba son unos **8.070 KB**: no entra por poco en los ~8.000 de
  datos de un ExHiROM. Con las tres compresiones sin pérdida —LZ2 donde va
  crudo, DTE en los textos y saltos en las secuencias— baja a unos
  **7.150 KB**, y quedan **~850 KB libres, unos 26 bancos de 32 KB**.
* **La cuenta de Lechuza contaba las muestras de más.** Sus 2.120 KB de
  muestras salían de sumar once corridas, y cada corrida arma su propio
  banco con otras tasas: la misma muestra a cuatro tasas contaba cuatro
  veces. Compilando el audio del juego entero de una vez —los 103 temas,
  los 135 efectos y los 322 paquetes— el banco pesa **520 KB** y los
  efectos **532 KB**: 1.052 KB, **1.068 menos**. El juego entero como hoy
  son unos **7.450 KB**, no 8.514.
* **Lo que faltaba** suma unos 630 KB en la ROM: las imágenes de
  `ShowPicture` que hoy no se dibujan (~430 KB, estimado), los cinco mapas
  que no entran en la VRAM (~105) y los efectos de sonido de las
  animaciones de la pelea (92). **Las animaciones de la pelea no suman**:
  van sólo en el `.msu`, y son 84 que no muestra ningún evento, 462 KB.
  Los **panoramas** quedan afuera: el modo 3 no tiene dónde dibujarlos.
* **Los fondos cuantizados por ChipSet** son el recorte de calidad que más
  da: los tiles de fondo del juego entero bajan de 41.968 a 15.097, unos
  **840 KB menos**. Cuesta colores en 94 de los 323 mapas —en el peor,
  de 97 a 51— y a la vista casi no se nota; y la carga de tiles de un mapa
  se duplica. **Con 8 MB no hace falta**: queda para cuando apriete.

## 1. La cuenta de Lechuza, corregida

Lechuza midió el juego entero convirtiéndolo en once corridas y sumando lo
que salía distinto en cada una. Para casi todo es la regla correcta —un
mapa sale igual en dos corridas, y cuenta una vez—, pero **no para las
muestras**: el banco de muestras es uno solo por cartucho y cada muestra
lleva la tasa que le deja su paquete más apretado, así que la misma muestra
sale a otra tasa en cada corrida, con otros bytes, y la suma la cuenta una
vez por tasa. De los registros del conversor de las once corridas salen
**648 versiones de sólo 178 instrumentos y golpes distintos**.

Compilando el audio del juego entero de una sola vez —un trabajo de audio
que es la unión de los once: 103 temas, 135 efectos, 322 paquetes—:

    rubro                                  Lechuza    de una vez
    banco de muestras (instrumentos)                   520 KB   235 muestras
    efectos de sonido                                  532 KB   135 efectos
    muestras, las dos                     2.120 KB   1.052 KB
    secuencias                            1.399 KB   1.399 KB   103 temas

Las secuencias dan lo mismo por los dos caminos, que es la prueba de que
la unión de los trabajos es el juego entero. **El juego entero, convertido
como hoy, son 8.514 − 1.068 = 7.446 KB**, 233 bancos de 32 KB.

Lo demás de su tabla se queda como está. Una diferencia que no cambia nada:
sumando las etiquetas del fondo corrida por corrida —tiles del fondo, de la
animación del ChipSet y de la capa de encima, y sus colores— dan 1.624 KB
y no sus 1.494; la regla de deduplicar por contenido no es la misma que la
de sumar por corrida, y con 130 KB de diferencia no se mueve ninguna
conclusión de abajo.

## 2. Lo que faltaba en la cuenta

### Las animaciones de la pelea

Hoy la ROM lleva sólo las animaciones que muestran los eventos del mapa
(`rom_animations` en `tools/port/battle_animations.py`): 21 en `release`.
La pelea no muestra ninguna. Lo que pide la pelea del juego entero, con la
regla de `Game_BattleAlgorithm` de EasyRPG —el `animation_id` de una
habilidad normal, el del arma, y el `unarmed_animation` del actor sin
arma—, sobre las habilidades que se pueden tener de verdad (las que
aprenden los actores, las que usan los enemigos, las de los ítems
especiales y las de `ChangeSkills`):

    qué                             animaciones  cuadros  como hoy   LZ2
    las que pide la pelea              111        2.285    570 KB   214 KB
      por habilidades                  101
      por armas                         29
      por actores sin arma              18
    las de las cinemáticas              42          787    168 KB    56 KB
    las de la pelea que no muestra      84        1.804    462 KB   180 KB
      ningún evento
    las dos                            126        2.591    630 KB   236 KB

"Como hoy" es como las guarda `release`: cada cuadro sin sus tiles vacíos
(`frame_without_gaps`), más su puntero, su entrada en la tabla y su
paleta. Crudas, a 2 KB por cuadro, serían 5,3 MB. Tres de las 111 no tienen
hoja (`Battle/` vacío) y no pesan nada.

**Las 84 que sólo usa la pelea van sólo en el `.msu`** (la decisión de
taro): **cero bytes de ROM**. Las **42 de las cinemáticas se quedan en la
ROM**, y ya están adentro de la cuenta de Lechuza —cada corrida las
convierte con `rom_animations`—: **a lo sumo 168 KB**, o 56 con LZ2 por
animación entera. La más grande, la 72, son 23 KB descomprimida: entra en
el búfer de LZ2.

### Los efectos de sonido de esas animaciones

Los `timings` de las 111 de la pelea piden 106 efectos. **39 no los lleva
el juego entero**, y convertidos como hoy —6 kHz, hasta 0,75 s— son
**92 KB**. Las 42 de las cinemáticas piden 37 y falta uno (1,4 KB).

Sin MSU-1 no hay animación, pero **el sonido puede ir igual**: es lo que
hacía la ROM con las animaciones del mapa entre el 2026-09-11 y el 12,
cuando sonaban y destellaban sin dibujo. La cuenta los suma; si no van, son
92 KB menos.

### Lo que la ROM no dibuja y tiene datos

* **Las imágenes de `ShowPicture`**: el juego entero muestra **97
  distintas** en 311 lugares, y la ROM dibuja sólo las que caben en una
  fila de objetos de 32 pixeles de alto (`picture.fits`): **49 son más
  altas**. A la escala de la consola, en 15 colores y a 4 bpp, las 97 son
  1.158 KB crudas y **~430 KB con LZ2**. Es un tope: algunas ya están en la
  ROM y en la cuenta de Lechuza, y dibujar las de pantalla entera pide un
  diseño que no existe (`wishlist/sistema-de-imagenes.md`). La cuenta las
  suma enteras.
* **Los panoramas**: 19 distintos en 44 mapas, **~770 KB con LZ2** a 4 bpp.
  **Quedan afuera**: en el modo 3 las dos capas de fondo son del mapa, y
  el conversor los tira (el comentario de `ChangePBG` en el compilador de
  eventos, y `wishlist/panorama-del-mapa-2.md`). No los suma.
* **Películas**: ninguna.
* **Los cinco mapas que no entran en la VRAM** (108, 127, 148, 250 y 285,
  ver Lechuza): a los 20,8 KB por mapa de su estudio, **~105 KB**. Se
  suman, porque son trabajo de todos modos.
* **Las páginas que no compilan** porque un teletransporte lleva a un mapa
  que no está en el cartucho desaparecen solas con el juego entero. Las
  divergencias de `workflow/divergencias/` son de comportamiento, no de
  datos: ninguna suma bytes que se puedan contar.

## 3. Lo que la achica

### LZ2 donde va crudo, y DTE en los textos

**LZ2** ya está medido por Lechuza: la tabla de bloques, el bytecode, los
battlers, las animaciones de las cinemáticas, la fuente y los fondos de
batalla livianos, **unos 470 KB** en el juego entero, sin perder nada. Las
poses y las secuencias no se pueden, y por qué está en su sección 5.

**DTE** —los valores de byte que el texto no usa pasan a significar un par
de letras, de un solo nivel— sobre el bloque `messages` de la corrida más
grande, la de los mapas 1 a 119:

    172.482 B, 88 valores de byte usados, 168 libres
    sólo pares de letras o espacio          115.586 B con la tabla   -33 %
    cualquier par                           111.054 B                -36 %

El primero es el que se puede hacer sin partir un código de control de sus
parámetros. Sobre los ~255 KB de mensajes del juego entero son **unos
85 KB**, sin perder nada y sin perder el acceso directo a cada cuadro. Es
la idea 3 de `todo/los-textos-sin-comprimir.md`, que estaba sin medir; los
mensajes repetidos (su idea 1) darían algo más y no están medidos.

### Las secuencias de música

Las ideas 2 y 3 de `todo/la-musica-pesa-789-kb.md` estaban medidas sobre el
formato del prototipo, y el de hoy ya es por nota. Medidas de nuevo, sobre
86 de los 103 temas (1.184 KB; los otros 17 llevan referencias en el
`.inc` y no se pudieron leer como bytes):

    idea                                       queda    ahorro    RAM
    2. saltar a lo que ya se tocó, sin anidar   74 %    -26 %     5 B
       (un salto de 4 B en lugar de una
       repetición de 8 B o más)
    3. LZSS con ventana de 4 KB                 54 %    -46 %     4 KB
    LZ2 del tema entero, de referencia          56 %     —        el tema

Sobre los 1.399 KB del juego entero: **saltos, −367 KB; LZSS, −638 KB**.
La 3 pide 4 KB de WRAM que suenen mientras dura el tema —también durante
la carga de un mapa, cuando el búfer de LZ2 está ocupado—, y Lechuza
encontró la WRAM toda repartida. Por eso la cuenta usa la 2, y la 3 queda
como un paso más si aparece esa RAM. La idea 4 —no escribir las notas que
nunca suenan— no está medida de nuevo.

### Las muestras, por tasa

Sobre el banco del juego entero compilado de una vez —235 muestras,
520 KB, a la tasa que hoy le deja a cada una su paquete más apretado—,
con un techo:

    techo     banco     ahorro
    hoy       520 KB
    16 kHz    401 KB    -119 KB
    12 kHz    316 KB    -204 KB
    10 kHz    271 KB    -249 KB
     8 kHz    225 KB    -295 KB

Los **efectos** van casi todos a 6 kHz y hasta 0,75 s: 112 de los 135,
271 KB. Los otros 23 son los que el proyecto pide **enteros**, a la tasa
de su WAV (`[sound_effects.whole]`, elegidos de oído): 262 KB. A 6 kHz
serían 86: **−176 KB**. Bajar todos a 4 kHz serían 118 más, y 6 kHz ya es
poco.

**Con MSU-1 nada de esto se pierde**: la música suena de las pistas y los
efectos de calidad salen del `.msu`.

### Los fondos de los mapas, por ChipSet

Hoy el fondo se cuantiza mapa por mapa (`layers.rs` de
`rm2k-snes-map-background`): cada mapa tiene su tabla de colores y sus
tiles, así que dos mapas con el mismo ChipSet no comparten un byte. La
idea de taro: sin MSU-1, una tabla de colores por ChipSet y un solo pool
de tiles para todos sus mapas; con MSU-1, el `.msu` lleva la versión por
mapa con todos los colores.

**Lo horneado no rompe el reuso del fondo**: el horneado pone eventos en la
**capa de encima**, no en la de abajo, así que el fondo de 8 bpp depende
sólo del mapa y de su ChipSet. Y la capa de encima pesa poco —61 KB en el
juego entero—: no vale la pena compartirla.

**Cómo se probó.** Los 323 mapas del juego dibujados con
`rm2k-render layers`, y la cuenta de `layers.rs` por mapa y por grupo: los
colores a 15 bits, contados sobre el dibujo y los de la animación del
ChipSet; si pasan del tope, `adeleine merge` —el mismo que usa el
conversor—; y los tiles de 8x8 únicos, con los espejos reusados como hace
Voodoo. El tope de cada mapa es el que le dio el conversor en las corridas
de Lechuza, y **el de un grupo es el del mapa más apretado**: en modo 3 el
fondo direcciona la CGRAM en directo, pero sólo la mitad de abajo —la de
arriba es de los sprites—, sin las 9 entradas de la ventana y sin las
paletas que se lleve la capa de encima: **103 como mucho**
(`docs/port/cgram.md`), y 55, 71 u 87 según el mapa. Por mapa, la cuenta
da los tiles del conversor con diferencias de uno o dos.

    43 ChipSets, 12 de un solo mapa
                              por mapa (hoy)   por ChipSet
    tiles del fondo              41.968          15.097
    crudos, a 64 B               2.624 KB          944 KB
    con LZ2                      1.656 KB          666 KB   en tramos de
                                                            64 tiles
    lista de tiles por mapa          —              82 KB   2 B por tile
    total                        1.656 KB          748 KB   -55 %

Llevado a lo que el conversor gasta hoy en esos tiles en el juego entero
—1.535 KB con LZ2, contando las etiquetas de las corridas—, son **unos
840 KB menos, 26 bancos**. Los grupos que más dan son los grandes: el
ChipSet 23, 33 mapas, de 6.331 tiles a 1.238.

**Cómo los usaría la ROM.** El pool de un ChipSet no entra en la VRAM —tres
pasan de 1.024 tiles, y el estudio de gráficos ya había visto que el pool
del 1 y el 2 juntos no entraba en ningún reparto—, así que **cada mapa
sube sólo sus tiles**: lleva la lista de cuáles son, y la VRAM queda igual
que hoy, porque fusionar colores sólo puede juntar tiles. El pool va en
tramos de LZ2 ordenados por qué mapas usan cada tile, y un mapa
descomprime los tramos que toca y sube de ahí los suyos. El tamaño del
tramo es el precio:

    tramo        LZ2 del pool   lo que descomprime un mapa, contra hoy
                                mediana   p90
    64 tiles       666 KB        x2,3     x5,5
    128            648 KB        x2,7     x10,7
    256            631 KB        x3,3     x18,7

Con 64, **la carga de los tiles de un mapa se duplica** en el mapa típico;
y los tiles son una parte de lo que tarda en cargar. La otra salida es
llevar el pool **crudo** y subir cada tile por DMA directo de la ROM, sin
descomprimir nada: 944 + 82 KB, **unos 580 KB menos** que hoy, y la carga
más rápida que hoy.

**Lo que cuesta en colores**, contra hoy:

* **94 de los 323 mapas pierden colores**; 43 pierden más de diez, y en
  promedio son 3,9 por mapa. Los que más pierden son los que comparten
  ChipSet con un mapa apretado: el 25 tiene tope 55 por uno solo de sus 14
  mapas.
* Los diez que más pierden, y cuántos pixeles cambian contra el original:

      mapa                     ChipSet  colores hoy -> por ChipSet  pixeles
      139 Room7                   25        97 ->  51               3,3 %
      137 Room5                   25        90 ->  45               2,9 %
      117 House3                  24       103 ->  65               3,9 %
      144 Shop In Garagaraboren   24       103 ->  66               3,2 %
       66 Lashe Area              31        99 ->  67               0,1 %
      112 ParadiseInteriors       24       103 ->  72               4,5 %
      113 Emily's House           24       103 ->  72               2,3 %
      114 Talan's House           24        93 ->  63               2,0 %
      119 Weapons and Armor       24       103 ->  74               3,9 %
      168 The Line Narrows        24       103 ->  74               2,8 %

  El que más pixeles cambia es el 215, un 9,7 %, con 103 colores hoy y 81
  por ChipSet. Las capturas lado a lado de los diez —hoy a la izquierda,
  por ChipSet a la derecha, sólo la capa de abajo— se le entregaron a
  taro. Mirando tres (112, 117 y 139), la diferencia cuesta encontrarla:
  `merge` fusiona los colores que menos se ven.
* **Una variante que pierde menos**: agrupar por ChipSet **y** por tope, así
  un mapa apretado no le baja los colores al resto. Pierden colores 50
  mapas y no 94, 1,6 en promedio, y el ahorro baja a **unos 710 KB**.

**Lo que no se midió**: los fondos con lo que el proyecto cambia encima
del volcado —los mapas forkeados de `parches/manual/`, seis—, y el costo en
ciclos de subir una lista de tiles sueltos en vez de un bloque.

## 4. La cuenta final

En KB. "Pierde" dice qué se pierde sin MSU-1; con MSU-1, nada de lo de
calidad se pierde, porque el `.msu` lleva la versión buena.

    el juego entero                                    KB      pierde
    como hoy, según Lechuza                          8.514
    las muestras, contadas de una vez               -1.068
    como hoy                                         7.446
    + los efectos de las animaciones de la pelea       +92
    + las imágenes de ShowPicture (tope)              +430
    + los cinco mapas que no entran en la VRAM        +105
    + las animaciones de la pelea                       +0     van sólo en el .msu
    con lo que faltaba                               8.073
    - LZ2 donde va crudo                              -470     nada
    - DTE en los mensajes                              -85     nada
    - saltos en las secuencias                        -367     nada
    sin pérdida                                      7.151
    - los fondos por ChipSet                          -840     colores en 94 mapas
    - los efectos enteros, a 6 kHz                    -176     los 23 elegidos de oído
    - el banco de muestras con techo de 12 kHz        -204     brillo de los instrumentos
    - sin los efectos de las animaciones               -92     la pelea muda
    con todo lo de calidad                           5.839

Contra los dos cartuchos:

    cartucho                        datos      con lo que   sin        con todo
                                               faltaba      pérdida
    4 MB, LoROM, 124 bancos         3.968 KB   no           no         no: sobran 1.870
    8 MB, ExHiROM                  ~8.000 KB   no, por ~70  sí, ~850   sí, ~2.160

**En 4 MB no entra ni con todo.** Sumando además lo que este estudio no
recomienda —LZSS en vez de saltos (−271), el banco a 8 kHz (−91 más),
todos los efectos a 4 kHz (−118 más), el S-DD1 en las poses (−640, ver
Lechuza) y sin ninguna imagen (−430)— quedan unos **4.290 KB**: siguen
sobrando 320. Y eso ya es otro juego.

**En 8 MB entra sin perder nada**, con unos 850 KB —26 bancos de 32 KB— de
margen, que es el que cubre lo que esta cuenta estima en vez de medir: las
imágenes, los cinco mapas, el reparto en bancos de 64 KB. Los recortes de
calidad son **otros 1.300 KB de reserva**, y se usan sólo si hacen falta.

## 5. Qué cambia para pasar a 8 MB

**ExHiROM**, que el FX Pak soporta (Lechuza, sección 5): las mismas
direcciones que HiROM para los primeros 4 MB, en `$C0-$FF`, y los otros 4
en `$40-$7D`, todo de a bancos de 64 KB. En grande, lo que toca:

* **El mapa de memoria y la cabecera.** `memoria.cfg` deja de ser 124 áreas
  de 32 KB en `$8000-$FFFF` y pasa a ser ~126 de 64 KB desde `$0000`; los
  bancos `$7E` y `$7F` siguen siendo la WRAM, así que esos 128 KB de ROM se
  ven sólo por la mitad alta de `$3E` y `$3F`. La cabecera va en
  `$40FFB0` del archivo, con el mapeo `$25` (`$35` con FastROM). **El empaquetado de bancos
  (`banks.rs`) ya está escrito para eso**: lo que asume es el tamaño y
  dónde empieza el banco, y en 64 KB el DMA entra mejor.
* **El banco 0 y el banco 1.** Los vectores de interrupción y el código que
  corre con el banco de datos en `$80` ven `$80:8000-$FFFF`, la mitad alta
  de un banco de 64 KB. **Las tablas del banco 0 no ganan lugar solas**:
  siguen siendo 32 KB vistas con direccionamiento absoluto, como hoy, y lo
  que no entre ahí va con puntero largo, como ya va todo lo generado.
* **Lo que cruza bancos a mano** —lo que lleva `.crossbank`, como las
  muestras que el driver sube byte a byte (`emit.rs`)— asume que un banco termina en `$FFFF` y el siguiente
  empieza en `$8000`. En ExHiROM empieza en `$0000`: hay que buscar cada
  rutina que incremente el banco a mano.
* **La SRAM** se muda de `$70:0000` (LoROM) a `$6000-$7FFF` de los bancos
  `$20-$3F` y `$A0-$BF`, de a 8 KB: las cuatro ranuras de 2 KB entran en una ventana, pero la rutina
  que guarda y la que lee las ranuras cambian de dirección.
* **No cambia**: la WRAM ni la RAM lejana —son de la consola, no del
  cartucho—, el puerto del MSU-1 en `$2000-$2007` y el `.msu`.
* **Lo que no está verificado**: que Mednafen (`snes_faust`) arme ExHiROM;
  los tres cores del arnés lo tienen (Tales of Phantasia es ExHiROM).
  FastROM sigue: `$C0-$FF` y `$80-$BF` son la mitad rápida.

`decisiones/el-cartucho-se-queda-en-4-mb.md` dice que pasar de 4 MB "es
cambiar cómo se calcula cada dirección, con todo lo que eso rompe en
hardware y no en el emulador", y que se revisa al llegar al 85-90 %:
**`release` ya está en 120 de 124 bancos, y con Tangle Forest en 124.**
Este estudio recomienda revisarla: el juego entero sin MSU-1 no entra en
4 MB con ningún recorte, y en 8 entra sin perder calidad.

## 6. La recomendación, por fases

De lo que más da por menos costo a lo que menos da. Ninguna está
implementada: de acá salen las tareas.

**Fase 1 — LZ2 donde va crudo y DTE en los textos: −555 KB, sin perder
nada.** Es lo único que le da lugar a `release` dentro de los 4 MB mientras
tanto —unos siete bancos a su escala, según Lechuza—, y vale igual en 8.
Cuesta descomprimir al entrar al mapa o a la pelea, y la WRAM detrás de la
grilla (Lechuza, sección 2).

**Fase 2 — ExHiROM, 8 MB: +4 MB.** Es lo que más da, y sin esto no hay
juego entero. Cuesta el mapa de memoria, la SRAM y lo que cruza bancos a
mano; **lo que lo cobra es el hardware**: una ROM de prueba en el FX Pak
antes de mudar el juego, como la del puerto del MSU-1.

**Fase 3 — saltos en las secuencias: −367 KB, sin perder nada.** Las
escrituras al DSP son las mismas, y lo que lo prueba es decodificar en
Python y comparar contra las de hoy, tema por tema. La LZSS (−271 más)
sólo si aparecen 4 KB de WRAM que puedan sonar durante una carga.

**Fase 4 — lo que faltaba**, que son features y no espacio: los cinco
mapas que no entran en la VRAM, el sistema de imágenes y, si taro quiere
la pelea con sonido sin MSU-1, los efectos de las animaciones. Y las
animaciones de la pelea desde el `.msu`, que con MSU-1 cuestan cero bytes
de ROM (`wishlist/animaciones-en-la-pelea.md`).

**Fase 5 — sólo si 8 MB aprieta: la calidad, en este orden.**
1. Los efectos enteros a 6 kHz (−176): un número en el proyecto, y con
   MSU-1 siguen enteros.
2. Los fondos por ChipSet (−710 a −840): el que más da, pero pide que el
   conversor convierta por grupo y no por mapa —el caché, las pruebas por
   mapa, todo lo que hoy es un mapa por llamada— y una carga de tiles
   sueltos en la ROM. Primero la variante por ChipSet y tope, que pierde
   la mitad de colores.
3. El techo de tasa del banco (−119 a −295): lo elige taro de oído.

## Cómo se midió

* **Las muestras de una vez**: un trabajo de audio armado con la unión de
  los `audio-job.json` de las once corridas de Lechuza —los temas por
  nombre, los paquetes por mapa, la herencia—, sin `emit`, y
  `rm2k-snes-audio compile` sobre él. Su `audio.json` trae cada muestra
  del banco y cada efecto con su tasa y sus bytes; los techos se
  calcularon como bytes por techo sobre tasa, en bloques de 9.
* **Las animaciones**: qué pide la pelea, del volcado (`skills`, `items`,
  `actors`, `enemies`, y los `ChangeSkills` y `ShowBattleAnimation` de los
  328 mapas, los comunes y las tropas); cuánto pesan, con
  `animation.by_numbers` y `battle_animations.frame_without_gaps` del
  conversor, y el `lz2` instalado. Sus efectos, de los `timings`, contra
  los efectos de los trabajos de audio de Lechuza, y la duración de cada
  WAV.
* **Las imágenes y los panoramas**: del volcado, sus archivos reducidos a
  15 colores con PIL a la escala de la consola, en tiles de 4 bpp, y el
  `lz2` instalado. Es una estimación del orden, no una conversión.
* **Los fondos**: `rm2k-render layers` sobre los 323 mapas, y en Python
  lo mismo que `layers.rs` —15 bits, `adeleine merge` con el tope de cada
  mapa del registro del conversor, tiles únicos con espejos, el formato
  planar de 8 bpp— por mapa y por grupo, con el `lz2` instalado. Las
  capturas, la capa de abajo pintada con las dos tablas.
* **DTE**: codicioso, el par más frecuente primero, sobre el bloque
  `messages` de la corrida de los mapas 1 a 119.
* **Las secuencias**: los `song_stream_N` de las corridas, por nombre de
  tema; los saltos y la LZSS, con un codificador codicioso de prueba que
  cuenta bytes y no decodifica.
* **Lo que se tomó de Lechuza sin medir de nuevo**: el resto de su tabla
  del juego entero, el ahorro de LZ2 y los 20,8 KB por mapa.
