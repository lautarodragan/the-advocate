---
name: "Sin resample: el escalado con una biblioteca de Rust"
description: "resample (el LANCZOS de Pillow bit por bit) y el bilineal de rm2k-render imitaban a Pillow para que la migración no moviera la ROM; con el Python ido, los dos pasan a una biblioteca estándar de Rust, aunque eso mueva píxeles"
type: refactor
assignee: Corbatita
---

De taro, el 2026-10-02: "me gustaría eliminar resample. No hay necesidad de
mantener compatibilidad con Python. Estuvo bien para la migración, pero
prefiero simplificar el pipeline y que los binarios que necesiten aplicar
transformaciones de imágenes usen alguna librería estándar o popular de
Rust".

Lo usan `rm2k-snes-images` (`pixels.rs`: título, Game Over, imágenes
grandes, fondos y battlers, animaciones, `ShowPicture` con zoom) y, con su
propio escalador bilineal, `rm2k-render` (`src/resample.rs`,
`battle_animation.rs`). Cambiar el escalador mueve goldens de ABL, que desde
hoy viven en su propio repo.
