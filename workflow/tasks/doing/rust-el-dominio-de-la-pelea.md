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
