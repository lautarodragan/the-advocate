---
name: "El mapa de debug"
description: "Un cuarto donde arranca Begin the Story, con una puerta a cada punto clave del juego —con el estado de alguien que jugó hasta ahí— y un NPC por compañero"
type: feature
assignee: taro
---

# Qué pidió taro

> podrías crear un nuevo mapa, para debug, que tenga puertas que llevan a
> distintos mapas clave, cada una con un cartel que diga su destino? la idea
> sería que begin game comience ahí. una puerta te llevaría al comienzo
> normal, otra a talans pad después de la intro, otra a los back alleys
> después de que asesinan al director, otra a talans pad pero con el auto… y
> tal vez un npc para cada uno de los 3 compañeros, que al hablarles te hagan
> change party. la puerta debería hacer teleport y también activar los
> switches que hagan falta, como si hubiera jugado el juego normalmente hasta
> ahí

Y después, sobre las pruebas: **una sola ROM** para la tanda y para lo que él
juega; el flag que lo apaga es para una entrega limpia, no para la tanda.

Sale de `2ca861a5`.

# Cómo nace un mapa que el juego no tiene

`parches/manual/nuevos/Map0900.{json,tiles}`, y no `mapas/`: un fork
reemplaza un mapa que existe y un mapa nuevo **no puede** pisar uno que
exista, así que son la misma regla dada vuelta y cada una necesita su red.
`fork.nuevos()` valida: las dos piezas, el id del nombre igual al de adentro,
y que `data/` no tenga ese mapa. El nodo del árbol (`data/maps.json`) que un
mapa nuevo no tiene lo trae el propio JSON, en el campo `arbol`, y
`lcf.TreeMap` lo suma. `lcf.Map` lo lee como a un fork.

* **El id, 900**: fuera de los 0 a 351 del árbol del juego, redondo para que
  se vea que no es del juego.
* **El chipset, el 10** (`LasheINT`, el de Lashe City Interiors, que ya está
  en el cartucho): el dibujo es el del cuarto de arriba a la derecha del mapa
  10 —paredes, piso liso, la salida de abajo— estirado a 26x15, con seis
  salidas y la consola de la pared del fondo parada en el piso como cartel.
* **La música**: `music_type` 1, "la pone un evento", o sea ninguna, como el
  mapa 4.

Lo armó un script descartable; de ahí en más el JSON se edita a mano.

# Cómo arranca "Begin the Story" ahí

La página 0 de `release` —la que corre al empezar, en el mapa 4, antes que
su enrutador— es un caso, `PRIMERO` en `cartuchos.py`. Hoy era `nada`. Con
`CON_MAPA_DE_DEBUG = True` es `mapa-de-debug`: un `Teleport` al 900 y Talan
en el grupo, porque DummyHero es un sprite vacío y el héroe no se vería.
`nada` pasa a ser una página más.

**Para una entrega limpia, `CON_MAPA_DE_DEBUG = False`**: el mapa sale del
cartucho y la página 0 vuelve a ser `nada`. Medido: esa ROM sale **byte por
byte igual** a la de `main` en `2ca861a5` (`.sfc` y `.msu`), armadas las dos
con `cartuchos.convertir` en directorios aparte.

"Resume the Story" no pasa por la página 0: la partida guardada ya tiene
prendido el switch que la apaga.

## Las pruebas que juegan desde el título

Dos caminos, y quedó una mezcla:

* **Las que juegan desde el título** —`tanda.partida(None)`, las
  cinemáticas, la música, el recorrido de Talan— eligen la página de
  `LA_PARTIDA_DE_VERDAD` (`nada`) por su número, como a cualquier caso: es la
  página 0 de la entrega limpia, en la misma ROM. Pasar por la puerta no daba
  lo mismo: las goldens de `cinematica` cuentan ticks desde el título y dos
  caen en la rampa del primer fundido, y llegar al 4 con un `Teleport` corre
  la rampa y el tinte (lo dice `CINEMATICAS` en `test_escenas_golden.py`).
  Habría que rehacer goldens que hoy prueban exactamente el arranque que se
  entrega sin el mapa.
* **El recorrido de la apertura** hace lo que sugirió taro: entra por "Begin
  the Story" al mapa de debug, camina hasta la puerta del comienzo normal y
  la cruza. Con eso la puerta queda cubierta de punta a punta. Su foto de
  "Kersh toma el control" sale con la lluvia en otra fase (344 pixeles,
  0,6%), dentro de la tolerancia de esas fotos.

# Las puertas

Rama elegida para todo lo que se ramifica: **la de Arden** (Neon Vipers),
llegando a tiempo al trabajo, **rechazando a Wick** —la misma que usa
`test_recorrido_sorbe_golden.py`—. El jugador es prolijo: abre los cofres del
camino y habla con la gente que deja un switch que alguien mira después. No
toma los desvíos que cambian ramas: ni el Hover-Tram (71/72/186), ni el
soborno (29), ni afeitarse (25).

Cómo se armó: cada tramo se leyó de los eventos de `data/`, y para no
perderse en los switches locales de cada mapa se cruzó qué switches **puestos
antes** de cada punto **mira alguien después** (un script descartable). Ésos
van todos, con el valor de esta rama; los demás, los de la historia. Cada
página de puerta dice de dónde sale cada cosa en sus `Comment`, que el
conversor saltea.

La velocidad del héroe también viaja: la cambian las rutas del juego (28 y
29) y la ROM la guarda. Cada puerta la fija con cinco bajadas y las subidas
que hagan falta.

    1  NORMAL START    mapa 4 (10,12), el arranque del LDB. Deshace lo que el
                       mapa cambia: el grupo y el 150.
    2  TALAN'S PAD     por el enrutador del 4 (11,9) con el prólogo hecho: 3,
                       5, 7-15, 21, 22 y 806. Corre la página 3 del 4 —el
                       cartel, la consola (81), Talan— y salta al 7.
                       Velocidad 5 (la página 2 del evento 5 del 3); el
                       despertador la deja en 4.
    3  BACK ALLEYS     20 (93,0), el Teleport de la salida del 19, con
                       '3D-Galax'. + Lashe City hasta el director: 24, 27, 30,
                       31, 32, 48, 54, 58, 73, 77, 78, 79-89, 90, 92, 129,
                       206. Oro 400 (despertador y cheque), 81, 97, 88.
                       Grupo Talan. Velocidad 5.
    4  WITH THE CAR    36 (10,8), donde deja el 34 (133, 148): la elección de
                       sector, y el 35 es el pad de Talan con auto. + los
                       callejones, las Rat Tracks, el Sector 27 y el almacén:
                       93, 95-97, los cofres 98-112, 116-118, 123-128, 113,
                       120, 121, 130, 132, 133, 137. Oro 845, los ítems de
                       todos esos cofres, Detect Aura (133) para Talan. Grupo
                       DummyHero, como lo deja el 33. Velocidad 4.
    5  THE RACE        49 (1,26), el Teleport de la página 2 del 36, con 182.
                       + la rama de Arden cerrada: 149, 151, 154, 156,
                       158-162, 166-169, 238, los tres cofres del 38
                       (544-546, 124, 157, +250). Velocidad 3 (el 41 la baja
                       al rechazar a Wick).
    6  THE WORLD       por el premio del 53 (11,10) con las tres vueltas
                       (171, 174-179, variable 38 en 0): da el oro y los
                       ítems, prende el 180 y pasa por la despedida del 64,
                       que arma el grupo y deja en el mundo. Velocidad 6 (la
                       carrera sube tres); la despedida la deja en 3.

Propuse la carrera y el mundo además de los cuatro pedidos, y **no** Sorbe: la
entrada a Sorbe está a veinte pasos de donde deja la puerta del mundo, así
que una puerta más sería un estado más para mantener por veinte pasos. La
carrera sí: sin ella, llegar a la largada son los cuatro sectores con auto.

# Los compañeros

Un NPC por cada uno —Arden (15), Saldra (17), AG7-17 (18)— con el gráfico del
juego. Hablarle lo suma al grupo si no está y lo saca si está
(`ConditionalBranch` de actor en el grupo). AG7 prende y apaga además el 150:
prenderlo corre el evento común 37 pegado detrás —ver
`divergencias/los-comunes-del-equipo-corren-al-cerrar-el-menu.md`— y entra
sabiendo la habilidad de su ArmCannon, que trae puesta de la base. No hace
falta darle el arma. Sin el 150 la página del 36 y la despedida del 64 no lo
meterían en el grupo.

**Los NPC no tocan los switches de rama** (54, 56): meter a Saldra no hace
que el juego crea que se eligió a los Lazer Teeth. Las puertas no sacan a los
compañeros que se sumaron, salvo la del comienzo normal.

# Lo que no reproduce

* **El nivel.** Talan llega a cada punto con el nivel inicial: las peleas del
  camino no se juegan, y no hay comando compilado para cambiar la
  experiencia o el nivel (`ChangeExp`, `ChangeLevel`). Si hace falta, es un
  opcode nuevo: avisar antes.
* **El equipo puesto**: los ítems llegan al inventario, sin equipar.
* **Absorb Aura** y las curas que da absorber auras: dependen de qué se
  detectó en qué pelea.
* Las tiendas, las reparaciones del taller y el juego de azar: ni el oro que
  cuestan ni lo que dan.

# Pruebas

`pruebas/abl/test_mapa_de_debug.py`, sobre `release`:

* la llegada por "Begin the Story", con golden (`mapa-de-debug-llegada`) y
  `celdas_mal_dibujadas` en cero;
* cada puerta cruzada caminando, con el mapa, la celda, los switches, el
  grupo, el oro, ítems y la velocidad al llegar;
* cada NPC suma y saca a su compañero (AG7, con el 150 y su habilidad);
* la entrega limpia, sin armarla: los casos de `release` con el flag apagado.

Y `test_recorrido_golden.py`, la apertura, entra por la puerta 1.

# Espacio

Medido contra la entrega limpia (= `main`): TABLAS, BSS, ZEROPAGE y el
banco 1 no se mueven; los bancos de datos, +7,9 KB (la cuenta de los `seg`
del `.dbg`). Los números del cartucho no se escriben: se miden.

Verificado con `just pruebas` (que corre `just cartuchos` antes) sobre el
árbol entero, en verde; y la entrega limpia contra `main` byte por byte, como
dice arriba. Las goldens y las capturas de las llegadas, para mirar, en la
carpeta de capturas del 2026-09-27 del mapa de debug.

# Qué tiene que probar taro

* Que "Begin the Story" caiga en el cuarto y se lean los seis carteles.
* Cada puerta, y jugar un rato desde cada una: que lo que sigue funcione
  como si se hubiera jugado —sobre todo la del auto (el Sector 35 y el pad) y
  la del mundo—.
* Los tres NPC.
* "Resume the Story" con una partida vieja.
