---
name: "Rust: el dominio de la pelea"
description: "El modelo de la pelea, sus escenas, sus animaciones y su pantalla de texto (battle, battle_scenes, scene, animation, battle_animations, battle_screen) al crate rm2k-snes-battle, con las ROMs byte por byte iguales"
type: refactor
assignee: Cardón
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
