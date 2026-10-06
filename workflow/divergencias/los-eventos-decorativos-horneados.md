# Qué

Con `[graphics] decorative_events = true`, un evento que es sólo un dibujo
—una página, sin comandos ni condiciones, con CharSet, sin movimiento propio y
que **nadie nombra**— se pinta en el fondo y **deja de ser un evento**: no
tiene fila, ni ranura, ni página en la tabla. Lo que cambia respecto de RM2k:

* **El ritmo de la animación es el del agua del ChipSet, no el de la
  velocidad del evento.** RM2k lo recorre en el ciclo 0, 1, 2, 1 al ritmo de
  `move_speed`; acá es la familia `water`, que cambia cada `WATER_FRAMES`. El
  ciclo es el mismo; el paso, no.
* **Todos arrancan en la misma fase.** En RM2k cada evento arranca en la
  columna de su `character_pattern`; acá el cuadro 0 de la familia es la
  columna 0 de todos.
* **Una translucidez que no entra mezclada se tramea.** Mezclar cada
  cuadro del evento con lo que tiene detrás agrega colores de más al fondo
  —el río de Weg, 100—; si eso le cuesta al suelo más de
  `GROUND_LOST_MAX` píxeles de sus propios colores, los translúcidos pasan a
  la trama (`five_of_eight`) que ya usan los sprites. Y si ni así entra, esos
  eventos siguen siendo objetos.
* **Un decorativo de la capa de abajo queda siempre bajo los objetos**,
  también bajo un objeto de su misma capa que esté más arriba en pantalla;
  RM2k los ordena por y.
* **Sólo los de la capa de abajo y los de la del héroe cuyo dibujo no se sale
  de su celda.** Uno que se sale se dibujaría detrás de un héroe parado en la
  celda de abajo, que lo tapa en RM2k. Los de la capa de arriba siguen siendo
  objetos.
* **El bloqueo pasa a la grilla.** Uno en la capa del héroe cierra su celda en
  la pasabilidad del mapa; ya no es un evento que bloquea sino una celda
  cerrada, así que tampoco lo cambia nada en la partida.

# Medido

Weg, mapa 95 de Vampires Dawn, con el agua de 183+24 eventos `water1`
translúcidos: 188 pasan a ser fondo, 59 quedan como objetos (los que
EV0016 mueve, las cascadas con giro, los de capa de arriba y los que tienen
condiciones). Tiles de sprite: 4096 antes, 960 después; de fondo, 327 antes y
394 después, 107 de ellos en la corrida del agua.

# Cuándo deja de alcanzar

Un fondo con la paleta llena —Uruya, mapa 165, con 8— no recibe ni un
color más sin perder los suyos, y sus decorativos siguen siendo objetos.

# Cómo reproducirlo

`wally map` sobre el request del mapa con `"decorative": true`.
