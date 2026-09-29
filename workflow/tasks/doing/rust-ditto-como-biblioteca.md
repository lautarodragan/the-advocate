---
name: "Rust: Ditto como biblioteca, y las reglas de RM2k"
description: "Un solo lugar en Rust que lee el volcado de data/ con tipos (la biblioteca de Ditto), y un crate rm2k-rules con las reglas de rpgmaker/rm2k.py; rm2k-render y rm2k-snes-battle dejan de leer el JSON a mano"
type: refactor
assignee: Zorzal
---

Paso previo al compilador de eventos en Rust, charlado con taro el
2026-09-29. Hoy `rm2k-render` (`source.rs`) y `rm2k-snes-battle`
(`game.rs`) leen el JSON del volcado a mano, cada uno con sus tipos; el
compilador de eventos y el resto del conversor van a necesitar mucho más.

Lo decidió Hornero:

- **La biblioteca de Ditto es el único lugar en Rust que sabe leer el
  volcado**, con tipos para lo que se usa. Ditto ya es biblioteca, pero con
  un modelo genérico dirigido por el esquema de liblcf.
- **Las reglas de RM2k van a un crate aparte, `rm2k-rules`**, en
  `tools/rm2k/`: lo que hoy hace `tools/rpgmaker/rm2k.py` (pasabilidad,
  capas, poses, gráfico de una página, translúcidos). Ditto es el formato;
  las reglas, lo que el formato significa.
- `rm2k-render` y `rm2k-snes-battle` pasan a usarlos.
