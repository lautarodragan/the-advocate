---
name: "Los eventos de tropa"
description: "Los 32 sistemas de batalla de los personajes, además del de Talan"
type: feature
assignee: Yarará
---

**Correr las páginas de evento de las tropas durante la pelea.**

Es lo que hace andar los sistemas de cada personaje: una habilidad de tipo switch
—`Detect Aura`, la de Talan— prende un switch, y las páginas de la tropa que lo
miran corren en la pelea.

**El mecanismo ya existe** desde el 2026-09-21, con el sistema de Talan
(`done/el-sistema-de-batalla-de-talan.md`): las páginas de tropa se compilan
deduplicadas, corren en la pelea con el mismo intérprete de los mapas, sus
mensajes salen en la pantalla de pelea, y una habilidad de tipo switch prende su
switch. Lo que falta es **completar comandos**: lo que una página de tropa puede
hacer es una lista explícita, `TROPA_COMANDOS` en `tools/port/eventos.py`, y
sólo deja pasar lo que se sabe que anda en la pelea.

Medido en el LDB el 2026-09-21:

- 300 tropas, 163 con páginas, **4287 páginas y sólo 291 distintas** por contenido
  (el juego las copia en cada pelea);
- **4278 dependen sólo de `switch_a`**; 9 miran el turno o los HP;
- **32 switches** las disparan, uno por sistema, cada uno en 140 a 163 tropas.
  Los de Talan son el 134 (`DetectedAura`) y el 135 (`AbsorbedAura`);
- `ConditionalBranch_B` ya está: el juego usa sólo 2 de sus 6 tipos, switch y
  variable, y se traducen a las ramas de los mapas.

Lo que traba a las páginas que quedaron afuera, contado por páginas al terminar
el sistema de Talan:

- **`ChangePartyMembers`: 2520**, y es lejos lo que más traba;
- `PlaySound` 280, `ChangeCondition` 140, `PlayBGM` 140, `ChangeHP` 129 —en la
  pelea tiene que escribir los HP de la pelea y no `FAR_HP`—, `ChangeMonsterHP` 24;
- las condiciones de turno, HP del enemigo y HP del actor: 173 páginas;
- la forma de **equipar** de `ChangeEquipment`, que no compila: sólo está la de
  sacar una ranura.

**Y el espacio se va a acabar antes que los comandos**: las páginas de tropa del
juego entero son unos 48 KB entre código y mensajes, y no entran en ningún lado.
Hoy van en el banco 1, que en los cartuchos grandes quedó con unos 8,8 KB libres.
Pide comprimir, el acomodo de bloques, o traerlas por MSU-1.

Referencia: `Game_Battle::UpdateEvents` y `Game_Interpreter_Battle` de EasyRPG.

**Lo que ya hizo `tasks/*/eventos-de-tropa-de-release.md`** (2026-09-28), que
es lo que se nota en las peleas de `release`: las condiciones de turno, de HP
del enemigo y de HP del actor —las tres, con sus números en una cabecera
delante del código de la página y no en tablas del banco 1—, los enemigos
ocultos con `ShowHiddenMonster`, y `PlaySound` y `ShakeScreen` en la página.
Lo que queda es de los sistemas: `ChangePartyMembers` sigue siendo lejos lo
que más traba, y después `ChangeHP` y `ChangeMonsterHP` sobre los HP de la
pelea, `ChangeCondition`, `ChangeMonsterCondition`, `ChangeEquipment` para
equipar, `PlayBGM` y `FlashScreen`. **Y el audio**: el `PlaySound` de una
página se pide pero su efecto no entra en el paquete de la pelea salvo que
esté en `SE_DE_TROPA_AL_PAQUETE`, porque el paquete ya limita muestras; los
sistemas tienen efectos propios y van a chocar con eso.

# Status

2026-09-30, Yarará, sobre `main` en 1a82726. En curso.

# Lo medido al empezar (2026-09-30, sobre 1a82726)

Con un script descartable sobre `rom/data/db/troops.json` y la lista de
`TROOP_COMMANDS` de `tools/rm2k-snes/events/src/troops.rs` (las ramas de pelea
cuentan como las del mapa). Cuenta páginas con algún disparador.

**El juego entero**: 4451 páginas, 1355 entran por sus comandos. **Las 69
tropas de `release`**: 1671 páginas, 532 entran —lo mismo que dice
`conversor.log`: "troop pages: 532 of 1671 in 124 distinct body(ies), 8863 B
of code and 9121 B in 162 message(s)"—.

Lo que traba, en `release` (páginas que lo usan; entre paréntesis, las que
traba sólo él):

    ChangePartyMembers       918 (918)   las 18 invocaciones, 814 a 831
    ChangeHP                 203
    ChangeMonsterHP          152
    ChangeCondition          102
    ChangeMonsterCondition    69  (18)
    ChangeMonsterMP           51
    FlashScreen               51
    PlayBGM                   51
    ChangeEquipment           51

Por sistema (switch A), en `release`: andan enteros **9 de 32** —134, 135,
138, 141, 143, 144, 146, 813 y 860—, el 803 anda en 33 de sus 51 páginas y
el 801 en 1. Lo que traba a cada uno de los demás:

    799 Inscribe          ChangeMonsterCondition, ChangeMonsterMP,
                          FlashScreen, ChangeMonsterHP, ChangeCondition,
                          ChangeHP
    801 LifeForStrength   ChangeHP (restar, letal) y ChangeMonsterHP; y el
                          ControlVars con los HP de un actor, que no compila
    802 Sacrifice         ChangeCondition (sacar la muerte) y ChangeHP
    803 ControlMachines   ChangeMonsterCondition (18 de 51)
    809 Play Radio        PlayBGM, ChangeEquipment para equipar, ChangeHP,
                          ChangeMonsterHP
    814-831 invocaciones  ChangePartyMembers (sacar a Emily, 26, y poner a
                          la invocación, 36 a 53)

Las formas que usan, del LDB entero: `ChangeMonsterHP` siempre restando una
constante y letal, al enemigo 0, 1 o 2; `ChangeMonsterMP` restando 40;
`ChangeMonsterCondition` con los estados 22 (Control) y 23 (BarkWall), que la
pelea no tiene; `ChangeCondition` siempre "sacar el estado 1 al grupo", que
es revivir; `ChangeHP` sumando al grupo o a Emily, o restándole 999 a Talan,
letal.

**El espacio**, `just espacio` sobre los cartuchos de la base:

    release        bancos de datos 115 de 124, 9 libres; huecos 8.799 B;
                   banco 0 50 B; banco 1 3.126 B
    test-special   banco 0 943 B; banco 1 5.630 B
    encounter-...  banco 0 1.003 B; banco 1 5.901 B

Lo que la tarea decía del espacio ya no es así: **el código y los mensajes
de las páginas no están en el banco 1 desde el 2026-09-27**, están en
RODATA, donde sobran nueve bancos. Lo que sigue en el banco 1 son **las
tablas por página** —`tpage_flags`, `tpage_sw_a` y `tpage_code`—, cinco
bytes por página: con las 532 de hoy son 2.660 B, y con las 1671 serían
8.355 B, que no entran en los 3.126 que quedan. Sólo las 918 de las
invocaciones son 4.590 B.

# Lo hecho (2026-09-30, Yarará)

**El espacio**: las tablas por página se fueron a RODATA con el código y los
mensajes (a23eedf). **Es una decisión de espacio que no pidió nadie** y la
tiene que ver taro: es el criterio del 2026-09-27 (8d6757e) aplicado a lo que
quedaba. Sin ella, las 918 páginas de las invocaciones no entraban en el
banco 1 de `release`. Se revierte sola, y entonces lo de abajo no entra.

**El mecanismo**: una página de tropa corre con los opcodes del mapa, y los
del grupo —`ChangePartyMembers`, `ChangeHP`, `FullHeal`, el `ChangeCondition`
que revive, `ControlVars` con los HP de un actor— tocan `party` y `FAR_HP`.
Así que cada tramo de página pasa por `ba_sync_out` —los HP y SP de la pelea
a `FAR_HP`/`FAR_SP`— y `ba_sync_in` —de vuelta, y el grupo: el que salió deja
su lugar vacío, el que entró va al primero vacío, desde `ba_actor_setup`, lo
de `ba_build` para un actor—. Ver `battle_troop.s`. Lo que eso no hace como
RM2k está en `divergencias/lo-que-las-paginas-de-tropa-no-modelan.md`.

**Los comandos**, con su prueba en `rom/pruebas/rpgmaker/test_sistemas_de_tropa.py`:

    ChangePartyMembers     el opcode del mapa, OP_PARTY
    ChangeHP que resta     OP_ACTOR (nuevo, 0x36), con sus bits: resta,
                           letal, por variable
    ChangeCondition        sacar la muerte es OP_ACTOR con ACT_REVIVE
    ChangeSP               OP_ACTOR con ACT_SP (no lo usa ninguna tropa:
                           es para el común 35, ver abajo)
    ControlVars de actor   la clase 5 de OP_VAR: HP, SP y sus máximos
    ChangeMonsterHP y MP   OP_ENEMY (nuevo, 0x37)
    FullHeal               ya andaba en el mapa; entra por lo mismo
    ChangeEquipment        equipar armadura, casco o accesorio a un actor:
                           OP_ACTOR con ACT_EQUIP, y la pelea toma los
                           parámetros nuevos en `ba_reparam`
    PlayBGM                se acepta y no se hace (ver abajo)

OP_ACTOR, `ChangeSP` y el `ChangeHP` por variable se prueban también en el
mapa: `rom/pruebas/rpgmaker/test_curar.py`, con el caso `curar-restar`.

`ChangeMonsterMP` compila y la ROM lo hace, pero **ninguna prueba lo corre**:
sólo lo usa el 799, que sigue trabado por `ChangeMonsterCondition`.

El modelo de la pelea (`rm2k-snes-battle`) corre lo mismo en las páginas:
quién entra y sale, los HP del grupo y del enemigo, `ControlVars` y las ramas
por variable. Una habilidad de switch ahora prende su switch para las
páginas (`lit_by_skills`), sin cambiar el `state` de la respuesta: los 400
hashes de `tests/model.rs` siguen iguales, medido.

**Cuántos sistemas andan en `release`**: 30 de 32 —los 9 de antes, el 801,
el 802, las 18 invocaciones y el 809, `Play Radio`, sin su música—; el 803 en
33 de sus 51 páginas. Traban el 799 (`Inscribe`) y el resto del 803
(`ControlMachines`), los dos por `ChangeMonsterCondition`: la pelea no tiene
estados, y hacerlos es un sistema entero —duración, restricciones, lo que
hacen BarkWall (23) y Control (22)—. El 799 además pide `FlashScreen` en la
pelea, que hoy tiñe la paleta del mapa y no la de la escena. "troop pages:
1602 of 1671 in 149 distinct body(ies), 9941 B of code and 9515 B in 172
message(s)". En el juego entero entran 4285 de las 4451 páginas.

**La música de `Play Radio` no suena**: el `PlayBGM` de una página de tropa
se acepta y no se hace, porque su tema iría al paquete de la pelea y le
bajaría la tasa al de batalla —la misma regla que deja afuera a los efectos
de las páginas— y ninguno de los tres tiene pista de MSU-1. Es una decisión
de audio para taro; está en
`divergencias/lo-que-las-paginas-de-tropa-no-modelan.md`.

**El espacio después** (`just espacio`, `release`): banco 0 **13 B** (de 50),
banco 1 5.054 B (de 3.126, con las tablas afuera), bancos de datos 116 de 124
y 8 libres. El banco 0 se come con las dos entradas de opcode (9 B cada una),
la de `ControlVars` de actor (10 B) y los casos nuevos. **Es el límite que
sigue**: la prueba de `Play Radio` quería a Emily en el grupo del caso, y eso
la vuelve un actor del cartucho con sus ítems y su nivel en tablas del banco
0 —medido, 15 B contra 13—, así que la prueba la deja afuera. Lo próximo que
sume un actor al cartucho, o un opcode, no entra sin mover algo del banco 0.

**Números usados**: opcodes 0x36 (OP_ACTOR) y 0x37 (OP_ENEMY). RAM lejana:
`$7E7A2A` (`BA_SYNC_I`), dentro de lo que ya era de las páginas
($7A10-$7A3F). Tuplas de `test_*_golden.py`: ninguna.

**Lo que falta en el juego para jugar las invocaciones**: después de la
pelea el grupo queda con la invocación en lugar de Lerle. En RM2k lo arregla
el común 35, `ResetAfterBattles`, que corre la automática `AfterBattleMint` de
los mapas con encuentros; acá no compila —ver
`divergencias/llamada-salteada.md`—. Medido con el compilador de esta rama:
**cada uno de sus comandos compila** —lo que faltaba era el `ControlVars` de
actor, el `ChangeHP` por variable y `ChangeSP`, que ya están—, y el común
entero compila solo (1.773 bytes) si las variables que nombra tienen ranura.
Llamado desde un mapa, en cambio, se saltea: **las variables que sólo nombra
un común no tienen ranura**. El barrido de variables recorre los mapas y las
tropas y no los comunes (`indices.rs`), y sumarlos corre las ranuras de las
demás, que es lo que hace que una partida guardada con un cartucho cargue en
otro. Es una decisión para taro; con ella, el común 35 corre después de cada
pelea al azar, que es mucho más que las invocaciones —cura a las 18, le saca
a Emily la radio, le rearma a Talan las habilidades de aura y a AG7 las de
sus piezas— y hay que medirlo aparte.
