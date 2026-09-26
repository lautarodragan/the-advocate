---
name: "Chips de expansión: SA-1 y S-DD1"
description: "Si conviene pasar el cartucho a SA-1 o a S-DD1: soporte, lo que da cada uno medido, lo que cuesta, y cuándo"
type: refactor
---

# Qué

taro preguntó el 2026-09-26 si conviene usar un **chip de expansión** de los que
usaron juegos oficiales y que el FX Pak Pro soporte, limitado a dos: el
**SA-1** (un segundo 65816 a 10,74 MHz, Super Mario RPG, Kirby Super Star) y el
**S-DD1** (un descompresor por hardware, Star Ocean y Street Fighter Alpha 2).

Esto es la investigación, no la implementación: ninguna línea de la ROM cambió.
Lo que sigue sale del código de los emuladores y del firmware del FX Pak
—clonados en `/extras/ref/`—, de fullsnes, y de mediciones hechas con el arnés
sobre `8527f44`. Cómo se reproduce cada cosa está al final.

# Status

Investigado el 2026-09-26. **La recomendación es no migrar ahora a ninguno**, y
tener al S-DD1 como la respuesta preparada para cuando el cartucho llegue al
umbral de `decisiones/el-cartucho-se-queda-en-4-mb.md`. El SA-1 se vuelve a
mirar recién cuando se encare la carrera en auto, y sólo si antes no alcanzó
con optimizar el intérprete. El porqué está en "La recomendación".

# El soporte

| | SA-1 | S-DD1 | MSU-1 junto con el chip |
| --- | --- | --- | --- |
| **FX Pak Pro** | Sí, desde el firmware **v1.9.0** (RedGuy). Hasta 8 MB | Sí, desde **v1.10.0** (magno) | **Sí en los dos.** El core de SA-1 compila el MSU-1 sólo en el Mk3, que es el Pro: en un sd2snes Mk2 no hay MSU-1 con SA-1 |
| **Mednafen**, módulo `snes` (el que usa por omisión, un fork de bsnes v0.059) | Sí | Sí | **No**: ese módulo no tiene MSU-1, igual que hoy |
| **Mednafen**, módulo `snes_faust` (experimental, se pide con `-force_module snes_faust`) | Sí | Sí | **Sí**. Su documentación dice "timing is approximate" |
| **snes9x** (el core de la tanda) | Sí | Sí, por HLE: descomprime la transferencia entera al arrancar el DMA | Sí |
| **bsnes** (el de `test_cores.py`) | Sí | Sí | Sí |
| **mesen-s** (libretro) y **Mesen2** | Sí | Sí | Sí |
| **ares** | Sí | Sí | Sí |

Lo que dice cada fila, con dónde está escrito:

* **FX Pak.** `CHANGELOG` de `sd2snes` (clonado en `cf7e21d`, que es el v1.11.2):
  "v1.9.0 — add SA-1 support by RedGuy", "v1.10.0 — add S-DD1 support by
  magno". La detección es `src/smc.c:232-257`: `map & 0xEF` —o sea que el bit de
  FastROM da igual— en `$23` con tipo `$32/$34/$35/$36` es SA-1, en `$22` con
  `$43/$45` es S-DD1. Los dos cores de FPGA traen su `msu.v`
  (`verilog/sd2snes_sa1/` y `verilog/sd2snes_sdd1/`), y el decodificador de
  direcciones de los dos habilita el MSU-1 en `$2000-$2007` igual que el core
  base (`address.v:116` y `:105`). La diferencia es que `sd2snes_sa1/msu.v`
  envuelve todo en `` `ifdef MK3 ``. El mapeador del SA-1 guarda tres bits por
  bloque de 1 MB (`sd2snes_sa1/address.v:73`): 8 MB. Los save states **no**
  andan con juegos de chip (nota del v1.11.0).
* **Mednafen.** `Documentation/snes.html` y `snes_faust.html` del tarball de la
  1.32.1, que es la instalada. El módulo `snes` detecta el SA-1 y el S-DD1 en
  `src/snes/src/cartridge/header.cpp:151` y `:160`, y no trae nada de MSU-1.
  `snes_faust` lista "CX4, DSP-1, DSP-2, MSU1, S-DD1, SA1, Super FX"
  (`src/snes_faust/cart.cpp:352-354` detecta, `msu1.cpp:430` mapea el MSU-1
  aparte del chip). **De paso**: `docs/snes/emulators.md` dice que Mednafen no
  tiene MSU-1, y es cierto sólo del módulo por omisión. Con
  `mednafen -force_module snes_faust abl.sfc` debería sonar el MSU-1 hoy mismo;
  no lo probé.
* **snes9x.** `memmap.cpp:2172-2225`: la clave es `(tipo << 8) | mapeo`, y el
  SA-1 es **sólo `0x3423` o `0x3523`**, o sea mapeo `$23` exacto. Con `$33` —el
  mismo con el bit de FastROM— no lo reconoce. El S-DD1 es `0x4332` o `0x4532`.
  El MSU-1 va por `ppu.cpp:241` y `:989`, que no miran el chip. El S-DD1 es
  HLE: `dma.cpp:131-155` descomprime todo al arrancar el DMA, sólo si el canal
  está en modo de dirección fija, y limpia `$4801` entero en vez de canal por
  canal como bsnes.
* **bsnes.** `heuristics/super-famicom.cpp:255-293`: mapeo `$22/$32` es S-DD1,
  `$23/$33` es SA-1, y el nibble alto del tipo lo confirma. Los tableros son
  `SA1-RAM` y `SDD1-RAM` de `boards.bml`. El MSU-1 se carga si existe
  `msu1/data.rom`, sin mirar el tablero (`sfc/cartridge/load.cpp:72`).
* **Mesen2** (`Core/SNES/BaseCartridge.cpp:274-275`, por el nibble alto del tipo)
  y **mesen-s** (`Core/Sa1.cpp`, `Core/Sdd1.cpp`): el MSU-1 lo arma
  `SnesConsole.cpp:127` aparte. **ares**: `mia/medium/super-famicom.cpp:556-600`
  es la misma heurística de bsnes, y el MSU-1 va aparte
  (`ares/sfc/cartridge/load.cpp:54`).

O sea que **la cabecera tendría que decir `$23` y `$35` para el SA-1** —SA-1,
RAM y batería; `$23` porque snes9x no acepta otra cosa— y **`$32` y `$45` para el
S-DD1**. Ningún emulador de los que importan es un obstáculo, y Mednafen tampoco:
queda como está hoy, sin MSU-1, que es el camino que la ROM ya soporta.

# Qué daría cada uno

## Más de 4 MB

La decisión de 4 MB dice que pasar de ahí es ExHiROM. Los dos chips tienen su
propio mapeador, y ninguno pide ExHiROM:

* **SA-1**: hasta **8 MB**, en bloques de 1 MB (`$2220-$2223`, fullsnes "SNES
  Cart SA-1 Memory Control"). Se ven **cuatro a la vez**: con 4 MB no hay que
  conmutar nada, y de 4 a 8 hay que elegir qué bloque va en cada ventana.
* **S-DD1**: bloques de 1 MB en cuatro ventanas `$C0-$FF` (`$4804-$4807`). Star
  Ocean usa 6 MB; bsnes acepta 4 bits por registro, y el FX Pak desde el v1.11.1
  detecta S-DD1 de más de 48 Mbit ("fixes the PT-BR translation of Star
  Ocean"). La ventana LoROM `$00-$3F:8000` ve **sólo los primeros 2 MB**
  (`sfc/coprocessor/sdd1/sdd1.cpp`, `mcuRead`).

Pero con S-DD1 la pregunta de los 4 MB cambia de forma, porque **comprime**: lo
medido abajo dice que los gráficos que viajan por DMA quedan en menos de un
tercio. El juego entero se estimó en ~7 MB sin comprimir, y el grueso son
gráficos.

## Compresión: el S-DD1

**El formato.** No es un LZ: es un codificador **binario adaptativo por
contexto**, bit por bit, con corridas codificadas en Golomb y ocho "buckets" de
corrida según la probabilidad estimada (fullsnes, "SNES Cart S-DD1
Decompression Algorithm"; la descripción original es de Andreas Naive). Lo que
lo hace bueno para esta consola es que **entiende los tiles planares**: tiene
modos de 2, 4 y 8 bitplanes, y el contexto de cada bit es la historia de su
propio plano, incluida la fila de arriba. Tiene además un modo "8 bits" para
datos que no son tiles.

**Hay compresor, y ahora hay uno nuestro.** Andreas Naive publicó un compresor
en C++ en la wiki de superfamicom.org (`CompressionExample.7z`, página "S-DD1"),
sin licencia explícita. Para medir sin depender de eso escribí uno desde el
pseudocódigo de fullsnes: `/extras/scratch/chips/sdd1.py`, unas 150 líneas.
**Lo verifica un decodificador que no es el mío**: cada bloque comprimido se
descomprime con el de snes9x —`sdd1.c`, compilado aparte— y sale byte por byte
igual. Lo que **no** está verificado es contra el chip de verdad; el FX Pak
tampoco lo es: es una reimplementación en VHDL del mismo algoritmo.

**El ratio, medido el 2026-09-26** sobre los bloques de `release` de `8527f44`,
eligiendo por bloque la mejor de las cuatro configuraciones de contexto. zlib
-9 va de referencia, como techo de lo que da el software —un descompresor en
65816 queda bastante por debajo de zlib—:

    clase          bpp  unidad          crudo      S-DD1            zlib -9
    map_tiles       8   el mapa       458,9 KB   252,7 KB (55%)   223,9 KB (49%)
    sprite_poses    4   la pose, 512  366,0 KB   108,1 KB (30%)   135,0 KB (37%)
    sprite_tiles    4   el bloque     287,8 KB    61,3 KB (21%)    53,2 KB (18%)
    anim_batalla    4   el bloque     548,0 KB    17,5 KB ( 3%)    21,6 KB ( 4%)
    battler         4   el bloque      74,8 KB    34,2 KB (46%)    32,9 KB (44%)
    fondo           8   el fondo       48,0 KB    27,6 KB (58%)    31,1 KB (65%)
    titulo_tiles    8   la imagen      31,0 KB    13,3 KB (43%)    13,7 KB (44%)
    above_tiles     4   el mapa        19,3 KB    10,6 KB (55%)    11,3 KB (59%)
    map_celdas      8b  el mapa       278,2 KB    38,4 KB (14%)    22,9 KB ( 8%)
    map_bloques     8b  el mapa        51,8 KB    23,4 KB (45%)    20,2 KB (39%)
    evcodigo        8b  el mapa        39,1 KB    29,7 KB (76%)    16,1 KB (41%)
    mensajes        8b  el bloque      64,8 KB    55,7 KB (86%)    26,0 KB (40%)
    total                            2267,7 KB   672,6 KB (30%)   608,1 KB (27%)

Tres lecturas:

* **En tiles le gana o empata a zlib**, y en las poses, que es lo que más
  importa, le gana claro: 30% contra 37%. En lo que no son tiles —bytecode,
  texto— pierde feo: su modo de 8 bits no ve repeticiones de bytes, sólo
  estadística de bits.
* **`anim_batalla` es 97,8% ceros** —medido: 931 tiles distintos de 17.536—.
  Esos 530 KB los recupera cualquier RLE o deduplicación por software y no son
  un argumento para el chip. Se lo paso al que investiga la compresión por
  software. Sin ella, los gráficos que viajan por DMA bajan de 1286 KB a 507 KB
  con el S-DD1.
* **Lo que sólo el chip da es descomprimir sin CPU**: el S-DD1 entrega un byte
  por ciclo de DMA, así que una pose comprimida se sube en vblank en el mismo
  tiempo que una cruda y sin una sola instrucción de más. Por software, las
  poses en caliente —que se suben por DMA en el vblank, como FF5— costarían
  CPU en el peor lugar.

**Las restricciones**, todas en el código de los emuladores:

* **Sólo por DMA.** Leer los datos comprimidos con la CPU devuelve los bytes
  comprimidos. El DMA tiene que salir de `$C0-$FF`, con el canal prendido en
  `$4800` y `$4801`, y **con la dirección de origen fija** —el bit 3 de `DMAP`,
  el mismo truco que ya usa el puerto de datos del MSU-1—: bsnes compara cada
  lectura contra la dirección con que arrancó el DMA (`sdd1.cpp`, `mcuRead`), y
  snes9x sólo descomprime con `AAddressFixed`.
* **Un DMA es un flujo**, que arranca de cero, de hasta 64 KB. No hay acceso
  aleatorio adentro: **la grilla del mapa, que se recorre con un puntero al
  caminar, no puede quedar comprimida en la ROM**. Se podría descomprimir a la
  WRAM al cargar el mapa —el DMA llega a `$2180`— y el banco `$7F` está libre,
  pero eso es otra decisión.
* **El destino puede ser cualquiera del bus B**: VRAM, CGRAM, o la WRAM por
  `$2180`.
* **El mapa de memoria cambia**, y no poco: la ventana LoROM ve sólo los
  primeros 2 MB, así que todo lo que hoy vive en los bancos `$40-$7D` —los 2 MB
  de arriba— pasa a `$C0-$FF`, en bancos de 64 KB. La SRAM queda donde está,
  en `$70` (tablero `SDD1-RAM` de bsnes, `Sdd1.cpp:25` de Mesen2, snes9x mapea
  `$70-$7F`), y **el FastROM se conserva**: `$32` es el mapeo rápido que usan
  los dos juegos, y `$80-$BF` sigue siendo el espejo de `$00-$3F`.

## CPU: el SA-1

Un 65816 a 10,74 MHz con 2 KB de I-RAM, la BW-RAM del cartucho —que es la SRAM,
con batería—, interrupciones cruzadas, multiplicación y división, conversión
de bitmap a planar por DMA y lectura de bits de largo variable (fullsnes, "SNES
Cart SA-1"). **No ve la WRAM de la consola, ni el PPU, ni el APU, ni los DMA de
la CPU principal.**

Lo que rinde de verdad está en `sfc/coprocessor/sa1/memory.cpp` de bsnes:

    el SA-1 lee...          ciclos   o sea         si la CPU principal está
                                                   en la misma memoria
    ROM                        1     10,74 MHz     2 ciclos: 5,37 MHz
    I-RAM                      1     10,74 MHz     3 ciclos
    BW-RAM                     2      5,37 MHz     4 ciclos

La CPU principal, contra eso, lee la ROM a 3,58 MHz con FastROM y la WRAM a
2,68. **La trampa es la columna de la derecha**: nuestro código entero corre
desde la ROM, así que mientras la CPU principal trabaja, cada lectura de ROM del
SA-1 cuesta el doble. Un intérprete que lee bytecode de la ROM y estado de la
BW-RAM rinde entre **1,5 y 3 veces** el de hoy, no cuatro, y el extremo bueno
pide que la CPU principal espere con `wai` o desde la WRAM.

**Y el FastROM con SA-1 no está claro.** fullsnes: "The SNES CPU can access
memory at 2.68MHz rate (or 3.5MHz, but that mode may not be used in combination
with the SA-1)". bsnes y snes9x respetan `MEMSEL` igual, y Mesen2 hasta modela
el FastROM contra los conflictos del SA-1 (`Sa1Cpu.cpp:141`), así que **ningún
emulador lo cobraría**. El FX Pak no es el chip de verdad sino una FPGA, así que
lo que haga ahí tampoco prueba lo que haría un SA-1 real, pero es lo que importa
para taro. Perder el FastROM es perder lo que ganó `RAPIDO` el 2026-09-11 —la
apertura perdía un cuadro de cada tres sin él— en todo lo que se quede en la
CPU principal.

# Dónde se va hoy el cuadro

## El método

La ROM no tiene perfilador, así que armé **una copia sondeada**:
`/extras/scratch/chips/instrumentar.py` copia `rom/src/` a un directorio aparte,
pone después de cada `jsr` del lazo principal un `jsl` a una sonda que lee la
línea del contador vertical (`$2137`/`$213D`) y acumula en `$7F:F000` cuántas
líneas pasaron desde la sonda anterior, y hace lo mismo alrededor de
`music_tick` en `irq_musica`. Arma contra los `.inc` de `rom/build/release`, sin
tocar el árbol. `medir.py` corre escenas y, en cada vuelta del lazo, reparte sus
líneas por rutina.

**Cada sonda cuesta una línea** —medido: dos sondas seguidas dan 1,0 entre
ellas—, y en una vuelta normal corren unas 27. O sea que las vueltas sondeadas
están **~27 líneas infladas**, y lo que dicen de "cuadros perdidos" es
pesimista. Por eso cada escena se corrió también en la ROM de verdad
(`REAL=1`), contando vueltas contra cuadros. Una vuelta tiene 262 líneas.

## El minijuego de las piedras (mapa 11)

    escena                                  ROM de verdad            sondeada
    caminando en (19,46), sin piedras       599 vueltas / 600        598 / 600
    modo piedras, quieto                     60 / 60                  60 / 60
    modo piedras, tirando dos piedras       139 / 140                138 / 140
    modo piedras, caminando                 240 / 240                239 / 240

En el emulador, **hoy el minijuego casi no pierde cuadros**: uno cada 140 a 600.
Lo que sí dice la sonda es que **el margen es fino y dónde está el gasto**:

    modo piedras, quieto — 191 líneas por vuelta (~164 sin las sondas)
       paralelos (eventos_de_mapa)    123   el 47% de las 262
       build_oam                       28
       flush_video                      6
       el resto, de a una o dos       ~34   (casi todo, la sonda misma)

Las vueltas que se pasan son las que suman al paralelo un paso del héroe
(`move_hero` 14, `stream_map` 30) o un refresco de páginas (21). **El que come
es el intérprete de los paralelos**: el mapa tiene **13 páginas paralelas
sin espera** —las seis `Light*`, el ídolo, tres guardias, la PC, `EV0017` y el
`LightFloor` de 145 comandos—, y cada una corre entera en cada cuadro. Salen a
unas 9 líneas por página.

No reproduje un lag fuerte. Si taro lo ve jugando, lo más probable es que sea
alguno de esos picos sumado a algo que estas escenas no tocan —un guardia
caminando, un mensaje—, y con 60 líneas de margen alcanza con poco. **Es CPU**, y
es justo lo que el SA-1 acelera.

## La terraza (mapa 32)

La cinemática de `EV0005` no tiene ningún `TintScreen`: **los "tintes" son
destellos**, siete `FlashSprite` —Kersh azul, Arden celeste, el héroe rojo— y
tres `FlashScreen`. Jugada hasta la pelea con A cada 20 cuadros, **la ROM de
verdad pierde 9 cuadros sueltos en ~2100**. Las vueltas pesadas, sondeadas:

    121 vueltas de más de 224 líneas, 260 en promedio; la peor, 289 (~262 sin
    las sondas):
       destello_tick     103   FlashScreen: rehace la paleta entera
       flashes_tick       94   FlashSprite: rehace la paleta del evento
       build_oam          32
       flush_video        11
       paralelos          11

**Casi 200 de las 262 líneas se van en rehacer paletas** cuando un
`FlashScreen` y un `FlashSprite` coinciden. Es CPU pura: multiplicaciones y
divisiones por color, igual que el tinte (ver `tabla_canal` en
`rom/src/tinte.s`, que ya tuvo que sacarse noventa y seis `jsr` para entrar).
Subir la paleta a CGRAM en el vblank son 512 bytes: no es eso.

## La carrera (mapas 49-54)

No está en ninguna ROM, así que **no está medida**. Lo que se puede contar es
el trabajo (`/extras/scratch/chips/carrera.py`): los mapas 49, 52 y 54 tienen
**41 páginas paralelas cada uno** —`RaceController2` y cuarenta eventos de ~17
comandos que leen coordenadas, comparan y cambian el sprite—, contra las 13 del
mapa 11. A las 9 líneas por página del mapa 11, son **~370 líneas: no entra en
un cuadro** tal como está el intérprete hoy. Es una estimación de orden de
magnitud: las páginas del 11 no son iguales a éstas.

# Las ideas de taro, una por una

**El minijuego de las piedras.** El gasto es el intérprete de los paralelos
(~123 líneas). En el SA-1 esas páginas correrían 1,5 a 3 veces más rápido, o
sea que el margen pasaría de ~60 a ~110-140 líneas. Pero hoy casi no pierde
cuadros en el emulador, así que el SA-1 arreglaría un problema que por
software se arregla más barato: ver "Sin chip".

**La terraza.** Es el mejor candidato del SA-1 por forma —rehacer una paleta es
una función pura: entra la paleta y el destello, sale la paleta—, y el SA-1 la
haría en su I-RAM mientras la CPU principal sigue; el DMA de la CPU principal
lee la I-RAM y la BW-RAM, que están en el bus A. Pero también es el caso más
fácil sin chip: la paleta de un destello se puede calcular una vez por paso de
fuerza, o repartir entre cuadros, o no rehacer lo que no cambió.

**La carrera en auto.** Es el único caso donde el SA-1 podría ser la diferencia
entre 60 y 30 fps, porque ~370 líneas de paralelos no entran ni con un
intérprete el doble de rápido en la CPU principal. Con el SA-1, a 1,5-3 veces,
quedan 120-250. **Antes de decidir hay que medirla**: meter el 52 en un cartucho
de prueba y correr la sonda.

**Mover los eventos paralelos al SA-1.** Es lo general, y por eso es la versión
que vale: no sabe nada de ABL. Lo que pide:

* **todo lo que el bytecode toca tiene que vivir en la BW-RAM o la I-RAM**: las
  variables (hoy en `$7E:2600`, por la ventana de `WMADD`), los switches, la
  tabla de eventos con sus posiciones, el estado de cada paralelo
  (`FAR_PAR_ESTADO`), el azar, el inventario. Son todos los usuarios de
  `WMDATA` —unos 190 en 17 archivos— y los de la BSS que el intérprete mire;
* **lo que el bytecode hace con el hardware no lo puede hacer el SA-1**:
  `PlayBGM`, `PlaySound`, un mensaje que sube glifos, un teletransporte que
  recarga la VRAM, un tinte que sube paletas. Esos opcodes pasan a ser pedidos
  en una cola que la CPU principal atiende;
* **el orden de `Game_Map::Update` no se puede romper**: los paralelos van
  antes del héroe y las goldens son de pixel exacto. O sea que la CPU principal
  **espera** a que el SA-1 termine, y lo que se gana es la velocidad del
  segmento, no el paralelismo. Lo único que se puede solapar es lo que no mira
  el estado de los eventos.

**Que la CPU principal procese las transiciones y el SA-1 haga los chequeos.**
En el mapa 11 "los chequeos" —dónde está la piedra, si pisé una luz— **son
páginas de RM2k**: las `Light*` y el `LightFloor`. Hacer que el SA-1 las haga sin
código de ABL es exactamente la idea anterior. Cualquier versión más fina —el
SA-1 compara posiciones y la CPU principal decide— necesita saber qué página
es "un chequeo", y eso es reconocer el minijuego por dentro, que es lo que
`done/el-mapa-11-se-rediseno.md` ya descartó con el camino 4.

# Diseños

**A. El intérprete de eventos en el SA-1, la CPU principal con el video y el
audio.** Es la idea anterior llevada a todo el intérprete: `eventos_de_mapa`,
`eventos_tick` y las rutas. Gana en los tres casos medidos y en la carrera.
Pide mudar el estado de los eventos a la BW-RAM y la cola de pedidos. El
problema grande es la sincronización: cada opcode que toca hardware es un ida y
vuelta, y un mensaje o una pelea son muchos.

**B. Todo el juego en el SA-1, la CPU principal como sirvienta de E/S.** Es como
están hechos Super Mario RPG y Kirby: el lazo entero corre en el SA-1, y la CPU
principal sólo hace el DMA del vblank desde sombras en la BW-RAM, lee el
control y toca la música por su IRQ. Gana todo, `build_oam` y `stream_map`
incluidos, y no hay sincronización dentro del cuadro. Tiene a su favor que el
SA-1 ve la I-RAM en `$0000-$07FF`, así que la página directa y la pila quedan
donde están. Pero la BSS —7680 bytes, llena— no entra en los 2 KB de I-RAM y
va a la BW-RAM a 5,37 MHz, y **la BW-RAM es la SRAM con batería**: trabajar
en ella cambia su CRC en cada cuadro, y el FX Pak graba la SRAM a la tarjeta
cuando la ve cambiar (`msu_savecheck` en `src/msu1.c:73`, en las pausas del MSU-1). Es el refactor
más grande de los tres.

**C. Trabajos puntuales.** Todo queda en la CPU principal y el SA-1 recibe
funciones puras: la paleta de un tinte o un destello, una descompresión por
software a 10 MHz. Es lo más incremental y lo más barato, pero **no toca el
intérprete**, que es lo que come en el mapa 11 y en la carrera.

# Qué costaría migrar

## El paso cero: cambiar el mapeo sin usar el chip

Es el camino incremental, y es el mismo para los dos: la ROM pasa a declarar el
chip, se reacomoda, y **no lo usa**. Lo verifican las goldens —la ROM tiene que
dibujar exactamente lo mismo— y `test_cores.py`.

Lo que toca:

* **`tools/ensamblado/bancos.py`**, el `.cfg` de `ld65`. Hoy son 126 áreas LoROM
  de 32 KB en `$00-$7D` y dos reservadas. Con S-DD1, los 2 MB de arriba van a
  `$C0-$FF` en bancos de 64 KB; con SA-1, o a `$80-$BF` (el mapeo por omisión de
  su MMC pone ahí los MB 2 y 3, en LoROM) o a `$C0-$DF`. Los dos reservados
  para `$7E-$7F` dejan de hacer falta.
* **`RAPIDO`**, en tres lugares. Con S-DD1 no cambia nada. Con SA-1 depende del
  FastROM: si vale, el MMC se programa para que `$80-$BF` sea espejo de
  `$00-$3F` (`$2222 = $80`, `$2223 = $81`) y los MB altos van a `$C0-$DF`; si no
  vale, el código se queda en `$00` y el espejo se va.
* **La cabecera** (`rom/src/cabecera.s`): dos bytes, y el checksum sigue en el
  mismo lugar.
* **La SRAM**: con S-DD1 queda en `$70`. Con SA-1 pasa a `$40` y hay que
  habilitarle la escritura a la CPU principal (`$2226`), que arranca protegida.
  `SRAM_BANCO` está en `partida.s`, `ranuras.s` y `nivel.s`.
* **El arnés**: `en_la_rom` de `pruebas/arnes/consola.py` es la fórmula LoROM y
  la usan las pruebas que leen tablas de la ROM. Y el conversor tiene dos
  supuestos de LoROM escritos (`snes_convert.py:2977` y `:3634`) y un puntero de
  grilla que cruza de banco sumando uno: un bloque no puede quedar a caballo de
  los 2 MB.
* **`just entregar`** y el `.sym` no cambian: los arma el mismo `ld65`.
* **El MSU-1** tampoco: `$2000-$2007` no choca con ninguno de los dos
  (`$2200-$23FF` del SA-1, `$4800-$4807` del S-DD1).

Del orden de **100 a 200 líneas**, casi todas en Python.

## Lo que viene después

* **S-DD1, las poses comprimidas.** El conversor comprime —el compresor de
  `/extras/scratch/chips/sdd1.py` va al caché de disco, porque en Python tarda
  minutos—, y el DMA de las poses pasa a modo de origen fijo desde `$C0-$FF`.
  Chico: el formato no toca la ROM más que en cómo se arma el DMA. Después, los
  tiles de los mapas y de los fondos al cargar.
* **SA-1, el diseño A o el B.** Semanas. Mudar el estado, el arranque del SA-1
  (arranca en reset y hay que darle su vector), el buzón y la cola de pedidos.

## Lo que cobrarían las pruebas y lo que no

**Lo cobran**: cualquier dato mal leído por el mapeo nuevo —las goldens, en
pixeles—; la memoria sin inicializar —`test_cores.py`, que con SA-1 también
tendría que mirar la BW-RAM—; la partida guardada —`test_guardar.py` y los de
ranuras, por la SRAM que expone snes9x—; un cuadro de más —`cuadros_perdidos` y
`test_el_hq_de_los_lazer_teeth_entra_en_el_cuadro`—.

**No lo cobra nada**, y hay que llevarlo al FX Pak:

* **el FastROM con SA-1**: los emuladores lo dejan andar;
* **el MSU-1 junto al chip** en el FX Pak, y el puerto de datos por DMA ahí;
* **la SRAM en el FX Pak**: dónde la mapea el core de S-DD1 —el v1.11.1 menciona
  un "mixed mapper SRAM layout"— y cómo graba la BW-RAM el de SA-1;
* **el tiempo del SA-1**: snes9x lo aproxima y bsnes no, así que en un mapa que
  entra justo `test_cores.py` podría empezar a dar rojo por un cuadro perdido en
  uno y no en el otro;
* **Mednafen**, que ninguna prueba corre.

# La recomendación

**No migrar ahora.** Ninguno de los dos arregla algo que hoy no tenga un
arreglo más barato:

* el mapa 11 casi no pierde cuadros, y lo que come es el intérprete;
* la terraza son paletas que se pueden calcular menos veces;
* el cartucho no llegó al umbral que la decisión de 4 MB se puso para
  revisarse (`radio.py` del estudio de compresión, sobre el `.dbg`, da ~77% el
  2026-09-26).

**El S-DD1 es la respuesta para el espacio**, y conviene tenerlo preparado para
cuando el cartucho llegue al 85-90%. Frente a la compresión por software gana
en lo que ésta no puede: descomprime **sin CPU**, en el mismo DMA, así que sirve
también para las poses que se suben cada cuadro. Deja todos los gráficos en
menos de un tercio, conserva el FastROM y la SRAM en `$70`, y lo corren el FX
Pak con MSU-1, los cuatro emuladores del arnés y Mednafen sin MSU-1. En contra:
lo usaron dos juegos, el compresor es nuestro, y la ROM se ata a un chip que
ningún cartucho común tiene.

**El SA-1 es la respuesta para la carrera**, si hace falta. Antes, dos cosas en
este orden: medir la carrera en un cartucho de prueba, y optimizar el
intérprete, que es general y sirve en cualquier consola. Si con eso los
paralelos de la carrera siguen sin entrar en el cuadro, el diseño A es el
camino. No se pueden tener los dos: son tableros distintos.

## Sin chip

* **El intérprete de los paralelos**, que es lo que más come en el mapa 11 y en
  la carrera. Lo general: fundir en el compilador los patrones de RM2k que se
  repiten en cada página —leer la X de un evento en una variable y compararla—,
  y leer las variables con `lda f:$7E2600, x` en vez de la ventana de `WMADD`
  (tres escrituras y dos lecturas por variable). El comentario de
  `ram_lejana.s` dice que esa memoria "no se puede indexar"; con
  direccionamiento largo sí se puede. Hay que ver con `git blame` por qué se
  eligió la ventana antes de tocarlo. No está medido cuánto ganaría.
* **Las paletas de los destellos**: calcular la paleta de cada paso de fuerza
  una sola vez, repartir el trabajo entre cuadros, o no rehacer lo que no
  cambió. La suma de color del hardware no sirve: da `c + f·s` y no la mezcla
  de RM2k.
* **La compresión por software**, que investiga otro agente: para
  `anim_batalla` alcanza con un RLE, y para los mapas se descomprime al cargar,
  que es cuando sobra tiempo. Lo que no puede hacer bien son las poses.
* **ExHiROM**, que el FX Pak soporta (`smc.c:259`, `mapper_id = 2`), sigue
  valiendo lo que dice la decisión: cambia cómo se calcula cada dirección, igual
  que el paso cero de cualquiera de los dos chips, y no da ni compresión ni CPU.

# Cómo se reproduce

Los scripts quedaron en `/extras/scratch/chips/`, y todos llevan la raíz del
worktree escrita adentro (`WT`): hay que cambiarla antes de correrlos, y hay que
armar `release` antes.

* `instrumentar.py` arma la ROM sondeada en su propio directorio;
* `medir.py <escena>` corre `mapa11_caminar`, `mapa11_piedras`, `terraza` o
  `terraza_real`, sondeada o con `REAL=1` en la ROM de verdad;
* `sdd1.py` es el compresor y descompresor, con su prueba de ida y vuelta;
  `armar_s9x.py` arma el decodificador de snes9x para compilarlo con
  `gcc -O2 -o s9x_sdd1 s9x_sdd1.c`, y `ratio.py` da la tabla de arriba
  (`ratio.log` es la corrida);
* `paralelos.py` y `carrera.py` cuentan las páginas paralelas de un mapa.

Los clones: `/extras/ref/sd2snes` (el firmware del FX Pak), `/extras/ref/ares`,
`/extras/ref/mednafen-src` (el tarball de la 1.32.1) y `/extras/ref/fullsnes`.
bsnes, snes9x, mesen-s y Mesen2 ya estaban; el snes9x de `/extras/ref` es el
mismo commit que el core instalado.
