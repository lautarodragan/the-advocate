---
name: "Los eventos de tropa"
description: "Los 32 sistemas de batalla de los personajes, además del de Talan"
type: feature
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
