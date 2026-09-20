# Qué

**`ConditionalBranch`: cinco de las doce clases.** Switch, variable, oro,
objeto y actor, y de la de actor tres de sus siete preguntas —está en el grupo,
sabe la habilidad, tiene puesto el objeto—.

# Por qué

El criterio con el que se fueron sumando, de cuando sólo estaba la de switch y
sigue valiendo: **modelar una rama que nada ejercita es inventarse una
diferencia**. Con la de switch sola entraban 21 de las 24 páginas que el
comando destraba, y las tres que faltaban preguntaban por el héroe en el grupo,
que sin grupo variable daba siempre lo mismo.

# Cómo compila

A dos opcodes: `OP_IF` —switch, polaridad y destino— y `OP_GOTO`, el salto sin
condición que va donde estaba el `else`. **El destino es absoluto dentro de la
página**, así que en la ROM saltar es asignar el cursor; quién es ese destino lo
resuelve el conversor, que es el único que ve la página entera, emitiéndolo en
blanco y parcheándolo al cerrar la rama.

El anidamiento sale de una pila y no de mirar la indentación como
`SkipToNextConditional`: él recorre una lista lineal, acá los bloques ya vienen
anidados.
