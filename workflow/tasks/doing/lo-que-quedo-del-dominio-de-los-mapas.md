---
name: "Lo que quedó del dominio de los mapas"
description: "Los cabos sueltos que dejó Mara al pasar los mapas a Rust"
type: refactor
---

De `testing/rust-el-dominio-de-los-mapas.md` (Mara, 2026-09-30):

- que `rm2k-snes-events scan` conteste los blancos de ruta de cada página,
  así `movable_events` sale de Python;
- los repartos de VRAM (`tools/port/vram.py`) en un solo lado: hoy los leen
  las pantallas y la emisión;
- la regla de los colores del cronómetro está dos veces: `timer_colors_of`
  en Python y `timer_colors` en `extras.rs`;
- sacar `voodoo` de la huella de `cartridge`: el conversor ya no corre el
  binario, la etapa de mapas lo usa como biblioteca (entra por el binario
  de `rm2k-snes-maps`);
- decidir si `rm2k-snes-maps layers` se queda: hoy sólo lo usan sus
  pruebas;
- el camino de los translúcidos tramados (`TRANSLUCENT_MODE=dither`) está
  portado pero ningún cartucho lo ejercita;
- los avisos de clippy de los tres crates.
