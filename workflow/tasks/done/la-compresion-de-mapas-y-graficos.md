---
name: "La compresión de mapas y gráficos"
description: "Cuánto pesa cada cosa del cartucho, cuánto comprime y cuánto cuesta descomprimirla; hechos el piloto, los tiles y las grillas en LZ2 y las poses deduplicadas"
type: refactor
---

# Qué

Comprimir lo que viaja en el cartucho para que entre el resto del juego —unos
7 MB sin comprimir según `decisiones/el-cartucho-se-queda-en-4-mb.md`— sin
pasar de 4 MB. **La música queda afuera a propósito**: hay otro trabajo en las
muestras, y taro prefiere comprimir el audio cuando termine todo lo de audio.

Esta tarea **absorbe `medir-la-compresion-de-mapas.md`**, la idea de taro del
2026-09-25 —trozos de bloques y capas separadas para las grillas—. Sus cuatro
variantes están medidas abajo, pero la pregunta que dejaba abierta —si las
grillas eran el 5% o el 30% del problema— sólo se contesta mirando el
cartucho entero, y el cartucho entero cambió la respuesta: lo que más pesaba
eran las animaciones de batalla, que eran casi todas ceros. Por eso una sola
tarea y no dos.

Medido el 2026-09-26 sobre `03c21fb`, con `release` recién armado. Los números
son de ese día y del reparto de mapas de ese día: el que retome esto los
vuelve a medir, no los copia. El método está al final.

# Status

**Hechos el piloto y los puntos 2, 3 y 4 de la recomendación.** Quedan el 5
(las poses espejadas) y el 6 (battlers y fondos), que nadie empezó.

* El piloto: las animaciones de batalla sin tiles vacíos (`bb3a4fc`).
* **2 y 3, el 2026-09-26**: los tiles del fondo, de la capa de encima, de los
  sprites, los dibujos de la animación del ChipSet y las grillas viajan en
  LC_LZ2 y la ROM los descomprime a la WRAM al cargar el mapa. Ver "Lo que se
  hizo", abajo.
* **4, el mismo día**: las poses iguales se guardan una sola vez.

**taro tiene que jugar**: cambiar de mapa mucho —con puertas, teletransportes
y el save point— y pelear, mirando que los mapas se dibujen enteros, que el
agua y los tiles animados se muevan, que los personajes caminen con sus
poses y que al volver de una pelea el mapa y las paredes sigan donde estaban.
Lo que se ve distinto es **el negro entre mapas**, más largo: ver los cuadros
abajo. Y taro tenía que ver una animación de batalla en el juego por el
piloto; sigue en pie.

# Lo que se hizo, el 2026-09-26

Medido sobre `main` con el paso 6 del audio mergeado (`2d6b665`), en
`release`.

    antes de todo esto (con el piloto)   2916,5 KB usados, 71,2%, último banco $63
    tiles en LZ2                         2480,4 KB, 60,6%
    grillas en LZ2 (y un caso nuevo)     2234,4 KB, 54,6%
    poses deduplicadas                   2141,2 KB, 52,3%, último banco $46

    por clase             crudo      LZ2
    map_tiles            458,9    262,5
    sprite_tiles         287,8     62,4
    above_tiles           19,3     13,0
    anim_tiles            14,6      6,6
    map_celdas           278,2     32,1
    total               1058,7    376,9   (681,8 KB menos)
    poses: 545 distintas de 732          (93,5 KB menos)

El compresor es un proyecto aparte, `tools/lz2/`, con un parser óptimo: sale
un poco más chico que el greedy de la medición (262,5 contra 266,4 en los
tiles del fondo). No emite el relleno creciente, que la ROM no lee.

**Cuadros de carga**, la vuelta del lazo que carga cada uno de los cuarenta
mapas, en el mismo orden antes y después y en la segunda pasada —así el
paquete de audio de cada mapa es el mismo y lo que cambia es sólo la
descompresión—. Incluye la subida del paquete de audio, que es lo que más
pesa:

    sin comprimir              33,9 de media, 76 el peor (mapa 26, audio)
    con todo, al final         40,3 de media, 80 el peor
    lo que suma comprimir       6,4 de media, 14 el que más (mapa 52)

Contra las estimaciones que taro dio por buenas —5 de media y 12 el peor,
sólo los tiles— queda un poco arriba porque suma la grilla, que se estimaba
aparte (1,2 de media, 5,8 el peor). El modelo de la medición (400 ciclos por
comando, 46 por byte) subestimaba un 40%; el que usa la cuenta del arranque es
700 y 60, que lo medido no pasa por más de medio cuadro.

**Lo que bajaría más**: un DMA a `$2180` para los literales y los rellenos, a
8 ciclos por byte contra unos 46 del `mvn`. Se descartó por lo mismo que en
el piloto —el cruce de un DMA general con el HDMA en la primera revisión de
la CPU—, aunque acá la pantalla está apagada y se podría apagar el HDMA
mientras dura la carga. No se probó en la consola.

**Dónde**: el descompresor es `lz2_descomprimir`, en el banco 1 (461 bytes con
sus entradas); el banco 0 quedó en 1029 libres en `release` y 1727 en
`test-special`. La WRAM: `$7F0000` es el buffer de carga, `$7F6000` los
dibujos de la animación, y la grilla en `$7E8000`, que es **la decisión con
costo**: `workflow/decisiones/la-grilla-vive-en-la-wram.md`.

**La grilla y la pelea**: la escena de la pelea es la mitad alta del `$7F`, así
que pisa el final de las grillas de más de 32 KB (hoy, sólo la del mapa 52).
`volver_de_batalla` vuelve a descomprimir la grilla entera.

**Cómo se verificó**: `test_lz2.py` hace la ida y vuelta de cada bloque de
cada cartucho por el compresor y por una referencia escrita aparte;
`test_carga_descomprimida.py` compara, en los cuarenta mapas, la VRAM recién
cargada, la grilla y los dibujos de la animación en la WRAM contra lo que el
conversor deja sin comprimir en `crudos/`, en snes9x y en bsnes, y la grilla
después de pelear en el mapa 52 (caso `pelea-en-52`). Se la vio fallar
rompiendo el relleno y sacando la segunda descompresión de la grilla; las
poses, apuntando cada una a su vecina (46 casos de la tanda en rojo).

# La radiografía

Sumando por prefijo de símbolo los bloques de `mapdata.inc`, que es el
contenido exacto de cada uno (la cuenta por símbolos del `.dbg` sirve para
casi todo, pero **se equivoca con `map_celdas`**: la grilla cruza de banco, y
restar la dirección del símbolo siguiente la corta en el borde. Por eso la
radiografía de `juntar-release-y-test-main.md` daba 285 KB y la del `.dbg`
208: son 278).

    release, 03c21fb           usado 3162 KB de 4096 (77,2%), último banco $6B

    anim_batalla   548,0 KB   274 cuadros de 2 KB
    map_tiles      458,9 KB   un bloque por mapa, 8bpp
    sprite_poses   366,0 KB   732 poses de 512 B
    sprite_tiles   287,8 KB   un bloque por mapa, 4bpp
    map_celdas     278,2 KB   las grillas
    muestra        262,2 KB   (audio: afuera)
    tema_stream    206,4 KB   (audio: afuera)
    battler         74,8 KB
    map_bloques     51,8 KB   los diccionarios de bloques
    fondo           48,0 KB   los de pelea que no van por el MSU-1
    paginas         39,8 KB   y evcodigo 39,2, mensajes 32,0, titulo_tiles 31,0
    above_tiles     19,3 KB   y anim_tiles 14,7, fuente_pre* 4 × 14,5

Las grillas **con sus diccionarios** —`map_celdas`, `map_bloques` y
`bloque_pass`— son 329 KB, el 10% del cartucho: ni el 5% ni el 30%.

# Cuánto comprime cada cosa

Por bloque, que es la unidad que se descomprime: un mapa, un cuadro, una pose.
**LZ2** es el LC_LZ2 de Nintendo (el de los Mario y Zelda de la consola:
copia, relleno de byte, de palabra, creciente, y repetición con dirección
absoluta de 16 bits en la salida), con un compresor greedy con un paso de
lazy, verificado con su descompresor. **LZSS 4K** es un LZSS de ventana de 4 KB
y largo de 3 a 18, como los de muchos juegos comerciales. **zlib -9** es la
cota de referencia; "junto" es zlib sobre todos los bloques de la clase
pegados, que dice cuánto se repite **entre** mapas.

    clase          crudo     RLE     LZ2   LZSS 4K   zlib -9   junto   lo del dominio
    anim_batalla   548,0    27,2    20,4    78,5     20,0     13,8    sin tiles vacíos: 36,0
    map_tiles      458,9   357,0   266,4   264,1    223,7    212,9    tiles únicos entre mapas: 445,4
    sprite_poses   366,0   138,6    83,9*  103,5     67,4     64,0    poses repetidas: -93,5
    sprite_tiles   287,8    91,6    63,5    82,6     53,0     33,4    tiles únicos entre mapas: 44,4
    map_celdas     278,2   176,7    32,8    47,9     22,7     22,2    ver las cuatro variantes
    battler         74,8    51,2    45,7    39,6     32,8     32,3
    map_bloques     51,8    35,7    28,3    25,7     19,9     15,8
    fondo           48,0    44,1    37,2    36,5     31,1     30,9
    evcodigo        39,0    37,6    21,4    20,4     15,9     14,2
    mensajes        32,0    32,1    18,8    16,7     13,3     13,3
    titulo_tiles    31,0    24,0    15,7    15,8     13,7     13,7
    above_tiles     19,3    16,0    13,1    12,9     11,2     10,6
    anim_tiles      14,6    11,7     6,7     6,7      5,6      5,5

\* Por banco de doce poses. **Pose por pose**, que es como se suben, LZ2 da
139,1 KB.

Lo que dicen las columnas del dominio:

* **`anim_batalla` era 94% relleno**: 1109 tiles con algo de 17.536, cuatro
  por cuadro de media. Ya está hecho: es el piloto.
* **Los tiles de mapa no se repiten entre mapas** —7126 únicos de 7342, y con
  espejos igual—, porque cada mapa cuantiza su paleta: el mismo dibujo sale con
  otros índices. Es lo que ya decía la decisión de 4 MB. Lo mismo explica que
  las copias que encontró el plan de Lashe City (39≡7, 43≡34, 45≡19) no se
  compartan solas; **no están medidas acá** porque esos mapas no están en el
  cartucho de hoy, y ninguna compresión por mapa las abarata: hace falta que
  el asignador las cuantice igual y que `Materiales` las deduplique.
* **Los tiles de sprite sí se repiten**: 1420 únicos de 9209 —los mismos
  personajes en muchos mapas, con la misma paleta—.
* **Las poses tienen 93,5 KB de poses idénticas**: la mitad dentro del mismo
  personaje (47,0: cuadros de caminata iguales) y la otra mitad entre
  personajes (46,5). Y otros **45,5 KB son el espejo horizontal** de una pose
  ya vista: la izquierda de muchos CharSet es la derecha dada vuelta.

El agente del S-DD1 midió lo mismo con el algoritmo del chip
(`wishlist/chips-sa-1-y-s-dd1.md`) y los números cruzan: `map_celdas` 278,2
KB, zlib 22,9 contra 22,7.

## Las cuatro variantes de las grillas

Sobre los 39 mapas distintos del cartucho, grilla más diccionario más
pasabilidad; "trozos N" son trozos de N×N bloques deduplicados, con índices de
un byte donde entran:

    1. como hoy                               329,1 KB   263 bloques el mapa que más
    2. trozos de 2 / 4 / 8 / 16               126,8 / 115,5 / 137,1 / 175,0 KB
    3. capas separadas, trozos de 1/2/4/8     302,2 / 131,7 /  99,9 / 124,9 KB
    4. capas y pasabilidad aparte, 1/2/4/8    437,2 / 162,5 / 130,7 / 180,6 KB
    LZ2 de la grilla entera                    87,8 KB (sin acceso directo)

Los trozos de 4×4 son el punto dulce de las dos primeras: **-214 KB**, y con
capas separadas **-229**. La pasabilidad aparte (4) pierde siempre: un byte
por celda pesa más que lo que ahorra separarla. El tope de 512 bloques no se
acerca en ninguna: el mapa con más trozos de 4×4 tiene 285.

Pero hay algo mejor que los trozos, y está en la recomendación: descomprimir
la grilla entera a la WRAM al cargar el mapa.

# Cuándo se descomprime cada cosa, y cuánto cuesta

El modelo de ciclos para LZ2, que es el que se usaría en todas las de carga:
~400 ciclos maestros de cabecera por comando y ~46 por byte de salida (un
`mvn` de 7 ciclos de CPU, con las lecturas de código en FastROM y la escritura
en la WRAM a 8). Un cuadro de NTSC son 357.954 maestros. Es un modelo, no una
medición: el piloto se midió en la consola emulada, esto no.

* **Los tiles del mapa, de los sprites, de la capa de encima y de la animación
  del ChipSet** se suben una vez, en `load_map`/`load_above`/`load_sprite`,
  con la pantalla apagada dentro del fundido: no se ven. Descomprimir LZ2 a un
  buffer en la WRAM y subir de ahí con el mismo DMA:

      map_tiles     2,97 cuadros de media, 7,21 el peor (27.584 B)
      sprite_tiles  1,28 de media, 2,53 el peor (15.200 B)
      above_tiles   0,20 de media, 1,03 el peor
      anim_tiles    0,56 de media, 1,13 el peor

  O sea **unos 5 cuadros más de negro por cambio de mapa de media, 12 el
  peor**. El buffer: el bloque más grande son 27,5 KB, y **`$7F0000` a
  `$7F7FFF` no lo usa nadie fuera de la pelea** —es `ESC_LIMPIO`, que la
  escena rearma al entrar—. `volver_al_mapa` y la vuelta de la pelea pasan
  por `load_map`, así que descomprimirían también, y la vuelta de la pelea
  sumaría esos cuadros a los que ya tarda.
* **Las grillas** hoy se leen del cartucho con un puntero de 24 bits, cada vez
  que se arma una tira o se pregunta una pasabilidad: acceso directo, y por eso
  la tarea original pedía trozos. **Pero se pueden descomprimir enteras a la
  WRAM al cargar el mapa y dejar el acceso directo como está**: sólo
  `ptr_mas` y `ptr_menos` saben que la grilla está en LoROM —que al pasar de
  `$FFFF` se sigue en el `$8000` del banco de al lado—, y **la WRAM tiene esa
  misma forma si se usa la mitad alta de los dos bancos**: `$7E8000-$7EFFFF`
  seguido de `$7F8000-$7FFFFF`. La grilla más grande son 40.000 B (mapa 52),
  que comprime a 1,9 KB. Descomprimir: 1,24 cuadros de media, 5,81 el peor.
  Lo que cambia en la ROM es la carga y **las dos lecturas de
  `M_PTR_MAP_CELDAS`** (`heroe.s` y `ventana_del_mapa.s`), que pasarían a
  apuntar a la WRAM. Lo que cuesta: reservar `$7E8000-$7EFFFF` para siempre
  —hoy está libre— y, en los mapas de más de 32 KB de grilla, volver a
  descomprimirla al salir de una pelea, que pisa `$7F8000`.
* **Las poses** se suben por DMA en el vblank, hasta cinco por cuadro, cuando
  un personaje cambia de pose. Comprimirlas pediría descomprimirlas en tiempo
  real —LZ2 por pose da 139 KB, pero cinco poses son 2,5 KB de salida por
  cuadro, cerca de un tercio de un cuadro de CPU con este modelo— o precargar
  las de un mapa en la WRAM: el mapa con más personajes animados tiene 15, o
  sea 90 KB, que es casi toda la WRAM que queda libre fuera de la pelea y no
  deja lugar para la grilla ni para el buffer de carga. **No entra ninguna de
  las dos** mientras no se haga lo de abajo, que achica ese número. Lo que
  sí entra es deduplicarlas, que no cuesta nada en la consola: las tablas de
  poses ya llevan un puntero por pose (`npc_poses`, `actor_table`), así que
  dos iguales pueden apuntar al mismo lugar. Los espejos piden además el bit
  de espejo en el atributo de OAM del personaje: más riesgo.
* **Las animaciones de batalla** no se cargan al entrar a la pelea, aunque
  el nombre lo sugiera: se dibujan sobre el mapa y **se suben 2 KB por vblank
  cada dos cuadros**, cuadro a cuadro. Por eso el piloto
  las rearma en la RAM lejana fuera del vblank. Ver "El piloto".
* **Los battlers y los fondos** se cargan al entrar a la pelea, en el
  fundido: 1,0 y 2,1 cuadros de media. La escena ya usa el banco `$7F` entero;
  el battler más grande descomprimido (11,5 KB) cabría en la RAM lejana. Poco
  ahorro: -29 y -11 KB.

# La recomendación

Por KB ahorrados, con el costo y el riesgo al lado. Los números de ahorro son
contra el cartucho de hoy, después del piloto.

    qué                                  ahorra    costo en la consola                   riesgo
    1. anim_batalla sin tiles vacíos      -512 KB   8 scanlines por cuadro nuevo, 50     HECHO
                                                    el peor; 2 KB de RAM lejana
    2. tiles de mapa, sprites, encima y   -431 KB   ~5 cuadros más de negro por cambio   bajo
       animación del ChipSet, LZ2                   de mapa, 12 el peor; buffer en
                                                    $7F0000; el descompresor
    3. grillas, LZ2 a la WRAM al cargar   -245 KB   1,2 cuadros de media, 5,8 el peor;   bajo
                                                    reservar $7E8000-$7EFFFF
    4. poses idénticas, deduplicadas       -94 KB   ninguno: sólo el conversor           muy bajo
    5. poses espejadas                     -46 KB   el bit de espejo en la OAM           medio
    6. battlers y fondos, LZ2              -40 KB   ~3 cuadros al entrar a la pelea      bajo
    (grillas en trozos de 4×4             -214 KB   una indirección más por celda en     alto
     con capas: si no hubiera WRAM)                 cada lector de la grilla

**Qué primero: el 2 y el 3 juntos**, porque son un solo trabajo —un
descompresor LZ2 en la ROM y el compresor en el conversor— y entre los dos
son **676 KB**. LZ2 y no otro por tres razones: en los tiles queda a un 20% de
zlib, y en las grillas a 10 KB; su repetición con dirección
absoluta en la salida es exactamente lo que un `mvn` dentro de un banco de la
WRAM hace de un saque, así que el descompresor es corto y rápido; y es un
formato que la consola ya conoce —hay descompresores de referencia y
herramientas para mirarlo (Lunar Compress)—. El LZSS de ventana de 4 KB
comprime igual en los tiles de mapa, algo mejor en battlers y fondos, y
bastante peor en sprites y grillas, que es donde está el volumen.

**El 4 es gratis y se puede hacer en cualquier momento**: sólo el conversor, y
lo verifica la tanda tal cual —la ROM sube los mismos bytes desde otro
lugar—.

Con el 1 al 4, `release` bajaría de unos 2650 a unos 1880 KB usados: del 65%
al 46%. Es una estimación, suma de las columnas de arriba.

# El piloto

**Qué**: cada cuadro de animación de batalla se guarda como la lista de sus
tiles con algo —un byte con su número en la caja y sus 32 bytes— y un `$FF`
(`cuadro_sin_vacios` en `snes_convert.py`). Cuando el tick elige un cuadro
nuevo, `anim_cuadro_armar` (banco 1, `animacion_de_batalla_cuadros.s`) borra
de `ANIMB_BUF` los tiles del cuadro anterior y copia los del nuevo; el vblank
sube los 2 KB de `ANIMB_BUF` con el mismo DMA de siempre. Se eligió éste y no
los tiles de mapa porque ahorra más del doble y no tiene descompresor: el
"descompresor" es una copia.

**Cuánto ahorra**, en `release`: `anim_batalla` de 548,0 a 36,0 KB; el
cartucho de 3162 a 2650 KB usados, y el último banco de `$6B` a `$5B`.

**Cuánto cuesta**:

* **Banco 0**: devuelve 12 bytes —el vblank ya no calcula el puntero—: 1180
  libres en `release`, 1878 en `test-special`. **Banco 1**: 318 bytes.
* **RAM lejana**: `$7E7000-$7E77FF`, reservado en `ram_lejana.s`, y tres
  bytes en `$7E3616` (`ANIMB_PREV`).
* **CPU**: medido con una ROM instrumentada —el contador vertical leído antes
  y después de `anim_cuadro_armar`— con las catorce animaciones en el mapa 52,
  el de más personajes que dibuja animaciones: **8 scanlines de media y 50 la
  peor**, de 262, una vez cada dos cuadros. La peor es la 132, donde dos
  cuadros seguidos suman 55 tiles.
* **Cuadros perdidos** del lazo con las catorce seguidas: en el mapa 52, 2
  antes y 4 ahora; en el 6 y en el 3 (el Emitter Room, 35 personajes), cero y
  cero. El 52 ya perdía sin esto.
* **Cuadros de carga**: `anim_buf_limpiar` borra los 2 KB al cargar cada mapa,
  con la pantalla apagada: unos 10.000 ciclos de CPU, menos de un cuadro.

**Cómo se verificó**: `just pruebas` en verde sin tocar ninguna golden, y la
prueba nueva `pruebas/rpgmaker/test_animacion_cuadros.py`, que pone a la ROM a
dibujar cada animación del cartucho —cambiándole la fila de la animación que
está dibujando— y compara la caja de la VRAM, cuadro por cuadro, los 274,
contra `cuadro_de_animacion`, la cuenta sin comprimir. Corre también en
bsnes, que enciende con la WRAM llena de basura; ahí compara `ANIMB_BUF`
porque el core no expone la VRAM. Se la vio fallar rompiendo el rearmado de
tres maneras: sin borrar el cuadro anterior (274 de 274 mal), leyendo los
tiles corridos un byte (216 de 274), y sin el borrado de la carga del mapa
(274 de 274, en los dos cores).

**Si hiciera falta bajar el peor caso**: no borrar los tiles del anterior que
el nuevo pisa (en la 132 son casi todos), o un DMA a `$2180` en vez de la
copia por CPU —cinco veces más rápido—, que se descartó por el cruce del DMA
general con el HDMA en la primera revisión de la CPU; ver el comentario de
`animacion_de_batalla_cuadros.s`.

# Preguntas

Las dos, contestadas por taro el 2026-09-26: reservar `$7E8000-$7EFFFF` para
la grilla, sí, como prueba y con la decisión escrita; y los cuadros de más por
cambio de mapa, "perfectamente aceptables".

# Método

Todo sale de `rom/build/release/`: los bloques de `mapdata.inc` leídos por
etiqueta —`.byte` hasta la línea siguiente que no sea `.byte` ni `.segment`,
porque la grilla cruza de banco en el medio— y agrupados por el nombre sin el
`_N` del final; el total usado es la suma de los segmentos `ro` del `.dbg`. Los
compresores se escribieron para esto, en Python, y cada LZ2 se verificó
descomprimiéndolo. Los scripts eran descartables y no están en el repo; lo que
hay que rehacer es: un lector de bloques, LZ2 greedy con lazy, y el modelo de
ciclos de arriba.

Los cuadros perdidos se cuentan con `cuadros_perdidos` del arnés alrededor de
cada animación, puesta a dibujar escribiendo `ANIMB_FILA`, `ANIMB_N`,
`ANIMB_T`, `ANIMB_CUADRO` y `ANIMB_ACTIVA` —lo mismo que hace la prueba—,
después de `ir_al_mapa`. Las scanlines, con una copia de la ROM que lee
`$213F`, `$2137` y dos veces `$213D` antes y después del `jsl`, y anota los
cuatro bytes en `$7E7F00`.
