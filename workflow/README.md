# Dónde quedamos

Lo que existe **sólo mientras alguien trabaja**: qué se decidió y sigue
valiendo, qué espera respuesta de taro, qué no se probó todavía, qué no cubre
la tanda, y hacia dónde vamos.

Lo que **no** va acá: el relato de lo hecho. Eso está en `git log`, que en este
repo tiene mensajes largos justamente para eso, y lo durable está en
`README.md`. Este archivo llegó a tener dos mil líneas por append-only y se
volvió inusable; se borra sin culpa lo que ya esté en esos dos lados.

Se escribe **mientras se trabaja**, no al final.

Los siguientes sub-directorios tienen la misma estructura:
- un _item_ por directorio
- cada directorio tiene un propósito

Estos son:
- `wishlist/` es lo que nos gustaría hacer y nadie está haciendo
- `divergencias/` es dónde la ROM no hace lo que RM2k hace, con lo medido y cómo reproducirlo; 
- `decisiones/` son las decisiones tomadas que siguen valiendo, las que hay que conocer para no
rehacerlas ni contradecirlas.
- `tareas/` son las tareas que aún quedan pendientes de tomar, o que están en progreso
