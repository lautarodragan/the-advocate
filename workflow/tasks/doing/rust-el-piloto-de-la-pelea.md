---
name: "Rust: el piloto del conversor, las tablas de pelea"
description: "El primer dominio del conversor en Rust: el crate rm2k-snes-battle con las tablas de experiencia y encuentros (battle_tables.py), llamado por el Python por el PATH, con las ROMs byte por byte iguales"
type: refactor
assignee: Surubí
---

Paso 4 del camino a Rust, con lo que se charló con taro el 2026-09-29:

- el conversor se migra **por etapas**, con el Python orquestando y
  llamando a cada etapa de Rust por el PATH, como `rm2k-render` y
  `rm2k-snes-audio`;
- en Rust queda **un crate por dominio**, porque Cargo no permite ciclos
  entre crates y así la frontera la hace cumplir el compilador; el
  orquestador (`rm2k-snes-convert`, más adelante) no tiene lógica de ningún
  recurso;
- el piloto es chico a propósito para fijar la forma: `battle_tables.py`
  (experiencia y encuentros) va a `tools/rm2k-snes/battle/`, el crate
  `rm2k-snes-battle`, que después va a recibir el resto de la pelea.
