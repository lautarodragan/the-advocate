---
name: "Rust: Adeleine"
description: "tools/port/adeleine.py (qué colores se pierden y cómo se agrupan en paletas) como crate propio en tools/snes/, al lado de Voodoo, con las ROMs byte por byte iguales"
type: refactor
assignee: Tucán
---

De taro, el 2026-09-29: empezar por Adeleine a Rust. Ya decidido
(`workflow/decisiones/las-herramientas-se-separan-de-abl.md`): Adeleine es
un crate propio en `tools/snes/`, al lado de Voodoo y no adentro, porque
Voodoo no decide colores (AGENTS.md). No sabe nada de RPG Maker: colores,
tiles y el límite de 16 por paleta. Es el paso antes de que `rm2k-render`
sume los CharSets.
