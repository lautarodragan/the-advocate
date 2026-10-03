---
name: "Los eventos de tropa de release"
description: "Las páginas de tropa que las peleas de release piden: el Rat King que llama a sus ratas, el despegue en la pelea de los agentes, y las condiciones de turno y de HP"
type: feature
assignee: taro
---

# Qué

La parte de `todo/eventos-de-tropa-en-la-pelea.md` que se nota **en las peleas
que `release` puede pelear hoy**, que es lo que pidió taro el 2026-09-28 con
dos casos del primer gran hito:

> - la batalla con Rat King no es como la original. en nuestra versión, aparece
>   con dos ratas desde el comienzo. en el original, rat king invoca ratas cada
>   tanto.
> - los eventos de la pelea con los 2 agentes: en los primeros turnos aparece
>   el texto de "el hover tran está despegando" y creo que viene acompañado de
>   un efecto de sonido
> - no sé si hay más cosas asociadas actualmente a los eventos de batalla

Los 32 sistemas de personaje siguen en la grande.

# Status

2026-09-28, en `testing/`: hecho por Ceibo en su rama, sobre `main` en
40f4011, en dos commits —d2d820a (la automática que compila a nada) y
208c828 (lo demás)—; `just cartuchos` y `just pruebas` en verde. Lo que queda
es de taro: jugarlo (ver abajo) y decidir el trueno.

# El inventario

Medido con un script descartable sobre `data/db/troops.json`, los mapas de
`cartuchos.MAPAS_DEL_JUEGO` —sus `EnemyEncounter` y los encuentros del árbol— y
el `tropa_id` del `release` armado: **69 tropas**. Diecisiete de ésas sólo las
piden las páginas de prueba (159, 161, 219-227, 232-236); el resto, el juego.

La regla de cuándo corre cada página es la de easyrpg y ya estaba en la ROM
(`ba_pag_probar`): antes de pedir las órdenes, antes de cada acción y después
de la última, la primera que se cumpla y no haya corrido en este turno.

    tropa             en RM2k                          la ROM antes     ahora
    97 Rat King       empieza solo; llama a una rata   las tres desde   igual que
    (mapa 26)         con el rey al 60% y a la otra     el principio,    RM2k
                      al 30%, con su mensaje            sin mensajes
    102/104 agentes   turno 1: trueno, sacudida y      nada             sacudida y
    (mapa 32)         "The Captain has taken off in                     mensaje; el
                      the ship!"; la 104 además trae                    trueno no
                      un guardia oculto que llama al                    suena (ver
                      30%                                               abajo)
    86 Lazer Teeth    "It's not too late to            nada             igual que
    (mapa 9)          surrender!" cada 3 turnos con                     RM2k, con
                      Talan al 50%; "Give up!" cada                     Talan en el
                      2 con Talan al 30%                                grupo
    las 69            turno 0: prende el 498, que      nada             lo prende
                      después de la pelea corre el                      (el común
                      común 35                                          no corre)

## Lo que ya corría

Las páginas de `switch_a` con comandos de `TROPA_COMANDOS`: el apostar de Arden
(138), el robar de Saldra y Arden (141, 146), MindBlast y MindProbe (143, 144
en la 82), Detect Aura y Absorb Aura (134, 135) y ObtainEnemySouls (860).

## Lo que no corría por una condición o un comando que falta

**El turno 0, en las 69.** Cada tropa del juego trae una página de "turno 0"
—base 0, sin múltiplo— que prende el switch 498, `TheAfterBattleMint:)`. En
los mapas con encuentros un evento automático con ese switch llama al común 35,
`ResetAfterBattles`: cura a los actores 36 a 53 —las invocaciones—, los saca
del grupo, le repone a AG7 las habilidades de sus piezas y apaga el 498. Las
tropas 102 y 104 traen otra que prende el 461, `InFight,NeedReset`, que ningún
mapa de `release` mira.

**El Rat King (97, `EnemyEncounter` del mapa 26).** No es por turno: las dos
ratas (`GiantRat`, miembros 1 y 2) están **ocultas** en la tropa —`invisible`,
que el port no leía—, y las muestran dos páginas **por HP del enemigo 0**, el
rey, con `ShowHiddenMonster`:

- en 60% o menos, "The KINGRAT cries out for help!" y la rata 1;
- en 30% o menos, "The KINGRAT cries out for help again! Its subhuman voice
  sounds desperate!" y la rata 2.

Cada una adentro de una rama por un switch (1005, 1006) que la propia página
prende, así que salen una vez **en la partida**: si se pierde o se huye, en la
revancha no vuelven. Es de RM2k.

**Los agentes (102 y 104, `EnemyEncounter` del mapa 32).** Dos variantes de la
misma pelea en la terraza del hover tram; la 104 trae el segundo guardia
oculto, que llama una página por HP del enemigo 0 (30% o menos: "AGENCY GUARD:
This guy's tougher than he looks! Give me some help here!"). Las dos tienen una
página de **turno 1** —la primera ronda de acciones, después de dar las
órdenes— con `PlaySound` `Thunder9`, `ShakeScreen` de dos segundos que espera,
y "TALAN: The Captain has taken off in the ship!".

**Los Lazer Teeth (86, mapa 9).** Dos páginas por turno **con múltiplo** y HP
de Talan (actor 14): base 1 cada 3 con Talan al 50% o más, y base 0 cada 2 con
Talan al 30% o menos. Sólo mensajes.

**La condición de turno de easyrpg** es
`Game_Battle::CheckTurns(turno, turn_b, turn_a)`: `turn_b` es la base y
`turn_a` el múltiplo —al revés de lo que sugieren los nombres de liblcf—, y
con múltiplo 0 es "exactamente en la base". El turno arranca en 0 y lo sube
`NextTurn`, cuando el grupo terminó de dar las órdenes. Con el otro orden el
despegue saldría en todos los turnos y "It's not too late" en todos desde el
3.

## Las de los sistemas de personaje

Todo lo que sigue sin correr en las tropas de `release` es de los sistemas de
los switches 799 a 831, entre 22 y 24 páginas por tropa en las del mundo (108
en adelante). Contado sobre las 69 tropas, lo que traba a cada página:

    ChangePartyMembers                              las 18 invocaciones
    ChangeHP y ChangeMonsterHP                      Inscribe, LifeForStrength
    ChangeCondition y ChangeHP                      Sacrifice
    ChangeMonsterCondition                          ControlMachines
    ChangeEquipment, ChangeHP, ChangeMonsterHP y    Play Radio
    PlayBGM
    lo anterior más ChangeMonsterMP y FlashScreen   el 799

Ninguna se dispara en `release`: sus switches los prende sólo la habilidad de
cada sistema —medido: ningún mapa del cartucho ni ningún común los prende—, y
ninguna de esas habilidades la tiene nadie del grupo. Quedan en la grande.

# Lo hecho

**Las tres condiciones que faltaban**: turno, HP de un enemigo y HP de un
actor (`eventos.disparo_de_tropa`, `ba_pag_cumple`). Los números de cada una
no van en tablas por página del banco 1 —diez bytes por cada una de las
quinientas no entraban— sino en una **cabecera de diez bytes delante del
código de la página**, en `tropa_codigo`, que está en RODATA; la ROM la copia a
`BA_COND` cuando la página mira alguna de las tres (`ba_pag_cabecera`). El
tramo de HP se cuenta como `AreConditionsMet` —`100 * hp / máximo`, entero—
sin dividir, comparando productos de veinticuatro bits (`ba_pag_hp`).

**Los enemigos ocultos** (`BAF_OCULTO`, `tropa_ocultos`): un oculto ocupa su
lugar sin `BAF_HAY`, así que todo lo que mira quién está —el blanco, las
acciones, la victoria— lo saltea sin saber de ocultos, que es el `Exists()` de
easyrpg. No tiene renglón, no se dibuja, no da experiencia ni oro al ganar
(`ba_sin_ocultos`: `GetExp` y `GetMoney` suman los muertos) y no tira botín.
**`ShowHiddenMonster`** es OP_SHOW_ENEMY (0x33): le cambia un bit por el otro
(`ba_mostrar_oculto`), y `escena_tick`, que ya borraba al que muere, pone al
que aparece por el mismo camino: sus celdas desde el fondo limpio y los que se
ven encima, en el orden de dibujo.

**`PlaySound` y `ShakeScreen` en una página de tropa.** La sacudida es la de
`Game_Screen` y mueve la escena (`ba_sacudir`); su espera, un OP_DELAY, la
cuenta `ba_pag_paso` con `BA_PAG_ESPERA`.

**El trueno no suena**, y es una decisión que queda para taro. El efecto de un
`PlaySound` de página va al paquete de audio de la pelea, que ya limita
muestras: medido contra el `release` de antes, el `Thunder9` le baja a
`T_VGFighterMAX_Masako` seis instrumentos de 13,6-14,1 a 11,5-11,7 kHz y el
BRASS64 de 16,3 a 10,8. La regla de taro para los efectos es que ningún
instrumento pierda tasa por ellos, así que el efecto se compila y se pide pero
no entra en el paquete; sumarlo a `SE_DE_TROPA_AL_PAQUETE` (snes_music.py) lo
hace sonar, con MSU-1 y sin él. Con MSU-1 el tema de batalla suena por su
pista y la baja no se oiría; el efecto tampoco suena ahí sin la línea, porque
los efectos de calidad del `.msu` son los del paquete. Los cuatro efectos de
sistemas que de paso compilaban quedaron también afuera por la misma regla,
sin costar nada.

**La página de turno 0 al abrir la pelea** corre en el mismo cuadro en que se
arma, y no en el que viene: las 69 tropas la traen, y así la pelea abre
pidiendo órdenes como antes.

**Lo que destapó el turno 0**: el `AfterBattleMint` de los mapas con
encuentros sólo llama al común 35, que no compila, así que la página compilaba
a nada y, con el 498 prendido, corría para siempre: después de la primera pelea
el héroe no daba un paso. Una automática que compila a nada ahora no se lleva,
igual que una vacía. En su commit, y en
`divergencias/llamada-salteada.md` lo que cuesta.

**El modelo** (`batalla.PaginaDeTropa`, `Batalla.revisar_paginas`): sabe cuándo
se cumple una página y corre de ella sólo lo que cambia quién pelea
—`ShowHiddenMonster`, los switches y las ramas por switch—, en los mismos
momentos que la ROM. Con eso `test_eventos_de_tropa.py` predice en qué turno
aparece cada rata y los HP exactos de los cuatro.

Lo que la ROM hace distinto, en `divergencias/lo-que-las-paginas-de-tropa-no-modelan.md`:
los HP de un actor que no pelea, la sacudida sólo de la escena, y el trueno.

# Lo que quedó afuera

- **Los sistemas**: ver arriba. Lo que más destraba sigue siendo
  `ChangePartyMembers` en la pelea (las 918 páginas de invocaciones de las 69
  tropas), y después `ChangeHP` sobre los HP de la pelea.
- **Los mensajes largos se cortan a 31 letras**: el despegue sale "The Captain
  has taken off in th" y el segundo llamado del rey pierde la "s" de
  "sounds". Es `todo/los-textos-de-la-pelea-no-entran.md`, que ya lo tenía con
  Absorb Aura.
- **El común 35** no corre: ver `divergencias/llamada-salteada.md`.

# Números usados

- Opcode: 0x33, OP_SHOW_ENEMY. El 0x34 no hizo falta.
- RAM lejana: `$7E7A10`-`$7E7A29` (`BA_TURNO` a `BA_COND`), en
  `rom/src/ram_lejana.s`.
- Tuplas de `test_*_golden.py`: ninguna.

# Pruebas

`pruebas/rpgmaker/test_eventos_de_tropa.py`, con cuatro casos nuevos:
`pelea-97` (AG7 contra el Rat King), `pelea-97-sin-ratas` (con el 1005 y el
1006 ya prendidos), `pelea-102` (Kersh contra los agentes) y `pelea-86` (Kersh
y Talan contra los Lazer Teeth).

* el Rat King turno por turno contra el modelo: HP de los cuatro, quién sigue
  oculto, qué dibuja la escena —el bit de `ESC_VIS` y, en los pixeles, el
  búfer compuesto contra el fondo limpio—, los dos mensajes del LDB, y que las
  ratas aparezcan en turnos distintos (el 4 y el 8);
* sin ratas: el cursor de blanco no llega a ninguna, matar al rey gana, y la
  victoria da 50 de experiencia y 150 de oro, los del rey solo;
* el despegue: nada en el turno 0, la sacudida y después el mensaje en el
  turno 1 antes de la primera acción, y nada en el 2;
* que el despegue pida su efecto: el OP_SOUND del `Thunder9` en el código de
  la página, leído de la ROM;
* la condición con múltiplo: la página de los Lazer Teeth sale en los turnos 1
  y 4 y no en el 2, el 3 ni el 5;
* la regla de `CheckTurns` y lo que las pruebas suponen del LDB.

En rojo con el defecto puesto: la base y el múltiplo al revés (cuatro de las
siete), `escena_tick` sin poner al que aparece, y la composición dibujando a
los ocultos —que es el error que tuvo la primera versión, y que sólo la
comparación de pixeles cobró—.

# Qué tiene que probar taro

- **El Rat King** (Rat Tracks, mapa 26): empieza solo; con el rey más o menos
  a la mitad, "The KINGRAT cries out for help!" y aparece una rata; cerca del
  final, el segundo llamado y la otra. Las dos pelean y se les puede pegar.
- **La pelea de los agentes** en la terraza (mapa 32): después de dar las
  órdenes del primer turno, la escena tiembla dos segundos y sale "TALAN / The
  Captain has taken off in th" (cortado). Sin trueno: decidir escuchando si
  entra (una línea, ver arriba).
- **Que después de una pelea al azar** (Rat Tracks, la planta, el mundo) el
  héroe siga caminando: es lo que se rompía con el turno 0.
