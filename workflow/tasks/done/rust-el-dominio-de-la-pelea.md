---
name: "Rust: el dominio de la pelea"
description: "El modelo de la pelea, sus escenas, sus animaciones y su pantalla de texto (battle, battle_scenes, scene, animation, battle_animations, battle_screen) al crate rm2k-snes-battle, con las ROMs byte por byte iguales"
type: refactor
assignee: taro
---

De taro, el 2026-09-30, en la migración del conversor a Rust: después de las
pantallas (Tataupá) va la pelea. `tools/rm2k-snes/battle/` ya tiene la
experiencia y los encuentros; lo que queda en Python es `tools/port/battle.py`,
`battle_scenes.py`, `scene.py`, `animation.py`, `battle_animations.py` y
`battle_screen.py` —este último es la pantalla de texto de la pelea que las
pantallas dejaron afuera—.

Sale de `main` en el commit que lanza la tarea. Ahí: `NO_CACHE=1 just
cartuchos` da `abl.sfc` `cdcc323197ee6c66…`, `special` `15e4f331fe8ff812…`,
`encounter-every-step` `dc83ed698b348032…`; `just pruebas` 878,
`just -f tools/justfile test` 49.

## Inventario: qué hace hoy el Python

Leído el 2026-09-30:

| módulo | qué hace | quién lo usa |
|---|---|---|
| `battle.py` | **las reglas** que la emisión escribe —qué habilidades sabe ofrecer la pelea (`skill_usable`, `skills_of`, `level_learned`, `skill_command_name`), qué acciones tiene cada enemigo (`actions_of_enemy`), qué ítems se ofrecen (`item_usable_in_battle`), el SP del arma, el oro de una tropa— y **el simulador**: `Rng`, `Combatant`, `Battle` y `TroopPage`, que juegan la pelea con el mismo azar que la ROM | `mapdata` (las reglas), y las pruebas de ABL (el simulador, turno por turno contra la consola) |
| `battle_screen.py` | la pantalla de texto de la pelea: la geometría (`BA_*`, las cinco órdenes), los renglones de la victoria y su chequeo de que entran, las órdenes recortadas, el texto del revivido, e `item_text` —la regla de las pantallas para escribir con su fuente— | `mapdata`, y las pruebas (`arnes/batalla.py`, `test_victoria.py`) |
| `scene.py`, `battle_scenes.py` | los fondos y los battlers: cuáles lleva el cartucho, sus píxeles —escalados con el `LANCZOS` de Pillow, reducidos con `palette.reduce` o `adeleine`— y sus bytes para el `.inc` y el `.msu` | `snes_convert`, `mapdata`, `msu_data`, las pruebas de la escena |
| `animation.py`, `battle_animations.py` | las animaciones de batalla: sus celdas por `rm2k-render`, el tono de la consola (`color.apply_tint`), el achique con `LANCZOS`, `palette.reduce`, y los cuadros para el `.inc` | `snes_convert`, `map_convert`, `obj_extras`, `mapdata`, `test_parches`, `test_animacion_cuadros` |

## La frontera

**Entra a `rm2k-snes-battle`: el modelo de la pelea y su pantalla de texto**
—`battle.py` y `battle_screen.py` enteros—. **Quedan afuera los dibujos de
la pelea** —`scene.py`, `battle_scenes.py`, `animation.py`,
`battle_animations.py`—: ver "Lo que queda afuera".

La etapa suma cuatro subcomandos a `tables`, que no cambia:

* **`model`**, el segundo llamado del conversor, después de compilar.
  **Recibe** lo que decidió el cartucho y lo que contestaron otros
  dominios: los actores que pueden estar en el grupo (`possible_members`),
  las tropas que pide el cartucho (las del compilador), los ítems que
  conoce (`items_rom`), los pares (actor, habilidad) del compilador
  (`events.SKILL_SLOT`, en el orden de su ranura) y el ancho del nombre de
  un ítem, que es de las pantallas. **Lee del volcado** los actores, las
  habilidades, los ítems, los enemigos, las tropas, los términos y los
  estados. **Devuelve** en `model.json`: la geometría de la pantalla
  (`layout`, con `BATTLE_SEED` y `ACTIONS_MAX`); los enemigos de las tropas,
  con sus acciones; las habilidades que lleva el cartucho y las que enseña
  subir de nivel; en qué nivel enseña el LDB cada par; qué ítems se ofrecen
  en la pelea; el oro y la experiencia de cada tropa; y los textos que la
  pelea escribe, ya recortados —los renglones de la victoria, las órdenes,
  el de cada actor para su habilidad, el revivido, los nombres de enemigos
  y habilidades—. Y dice que no si la victoria no entra en su ventana o un
  enemigo trae más acciones de las que pesa la ROM.
* **`simulate`**, para las pruebas: una pelea —actores con su equipo, su
  nivel y sus habilidades si se las cambia; enemigos sueltos o una tropa;
  la semilla, las páginas de una tropa y sus switches— y una lista de
  pasos —empezar, un turno con sus órdenes, huir, una acción de enemigo,
  poner HP—; contesta el estado entero al final y lo que devolvió cada
  paso. Las pruebas de ABL lo piden por `rom/pruebas/arnes/modelo.py`, que
  guarda los pasos y vuelve a jugar la pelea cada vez que hay que mirarla:
  es determinista, y así la etapa no guarda estado entre llamados.
* **`lines`**, para las pruebas: los renglones de la victoria armados como
  los arma la ROM —"90 EXP", "Kersh LEVEL 21 achieved!"—.
* **`layout`**: la geometría sola.

**La emisión sigue en Python** (`mapdata`): lee de `model.json` lo que hoy
le pregunta a `battle.py` y a `battle_screen.py`, y los campos crudos del
LDB —el HP de un enemigo, el costo de una habilidad— los sigue leyendo de
`lcf`, como hoy: son datos, no reglas. `item_text`, la regla de las
pantallas con que la emisión escribe todos sus textos, pasa a
`screen_stage.py`, que es donde vive lo de las pantallas del lado de
Python.

**El compilador de eventos no se duplica**: las páginas de tropa las
compila `rm2k-snes-events`, y lo que la etapa lee de ellas es sólo lo del
simulador —cuándo corre una página y qué `ShowHiddenMonster`,
`ControlSwitches` y ramas de switch tiene—, que el compilador no modela.

**Las reglas de RM2k que ya usan otras etapas** —el parámetro de un actor en
su nivel, el equipo sumado— se copian adentro de la etapa, como las tiene
`rm2k-snes-screens` en su `texts.rs`: pasarlas a `rm2k-rules` es tocar
otras dos etapas, y queda anotado.

## Lo que queda afuera

* **Los dibujos de la pelea**: los fondos, los battlers y las animaciones.
  Los tres pasan por el escalado de Pillow (`LANCZOS`) y por
  `palette.reduce`, que son los mismos de `palette.convert` —el título, el
  Game Over, las imágenes—, y las animaciones además por `color.apply_tint`,
  que es el del tinte de la pantalla. Llevarlos sin eso sería mudarlos a
  medias: el escalado tiene que pasar primero, para todos juntos. Lo que no
  es de píxeles —cuáles fondos y battlers van, `patch_uses`, el formato de
  sus bytes— se queda con ellos, porque sin los píxeles no hace nada.

## Hecho

**El modelo de la pelea y su pantalla de texto están en Rust**, en
`rm2k-snes-battle`, y `battle.py` y `battle_screen.py` se borraron. Las
tres ROMs y todo `rom/build/` salen byte por byte iguales a los de `main`;
la única diferencia es de la prosa del último commit, en los `.dbg`: ver
abajo. Los dibujos de la pelea siguen en Python: ver "Lo que queda
afuera".

| commit | qué |
|---|---|
| `254a53a3` | la tarea: inventario y frontera |
| `e9441441` | la etapa con `model`, `simulate`, `lines` y `layout`; `snes_convert` la llama por `port/battle_stage.py` y `mapdata` escribe lo que contesta; las pruebas de ABL piden la pelea por `rom/pruebas/arnes/modelo.py` |
| `ee79eefe` | las pruebas del crate contra los hashes del Python, con su juego chico en `tests/game/` |
| `382c046c` | el borrado, sólo borrado |
| `cd570252` | la prosa que nombraba lo borrado —el runtime, `mapdata`, `lcf`, las pruebas, `tools/README.md`, `AGENTS.md`— |
| `a784774c` | merge de `main` (`0cb3625c`) |

**El crate** suma a `tables`, que no cambió:

* `db.rs`: la base como la lee la pelea —actores, habilidades, ítems,
  enemigos, estados, términos y, sólo si el pedido nombra una, las
  tropas, que son casi toda la base—;
* `rules.rs`: lo que RM2k dice de la base, recortado a lo que hace esta
  pelea —qué habilidades ofrece y a quién, qué hace cada enemigo, qué
  ítems van en la lista, el SP del arma, lo que da una tropa—;
* `screen.rs`: la geometría de la pantalla y los textos —las órdenes,
  los renglones de la victoria, el revivido— y el chequeo de que entran;
* `simulate.rs`: la pelea turno por turno —el azar, los combatientes, las
  páginas de tropa—, con cada fórmula nombrando su función de easyrpg;
* `model.rs`: los pedidos y las respuestas de `model`, `simulate` y
  `lines`. Su README dice la forma de cada uno.

Del lado de Python queda `port/battle_stage.py` —el pedido de `model`—,
`item_text` pasó a `port/screen_stage.py`, y las pruebas tienen
`arnes/modelo.py`, con los mismos nombres del modelo de antes
(`Battle`, `play_turn`, `actor_of`), que guarda los pasos y vuelve a jugar
la pelea entera cada vez que hay que mirarla.

**Lo que cambió de la frontera planeada**: nada de fondo. Dos cosas que
no estaban escritas:

* **`CheckTurns` dejó de probarse en las pruebas de ABL**: era
  `modelo._turns`, una función del modelo que la prueba llamaba directo.
  Los cuatro casos pasaron al crate (`check_turns_is_easyrpgs`), y la
  prueba de los Lazer Teeth espera los turnos 1 y 4 escritos.
* **Las órdenes con ítem o habilidad llevan su número**, no el objeto de
  `lcf`; y la tropa de una pelea va por número (`troop=`, `pages=`).

## Cómo se verificó

Con scripts descartables en `<scratchpad>/cardon/`:

* **`compara_model.py`**: lo que `mapdata` le preguntaba a `battle.py` y
  a `battle_screen.py`, contra `model`, en 41 juegos de entradas sobre el
  juego entero —todos los actores, tropas e ítems, y cuarenta al azar con
  pares (actor, habilidad) de más—, y la geometría nombre por nombre:
  igual.
* **`compara_simulate.py`**: 5500 peleas al azar sobre el juego entero
  —con ataques, defensas, huidas, ítems, habilidades, acciones de
  enemigo sueltas, HP puestos a mano, páginas de tropa con sus switches—,
  el estado entero de cada combatiente y lo que devolvió cada paso:
  iguales, y las que el Python rechazaba, rechazadas.
* **`referencia.py`**: el juego chico de las pruebas del crate y los
  hashes del Python —400 peleas, 1808 turnos, 30 que se niegan; 26
  modelos; los renglones de la victoria—, que ahora son
  `cargo test -p rm2k-snes-battle`.
* **Los cartuchos**: `NO_CACHE=1 just cartuchos` y el sha256 de todo
  `rom/build/` —1032 archivos, sin el caché, los `.o`, `sello.txt` ni
  `conversor.log`; el `.dbg` sin `mtime`; los PNG decodificados—, iguales
  a la base después de cada commit hasta el borrado. Después de la prosa,
  iguales salvo los tres `.dbg`, que nombran el tamaño de los fuentes del
  runtime: con los tamaños de antes dan el mismo sha256
  (`verifica_dbg.py`); los comentarios se reescribieron sin cambiar
  cuántos renglones tiene cada archivo, así que ninguna línea se corrió.
* **Los sha256 de las ROMs**, iguales en `main` y acá, también después
  del merge:
  * `release/abl.sfc` `cdcc323197ee6c66d82b1304ce20c3c37f4124d13a6867e851fd13226046b7df`
  * `tests/special/prueba.sfc` `15e4f331fe8ff8123803ae3819a2212a5b84d71cd0a053b7261a9188bbab84b9`
  * `tests/encounter-every-step/prueba.sfc` `dc83ed698b348032514dbb76eaf5f535b6296944075fcba786087533ed5b8a4b`
* **Las tandas**, después de cada commit y sobre el merge: `just pruebas`
  878, `just -f tools/justfile test` 49, `cargo test -p rm2k-snes-battle`
  en verde.

## Al mergear

* Instalar en el global `battle`: `just -f tools/justfile install
  battle`. Sin el `rm2k-snes-battle` nuevo el conversor para en el
  segundo llamado —el viejo no sabe `model`— y las pruebas de la pelea
  también.
* `install-scripts` no hace falta: se agregaron y se borraron módulos
  (`port/battle_stage.py`, `rom/pruebas/arnes/modelo.py`), no programas,
  y ningún symlink del global apunta a ellos.
* No mueve la ROM ni goldens.

## Lo que queda afuera

* **Los dibujos de la pelea**: los fondos, los battlers y las animaciones.
  Los tres pasan por el escalado de Pillow (`LANCZOS`) y por
  `palette.reduce`, que son los mismos de `palette.convert` —el título, el
  Game Over, las imágenes—, y las animaciones además por `color.apply_tint`,
  que es el del tinte de la pantalla. Llevarlos sin eso sería mudarlos a
  medias: el escalado tiene que pasar primero, para todos juntos. Lo que no
  es de píxeles —cuáles fondos y battlers van, `patch_uses`, el formato de
  sus bytes— se queda con ellos, porque sin los píxeles no hace nada.

## Lo que falta

* **Los dibujos de la pelea**, de arriba: `scene.py`, `battle_scenes.py`,
  `animation.py` y `battle_animations.py`, después del escalado.
* **Los actores no tienen crítico, ni en la ROM ni en el modelo, y el LDB
  dice que sí.** El modelo de Python leía `critical_hit` con un `getattr`
  que siempre caía en el default —`lcf.Actor` no guarda el campo—, y
  `battle.s` pone `BA_CRIT` en cero con el comentario "no actor in ABL has
  a critical hit". El volcado dice lo contrario: Kersh, Core, Manta,
  Talan, Arden y AG7 tienen `critical_hit` prendido, la mayoría con
  `critical_hit_chance` 30. Los dos lados se equivocan igual, así que
  ninguna prueba lo ve. Se conservó —con un comentario en
  `Combatant::actor`—, porque arreglarlo mueve la ROM y el azar de todas
  las peleas: es de otra tarea, y habría que medirlo contra el original.
* **Las reglas del actor están tres veces en Rust**: el parámetro en su
  nivel y el equipo sumado viven en `rm2k-snes-battle` (`rules.rs`), en
  `rm2k-snes-screens` (`texts.rs`) y, en Python, en `port/rules.py`, que
  todavía usan la emisión y el compilador. Su lugar es `rm2k-rules`; no se
  movieron para no tocar otras dos etapas.
* **`lcf` guarda campos que sólo leía `battle.py`**: `Enemy.actions` y
  `EnemyAction`, `Actor.rename_skill` y `skill_name`, `Skill.id`. Quedaron
  sin uso; se pueden borrar.
* **Una pelea de las pruebas se vuelve a jugar entera en cada turno**:
  cuesta un proceso por turno —diez milisegundos, noventa con una tropa,
  que son casi toda la base—, y ninguna prueba juega más de treinta.
