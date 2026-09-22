---
name: "Efectos de sonido"
description: "PlaySound suena, con sus muestras en el paquete del mapa"
---

### Los efectos de sonido

`PlaySound` suena. Compila a `OP_SOUND` con el índice del
efecto en `sonido_tabla`, que lleva por efecto la muestra, la altura, el
volumen de cada lado y cuántos cuadros dura: el tempo de RM2k estira la altura
y la duración, y el paneo baja el lado contrario.

Tres decisiones, las tres por la ARAM:

* **Van por mapa**: ver "El paquete de audio de cada mapa", más abajo. Hasta
  ahí se quedaban con lo que la música dejaba libre, y de los 38 que pide la
  demo entraban 5.
* **A 6 kHz y a lo sumo tres cuartos de segundo** —era uno hasta el paquete,
  que tiene que subirlos en el fundido de cada salto—. Uno más largo repite sus
  últimos 0,4 s hasta durar lo que dura en RM2k: la lluvia de la apertura son
  cinco segundos de ruido y así se la oye entera.
* **El efecto le roba la voz 7 a la música**, que es de percusión. La ROM
  guarda una sombra de los registros de esa voz que la música escribe
  (`dsp_musica`), y al terminar el efecto la devuelve tal cual; mientras suena,
  la música no la toca.

La tanda no mide audio: compara imágenes, y `OP_SOUND` no cuesta un tick. Lo
que se corrió fue una grabación de la apertura de
`abl` con el núcleo de libretro, contra la misma ROM con el volumen de
los efectos en cero: los disparos caen en los cuadros 191, 433 y 576, y en el
hueco entre el fin del tercero y el siguiente (cuadros 890 a 920) las dos
salidas son idénticas muestra por muestra. Es decir, la música vuelve entera.
Si suenan bien lo dice el oído de taro.

`play_sound_effect` en las rutas sigue aceptándose sin hacerse.
