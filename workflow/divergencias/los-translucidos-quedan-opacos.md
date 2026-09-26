# Qué

El "Trans" de RM2k dibuja el evento al 160 de 255 sobre lo que haya detrás. Acá
esa mezcla se calcula al convertir y queda **horneada** en el gráfico, que es
exacto en la foto y opaco en movimiento. Por qué se puede está en
`decisiones/los-translucidos-van-horneados.md`.

Lo que se pierde:

* **Nadie se ve por detrás**, ni el héroe ni otro evento.
* **Si detrás hay un tile animado, la mezcla vale para un dibujo solo.**
* **Dos eventos con el mismo CharSet sobre fondos distintos son dos
  gráficos**, y por lo tanto dos paletas.

# Medido

El 2026-09-12, sobre las 39 páginas horneables de los 35 mapas con
translúcidos:

* cuatro se superponen con el sprite de otro evento —mapas 74, 152 y 305—, y
  ahí la mezcla es contra el piso y no contra el vecino;
* dos están sobre agua —los save points de los mapas 59 y 178—, que adentro del
  cuadro de 24x32 del sprite queda quieta;
* sólo tres mapas cambian de paletas y **ninguno se cae**: el 9 pasa de siete a
  ocho, el 117 de seis a siete, y el 37 suma un gráfico con paleta ajena.

# Cómo se ve hoy

Un fuego sobre un barril o un save point se ven igual que en RM2k. El Kersh
translúcido del mapa 305, que se superpone con un Guard, lo tapa.

# Cuándo deja de alcanzar

Un translúcido que camine, o uno parado sobre algo que se mueva. En este juego
no hay ninguno; en otro, la salida es el color math.
