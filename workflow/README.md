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
- `tasks/wip/` tareas en progreso
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

`type` va siempre. `assignee` va sólo cuando la tarea **no** la puede tomar
cualquiera: `taro` para las suyas y para las que esperan algo de él —jugar,
mirar unas goldens—. Sin `assignee`, la toma quien llegue, que suele ser un
agente. Las de `done/` son de antes de estos campos y no los llevan.
