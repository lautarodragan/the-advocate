# Qué

Un evento que se dibuja con un tile del ChipSet, es **completamente opaco** y
tapa entero el tile que tiene debajo, no necesita dibujarse como evento: puede
formar parte del mapa. El evento sigue existiendo para su lógica —dispararse,
cambiar de página, ser un blanco—; lo que se ahorra es dibujarlo.

A nivel conceptual, no necesariamente implementado así.

# Status

Por hacer. Debería ser barata.

# Por qué

Sale del **HQ de los Lazer Teeth (mapa 11), que laggea**. Ya se le aplicaron
varias optimizaciones y sigue siendo el mapa más apretado del juego: es el que
usa `pruebas/rpgmaker/test_paralelos.py` para medir si el cuadro entra, y el
que queda al borde en las mediciones de presupuesto.

Lo que cuesta un evento dibujado, y que esta regla evita: su fila de OAM, su
paso por el compositor de sprites, y la presión sobre el banco de sprites y
sobre las paletas —un CharSet que entra al banco se lleva una de las ocho
paletas de sprite—.

# Qué hay que cuidar

* **Que tape de verdad**: el gráfico tiene que ser opaco en las 16x16 (o lo que
  ocupe) y no dejar ver nada del tile de abajo.
* **Que no cambie**: si alguna página del evento cambia su gráfico, o el evento
  camina, o su página activa depende de una condición, el dibujo no es fijo.
  La condición fácil y segura: el evento tiene una sola página, sin ruta y sin
  comandos que cambien su gráfico.
* **La capa y la prioridad**: un evento "encima" no se puede hornear en la capa
  de abajo sin cambiar qué tapa a qué.
* **Los tiles animados**: si el tile del ChipSet que usa está en una corrida
  animada, hornearlo lo hace animar con el mapa, que puede ser lo correcto o no.
* **La interacción no cambia**: el evento se sigue emitiendo en la tabla de
  páginas; lo único que no se emite es su dibujo.

# Cómo se verifica

* Las goldens del mapa 11 y de los demás mapas con eventos así **no se mueven**:
  se ve igual, se dibuja distinto.
* `test_paralelos` mide los cuadros perdidos del mapa 11: ahí se ve la ganancia.
* Cuántos eventos del juego caen en la regla, medido antes de implementar.
