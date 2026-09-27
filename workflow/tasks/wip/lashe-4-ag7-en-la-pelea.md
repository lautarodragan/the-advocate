---
name: "Lashe 4: AG7 en la pelea"
description: "Las habilidades del droide según sus piezas, el SP de las armas, y ShortCircuit de los enemigos"
type: feature
---

# Qué

El hito 4 de `lashe-city-hasta-la-carrera.md` —el contexto está ahí—. Tiene dos
mitades que no se pisan:

- **los enemigos de la planta** (tropas 108 a 114): se puede hacer en cualquier
  momento, con casos de pelea en `test-main`;
- **AG7-17** (actor 18): después del hito 3, que es el que lo mete al grupo.

# Los enemigos

Cinco de las siete tropas de la planta traen un enemigo con **`ShortCircuit`**
(habilidad 188: tipo normal, alcance un enemigo, poder 28, 12 SP, animación
62): Scrapped Droid, Trash Hauler, Tangle Wire y Junkbot. La pelea sólo hace el
ataque básico (`batalla.acciones_de_los_enemigos`, y su gemelo en
`rom/src/batalla.s`, el `CreateEnemyActions` con la acción `kind` 0). Lo que
pide:

- elegir la acción como `Game_Enemy` —las acciones del enemigo tienen
  `rating` y condiciones—, y en el mismo orden de azar de los dos lados, que es
  el contrato con `batalla.py` (ver `done/battle.md`);
- aplicar la habilidad con `Algo::CalcSkillEffect`, que ya está para las del
  grupo;
- la animación 62 en la pelea (la escena compuesta ya dibuja animaciones).

`test_batalla.py` predice los HP exactos: se mueve igual.

# AG7-17

Del LDB: nivel 6, arma 269 (`ArmCannon-!R`), armadura 282, `skills` vacío y
`skill_name` "Components". Sus habilidades **no se aprenden por nivel**: se las
da el evento común 37, `UpdateAG7 Skills`, que es **paralelo con el switch
150** y hace `ChangeSkills` según el arma que tiene puesta (268 en adelante →
236 en adelante). La ROM no corre eventos comunes paralelos ni automáticos
(`eventos.COMUNES` sólo sirve a `CallEvent`).

Los caminos, a decidir midiendo:

- **eventos comunes paralelos de verdad**: un intérprete más, que corre
  mientras su switch esté prendido. Es lo general —el 1 (`TalanLateForWork`,
  switch 67) ya lo pide en `release` y hoy no corre— pero cuesta RAM lejana y
  un lugar en el lazo por cuadro;
- **compilar el evento 37 como lo que es**: una función del equipo de AG7,
  corrida al salir del menú de equipo y al entrar al grupo. Es lo que el
  tutorial dice que hace ("these abilities become available once you equip a
  particular component and exit the menu"), pero es un caso a medida.

Y lo que la pelea de hoy deja afuera de sus 17 habilidades (pregunta 6 del
plan), con `habilidad_usable_en_batalla`:

    de a muchos       236 TillTheyGlow, 240 SwingingCut, 244 BioWarfare,
                      245 BombsAway, 251 MultiMissiles
    todo el grupo     253 RemoveStatus
    tocan estados     244, 247 HeadButt, 253 (los estados no existen)

**El SP de las armas**: en RM2k2000 atacar con un arma cobra su `sp_cost`
(ArmCannon 1, ArmLauncher 2, PortableNuke 5), y el tutorial lo explica. La
pelea no lo cobra; hacerlo es chico y va de los dos lados.

# Números a repartir

Si se hacen los eventos comunes paralelos: su RAM lejana. Si alguna habilidad
nueva necesita un opcode, uno.

# Pruebas

- Casos de pelea con una tropa de la planta: el enemigo usa `ShortCircuit` y
  el HP que deja es el que predice `batalla.py`.
- AG7 en el grupo con su arma: tiene la habilidad que corresponde, y la pierde
  si se cambia el arma y se sale del menú.
- El SP que cuesta un ataque de AG7.

# Qué tiene que mirar taro jugando

Pelear en la planta con AG7: su menú de "Components", las habilidades que
aparecen según la pieza, el SP que baja al atacar, y los enemigos que hacen
`ShortCircuit`.
