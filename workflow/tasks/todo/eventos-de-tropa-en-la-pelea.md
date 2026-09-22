---
name: "Los eventos de tropa"
description: "Los 32 sistemas de batalla de los personajes, además del de Talan"
---

**Correr las páginas de evento de las tropas durante la pelea.**

Es lo que hace andar los sistemas de cada personaje: una habilidad de tipo switch
—`Detect Aura`, la de Talan— prende un switch, y las páginas de la tropa que lo
miran corren en la pelea. Hoy el port no corre ninguna página de tropa, y además
muestra las habilidades de tipo switch en la pelea sin que hagan nada.

Medido en el LDB el 2026-09-21:

- 300 tropas, 163 con páginas, **4287 páginas y sólo 291 distintas** por contenido
  (el juego las copia en cada pelea);
- **4278 dependen sólo de `switch_a`**; 9 miran el turno o los HP;
- **32 switches** las disparan, uno por sistema, cada uno en 140 a 163 tropas.
  Los de Talan son el 134 (`DetectedAura`) y el 135 (`AbsorbedAura`);
- 216 de los 291 cuerpos usan comandos que sólo existen en pelea
  (`ConditionalBranch_B`, `ChangeMonsterHP`/`MP`/`Condition`, `ShowHiddenMonster`,
  `TerminateBattle`), y aparecen `ChangePartyMembers` (5040 veces) y la forma de
  equipar de `ChangeEquipment`, que hoy no compila.

El primer tramo, acotado a Talan, es `el-sistema-de-batalla-de-talan.md`.

Referencia: `Game_Battle::UpdateEvents` y `Game_Interpreter_Battle` de EasyRPG.
