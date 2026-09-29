# Qué

**Los eventos disparan con dos bits cada uno, no con una cola.** Es el
`waiting_execution` de `Game_Event`: `FLAG_AUTO` dice si la página activa del
evento es una automática que compiló, y `FLAG_WAIT` si tiene una página
esperando turno —la haya puesto el barrido de las automáticas, la tecla de
acción o un contacto—.

# Por qué

Reemplazó a una cola de ocho punteros que se llenaba y descartaba, y que
pasada la octava interacción leía sus propios contadores como bytecode.

De ahí salen dos cosas que antes no pasaban, y que hay que tener presentes al
escribir una página: **una automática se repite** mientras siga siendo la
activa, y **una que se vuelve activa con el mapa ya cargado arranca**. Lo
segundo es lo que dejaba muerta la segunda mitad del recuerdo de CORE y MANTA.
