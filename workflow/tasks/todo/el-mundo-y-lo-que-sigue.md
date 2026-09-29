---
name: "El mundo y lo que sigue"
description: "Plan: el mapa del mundo (66) en release, el capítulo de Lashe Area hasta el túnel a Paradise, y el espacio que falta para meterlo entero"
type: feature
---

# Qué

Lo que sigue a `la-carrera-y-lo-que-sigue.md`. Hoy la demo termina al final
de la escena del 64, con un fork (`parches/manual/mapas/Map0064.json`) que
cambia el `Teleport [66, 71, 29]` por el cartel de fin. Esto es **qué hace
falta para que entre el mapa del mundo, el 66, y lo que se alcanza desde él**
hasta el próximo corte natural, medido y no implementado. Los hitos de abajo se
vuelven tareas propias al lanzarlos.

Todo lo medido acá es del 2026-09-27 sobre `c84ed2b`, con variantes de
`release` armadas aparte: ni `release` ni `cartuchos.py` ni el conversor en
`main` se tocaron. **Nada de esto lo cubre `just pruebas`**: son variantes
que ninguna receta arma, y lo que se corrió en el emulador está dicho con
todas las letras en cada lugar.

Los scripts quedaron en `/extras/scratch/mundo-plan/`, que sobrevive a la
sesión (las variantes armadas no: pesan). `armar.py` arma una variante,
`medir.py` saca el espacio con el método de `AGENTS.md`, `far.py` el banco 1,
`grande.py` relinkea una variante que no entra en 4 MB con bancos de mentira y
dice cuántos pide, `ffd.py` estima el acomodo de bancos con first-fit
decreasing, `categorias.py` y `tablas.py` dicen qué creció, `culpables.py`
qué comando frena cada página, `grafo.py`, `switches.py` y `dependencias.py`
arman el recorrido, y `probar66.py` corre una variante en el emulador.
`hacks.diff` son los interruptores de medición que hicieron falta en el
conversor —todos detrás de una variable de entorno; con ninguna puesta,
`release` sale byte por byte igual, comprobado—:

    MUNDO_SEGUIR=1     los topes de VRAM, de LZ2 y de la tabla de alturas del
                       .msu se imprimen (MEDICION-…) en vez de cortar
    MUNDO_PASO=4       el bloque de textos de a 4 bytes (la ROM sigue
                       multiplicando por 2: los textos salen corridos)
    MUNDO_SIN_TIMER=…  esos mapas sin los dígitos del cronómetro
    MUNDO_BLOQUES=…    anota el tamaño de cada `.bloque` para `ffd.py`
    MUNDO_TILEMAP=…    vuelca el tilemap de cada mapa
    y el quinto reparto de VRAM (ver "El 66"), agregado al final de LAYOUTS

# El 66

    Lashe Area   100x75 celdas, chipset 31, sin panorama
    fondo        527 tiles únicos de 8bpp, 97 colores (100 de 103 en CGRAM)
    encima         5 tiles
    sprites      222 tiles: 16 personajes en 12 ranuras, las 8 paletas
                 (Crown3:4 baja a 14 colores para que entren los dígitos
                 del cronómetro)
    eventos      42, 23 con CharSet; 2 horneados (el 11 y el 13)
    grilla       344 bloques, 15.000 B: entra en la mitad baja de la WRAM

**Por qué no entra hoy.** Los cuatro repartos de `LAYOUTS` dan, con 222
sprites, a lo sumo 480 tiles de fondo ("+fondo" y "+ambos"), y el 66 pide 527.
Pero `docs/port/vram.md` ya tenía la respuesta: el techo con 256 sprites es
**544**, y "+fondo" está 64 por debajo sólo porque subirlo le cambiaría el
reparto a los mapas que ya lo usan. Un quinto reparto **al final** no le
cambia nada a nadie:

    sprites     $0000   8 KB  256 tiles
    tiles       $1000  34 KB  544 tiles de 8bpp   <- la base de BG1
    ventana_map $5400   2 KB
    mapa        $5800   4 KB
    encima      $6000         128 tiles
    ventana     $6800         256 tiles
    tilemap     $7800         el de encima

Pasa `_controlar_repartos` y `_controlar_ranuras` tal cual, y le deja al 66
17 tiles de fondo y 34 de sprite de margen.

**El segundo tope, que aparece detrás:** los tiles del fondo del 66 miden
33.728 B y el buffer de carga de LZ2 (`LZ2_BUFFER`, `$7F0000`) mide 32 KB. Lo
que se pasa cae en `$7F8000`, que es la mitad alta de la grilla —vacía en el
66, que usa sólo la baja—, así que **en el 66 funciona de casualidad**. El
arreglo de verdad es partir el bloque del fondo en dos flujos de hasta 32 KB,
cada uno descomprimido y subido por DMA antes del siguiente, como ya se hace
con la grilla. Es código de `descomprimir.s`, que vive en `FAR`.

**Visto en el emulador** (variante `m0p2`: `release` más el 66, con el
bloque de textos de a 2 bytes, el core por omisión del arnés): el 66 carga,
`celdas_mal_dibujadas` da cero, la ventana muestra el texto del evento 2
("I can't just walk back into Lashe City!") bien, una pelea forzada con
`ENC_PIDE` (Snarling Wolf) se gana y se vuelve al mapa bien dibujado, y
caminando 17 celdas para arriba y 4 para abajo `cuadros_perdidos` queda en
cero. La pelea sale **sin fondo**: el cartucho lleva tres, y los del mundo
son otros (ver la pregunta 6).

## Los caminos, con su límite

1. **El quinto reparto (544 con 256 sprites).** Medido: entra, con 17 y 34
   tiles de margen, y se ve. Cuesta una entrada en `LAYOUTS` y el LZ2 en dos
   flujos; nada de banco 0 (el reparto viaja en el registro del mapa, y la
   ROM ya lee todo de ahí). El límite es el techo del hardware: 544 con 256
   sprites, 512 con 320 (`docs/port/vram.md`). **Recomendado.**
2. **Tiles subidos en caliente al moverse**, como las poses. Medido sobre el
   tilemap del 66: la ventana de 64x32 celdas de 8 px que la ROM mantiene
   dibujada toca a lo sumo **307** tiles distintos de los 526 (la pantalla con
   un borde de una celda, 254). O sea que con esto el 66 entraría hasta en el
   reparto de 448. Pero pide un caché de tiles con asignación y desalojo en
   la ROM, y subir columnas nuevas en el vblank junto con las poses: mucho
   código, y banco 0. **No hace falta hoy**; es el camino del día que un mapa
   pase de 544.
3. **Partir el chipset** en zonas con su propio juego de tiles, recargando al
   cruzar. Es el 2 sin caché: el mismo 307 como tope por zona, y un corte
   visible al cambiar. Peor que el 1 para el 66.
4. **Menos colores con el asignador.** No achica lo que falta: el 66 usa 97
   colores y el reuso ya es del 98%, con el espejado deduplicado (716 celdas
   lo usan). Lo que sobra son **tiles distintos**, y 148 aparecen una sola
   vez: fusionarlos sería cambiar pixeles, que es decisión del asignador y
   se vería.
5. **El MSU-1 como fuente.** **No aplica**: lo que falta es VRAM, no ROM, y el
   MSU-1 sólo puede reemplazar algo que la ROM ya lleva (`docs/port/msu-datos.md`,
   "sin MSU-1 el juego anda igual"). Sirve para el espacio del cartucho, no
   para esto.

# Qué hay en el mundo

El 66 **no es un mapa con vehículo**: se camina. Los pueblos y lugares son
eventos dibujados con un tile del chipset que llevan a otro mapa al pisarlos
(`Teleport` y el switch 236, "OnTheWorldmap", que habilita guardar desde la
paralela 26). Los encuentros son **por zona**: cuatro áreas (184 a 187) con
entre 9 y 16 tropas cada una, cada 65 pasos; la ROM ya los hace. El auto sí
aparece, pero como **actor** del grupo: `DaliaGoingToTasgarde` (el 14) saca a
Dalia, mete a `MobilizedCar` (22), le fuerza una ruta de sesenta pasos hasta
Tasgarde, y la devuelve.

A dónde lleva: 67 Yun Town, 69 Sorbe Village, 68 Drust Camp, 74 Tasgarde
Military Base, 259 Northern Highway Bridge (con el 252), 105 Mountain Path
("<-- Paradise Tunnel 2 Km", con un `ShowChoice`), 310 New Tangle Forest, 312
Burning Forest (con el 847), 348 Small General Store, y al propio 66 (cruzar el
puente, con el 849).

## Lo que la ROM no hace, contado

Con `culpables.py` sobre los 44 mapas del capítulo: **893 de 905 páginas
disparables compilan**. Lo que frena las otras doce, en orden de cuánto
destraban:

    del camino principal (todas automáticas: cada una traba la historia)
    ChangeEncounterSteps       2  66 ev14 (el viaje de Dalia a Tasgarde),
                                  81 ev6 p5
    ControlSwitches alternar   2  89 ev4, 93 ev4 p2 (la historia de Eisen)
    ChangeScreenTransitions    2  93 ev4 p1 (a "ninguna"), 95 ev55 (a "el corte")
    Comment                    1  81 ev6 p1, "HEALING TALAN'S ANKLE"
    Teleport -> 105            1  66 ev18: el fin del capítulo (va el fork)

    de lo opcional
    InputNumber + comparar     1  68 ev10: contra 35421, que no entra en un
                                  word con signo (Drust)
    EraseEvent                 1  311 ev4 (Tangle)
    condición de cronómetro    2  312 ev10 (rama) y ev81 (condición de página;
                                  es la que prende TangleForestDONE)
    ShowChoice con cancelar    1  348 ev1 p2

* **`ChangeEncounterSteps` ya se puede hacer**: el comentario de
  `eventos.py` que lo frena dice que "no hay encuentros al azar", y los hay
  —`rom/src/encuentros.s`—. Es escribir `ENC_BASE` con el `1/pasos` que el
  conversor ya sabe calcular (`eventos.enc_base`); cero es apagarlos, que es
  lo que pide el viaje de Dalia. RM2k lo vuelve al valor del mapa al cargar
  otro, y `encuentro_mapa` ya pisa `ENC_BASE` en cada carga.
* **Alternar un switch** (`ControlSwitches` operación 2) el compilador lo
  puede escribir con lo que ya hay —una condición y los dos `ControlSwitches`—,
  sin código nuevo en la ROM.
* **`Comment`** no hace nada en RM2k: se saltea al compilar.
* **Las dos transiciones** son las instantáneas; la ROM ya tiene
  `TRANSICION_BORRAR/MOSTRAR` (`op_transition`) y le falta el valor "sin
  fundido". Ver `wishlist/las-otras-transiciones-de-rm2k.md`.

Y lo que ya se acepta sin hacer (`ACEPTADOS_SIN_HACER`), que compila y no se
ve:

    ShowPicture/Move/Erase    81: el cartel "MeanwhileLashe" (la historia pasa
                              a Dalia); 95: el contador de Fortitude, dos
                              dígitos en imágenes (los comunes 9 y 10) sobre la
                              variable 48, en el minijuego "Into The Machine";
                              311: la sombra del hover
    ChangeSystemBGM           76, 311, 312
    ChangeHeroTitle           81

Ningún evento del camino principal depende de lo opcional: lo único que Yun
Town le presta a Sorbe son dos diálogos (switches 241 y 247), y el 847 de
Tangle sólo cambia unos árboles del 66 (`dependencias.py`).

# Lo que sigue

## El recorrido

    64  la despedida: Teleport [66, 71, 29]              (hoy: fin, fork)
    66  el mundo. ev1 prende StillLimping (239): Talan renguea
    69  Sorbe Village -> 76 Sorbe Mountain -> 81 Dr. Vago's House
        (77 a 80: spa, posada, armas, alcalde)
    81  la curación del tobillo; con el 270, prende TalkedWithVago (252)
        y lleva a 82
    82  Director's Office -> 83 Dalia at the Factory (en Lashe City)
    84  OutsideFactory: Dalia sale al mundo (grupo: Dalia fuera, DummyHero)
    66  ev14: el auto de Dalia hasta Tasgarde (ChangeEncounterSteps)
    74  Tasgarde -> 85 Tasgarde Lab (con Dalia) -> 86 Eisen's Story
    86..95, 99, 100  la historia de Eisen, encadenada; el 95 es el minijuego
    101 Lab After Eisen's Story -> 102, y de vuelta a 81, con Talan
    66  ev15 -> 259 Northern Highway Bridge -> 255 Under the Bridge: prende 849
    66  ev18, "Paradise Tunnel 2 Km": Yes -> 105 Mountain Path -> 106 -> 108
        Distant Paradise, que es otro capítulo (padre 0 en el árbol)

**El corte natural es el 66 ev18**: el `ShowChoice` "Yes - Continue onward"
lleva al túnel a Paradise, un capítulo nuevo. Ahí va el fork del fin de la
demo, y el del 64 se borra.

Lo opcional cuelga del 66 y se puede dejar para después sin romper nada
(salvo Tangle Forest, que está en el camino al túnel: ver el hito 4):
**Yun Town** (67, 70 a 73), **Drust Camp** (68, 103 las minas, 199 a 201) y
**Tangle Forest** (310 a 313, que usa el cronómetro). 75, 198 y 104 no se
alcanzan por `Teleport` desde el capítulo.

## Qué entra hoy, mapa por mapa

Convirtiendo cada uno en el cartucho del capítulo entero, con el código de
`main`:

    66  no: la VRAM (ver arriba). Con el quinto reparto, sí
    69  no: "encima necesita 157 tiles y entran 128"
    67  no: dos veces. El cronómetro no encuentra paleta (ya tiene dos
        gráficos pintados con paleta ajena), y encima pide 163 tiles
    los otros 41: sí

Detrás de eso, avisos que no frenan: 67, 68, 69 y 199 pintan de dos a cuatro
personajes con una paleta ajena, y 67, 68, 69, 77, 199 y 200 se quedan sin
gotas de lluvia por falta de paleta.

**La capa de encima del 69 y del 67.** Los cinco repartos tienen la capa de
encima en 128 tiles porque la ventana arranca en el índice 128 de BG2
(`VENTANA_TILE_BASE`, fija) y el tilemap de encima está clavado en `$7800`.
Un reparto con la base de BG2 en `$5000` le da 256:

    sprites     $0000  12 KB  384 tiles
    mapa        $1800   4 KB
    tiles       $2000  24 KB  384 tiles de 8bpp
    encima      $5000   8 KB  256 tiles      <- la base de BG2
    ventana     $6000   8 KB  256 tiles      <- los índices 256..511
    ventana_map $7000   2 KB
    tilemap     $7800         el de encima

El 69 (329 de fondo, 157 encima, 283 sprites) y el 67 (253, 163, 244) entran.
Lo que cuesta: la ventana arranca en el 256 y no en el 128, y `ventana_celdas`
lleva ese índice horneado, así que hace falta un segundo plano de la ventana
(2 KB de ROM) y que el mapa diga cuál usar. **No se probó**: es la cuenta de
alineaciones, no una variante.

**El cronómetro del 67** se va sin tocar paletas: el cronómetro del capítulo
sólo corre entre el 311 (arranca) y el 312 (para), y fuera de Lashe entre el 7
y el 9, 11 o 16. `args.timer_en` hoy es "todos los mapas"; si fueran los
alcanzables por `Teleport` entre un arranque y una parada, el 67 no llevaría
dígitos. Medido con `MUNDO_SIN_TIMER=67`: con eso convierte (y queda sólo lo de
la capa de encima).

## Espacio

Con `medir.py`, `far.py` y `grande.py`. Todas con el quinto reparto y el
bloque de textos de a 4 bytes (salvo `release`). BSS y ZEROPAGE no se mueven en
ninguna: 138 y 4 bytes libres. "Bancos" son los de datos, del `$02` al `$7D`:
**entran 124**. "FFD" es lo que pediría el acomodo con first-fit decreasing
(ver abajo).

    variante                              mapas  cartucho  bancos (FFD)  banco 0  banco 1
    release hoy                             65     73,8%   101  (93)      224     9.000
    m0  + 66                                66     75,6%   104            224     8.298
    m1  + Sorbe (69, 76 a 81)               73     80,9%   110            192     8.141
    m2  + 82 83 84                          76     81,4%   112            192     8.141
    m3  + Tasgarde y Eisen (74, 85 a 102)   91     88,5%   121            167     8.141
    m4  + 259 255: el camino principal      92     90,0%   122 (114)      163     8.141
    m4  + Yun (67 71 72)                    95    no entra 125            127     8.141
    m4  + Drust (68 103 199 200 201)        97    no entra 126             83     7.913
    m4  + Tangle (310 a 313)                96    no entra 127            117     8.022
    X = 105 (ver "La regla")               100    no entra 130 (121)       47     7.913
    todo el capítulo                       104    no entra 135 (125)        7     7.794

**El porcentaje engaña**: `m4` dice 90% y le quedan **dos bancos**. Los 64 KB
de `$7E` y `$7F` no son ROM, y el acomodo deja en promedio 2,3 KB libres por
banco —270 KB en `release`, 280 en `m4`— porque es secuencial: un bloque que no
entra en lo que queda salta al banco siguiente y el hueco no lo usa nadie.

**Lo que aprieta, en orden:**

1. **El cartucho.** El camino principal entra con dos bancos; cualquiera de las
   tres zonas opcionales, no. Lo que creció de `release` a todo el capítulo
   (+917 KB en etiquetas): poses +238 KB, tiles de fondo +221, streams de
   música +93, tiles de sprite +52, bloques +51, battlers +37, grillas +26,
   páginas +25.
2. **El bloque de textos.** El operando de `OP_MESSAGE` es de 16 bits de a 2
   bytes: 128 KB. `release` usa 99.346 B; **`m4` usa 131.066 de 131.072**, o
   sea que el camino principal entra por seis bytes. De a 4 bytes (dos `asl`
   en `msg_empezar`) son 256 KB y cuestan 2,2 KB de relleno en `m4`. El juego
   entero son unos 161 KB (`Mensajes.volver`), así que esto hace falta igual.
3. **El banco 0.** `m4` deja 163 bytes; todo el capítulo, 7. Lo que crece no
   son los mapas sino **las tablas de ítems** (6 B por ítem: `item_precio`,
   `item_id`, `item_tipo`, `item_uso`; 966 B en todo el capítulo) y **las de
   temas** (4 B por tema). Mudar las de ítems al banco 1, como el hito 4 de
   Lashe City mudó `tropa_codigo`, devolvería casi 1 KB.
4. **La tabla de alturas de los efectos del `.msu`** (`se_msu_altura`) mide
   paquetes × sonidos × 2 B, casi todo ceros, y tiene que entrar en un banco:
   19 KB en `release`, 29 KB en `m4`, 32,1 KB con X = 105 y **33,8 KB con todo
   el capítulo, que ya no entra**. Guardar por paquete sólo sus efectos la
   arregla.

**El acomodo de bancos (`tools/ensamblado/bancos.py`) es la palanca más barata**:
con los tamaños de cada `.bloque` de `m4`, first-fit decreasing pide 114
bancos en vez de 122 —ocho bancos, 256 KB— sin tocar la ROM. Con eso X = 105
entra (121 de 124) y todo el capítulo sigue sin entrar (125). Es una cota
optimista: `ffd.py` ignora cualquier restricción de orden entre bloques, y
habría que ver cuáles hay (el `.cruza`, las tablas que se recorren seguidas).
Lo que sigue después está medido en otros lados: las poses espejadas
(`testing/la-compresion-de-mapas-y-graficos.md`, el punto 5) y la música
(`todo/la-musica-pesa-789-kb.md`, las ideas 2 a 4). Y
`decisiones/el-cartucho-se-queda-en-4-mb.md` dice que se revisa al llegar al
85-90%: `m3` ya está ahí.

## La regla de los mapas

La de hoy es "id menor a `MENOR_A`, menos `EXCLUIDOS`, más `AGREGADOS`". El
capítulo son casi todos los ids de 66 a 104, más algunos altos:

* **Por id**: `MENOR_A = 105`, con la exclusión creciendo en seis —65
  (Northern World, carpeta), 75 (inalcanzable), 96 97 98 (respaldos), 104 (de
  otro capítulo)— y los agregados en cuatro —199 200 201 259—. El 255 y el 348,
  que hoy son `MAPAS_DE_PRUEBA`, pasan a ser del juego (y el 70, el 73 y el 74,
  que ya estaban, también). Pero **no entra** (130 bancos) hasta el acomodo:
  mientras tanto la exclusión suma lo opcional —67 68 71 72 103, y 199 200 201
  dejan de ser agregados—, y la lista pasa a dieciséis.
* **Por subárbol**: los descendientes del 66 son exactamente el capítulo más
  el 75, el 198 y el 105, y menos el 83 y el 84, que cuelgan de Lashe City. O
  sea "el subárbol de 66, menos 75 198 105, más 83 84", con el mismo problema
  de espacio para lo opcional.

Tangle Forest (310 a 313) queda afuera de las dos mientras no haya lugar.

# Hitos

**1. El 66 entra.** (Hecho: `testing/mundo-1-el-66-entra.md`.) El quinto reparto al final de `LAYOUTS` y el fondo de más
de 32 KB en dos flujos de LZ2. El 66 en `release`; el fork del 64 se borra y
el fin de la demo pasa a un fork del 66 que corte al pisar Sorbe (ev10), así
el mundo se puede caminar y pelear. Las demás entradas del 66 no hacen nada
—sus páginas no compilan porque el destino no está—, como pasó con el 64
antes. Cartucho 75,6%, banco 0 sin cambios. Se prueba: una golden del 66
recién llegado, `celdas_mal_dibujadas` en cero, una pelea en el 66 que vuelve
al mapa (es la que pisaría la mitad alta de la grilla si el LZ2 no se parte),
y `test_carga_descomprimida` con un fondo de dos flujos.

**2. Sorbe y la curación.** (Hecho: `testing/mundo-2-sorbe.md`.) El reparto con la capa de encima de 256 (el 69), el
`Comment` salteado, y `ChangeEncounterSteps` hecho. 69 y 76 a 84 en
`release`; el fin de la demo pasa a la entrada de Tasgarde (66 ev13), que es
adonde lleva el viaje de Dalia. 81,4%, banco 0 192 menos lo de
`ChangeEncounterSteps`.

**3. El espacio.** (Hecho: `testing/mundo-3-el-espacio.md`; al camino principal le quedan diez bancos, y entran él y una o dos de las zonas opcionales, no las tres.) El acomodo con first-fit decreasing en `bancos.py`, con la
ROM armando igual y las goldens sin moverse; la tabla de alturas del `.msu` por
paquete; el bloque de textos de a 4 bytes; y `medir.py` —o lo que lo
reemplace— diciendo bancos libres y no un porcentaje. Puede ir en paralelo con
el 1 y el 2; **tiene que estar antes del 4**, que deja tres bancos.

**4. Tasgarde, Eisen y el puente: el capítulo.** (Hecho:
`testing/mundo-4-el-capitulo.md`. **La demo termina en la entrada de Tangle
Forest (66 ev19), no en el 18**: el túnel a Paradise está del otro lado del
bosque, y del puente al túnel no se llega caminando por el mundo —se cruza por
310, 311, 313 y 312, que sale al oeste—. O sea que Tangle Forest no es
opcional: es el hito siguiente del camino principal.) El alternar switches en el
compilador, las dos transiciones instantáneas, y el cartel y el contador
según lo que conteste taro (preguntas 3 y 4). 74, 85 a 102, 259 y 255; el fin
de la demo al fork del 66 ev18, "Continue onward". La regla de mapas según la
pregunta 5.

**5. Lo opcional**, detrás del 3: Yun Town (el cronómetro por alcance, y el
reparto del 2 para su capa de encima), Drust Camp (comparar contra más de
32767), y Tangle Forest (el `EraseEvent`, las condiciones de cronómetro, el
cancelar de un `ShowChoice` para el 348) cuando haya lugar: con el acomodo
solo todavía no entra. Las tablas de ítems al banco 1 van acá, que es donde
el banco 0 se acaba.

Lo que hay que repartir si van en paralelo: el reparto de VRAM nuevo va
**último** en `LAYOUTS` y los dos (el del 1 y el del 2) lo tocan, así que
conviene el mismo agente o uno detrás del otro; un opcode para
`ChangeEncounterSteps` en `tools/snes/protocol/events.toml`, el del 2.

# Lo que taro contestó (2026-09-27)

1. **La demo termina donde llegue cada hito**, con el final del capítulo (66
   ev18) como meta.
2. **Lo opcional va detrás del hito de espacio**, Tangle último.
3. **El cartel "Meanwhile in Lashe City"**: un fork del 81 con un
   `ShowMessage`, como el de la carrera.
4. **El contador de Fortitude**: deuda, en
   `todo/el-contador-de-fortitude-no-se-ve.md`.
5. **La regla de mapas**: le da igual cualquiera de las dos; queda por id,
   como se decidió en la carrera.
6. **Los fondos de batalla**: todos van al `.msu`, estén o no en el
   cartucho, y las peleas cuyo fondo no entra en la ROM comparten uno de los
   que ya hay, en baja calidad, en vez de salir en negro. Es su propia tarea:
   `todo/todos-los-fondos-en-el-msu-1.md`.
7. **El cartucho**: exprimir primero. taro: "a este ritmo, ni 6 MB ni 8 MB
   nos van a permitir cubrir todo el juego".

# Preguntas para taro

1. **Dónde termina la demo**: (a) al final del capítulo, en el `ShowChoice` del
   66 ev18 hacia el túnel de Paradise; (b) antes, cuando entra cada hito (en
   Sorbe, en Tasgarde), y moviéndolo. **Recomendado: (b) mientras se
   trabaja, con (a) como meta**: cada hito se juega entero.
2. **Lo opcional** (Yun Town, Drust Camp, Tangle Forest): ¿va en la demo? No
   entra ninguno sin el hito 3, y Tangle ni con él. **Recomendado: el camino
   principal primero, lo opcional detrás del espacio, Tangle último.**
3. **El cartel "Meanwhile in Lashe City"** del 81, que es el cambio de
   protagonista a Dalia: (a) un fork que lo cambie por un `ShowMessage` con el
   mismo texto, como el de la carrera; (b) un segundo cartel por ROM
   (`wishlist/sistema-de-imagenes.md`); (c) deuda. **Recomendado: (a).**
4. **El contador de Fortitude** del minijuego del 95: sin él se juega sin ver
   cuánto aguanta Eisen. (a) mostrar la variable 48 con los dígitos del
   cronómetro, que ya están en la ROM; (b) un mensaje cuando baja; (c) deuda.
   **Recomendado: (a)**, pero sólo si el minijuego se puede perder —hay que
   mirarlo antes—; si no, (c).
5. **La regla de mapas**: por id (`MENOR_A = 105` y la exclusión creciendo) o
   por subárbol ("el subárbol del 66"). **Recomendado: por id, como se
   decidió en la carrera, con `MENOR_A = 105` recién cuando entre X = 105
   entero (después del hito 3)**; mientras tanto, los agregados del camino
   principal.
6. **Los fondos de batalla del mundo**: las peleas del 66 salen sin fondo
   porque el cartucho lleva tres, y el mundo usa otros cinco terrenos (plains5,
   desert1, forest5, forest6, mroad2). Cada uno son 16 KB de respaldo en la ROM
   y 32 KB en el `.msu`. ¿Entran en este plan o son deuda? **Recomendado:
   deuda hasta después del hito 3.**
7. **El cartucho**: `m3` ya está en el 88,5% que la decisión de 4 MB dice que
   dispara la revisión. ¿Se abre ahora (ExHiROM, SA-1, S-DD1:
   `wishlist/chips-sa-1-y-s-dd1.md`) o se sigue exprimiendo? **Recomendado:
   exprimir primero** —el acomodo da ocho bancos sin tocar la ROM—, y abrirla
   con el número del capítulo siguiente delante.
