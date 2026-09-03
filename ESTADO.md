# Dónde quedamos

Lo que existe sólo mientras alguien trabaja: qué está a medias, qué se cree sin
haberlo corrido, y qué se dejó afuera a propósito. Todo lo durable va al
`LEEME.md` de cada port y a los mensajes de commit, que en este repo son largos
justamente para eso.

Se escribe **mientras se trabaja**, no al final. Un resumen escrito al cerrar
es la misma operación con pérdida que compactar, sólo que a un archivo.

Última vez que se tocó: 2026-09-03.

## En vuelo

Se está tapando la lista de más abajo: supuestos escritos de los dos lados y
corridos de ninguno. Cerrado el primero, **la prioridad de objeto contra la capa
de encima**, con tres casos nuevos en `snes-hitos` y una receta `snes-encima`.

El hito 12 —el intérprete de eventos— quedó cerrado de los dos lados el
2026-09-02, en `f337a02` y `fe2767d`.

    just snes-hitos    49 comparaciones, todas en 0 pixeles de 57344

El corte siguiente que se propuso, sin empezar: **la cinemática de apertura**.
El mapa 4 ya prende el switch 20, que es la condición de la página que abre el
mapa 1, así que el enganche funciona. Falta que exista un grupo —la condición
pide `actor`— y cuatro comandos: `PlayBGM`, `WeatherEffects`, `MoveEvent` y
`ChangePartyMembers`. Mientras tanto el héroe queda parado adentro del caño,
que es donde RM2k también lo deja.

Después del hito, el mismo día, se armó la documentación de proceso: este
archivo y `AGENTS.md` en `92509fc`, y el contenedor y `snes-tinte` en `d7597cc`
y `2cc8078`. Nada de eso toca la ROM.

Dos cosas cambiaron del lado de taro, en su `box`, y no se ven desde el repo:
sacó el montaje de sólo lectura de `/home/taro/git/gaming/abl-rm`, que no usaba
nadie, y pasó a `--rm --replace --name` para que los contenedores dejen de
acumularse. Si algo del entorno se ve distinto a lo que dice `AGENTS.md`, es
por ahí.

## Lo que se cree y no se corrió

Esta sección existe porque el commit `c64e4d9` decía "Verificado" sobre un
camino que ninguna prueba ejecutaba, y eso costó tres errores encadenados. Un
commit narra lo hecho; los supuestos no tienen dónde vivir. Acá.

* ~~**`OBJ_PRIORITY_ABOVE = $20`.**~~ Cerrado el 2026-09-03. La respuesta
  resultó ser que con los datos del juego **no se puede** ejercitar: se
  relevaron los 335 mapas y hay un solo evento con gráfico en esa capa —el
  Package del mapa 261— y la capa de encima de ese mapa no llega a pisarlo por
  dos pixeles. Donde no hay capa de encima, las prioridades 1 y 2 dibujan lo
  mismo. Así que la prueba pasa por el héroe: `snes-encima` lo sube a prioridad
  2 en una celda donde la capa lo tapa a medias, que es el mismo byte de
  atributos y el mismo `emit_object` que usaría un evento "above". Los dos
  lados coinciden en 0, y las dos referencias —prioridad 1 y prioridad 2—
  difieren en 284 pixeles, o sea que el par no da cero por casualidad. El
  Package igual entró en la tanda, por el orden capa-antes-que-Y. Ver "Cómo se
  verifica" en `snes/LEEME.md`.
* **El orden de la tabla de mapas.** La referencia ahora la recibe entera, y es
  necesario porque un teletransporte compilado guarda el índice y no el número
  de mapa. Pero ningún mapa de `snes-hitos` teletransporta por evento salvo el
  4, y ahí la tabla tiene dos entradas: equivocarse de orden no lo detectaría
  ninguna prueba actual.
* **El tope de ocho saltos.** La referencia modela el `dec/beq` de la ROM, que
  se queda en el mapa donde estaba. Nada encadena ocho teletransportes, así que
  el caso límite está escrito de los dos lados y corrido de ninguno.
* **La guarda de la paleta vacía** en `tenir_paleta`. Se puso porque el
  conversor emite `SPRITE_CGRAM = 0` cuando un mapa no declara sprites. No se
  relevaron los 335 mapas para ver si alguno lo hace de verdad.
* **Las 29 páginas que compilan a puro `FIN`.** Se asume que no se ven porque
  todos sus comandos son de los "ignorables". Es por construcción, no por
  medición mapa por mapa.

## Lo que se dejó afuera a propósito

* **Que un NPC frene al héroe.** La referencia tampoco lo modela, y es a
  propósito: modelar de este lado algo que la consola no hace inventa una
  diferencia. Los dos lados se mueven juntos o ninguno.
* **La saturación del tinte.** El conversor sólo deja pasar la neutra, así que
  una página que la use no se emite. Aceptarla sin aplicarla sería el error de
  siempre: la referencia haría lo mismo mal.
* **Los builds numerados de `snes/build/`.** No están en git y no los produce
  ninguna receta salvo el 12. Armar uno a mano es cómo se terminó mirando el
  mapa 6 creyendo que era la demo del hito 12 —ver `AGENTS.md`—.
