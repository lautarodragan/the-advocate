# Qué

**La página de prueba se apaga sola**, prendiendo el switch 1023 en su primer
comando, con una segunda página vacía que lo pide. Su evento es el primer
índice libre del mapa y no un número alto.

# Por qué

Es el idioma con el que las páginas del juego se desactivan, y no lo
ejercitaba nada. Sin él, ahora que las automáticas se repiten, la página de
prueba reiniciaría su propia ruta para siempre.

Lo del índice: los barridos de la ROM van de cero a `ev_total`, así que un
número alto quedaría afuera.
