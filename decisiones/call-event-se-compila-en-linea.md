# Qué

**`CallEvent` se compila en línea** desde el 2026-09-12, sin pila de
intérpretes. Con eso el Hover-Tram del mapa 9 se puede tomar.

# Por qué

En RM2k es `Push<ExecutionType::Call>`, una pila de intérpretes; acá no hace
falta ninguna, porque el llamado corre entero antes de que siga el que llamó,
así que pegar su bytecode en el lugar da lo mismo. **Ninguna llamada de este
juego es recursiva**, medido, y el anidamiento se topa en `LLAMADA_MAX`.

Es la única de las cuatro piezas de esa vuelta que **no toca al intérprete**: lo
que cambia es el bytecode que se emite, no quién lo corre.

# Lo medido

**Cero páginas ganadas y cero perdidas** —2882 antes y después—, porque si el
llamado no compila la llamada se saltea, que es lo que el port venía haciendo.
Exigir que compilara costaría **183 páginas** de las 221 que compilan y llaman.

Se hacen de verdad **10 llamadas** en cuatro mapas —el 9, el 11, el 114 y uno
más— y se siguen salteando 216, casi todas a eventos comunes que se cortan en
`ControlVars` y en los menús propios del original: eso tiene su propio archivo
en `divergencias/llamada-salteada.md`.

El precio en cartucho es **+608 bytes de bytecode en todo el juego, +0,9%**, y
se lo llevan tres mapas: el 11 (+344), el 9 (+195) y el 114 (+69).
