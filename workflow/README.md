# Estado del Trabajo

Esta carpeta es una especie de Jira casero, con un par de cosas
extra que no son tareas pero sí están relacionadas al output
de tareas.

Los siguientes sub-directorios tienen la misma estructura:
- un _item_ por directorio
- cada directorio tiene un propósito

Estos son:
- `divergencias/` es dónde la ROM no hace lo que RM2k hace, con lo medido y cómo reproducirlo; 
- `decisiones/` decisiones tomadas que no son "obvias" o no se pueden inferir del código y tareas
- `tasks/` son las tareas que aún quedan pendientes de tomar, o que están en progreso
- `tasks/todo/` tareas no empezadas
- `tasks/doing/` tareas en progreso: quien la toma la pasa acá antes que nada
- `tasks/testing/` hechas y a la espera de que taro las pruebe jugando
- `tasks/done/` tareas terminadas
- `tasks/wishlist/` es lo que nos gustaría hacer y nadie está haciendo

## El frontmatter de una tarea

    ---
    name: "Título corto"
    description: "Una línea: qué es, para la lista"
    type: bug | feature | refactor | test | docs
    assignee: taro
    ---

`type` va siempre. `assignee` dice quién la tiene: `taro` para las suyas y para
las que esperan algo de él —jugar, mirar unas goldens—, y el nombre del agente
para las de `doing/`. Ver "Tomar una tarea" en `AGENTS.md`. En `todo/`, sin
`assignee`, la toma quien llegue. Las de `done/` son de antes de estos campos y no los llevan.

**Acá se trackea todo, también lo de A Blurred Line**: su contenido, sus
pruebas, sus recetas, lo que lleva su cartucho. Del 2026-10-02 al
2026-10-10 sus tareas y sus decisiones vivieron en su repo; ese día
volvieron, por pedido de taro, "para trackear todo en un solo lugar", y su
repo se quedó sin `workflow/`. Un `workflow/…` escrito en un comentario de
ABL es éste.
