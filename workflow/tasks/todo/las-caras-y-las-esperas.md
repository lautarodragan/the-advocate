---
name: "Dibujar las caras y esperar de verdad en los escapes"
description: "Hoy ChangeFaceGraphic se acepta sin dibujar la cara, y los escapes \\. \\! \\| en mitad de una caja se descartan sin esperar. Hacerlos de verdad"
type: feature
agents: [Tijereta]
---

Deuda que dejó `testing/las-caras-y-los-escapes-de-espera.md`.

* **Caras**: `ChangeFaceGraphic` (10130) está en `ACCEPTED_UNDONE` del compilador de eventos y no hace nada; la caja sale sin cara. Al hacerlo, sacarlo de esa lista.
* **Esperas**: en RM2k `\.` espera un cuarto de segundo, `\|` un segundo y `\!` una tecla. La ROM sólo sabe esperar `\|` al final de la caja (el cabezal con las pausas); en el medio, `without_waits` de `tools/rm2k-snes/text/src/refit.rs` los descarta. Hacerlo de verdad pide que la caja se dibuje por tramos.
