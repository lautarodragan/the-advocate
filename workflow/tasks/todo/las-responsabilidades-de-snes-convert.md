---
name: "Las responsabilidades de snes_convert.py"
description: "Un archivo de ~8.200 líneas y ~140 funciones: repasar qué hace y partirlo por responsabilidad"
type: refactor
---

`tools/port/snes_convert.py` es enorme (cuántas líneas y funciones: `wc -l` y
`grep -c '^def '`). taro quiere repasar sus responsabilidades, el
2026-09-26, sin urgencia.

Primero un inventario: qué partes tiene (la conversión de mapas, gráficos,
paletas, eventos, audio, el reparto de la VRAM, la escritura de los `.inc`,
los casos de prueba, la línea de comandos, …), cuáles ya tienen su módulo
(`eventos.py`, `escena.py`, `asignador.py`, `batalla.py`, `tools/audio/`) y
qué quedó en el archivo grande que es de otra cosa. Después, una propuesta de
partición con el criterio del corte de `main.s`: primero lo mecánico (mover
sin cambiar), verificado con los cartuchos byte por byte iguales, y después
lo de criterio.

**Va después de la optimización de tiempo del conversor** (en curso el
2026-09-26), que no tiene que refactorizar nada para no mezclar las dos
cosas.

Relacionado: taro quiere que todas las herramientas terminen en Rust, no por
velocidad; cuando se encare eso se decide qué partes tienen sentido.
