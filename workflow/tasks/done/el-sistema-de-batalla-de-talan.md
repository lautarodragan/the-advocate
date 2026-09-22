**El sistema de batalla de Talan: `Detect Aura` y `Absorb Aura` en la pelea.**

Es el primer tramo de `eventos-de-tropa-en-la-pelea.md`, acotado a Talan: si anda,
el mecanismo está probado y los otros 31 sistemas son completar comandos.

Las dos habilidades son de tipo switch (3), sólo en pelea y sin costo de SP:

- `Detect Aura` (133) prende el switch 134 (`DetectedAura`);
- `Absorb Aura` (134) prende el switch 135 (`AbsorbedAura`).

Cada switch dispara una página en 142 tropas:

- **134**: 7 cuerpos distintos, y sólo usan comandos que el port ya tiene
  (`ChangeSkills`, `ShowMessage`, `ControlSwitches`, `ControlVars`);
- **135**: 86 cuerpos distintos, y suman el único comando nuevo que hace falta:
  `ConditionalBranch_B`, el de pelea.

Lo que falta: que una habilidad de tipo switch se pueda usar en la pelea y prenda
su switch, que corran las páginas de la tropa que lo miran —con sus mensajes en la
ventana de batalla—, y `ConditionalBranch_B`.

Hecho es: en una pelea, Talan usa `Detect Aura` y después `Absorb Aura`, y pasa lo
que pasa en RM2k, con una prueba que lo recorra.

Referencia: `Game_Battle::UpdateEvents` y `Game_Interpreter_Battle` de EasyRPG.
