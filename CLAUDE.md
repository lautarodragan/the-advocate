@AGENTS.md

Las reglas de este repo viven en `AGENTS.md`: **ése es el archivo de verdad**, y
es el que leen las demás herramientas. Este existe sólo porque Claude Code lee
`CLAUDE.md` y nada más —no sabe abrir `AGENTS.md`, ni se lo puede configurar—;
la línea de arriba lo importa, que es la forma que la documentación oficial da
para este caso. Si alguna vez hace falta algo específico de Claude Code, va acá
abajo, y no allá.

Hasta el 2026-09-12 esto era un symlink, y se prestó a exactamente la confusión
que este párrafo evita: editar `CLAUDE.md` dejaba `AGENTS.md` modificado en git,
los dos parecían archivos distintos desincronizados, y se commiteó un mensaje
que decía eso y era falso.
