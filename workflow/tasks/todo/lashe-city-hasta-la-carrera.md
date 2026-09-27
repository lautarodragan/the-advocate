---
name: "Lashe City con auto, hasta la carrera"
description: "Plan: de la cinemática del director y Kersh hasta el Teleport al 49, exclusive"
type: feature
---

# Qué

Llevar `release` desde donde termina hoy —la cinemática del director y Kersh,
mapa 34, que teletransporta al 36— hasta el `Teleport [49, 1, 26]` del evento 3
del mapa 36, **sin entrar a la carrera**. Lo pidió taro el 2026-09-25: "los
mapas de Lashe City en su versión con auto, lo del mafia boss, el camino
opcional de obtener al droide como parte de la party si fuiste por el hover
tram… y eventualmente la carrera para escapar. Me gustaría encarar todo hasta la
carrera, exclusive."

Esto es el plan; lo que se ejecuta son las tareas de cada hito:

    0. elegir-una-opcion-en-el-recorrido.md   el arnés elige la opción N
    1. lashe-1-los-cuatro-sectores-con-auto.md  37, 38, 47, 48 (+39, 56) y el 36
    2. lashe-2-boss-wick-y-los-vidcasts.md     40 a 45: el favor y el tobillo
    3. lashe-3-la-planta-y-el-droide.md        57, 59 a 63, 164: AG7 entra al grupo
    4. lashe-4-ag7-en-la-pelea.md              sus habilidades, y las de los enemigos
    5. lashe-5-la-cola-del-auto.md             el cierre del 36 por las tres ramas

Todo lo medido acá es del 2026-09-25 sobre `d118bc8`, con cartuchos armados
aparte en el scratchpad —`release` no se tocó—. Los scripts que lo midieron
quedaron en `/extras/scratch/lashe-plan/`: `medir.py` es la cuenta de qué
comando frena cada página (compila con el mismo andamiaje que `main()` del
conversor, y reemplaza al culpable por un comando ignorable hasta juntar
todos), `conv.py` es el conversor con un parche en memoria para seguir de largo
en el error del mapa 37, `testmain.py` arma un `test-main` con mapas de más,
`segs.py` y `banco1.py` leen el `.dbg` y el `.sym`, y `copias.py` mide cuánto
de un mapa es copia de otro.

# El subárbol de Lashe City

**"Lashe City con auto" son mapas distintos**, cada uno con su id —no páginas
de los mismos mapas según switches—, y casi todos copian el dibujo de un mapa
que ya está en `release`. Lo que dice el árbol (`data/maps.json`), con lo que
se midió de cada copia (`copias.py`: el mejor desplazamiento de la grilla de
tiles del mapa nuevo sobre el viejo, y cuántas celdas de la capa de abajo dan
iguales):

    id   nombre                        padre  release  qué es
    15   Lashe City                     0      -       carpeta: nadie teletransporta
     9   Lashe City 33,36               15     sí
    13     Hover-Tram                   9      sí
    11     Lazer Teeth HQ               9      sí      forkeado
     8   Lashe City - 34,35             15     sí
    12     Trash Dump 004               8      sí      el HQ de los Neon Vipers
     7   Talan's Pad                    15     sí
    10   Lashe City Interiors           15     sí      2 páginas saltan al 38
    14   NV Get Talan to Work           15     sí
    16   Running To Work Scene          15     sí
    17   Delcentric Factory             15     sí
    18     Auditorium                   17     sí      forkeado
    19     Talan and the Director       17     sí
    96       Backup                     19     -       inalcanzable
    20   Sector 30 Back Alleys          15     sí
    24     Sector30 Monsters            20     -       área de encuentros
    22   The Rat Tracks                 15     -       carpeta
    21     Rat Tracks B1                22     sí      (25: área)
    23       Beggar's Hideout           21     sí
    26     Rat Tracks B2                22     sí      (27: área)
    28   Sector 27 Back Alleys          15     sí      (31: área)
    29     Sector 27 Item Shop          28     sí
    30     Sector 27 Workshop           28     sí
    32   Sector 27 Warehouse            15     sí      forkeado (35: área)
    33     Escape From 27 Scene         32     sí
    34   AfterGettingCarCutscene        15     sí      director y Kersh
    36     LasheCityVehicle             34     sí      el "menú" del auto
    97     Backup                       34     -       inalcanzable
    37   Sector 35 With Car             15     NUEVO   copia del 8: sus filas 25-74, 67%
    39     Talan's Pad With Car         37     NUEVO   copia exacta del 7, eventos incluidos
    40     Boss Wick's Den              37     NUEVO   el mafia boss
    41     ScreenToneAdjuster           37     NUEVO   negro, como el 36
    42     The Vidcasts (Factory)       37     NUEVO
    43       Vidcasts (Office)          42     NUEVO   los tiles del 34, iguales
    44       Talan Stats                42     NUEVO   negro, como el 36
    45       Security Footage           42     NUEVO   el 19 entero: tiles y eventos
    46         Security Footage 2       45     -       inalcanzable
    98         Backup                   45     -       inalcanzable
    38   Sector 34 With Car             15     NUEVO   filas 33-74 = filas 0-41 del 8 (100%);
                                                        arriba, el HQ de los Vipers (53% del 12)
    47   Sector 33 With Car             15     NUEVO   copia del 9: sus filas 21-74, 53%
    56     Sector 33 Discount Items     47     NUEVO   65% del 29, la otra tienda
    48   Sector 32 With Car             15     NUEVO   nuevo: 25% del 9 como mucho
    57     Stash's Emporium             48     NUEVO
    59     Outside Recycling Plant      48     NUEVO   (180: área)
    60       Floor 1                    59     NUEVO   (181: área)
    61       Floor 0                    59     NUEVO   (182: área)
    62       Floor 2                    59     NUEVO   (183: área)
    63     Tunnel Into Lashe City       48     NUEVO
    55   Escape From Lashe City         15     -       carpeta de la carrera: afuera
    49..54 la carrera                   55     -       afuera
    64   Leaving Lashe City Scene       15     -       afuera: se llega desde el 53, después de la carrera
    83   Dalia at the Factory           15     -       afuera: otro capítulo, se llega desde el 82
    84     OutsideFactory               83     -       ídem

Y uno que no cuelga de Lashe City pero entra: **el 164, `AG7-17 Tutorial`**
(bajo `Tutorials`), porque la página que mete al droide en el grupo salta ahí y
vuelve con `RecallToLocation`. Es negro como el 36.

Los sectores con auto heredan la música (`music_type` 0, y el padre es el 15
que no la cambia): suena lo que puso el 36, `golden_axe-turtlevillage2`, que ya
está en `release`.

# El recorrido del jugador

Hoy lo jugable termina **en el mapa 36**: la página 1 del evento 3 —la de la
primera vez, switch 148, que prende el 34— tiene la elección de los cuatro
sectores y no compila porque los cuatro destinos (37, 38, 47, 48) no están en
el cartucho. Compila con los cuatro o con ninguno. El jugador queda en negro con
el auto.

## El eje: la elección del 36

`LasheCityVehicle` es una pantalla negra con el auto. La página 1 (switch 148)
pone el tema del auto, dice qué hay que hacer según el compañero y abre
`Sector 32 / 33 / 34 / 35`; cada opción salta al sector —la celda depende del
auto, switch 130 rojo o 131 azul— y **sigue corriendo allá**: saca a
`DummyHero` (10) y mete a Talan (14), al compañero —Saldra (17) si el 56, Arden
(15) si el 54— y a AG7-17 (18) si el 150.

En cada sector, subirse al auto (eventos 1 y 2 de 37, 38, 47 y 48) apaga el
148, prende el **149**, saca a todos, deja a `DummyHero` y vuelve al 36. Desde
ahí manda la **página 2** (switch 149): la misma elección, más la cola del
auto, que es el final de este plan (ver "El cierre").

## Lo que tiene que pasar antes de la carrera, por rama

El compañero lo decidió el jugador mucho antes: 54 (`NVAlly`, Arden, en la
escena de los Neon Vipers del mapa 12), 56 (`LTAlly`, Saldra, en el 9) o
ninguno. La página 2 del 36 sólo ofrece irse cuando se cumple:

    Arden   161 DoneWithVidcast  +  169 Arden's Whisper   (HQ de los Vipers, en el 38)
    Saldra  161                  +  181 SawAgencyIn33      (Sector 33, el 47)
    solo    161                  +  150 AG7-17 In Party    (el droide, desde el 48)

**Sin compañero el droide no es opcional**: sin el 150 la rama "solo" no llega
nunca a la cola del auto. Con Saldra es opcional, y con Arden no se puede: la
puerta de Stash dice "Looks like they're closed" (página 5 del evento 9 del 48,
switch 54).

## Tramo por tramo

**Sector 35 (37) — el tramo principal, obligatorio en las tres ramas.**

    37  la puerta de Talan (evento 1) ................... -> 39
    39  la computadora (evento 5) prende 151 ........... -> 37
    37  la puerta del vecino (evento 13, pide 151): golpea, prende 155;
        la página 3 (155, automática) funde a negro .... -> 41
    41  ScreenToneAdjuster: tinte y paso ................. -> 40
    40  Boss Wick, escena 1 (evento 7, página 1, automática):
        el "fat man" y sus chicas; ChangeScreenTransitions a zoom;
        prende 156 ....................................... -> 42
    42  The Vidcasts (evento 2, página 1): transición a mosaico -> 43
    43  la oficina (los tiles del 34) .................... -> 44
    44  Talan Stats: la voz de Zed ....................... -> 45
    45  Security Footage: la escena del director (el 19)
        otra vez, con el "REC" parpadeando (ShowPicture 'ABLrec');
        prende 160 ....................................... -> 40
    40  página 3 (160): Boss Wick sobre el video ........... -> 43
    43  página 2 (160) ...................................... -> 42
    42  página 2 (160): prende 161 DoneWithVidcast ......... -> 40
    40  página 4 (161): **el favor**. "Accept, and owe him a Favor" /
        "Refuse to be healed" (y una segunda confirmación)
          acepta:  164 WicksSurgeonDoesOper -> página 5: el cirujano,
                   ChangeHeroTitle de Talan a 'Fugitive', 267 AnkleAllBetter -> 41
          rechaza: 162 RefusedWicksOffer ........................... -> 41
    41  páginas 2/3 (162/164): prende 163 ................... -> 37
    37  evento 17 (163 + compañero): el comentario del compañero al salir

**El mafia boss no es una pelea**: es Boss Wick, un NPC con un evento. Te cura
el tobillo si aceptás deberle un favor. Lo que deja, y dónde se usa fuera de
este alcance:

    162 RefusedWicksOffer     el 66 (Lashe Area, mundo)
    164 WicksSurgeonDoesOper  el 64 (después de la carrera), el 69 (Sorbe Village),
                              el 81 (la casa del Dr. Vago)
    165 BumTalkKnowsFavor     el Bum del 37 (página 4, pide 164)
    267 AnkleAllBetter        el 69; si no lo operó Wick, lo prende el Dr. Vago en el 81
    título de Talan           'Fugitive', con ChangeHeroTitle (hoy aceptado sin hacer)

Todo eso son switches y viajan en la partida. El título la ROM lo acepta sin
hacer, y no se pierde nada visible: no hay pantalla que lo muestre.

**Sector 34 (38) — la rama de Arden.** El 38 es la calle del 8 más, arriba, una
versión con auto del HQ de los Vipers, al que se llega por el caño: eventos 20 y
21 (switch 54, contacto) prenden 167 y saltan a (2,10) del mismo 38; el 25
prende 168 y después 169; el 26 vuelve a (73,65). Los eventos 17 y 18 llevan a
Lashe City Interiors (10), que ya está.

**Sector 33 (47) — la rama de Saldra.** El evento 15 (contacto en (32,28))
tiene una rama por compañero: guardias de la Agency en el sector de los Lazer
Teeth, un `PanScreen`, y prende 181. Anda en las tres ramas; sólo Saldra lo
necesita. El 56 es una tienda (`OpenShop`).

**Sector 32 (48) — el droide.** Lo que taro llama "si fuiste por el hover
tram":

    48  el cartel de Stash (evento 7): con la Business Card (ítem 91, la que da
        Stash en el Hover-Tram, mapa 13) prende 183
    48  la puerta (evento 9): sin condición golpea y entra; con Arden, cerrada -> 57
    57  Stash (evento 2): la escena del "bald man" que te robó en el tram.
        Página 1 si robó los creds (72), 2 el ídolo (71), 3 nada (186) —los
        tres los prende el Hover-Tram—, 4 si **sobornaste al guardia** (29, el
        mapa 8). Te manda a la planta de reciclaje .... -> 59
    59  Outside Recycling Plant (encuentros, tienda, posada) -> 60
    60  Floor 1: pisos que se rompen. Cada baldosa (eventos 5 a 18, contacto)
        carga el mapa 61 en una variable y la celda del héroe más cinco filas
        en otras dos, y hace RecallToLocation: **se cae al piso de abajo** -> 61
    62  Floor 2: lo mismo (eventos 2 a 14)
    61  Floor 0: el Motivator Chip (ítem 126); el evento 13 (pide el ítem)
        prende 205 ........................................ -> 63
    63  Tunnel Into Lashe City ........................... -> 48
    48  la puerta, ahora por la página 2 (ítem 126) ......... -> 57
    57  página 5 (205 + ítem 126): prende 150, ChangePartyMembers +18, saca el
        chip, vuelve a (3,39) del 48, MemorizeLocation, y salta al tutorial -> 164
    164 el tutorial del droide (MemorizeBGM, textos, PlayMemorizedBGM,
        RecallToLocation) ................................... -> 48

Los datos contestan una duda de la frase de taro: **la escena de Stash también
se abre por el soborno** (página 4, switch 29), no sólo por el tram. Ver las
preguntas.

## El cierre

La página 2 del 36, con 238 apagado y la condición de la rama cumplida: el
compañero nota el auto de la Agency, prende **238**, y "Should we stay in Lashe
City or get out?". "Stay" sigue en la ciudad (y la próxima vez que vuelva al
auto se lo vuelve a preguntar, rama de arriba de la página). "We've got to get
out of here" prende **182** y hace el `Teleport [49, 1, 26]`: el límite.

# Qué falta para que corra

## Páginas que no compilan

Con un cartucho `release` + los 19 mapas de arriba (el 38 incluido para contar
páginas, aunque no convierte) y sin el 49: **336 de 397 páginas disparables
compilan**. Por mapa: 37, 38, 39, 41, 43, 44, 47, 48, 56, 59, 61 y 63 compilan
enteras. Lo que frena al resto, contado como lo cuenta `eventos.py` —páginas
donde aparece / páginas que destraba él solo—:

    RecallToLocation          55 / 54   los pisos del 60 (28) y del 62 (26), y el 164
    ChangeScreenTransitions    4 /  4   40 páginas 1 y 4 (las dos escenas de Wick),
                                        42 página 1, 45 página 1
    Teleport -> 49             1 /  1   36 página 2: el límite
    MemorizeLocation           1 /  1   57 página 5: la que mete al droide
    MemorizeBGM                1 /  0   164 (junto con los otros dos)
    PlayMemorizedBGM           1 /  0   164

Sobre **el juego entero** (5324 de 5472 compilan) `RecallToLocation` es lo que
más frena —60 páginas, 55 él solo— y `ChangeScreenTransitions` va tercero —15,
14 solo—, así que los dos van en la dirección en que se viene priorizando.

**Compilar no es andar**, y lo que compila pero no hace lo que el original:

- **`ChangeHeroTitle`** (40, el cirujano): aceptado sin hacer, y no se ve
  porque el port no muestra el título en ninguna pantalla.
- **`ShowPicture 'ABLrec'`** (45, un paralelo que hace parpadear "REC" sobre el
  video): la ROM lleva un cartel solo y ya es el de "One year previously", así
  que éste queda aceptado sin hacer.
- **El evento común 37, `UpdateAG7 Skills`**: es **paralelo con el switch 150**
  y es el que le da a AG7 sus habilidades según las piezas que tiene puestas
  (`ChangeSkills` por cada arma 268 en adelante). La ROM no corre eventos
  comunes paralelos ni automáticos —`COMUNES` sólo sirve a `CallEvent`—, así
  que AG7 entraría sin ninguna habilidad.
- **Los enemigos de la planta usan una habilidad**: `ShortCircuit` (188), en 5
  de las 7 tropas (108 a 114: Scrapped Droid, Trash Hauler, Tangle Wire,
  Junkbot). La pelea sólo hace la acción básica de atacar
  (`acciones_de_los_enemigos`, `CreateEnemyActions` con `kind` 0).

## Límites de recursos

**VRAM: el 38 no entra, y es el único.** Gasta 476 tiles de fondo y 347 de
sprite (18 ranuras, 8 paletas). Los tres repartos con ventana dan 448/448,
480/256 y 384/512: le faltan **28 tiles de fondo** en el primero o **91 de
sprite** en el segundo. En bytes entraría —476×64 + 347×32 son 41,5 KB de los
42 que quedan—; lo que no deja es la alineación: el tilemap de BG1 está clavado
en `$5800` (`VRAM_MAP`) en los cuatro repartos y corta el fondo en 448. Los
otros 18 convierten. (Resuelto el 2026-09-25 con la opción (d) de la pregunta 2:
ver ahí.)

**El conversor se planta en el 37** antes de llegar a la VRAM: "el evento 11 se
hornea en el mapa y además se dibujaba con una paleta ajena". Es `PawnDoorTop`,
un tile del ChipSet, y la regla de `eventos_horneables` no mira la paleta. El
comentario de ahí dice "ninguno de los mapas del juego lo pide hoy; si aparece,
hay que sacarlo de la regla". Apareció.

**CGRAM**: el 37 dibuja 5 gráficos con paleta ajena —las dos puertas de tile y
tres de la gente que aparece con el 161— y el 38, 3. Es lo mismo que ya pasa en
`release` (el 8 tiene 6); no traba.

**ROM: el cartucho cruza el umbral de la decisión de 4 MB.** Del `.dbg`, bancos
2 en adelante:

    release hoy                        2,82 MB, último banco $61
    release + los 18 que convierten    3,34 MB (+538 KB), último $74; el techo es $7D
    test-main hoy                      3,45 MB, último $77
    test-main + 37 39 47 48 56         último $7B
    test-main + los 18                 NO ENTRA: el asignador pide $7E

`decisiones/el-cartucho-se-queda-en-4-mb.md` dice "se revisa al llegar al 85-90%
del cartucho": con los 18 (sin el 38) `release` ronda el 86% contando lo usado,
y la carrera viene después. Y **`test-main` no entra**, que choca con la regla
de `cartuchos.py` de que "cada mapa que se suma al proyecto se suma a todos los
cartuchos". Ver las preguntas.

Lo que las copias podrían abaratar: el asignador no comparte datos entre mapas
—el 39 es el 7 celda por celda y sus tiles salen en otra dirección del
cartucho, con otros bytes—. Candidatos: 39≡7, 43≡34 y 45≡19 en tiles; 41, 44 y
164 son el negro del 36; 37, 38 y 47 comparten con el 8 y el 9 entre 88 y 216 de
sus celdas distintas. En la VRAM no se gana nada —cada mapa sube lo suyo—; en
ROM sí, y hay que medirlo.

**Banco 0**: con los 18, `TABLAS` crece 72 bytes (4 por mapa); quedan unos 2,2
KB en `release` y 1,9 en `test-main`. **Banco 1**: el último símbolo deja ~8,7 KB
en `release` con los 18 (~11 hoy) y ~5,5 en `test-main`; crecen las páginas de
tropa (108 a 114). **BSS**: 7700 de 7808, sin cambio; cualquier estado nuevo va a
la RAM lejana.

**ARAM**: el banco compartido no cambia (57.309 de 64.512 bytes). Los tres temas
nuevos **no aportan muestras** y suenan con las de otros: `Kfmus5` (la guarida
de Wick) con el 8% de sus notas, `tsmedit` (el cirujano) con el 53%, y
`fm2bar_gs` (Stash) con el 83%. Ninguno tenía pista de MSU-1; desde el
2026-09-26 todo tema del cartucho tiene la suya (`pista_msu` en
`tools/audio/snes_music.py`).
*Desde el 2026-09-26 esto cambió*: con el presupuesto por paquete todos los
temas aportan todas sus muestras, así que los tres entrarían enteros; lo que
cuesta un mapa nuevo es la tasa de las muestras que comparte con los paquetes
más llenos, y lo dice el informe del conversor ("la limita …"). Hay que
volver a medirlo al meter los 18.

**Páginas paralelas**: uno por mapa como mucho (37, 45, 47, 48, 59); lejos de
`PARALELO_MAX`.

## La elección del 36

Compila con sus cuatro destinos, así que el hito que mete los sectores los mete
a los cuatro: **37, 38, 47 y 48 van juntos**, y el 38 tiene que estar resuelto
antes. Las puertas de adentro (39, 40…, 56, 57) pueden quedar muertas hasta su
hito: una página con un `Teleport` a un mapa ausente no compila y el evento no
hace nada, que es lo de siempre.

Y la página 2 tiene el mismo problema con el 49: **sin resolver el límite, la
segunda visita al 36 deja al jugador trabado**. Eso va en el hito 1, no al
final.

## Peleas nuevas

Sólo encuentros al azar, en la planta (áreas 180 a 183, tropas 108 a 114). Ningún
`EnemyEncounter` en estos mapas y ningún jefe. Lo que falta: la habilidad de los
enemigos (arriba), y lo de AG7.

## El droide en el grupo

El actor 18, `AG7-17`: CharSet `AG717` 4 (ya está en el cartucho: es líder
posible y su cara ya sale en el menú), nivel 6, arma 269 (`ArmCannon-!R`) y
armadura 282. Lo que pide:

- **las páginas** de la planta y del 57: `RecallToLocation`, `MemorizeLocation`,
  `MemorizeBGM`/`PlayMemorizedBGM`, y el 164 en el cartucho;
- **sus habilidades**: el evento común 37 (arriba). Son 17 (236 a 253); con el
  filtro de hoy (`habilidad_usable_en_batalla`) cinco quedan afuera por ser de a
  muchos (236, 240, 244, 245, 251) y `RemoveStatus` (253) por ser de todo el
  grupo; tres tocan estados, que no existen;
- **el costo en SP de las armas**: el tutorial lo dice ("attacking with a
  weapon drains a small amount of the droid's SP") y en RM2k2000 es el
  `sp_cost` del ítem (ArmCannon 1, ArmLauncher 2, PortableNuke 5). La pelea no
  lo cobra.

# Hitos

Cada uno es jugable y se verifica por separado. El orden es el de la lista.

    0  el arnés elige la opción N          chico, en paralelo con el 1
    1  los cuatro sectores con auto        bloquea a todos los demás
    2  Boss Wick y los vidcasts            en paralelo con el 3, después del 1
    3  la planta y el droide               en paralelo con el 2, después del 1
    4  AG7 en la pelea                     la parte de enemigos, en cualquier momento;
                                           la de AG7, después del 3
    5  la cola del auto                    al final: junta los tres caminos

**Lo que hay que repartir al lanzarlos en paralelo** (ver "Sub-agentes" en
`AGENTS.md`): los números de opcode en `tools/protocol/events.toml` —el 2 pide
uno (transición), el 3 entre uno y cuatro (lugar recordado, tema recordado)—;
las direcciones de RAM lejana —el tema recordado (3),
la transición elegida (2), el intérprete de eventos comunes (4)—; y la lista de
`_DE_RELEASE` en `cartuchos.py`, que tocan todos y conviene mergear mirando.

Los números concretos no se escriben acá: se eligen al lanzar, mirando la
declaración de ese momento.

# Riesgos y preguntas para taro

**Lo que taro ya contestó (2026-09-25):**

* **(2026-09-26)** El cierre del 36 ("get out"): **un "fin de demo" con un
  mensaje de texto**, bien simple, en vez del `Teleport` al 49.
* **(2026-09-26)** Las transiciones de zoom: **van como fundido**.
* **(2026-09-26)** AG7 **no puede perder habilidades**, y las armas cobran SP
  si en el original lo hacen: **fiel al original**.
* **(2026-09-26)** El tutorial del droide (164): **se conserva**.
* **(2026-09-26)** El 38 ya entra en la VRAM (`done/el-tilemap-del-fondo-lo-elige-el-reparto.md`): no hace falta partirlo.
* **(2026-09-26)** El cartel "REC" del 45: **queda como deuda** por ahora.
* **(2026-09-26)** El soborno del guardia (switch 29) **se puede jugar**: el
  `DetourOfficer` (evento 19 del mapa 8, (62,32)) ofrece el soborno en su
  página 2 (switches 24 y 28: el 24 lo prende el evento 4 del mapa 7 al
  empezar, el 28 lo prende la primera charla con el oficial) y pide **500
  créditos** (`ConditionalBranch` de oro >= 500). Se juntan vendiendo el
  Idol al Pawn Guy (evento 24 del mapa 10): 600, 700 o 1000 según cuánto se
  regatee (si se regatea una vez más, no compra), más los 100 que da el
  evento 4 del mapa 7. Es el camino alternativo al Hover Tram (donde el ladrón
  roba todo: `ChangeGold -9999` en el mapa 13). Ojo: el Idol también abre el
  mapa 14 (página 2 de la puerta del HQ, con el switch 53).
* Pendiente: los mapas 64, 83 y 84. Quedaron afuera porque el 64 (`Leaving
  Lashe City Scene`) se alcanza desde el 53, **después de la carrera**, y el 83
  y el 84 (`Dalia at the Factory`, `OutsideFactory`) son **de otro capítulo**,
  a los que se llega desde el 82. taro no recordaba el porqué; se lo expliqué.

* **Primero el espacio, después los mapas.** El orden: el tinte (si tiene
  sentido arreglarlo), juntar `release` y `test-main`, y en paralelo mirar por
  qué la música pesa 789 KB y un piloto de fondos de batalla leídos del MSU-1.
  Este plan se encara cuando terminen esas mejoras, no antes.
* **Partir mapas, mejor no** (pregunta 2): da ventajas, pero obliga a analizar
  estáticamente los eventos del mapa y todas sus ubicaciones y cambios, y las
  fallas no serían obvias. Para el 38 buscar primero otra salida (menos tiles,
  cargar tiles al caminar) y partir sólo si no hay otra.

1. **El límite del 49.** ¿Qué hace la ROM cuando el jugador elige "We've got to
   get out of here"? Las salidas: (a) un fork del 36 que cambie ese `Teleport`
   por un cartel de fin de demo o por la vuelta al título, y que se borre el día
   que entre la carrera; (b) meter el 49 como está —el auto camina libre, que es
   lo que taro ya vio con la receta vieja—; (c) que el conversor compile todo
   `Teleport` a un mapa ausente como fin de demo, que cambia qué hacen muchas
   páginas del juego. **Recomendado: (a).**
2. **El 38 no entra en la VRAM.** (a) **partirlo**: el HQ de los Vipers de
   arriba es una isla aparte, a la que sólo se llega por los `Teleport` de los
   eventos 20, 21 y 26, así que va a un mapa propio y la calle se queda con el
   id 38. Estimado por celdas distintas: la calle ~71% del total y el HQ ~44%,
   los dos lejos del tope. Pero **`fork.py` no deja agregar ids** ("un fork
   reemplaza un mapa del juego, no agrega uno"): o se cambia esa regla, o se
   usa un id que existe y nadie alcanza (46, 96, 97, 98), que es trampa. (b)
   podar 28 tiles de fondo del 38 en un fork, que es artístico. (c) bajar 91 de
   sprite. (d) mover el tilemap de BG1 por reparto, que es tocar el motor.
   **Recomendado: (a) con la regla de `fork.py` cambiada a propósito.**
   **(d) está hecho (2026-09-25)**: un cuarto reparto baja el tilemap de BG1 a
   $1800 y da 480 de fondo con 384 de sprite; el 38 convierte con 4 tiles de
   fondo y 37 de sprite de margen, sin cambiarle el reparto a ningún mapa. Ver
   `done/el-tilemap-del-fondo-lo-elige-el-reparto.md`.
3. **El cartucho.** `release` con esto ronda el 86% —el umbral de revisar la
   decisión de 4 MB— y la carrera viene después. Y `test-main` no entra con los
   18 mapas. ¿`test-main` deja de llevar todos los mapas (y las pruebas de la
   zona nueva corren sobre `release`, como los recorridos), se arma un tercer
   cartucho de pruebas, o primero se hace que el asignador comparta los datos de
   las copias (39≡7, 43≡34, 45≡19) y se mide cuánto rinde?
4. **Las transiciones.** El 40 pide **zoom** (tipo 16) y el 42 **mosaico** (17).
   El mosaico lo tiene la consola (`MOSAIC`); el zoom en modo 3 no. ¿Zoom como
   fundido, declarado como deuda, y mosaico de verdad?
5. **El "REC" del 45.** ¿Segundo cartel por ROM, o deuda? Parpadea con un
   paralelo, así que hornearlo como el Hover Tram no sirve tal cual.
6. **AG7 en la pelea.** Con el filtro de hoy, 6 de sus 17 habilidades quedan
   afuera (las de a muchos y la de todo el grupo) y los estados no existen.
   ¿Alcanza con declararlo, o este hito hace el alcance de a muchos? Y el costo
   de SP de las armas: ¿se cobra?
7. **"Si fuiste por el hover tram"**: los datos dicen que la escena de Stash
   también se abre por el soborno al guardia (switch 29), que con Arden la
   puerta está cerrada, y que sin compañero el droide es obligatorio para llegar
   a la carrera. ¿Es lo que esperaba?
8. **El 83 y el 84** (Dalia at the Factory) cuelgan de Lashe City pero se llega
   desde el 82, que es de otro capítulo. **El 64** es después de la carrera.
   ¿Los dos afuera?
9. **El tutorial del droide** (164). Se puede conservar —pide `MemorizeLocation`
   y `RecallToLocation`, que la planta pide igual— o saltearlo con un fork del
   57. Recomendado conservarlo.

# Lo que no se midió

- **Los cuadros perdidos** caminando por el 37 (23 eventos) y el 38 (47): el 8,
  que es de su tamaño, era de los más cargados; conviene medirlos como el 11
  (`done/el-mapa-11-se-rediseno.md`) antes de dar por bueno el hito 1.
- **Cuánto pesa el 38** en ROM: no convierte.

El título del héroe no es un riesgo: el comentario de `CHANGE_HERO_TITLE` en
`eventos.py` dice que el port no lo muestra en ninguna parte, así que el
'Fugitive' del cirujano no se pierde de la pantalla.
