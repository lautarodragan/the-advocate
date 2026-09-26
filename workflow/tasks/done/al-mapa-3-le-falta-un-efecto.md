---
name: "Al mapa 3 le puede faltar un efecto"
description: "No le falta ninguno: el paquete llega incompleto, pero lo que falta no se pide hasta que el PlayBGM de evilrhys lo completa"
type: bug
---

# Qué

**Hay que investigarlo.** Puede ser que al entrar al mapa 3, el Emitter Room,
desde el 2, su paquete de audio no entre entero en la ARAM y se le caiga el
último efecto.

# De dónde sale

De la investigación de `efectos-de-sonido-sin-recortes.md`, el 2026-09-24.
**Es una cuenta, no algo medido en la ROM**: un sub-agente sumó los tamaños del
`musicdata.inc` de `abl`.

* el paquete del mapa 3, música más efectos, era de los dos más pesados del
  juego;
* durante el fundido del salto 2→3 sigue fija en la ARAM la muestra del tema
  que venía sonando, `TF3_1_awe`;
* sumados, pasaban el espacio que hay para muestras por unos 2,5 KB.

# Lo que se midió, el 2026-09-26

Contra `main` en `b581d4e`, que ya trae los efectos enteros (`4c2fa8e`), el
tema que gana y los temas de salida. Hasta `4939386` nada del audio cambió.
Sin MSU-1 y con MSU-1, en `release`, con un script descartable que anota cada
cuadro qué muestras del paquete del 3 hay en `FAR_ARAM_DE`, qué tema suena,
`PAQ_INCOMPLETO`, los efectos que arrancan en las dos voces (`SE_CUADROS` que
vuelve a subir) y los cuadros en que `vueltas` no avanza.

**El camino**: la apertura jugada, `viajar(2)`, un `ir_al_mapa` al lado del
ascensor dentro del mismo 2 —el recorrido no sabe jugar el resto del mapa—, el
switch 11 y el contacto con el evento 30, que es lo que hace el juego. En el 3,
caminar al temblor de (47,69), la puerta de (38,68) y la escena entera hasta
el salto al mapa 4.

**Una corrección a la premisa: el 3 no se carga con `TF3_1_awe` sonando.** Lo
que suena en todo el mapa 2 es `escape_newyork`, el tema de la apertura del 1:
el único `PlayBGM` de `TF3_1_awe` del juego es el que la página del ascensor
hace **después** del `Teleport` al 3. El caso `paquete-incompleto` prende
`TF3_1_awe` en el 2 a mano, así que ejercita el mismo mecanismo con otro tema;
el docstring de su prueba y el comentario de `tema_asegurar` dicen que el paso
del juego se hace "con el tema del 2 sonando", y no es así.

## Sin MSU-1

Cuadros de hardware desde la llegada al 3:

    0     llega con escape_newyork sonando (35.793 B fijos). Entran evilrhys y
          los cinco primeros efectos: Earth2, Open1, Switch1, Switch2, Key.
          PAQ_INCOMPLETO en 1; faltan quince efectos
    0-55  congelado bajo el fundido (la carga del mapa)
    101   termina el fundido y corre el PlayBGM TF3_1_awe: calla la música y
          rearma el paquete con TF3 adelante
    101-187  congelado, con la imagen puesta y sin música: 86 cuadros
    187   suena TF3_1_awe. Entraron nueve efectos (hasta Glass); faltan diez,
          de Earth4 a Fog2. PAQ_INCOMPLETO sigue en 1: TF3 + evilrhys + los
          20 efectos no entran en la ARAM de ninguna manera
    347   Earth2, el temblor: suena
    479   Open1, la puerta: suena
    778   FadeOutBGM de la puerta
    1044  PlayBGM evilrhys: suelta TF3 y completa el paquete. 34 cuadros
          congelado, con la música ya fundida y entre dos mensajes
    1078-3362  la escena: suenan los 20 efectos del paquete, cada vez que se
          piden
    3496  PlayBGM lufsorr, de salida: sube solo, 12 cuadros, y al 4

**No falta ningún efecto.** Mientras el paquete está incompleto —del cuadro 2
al 1044, unos 17 segundos— el mapa pide sólo Earth2 y Open1, y los dos están
desde la llegada porque son los primeros de la lista. Todo lo que faltó se usa
recién después del `PlayBGM` de evilrhys. Es el diseño de
`decisiones/el-tema-que-suena-gana-y-los-efectos-esperan.md` funcionando.

## Con MSU-1

Los tres temas van por pista, así que ninguno ocupa la ARAM: el paquete llega
**entero**, `PAQ_INCOMPLETO` nunca se prende, no hay ningún congelamiento más
que el del fundido y suenan los mismos efectos en los mismos cuadros.

# El hueco que sí se oye, sin MSU-1

**86 cuadros, 1,4 segundos, de imagen congelada y silencio** justo después de
que el mapa 3 aparece, por el `PlayBGM` de `TF3_1_awe`. No es por los efectos:
TF3 no está en el paquete del 3, así que hay que subirlo igual. Lo que se subió
en esos cuadros, comparando `FAR_ARAM_DE` antes y después:

* 61.614 B en total, a unos 720 B por cuadro;
* **25.623 B ya estaban en la ARAM** —evilrhys y los cinco efectos de la
  llegada— y se volvieron a subir en otro lugar, porque el paquete quedó
  incompleto y `paquete_cargar_ya` lo rearma todo desde cero (`compactar`);
* ese rearmado gana a lo sumo un efecto, Glass, que no se usa hasta después de
  evilrhys, que completa el paquete de todos modos.

Tamaños medidos en el cartucho: escape_newyork 35.793 B, TF3_1_awe 25.875,
evilrhys 19.377, los 20 efectos 43.029, y la ARAM de muestras son 63.419
(`ARAM_DATOS` a `ARAM_FIN`).

# Qué haría falta, sin bajarle calidad a nada (no se implementó)

1. **No compactar cuando no puede servir.** `compactar` existe para la
   fragmentación: un paquete que entra solo y quedaba afuera por los huecos.
   Si lo que se quiere (`FAR_QUIERE` distinto de cero) suma más que la ARAM,
   rearmar desde cero sólo reordena, y aquí cuesta ~36 cuadros de los 86. Una
   suma de `muestra_tabla + 3` sobre las marcadas antes de compactar alcanza
   para saberlo. El congelamiento bajaría a ~50 cuadros: lo que tarda TF3.
   No toca la tasa de nada; lo único que cambia es que pueden entrar un par de
   efectos menos hasta el `PlayBGM` siguiente, y en este mapa ninguno se usa
   en ese rato.
2. **Subir TF3 sin callar a escape_newyork.** escape (35.793) y TF3 (25.875)
   entran juntos (61.668 de 63.419): `tema_asegurar` podría soltar el paquete,
   subir el tema nuevo al lado del que suena y recién ahí cambiar. El juego
   quedaría congelado lo mismo —la subida no es asíncrona— pero sin el
   silencio. Es más trabajo y toca la misma rutina que el agente de "Dos bugs
   de audio en la ROM".
3. Lo que **no** sirve: subir TF3 en la llegada, debajo del fundido. Al lado
   de escape_newyork quedan 1.751 B, y Earth2 y Open1, que el mapa pide antes
   de evilrhys, son 3.780.

# De paso, lo que no suena en el 3 y no es del paquete

* **Los sonidos de las rutas.** La escena de evilrhys pide una docena adentro
  de rutas forzadas —Decision1, Blow1 a Blow6, Shot2 y Switch1— y el conversor
  los tira a propósito: ver `RUTA_SONIDO` en `tools/port/eventos.py`. Por eso
  esos nombres ni siquiera están en el paquete del 3. No hay tarea que lo
  tenga.
* **Tres efectos en el mismo cuadro, con dos voces.** En el cuadro 2799 la
  página pide Explosion4 y Glass juntos, y la animación 79 dispara Flame2 en
  el mismo: Glass no llega a sonar. Es el límite de dos voces de
  `efectos_de_sonido.s`, no la ARAM.
