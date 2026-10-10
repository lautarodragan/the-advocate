---
name: "Mundo 8: Distant Paradise por dentro"
description: "El primer día en Paradise en release —el Consejo y el recuerdo de Pierson, las casas, la noche, los sueños, el día de las Pruebas— hasta la salida a la granja (127), que no entra en la VRAM y es el nuevo fin de la demo"
type: feature
assignee: taro
---

De taro, el 2026-10-02: seguir con ABL en paralelo, "agregar más mapas".
Hoy la demo termina en la llegada a Distant Paradise: el fork del 108
(`parches/manual/mapas/Map0108.json`) cambia el `Teleport` al Consejo (110)
por el cartel del fin. Esto es lo que sigue: el capítulo de Paradise por
dentro, medido primero —qué mapas, qué pesa cada uno, qué no entra y por
qué— y metido después, hasta el próximo corte natural.

Base: ABL `a454257`, herramientas `4b8b0e10` (`abl.sfc` `8c9e670f…`, tanda
993).

# El corte: el primer día entero

Siguiendo las páginas desde la llegada (108 ev5) y los switches que prende
cada escena:

    108  la llegada: Isabella lleva a Talan al Consejo
    110  el Consejo: Pierson (ev11) cuenta la historia, un recuerdo en tres
         mapas —175 la montaña, 176 el mirador, 177 el valle— que vuelve al
         110 (484) a explicar las Pruebas (350, 349)
    108  el pueblo, al atardecer (361): las casas se recorren —112 a 120—
    110  Pierson (ev10, con 361 y 350): "Yes" lleva a la casa de Talan (362)
    114  la noche: la lluvia y, si vino AG7 (357), su recuerdo bajo la
         lluvia (el común 32, al 125); sale al pueblo de noche
    108  la chica que llora (ev34): Talan la sigue al mirador
    109  el mirador: Emily, y el salto al sueño (ev6, con 363)
    122  el sueño -> 123 -> 114 (367): la mañana -> 124, el segundo sueño
    114  Talan se despierta (372, 374); al salir, Pierson le perdona las
         Pruebas (ev7: 376)
    108  el día: el mirador de día (126, Emily: 380) y su casa (113 ev6: 381;
         al salir, ev7 la deja pensando y lleva a Talan a su casa)
    114  hora de la celebración (ev2 p6: 382)
    108  "se me hizo tarde" (ev34 p2: 383), y la salida a la granja: los
         eventos 20 y 21, con 382, saltan al 127

**El corte natural es la granja (127)**: ahí empieza la celebración, que es
la elección de profesión —y detrás, el resto del capítulo: la cantera, los
bandidos, el teatro—. Y el 127 es uno de los mapas que no entran en la VRAM
(731 tiles de sprite, 22 eventos que caminan:
`testing/mundo-7-camino-a-paradise.md`). En
`el-108-con-poses-compartidas.md` el próximo corte era el salto al sueño
(109 ev6); el día siguiente entra entero sin pedir nada más que el 126 y el
113, así que el corte se fue hasta la puerta de la granja.

**El fork del 108** vuelve a dejar el evento 5 como el original —la llegada
salta al Consejo— y cambia el `Teleport` al 127 de la página del 382 de los
eventos 20 y 21 por el cartel ("END OF THE DEMO / The celebration at the
farm is / not in the cartridge yet. / Thanks for playing!") y la vuelta al
título. Las otras páginas de esos eventos que saltan al 127 son de tandas
posteriores (396, 427, 441) y no compilan, como antes.

**La regla**: `below = 127`, con dos exclusiones más —el 111, una prueba
del autor a la que nada lleva, y el 121, de una tanda posterior, que sigue
como mapa de prueba— y el recuerdo (175 a 177) en `added`. El 119, la
armería, era mapa de prueba y pasa a ser del juego.

# Lo medido

Con una variante de `release` más los mapas de arriba —la que quedó—, el
compilador instrumentado (registra el comando que frena cada página, lo
cambia por un `Comment` y vuelve a probar, para juntarlos todos; en un
`target/` aparte, sin commitear) y `peso.py`, que suma lo que cada mapa
nombra en su registro de `map_table` y su `map_code`, siguiendo las
referencias de `mapdata.inc` y medido en el `.dbg`. "Propio" es lo que
ningún otro mapa usa: las poses y los tiles que comparte no cuentan. Los
scripts y el parche del compilador quedaron en `/extras/scratch/nandu/medir/`.

    mapa                   propio   fondo  encima  sprite  paletas
    109 Paradise Overlook   1.8 KB   121     9      83     4
    110 Council Chambers   19.7 KB    67     1     188     8
    112 ParadiseInteriors  11.3 KB   153     7     147     5
    113 Emily's House      11.5 KB   154    11     147     4
    114 Talan's House      11.9 KB   100     5     192     8
    115 House1             10.4 KB   163     5     147     4
    116 House2             13.2 KB   182    11     147     4
    117 House3             26.2 KB   137     5     403     7
    118 House4             20.6 KB   184     7     128     8
    119 Weapons and Armor  12.8 KB   166     3     147     5
    120 ConstructionTent    6.4 KB   114     1      83     3
    122 DreamSequence       6.2 KB    68     1      83     3
    123 Talan'sDream1       2.2 KB     2     1     147     4
    124 Talan'sDream2       2.9 KB     2     1     147     6
    125 AG7 in the Rain     2.3 KB   102     1     147     5
    126 OverlookAtDay       4.6 KB   121     9      83     4
    175 Mountain Flashback  7.4 KB   102     1     147     7
    176 Overlook            3.5 KB    20     1     147     6
    177 Paradise Found ;)  10.1 KB   150    29     147     6

**Todos entran en la VRAM** con los repartos de hoy, y **todas sus páginas
compilan** salvo las que saltan a mapas de tandas posteriores: 114 ev10 p3
(al 160, con 427) y 117 ev20 (al 142, con 427). Del 108, las que saltan a
la granja (127) y a la cantera (150). No hizo falta ningún comando nuevo.

**El 108 quedó justo**: 24 ranuras, 384 tiles de sprite de los 384 de
"+ambos". Antes eran 23 y 380: con el Consejo y las casas en el cartucho
compilan más páginas del 108 —la de la chica que llora mueve a Emily con
`SetEventLocation`, y la de "se me hizo tarde" les da ruta a tres
vecinos—, y los que algo mueve dejan de turnarse (70 quietos en 12 ranuras;
eran 72 en 13). Entra sin margen: un quieto más que deje de turnarse y no
convierte.

## Espacio

`just espacio release`, antes (el `release` de `/shared/abl-snes`,
`a454257`) y después:

                   antes                 después
    bancos         65 de 127, 3 lentos   71 de 127, 9 lentos
    libres         43 bancos             37 bancos
    huecos         59.217 B              94.332 B
    banco 0        2.868 B               2.868 B
    banco 1        14.204 B              14.204 B
    banco $C0      16.852 B              16.852 B
    BSS, ZEROPAGE  128 B, 4 B            128 B, 4 B
    textos         115.978 B             134.893 B (127.251 libres)

Seis bancos para diecinueve mapas y nueve temas. `test-special` y
`test-encounter-every-step` no se movieron.

# Lo que hubo que tocar en las herramientas

Rama `worktree-agent-a140cce898ba673eb` del repo de herramientas:

* **`BOOT_FRAMES` de 40 a 44** (`tools/runtime/far_ram.s`). El paquete de
  audio del mapa de arranque pasó de 14.976 a 15.651 B —el reparto de
  muestras se hace sobre todos los paquetes— y la cuenta de `boot_frames`
  dio 40 contra 40: el conversor se negaba a armar. Es lo que
  `decisiones/el-arranque-esta-dimensionado-para-el-paquete-de-arranque.md`
  de las herramientas dice que se hace, a mano. No movió ninguna golden.
* **Pista de MSU-1 para los temas del RTP que nombra el juego**
  (`rm2k-snes-audio`). `Farewell2`, el de la casa de Talan la primera
  noche, es del RTP y no lo nombra el `System`: no tenía número y sonaba
  por el SPC700 aunque hubiera MSU-1 (`test_todo_tema_tiene_su_pista`, en
  rojo sin el cambio). Van al final, después de los del `System`, y son los
  que nombra **el juego entero**, no el cartucho, así que ningún número de
  antes se movió. En ABL es uno solo: la pista **235**.

Ningún opcode nuevo (los `0x41`-`0x44` quedaron sin usar) y nada de RAM.

# Pruebas

* `abl/test_recorrido_paradise_dia_golden.py`: el primer día entero, del
  108 al cartel del fin y el título, con veintidós fotos **sin bendecir**
  (en `pendientes.txt`). Prende el 357 a mano, para que el recuerdo bajo
  la lluvia esté en el camino.
* `abl/test_recorrido_paradise_golden.py` termina ahora al llegar al
  Consejo: su foto del cartel y la del título se fueron, y la del Consejo
  es nueva y está pendiente.
* `abl/test_paradise_por_dentro.py`: trece llegadas con golden y
  `celdas_mal_dibujadas` en cero: 109, 110, 112 a 120, 125 y 126. Los
  mapas que son sólo escena (175 a 177, 122 a 124) los juega el recorrido.
* `parches/auto/mapas/`: diecinueve parches nuevos, de `just parches`; los
  que había no se movieron.

`just pruebas`: **1023 de 1026**. Las tres rojas son de
`test_musica_techos.py` —`T_VGFighterMAX_Masako` y `rshinld` recortan, y la
tabla no es la de esta mezcla—: los temas nuevos movieron el reparto. **No
se corrió `just techos`.** `just -f tools/justfile test` 52 en verde;
`cargo test -p rm2k-snes-audio -p rm2k-snes-cartridge -p
rm2k-snes-bytecode` en verde. `NO_CACHE=1 just cartuchos` da las mismas
huellas que con caché: `abl.sfc` `6041a546…`, `abl.msu` `a654f637…`.

Las llegadas y el recorrido son nuevos: cobran regresiones de acá en
adelante, no errores de nacimiento. Eso lo dice taro mirando.

## Goldens

**Nuevas**: las trece `paradise-1NN-llegada`, en su commit. **Ninguna
existente se movió**: tampoco las de los turnos del 108, aunque ahora se
turnan otras ranuras. Las trece y las fotos de los dos recorridos están
en `/shared/capturas/2026-10-02-paradise/`, con un `LEEME.txt`. **El merge
espera el visto bueno de taro.**

# Lo que no está hecho, y lo que se ve distinto

* **La granja (127)**, y con ella el resto del capítulo: necesita la caché
  de ranuras (la opción D de `testing/mundo-7-camino-a-paradise.md`), y ni
  así entra holgada. Es lo que sigue, y es de taro elegir.
* **Los panoramas** del mirador (109, Night1), del de día (126, Morning1) y
  del recuerdo (175 y 176, Night1) salen negros, como en todos los mapas con
  panorama: `wishlist/panorama-del-mapa-2.md`.
* **La lluvia de la noche no se ve** en el 108, el 110, el 114 y el 118: las
  gotas no entran en las paletas de sprite (lo dice el conversor). Suena
  `Rain1`; en el 125 sí llueve.
* **La música** de los mapas nuevos no se escuchó, y `test_musica_techos.py`
  está rojo (arriba).
* El recuerdo bajo la lluvia (125) depende del 357, que lo prende el túnel
  si AG7 vino: la rama sin él no la juega ninguna prueba.

# Lo que no cubre `just pruebas`

* Las casas del pueblo más allá de la llegada: nadie les habla a los
  vecinos.
* La armería (119) como tienda.

# Al mergear

* Herramientas: instalar `cartridge` (el runtime cambió: `BOOT_FRAMES`) y
  `rm2k-snes-audio` (`just -f tools/justfile install cartridge
  rm2k-snes-audio`). No hay Python nuevo ni renombrado en `tools/`.
* ABL: la pista **235** (`Farewell2`) es nueva: `just entregar` va a
  avisar que las de `/shared/msu/` no coinciden; va con `--actualizar-msu`.
* `just techos`, una vez, sobre el árbol mergeado.

# Qué tiene que probar taro

* Desde la llegada a Paradise: el Consejo y el recuerdo de Pierson; el
  pueblo al atardecer y sus casas; Pierson y la noche en la casa de Talan
  (con AG7 en el grupo antes del túnel, el recuerdo bajo la lluvia); la
  chica que llora, el mirador, el sueño y la mañana; Pierson en la puerta;
  Emily en el mirador de día y en su casa; la hora de la celebración y el
  cartel al salir hacia la granja.
* Si el pueblo de noche y los miradores se aguantan sin la lluvia ni el
  panorama, o si hay que priorizarlos.
* Qué hacer con la granja.
