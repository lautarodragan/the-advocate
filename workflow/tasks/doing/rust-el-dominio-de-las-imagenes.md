---
name: "Rust: el dominio de las imágenes"
description: "El escalado y la reducción de colores de las imágenes (palette, picture, title, Game Over, fondos de batalla) y, sobre eso, los dibujos de la pelea (scene, battle_scenes, animation, battle_animations) a Rust, con las ROMs byte por byte iguales"
type: refactor
assignee: Lapacho
---

De taro, el 2026-09-30, en la migración del conversor a Rust. Es lo que
dejaron afuera las pantallas (Tataupá) y la pelea (Cardón), por la misma
razón: el escalado LANCZOS de Pillow, `palette.reduce` y `color.apply_tint`
los comparten las imágenes de los mapas (`picture.py`), el título, el Game
Over, los fondos de batalla que van por MSU-1 (`msu_data.py`), las escenas
de la pelea (`scene.py`, `battle_scenes.py`) y sus animaciones
(`animation.py`, `battle_animations.py`). Se mudan juntos, empezando por el
escalado.

Sale de `main` en el commit que lanza la tarea. Ahí: `NO_CACHE=1 just
cartuchos` da `abl.sfc` `241dc9ad2bf8b43c…`, `special` `63779e111ee18923…`,
`encounter-every-step` `200a0b7355289700…`; `just pruebas` 882,
`just -f tools/justfile test` 49.
