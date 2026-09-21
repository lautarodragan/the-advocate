### El paquete de audio de cada mapa

La ARAM son 64 KB, y los instrumentos de los ocho temas de la demo son 53: los
efectos que piden el Linkage Block y el Emitter Room —43 y 55 KB— no entran ni
cerca. Por eso hay **un paquete por mapa**: al cargar uno se suben **los temas
que sus páginas pueden prender y los efectos que piden**, en el orden en que
aparecen, que es la prioridad si no entran todos. Cada tema
por separado son de 8 a 32 KB, así que en el Emitter Room entran sus dos temas,
los catorce efectos y el tema del mapa anterior, que sigue sonando.

Cómo está hecho:

* **Las muestras tienen número fijo en todo el cartucho**: las de la música y,
  detrás, las de los efectos. Es el SRCN que el stream de la música ya
  escribía, así que ni un byte del stream cambió. El directorio del SPC700
  tiene una entrada por muestra y **las que no están apuntan al silencio**, un
  bloque BRR de nueve bytes.
* **Qué muestras usa un tema** lo dice su stream: los valores que escribe en
  los registros SRCN (`muestras_del_stream`). El conversor emite esa lista por
  tema, y por mapa sus temas y las muestras de sus efectos (`paquetes`).
* **Las del tema que está sonando no se mueven**: la música sigue durante el
  fundido, y pisarle una muestra que está tocando sería ruido. Las que el
  paquete nuevo también quiere se quedan donde están, y las demás se sueltan.
  Lo que falta se acomoda en el primer hueco donde entre, recorriendo la lista
  de lo ocupado en orden (`paquete_cargar`, `colocar_muestra`).
* **El driver del SPC700 aprendió a escribir la ARAM**: tres comandos más en
  el puerto 2 —un byte, el puntero y un bloque de ternas— al lado del par del
  DSP de siempre. La música sigue mandando pares con el puerto 2 en cero, y la
  subida va en tandas de 85 ternas con las interrupciones cortadas, así que
  la música se atrasa un poco y no se pierde. Son unos 55 KB por segundo.
* **Un `PlayBGM` de un tema que el mapa no traía** —el del título, o uno de un
  evento común— calla la música, suelta todo y rearma el paquete con ese tema
  adelante: congela la imagen lo que tarde. Un efecto que no entró no suena.

Lo que cuesta: el fundido de un salto dura lo que tarda la subida. Del mapa 1
al Emitter Room son 58 cuadros perdidos, de los que unos 14 son la carga del
mapa de siempre: unas siete décimas de segundo de negro más.

Cómo se verifica, porque la tanda no mide audio: la ARAM se lee del estado
guardado del core —`retro_serialize`, ubicando el driver— y cada muestra que la
ROM dice tener se compara con la del cartucho byte por byte, con su entrada del
directorio. Y `pruebas/rpgmaker/test_musica_paquete.py` lo cobra solo: para el tema que la
ROM dice estar tocando, que cada muestra de su `tema_muestras` tenga entrada en
`FAR_ARAM_DE`. Hace falta una prueba de estado porque **el silencio no cambia un
pixel**, y el tema de la pantalla de título es el más expuesto: es el único que
ningún paquete trae —sale de `title_music` del LDB y los paquetes se arman con
los `PlayBGM` de cada mapa— así que depende por entero de ese camino.
