---
name: "El contador de Fortitude no se ve"
description: "El minijuego de Eisen (mapa 95) lleva la cuenta en la variable 48 y la muestra con una imagen que la ROM no dibuja"
type: bug
assignee: Chimango
---

Del plan `el-mundo-y-lo-que-sigue.md` (pregunta 4). El minijuego del 95 compila
y se juega, pero sin ver cuánto aguanta Eisen: el contador de Fortitude es una
imagen que la ROM no dibuja. taro lo dejó como deuda el 2026-09-27.

Los caminos que estaban sobre la mesa: mostrar la variable 48 con los dígitos
del cronómetro, que ya están en la ROM; un mensaje cuando baja. Antes de elegir
hay que mirar si el minijuego se puede perder: si no, el contador es sólo
información.

**Se puede perder**, mirado en el hito 4 (`testing/mundo-4-el-capitulo.md`):
cada salto y cada escalera del 95 restan 5 a la variable 48, que arranca en
99, y con la variable en cero la paralela 56 dice "So... tired... can't go
on...", devuelve a Eisen a la entrada, apaga las tres palancas y la repone en
99. La ruta de
`test_recorrido_capitulo_golden.py`, que va derecho a las tres palancas y a la
escotilla, termina con 4: sin ver el contador, cualquier rodeo obliga a
empezar de nuevo sin que el jugador lo vea venir. Así que el contador no es
sólo información.

## Tomada el 2026-09-30

Decidido por Hornero, con la autorización de taro para decidir sin
esperarlo: el camino es **mostrar la variable 48 con los dígitos del
cronómetro**, que ya están en la ROM, en el lugar y en el momento en que el
original muestra su imagen —medirlo con el RPG_RT en Wine—. Un mensaje
cuando baja no avisa antes de perder, que es lo que importa. Cambia lo que
se ve: las goldens que se muevan esperan el visto bueno de taro.

## Qué hace el original (Chimango, 2026-09-30)

Medido con el RPG_RT de 2015 en Wine, sobre una copia del juego cuyo EV0001
del mapa 4 lleva a Eisen al 95. Las capturas, en
`/shared/capturas/2026-09-30-fortitude/original-*.png`.

* **Son tres imágenes**, fijas a la pantalla —no se mueven con la cámara—:
  la 1 es el rótulo `Fortitude` (110x25, azul en cursiva) centrado en
  (70, 10); la 2 es la decena y la 3 la unidad, dígitos rojos de 16x16
  (`Picture/0.png` a `9.png`) centrados en (55, 30) y (70, 30).
* **Aparecen** cuando termina la escena de entrada (EV0001 o EV0005, los dos
  del 95), justo antes de "A NOTE ABOUT FORTITUDE": las tres de golpe, en
  99, sin fundido.
* **Cambian** sólo cuando corre el común 9, `FortitudeDisplay`: cada salto y
  cada escalera del 95 —treinta y una páginas— restan 5 o 10 a la variable 48
  y lo llaman. El común recorta la 48 a 0..99, pone la decena con una cadena
  de `ConditionalBranch` y la unidad con el común 10, `CalculateSecondDigit`,
  sobre la variable 49; **debajo de 10 borra la decena** (" 9", no "09").
  Tras un salto desde 99 se ve 94.
* **Se van al cambiar de mapa**, y con el fundido del teleport: RM2k 2000 no
  tiene el flag de las imágenes de 2003, y `ShowParams` arranca con
  `erase_on_map_change` prendido (easyrpg, `game_pictures.h`). Un teleport al
  mismo mapa no las borra: el "So... tired" de la paralela 56 manda a Eisen a
  la entrada del 95 y el contador sigue, en 99. Al volver del 99 al 95
  (después de la escena de los misiles) no hay contador hasta el próximo
  salto, que muestra sólo los dígitos: **el rótulo no vuelve**.
* El tinte no las toca —`affected_by_tint` arranca apagado— y el mensaje de
  abajo no las tapa.

## Por qué el común 9 nunca corrió en la ROM

La variable 49 sólo la nombran los comunes 9 y 10, y el barrido que le da
lugar a cada variable (`indices::variables`) mira las páginas de los mapas y
de las tropas, no los comunes. Sin lugar para la 49 el común no compila, y un
`CallEvent` a un común que no compila se saltea: los treinta y un saltos
restaban y nadie dibujaba nada.

Darle lugar no alcanza, y se probó: con los comunes en el barrido, el común 9
compila a **1.345 bytes**, y como `CallEvent` se compila pegando el cuerpo en
el lugar de la llamada, son 1.345 bytes por salto —40 KB en el mapa 95, sin
contar los dígitos— para una cadena de `if` que decide qué dígito mostrar. Y
sumaría 71 variables que sólo nombran comunes, que harían compilar otros
comunes en otros mapas: fuera de esta tarea.

## Cómo se hizo: el común 9, declarado como contador

**`OP_COUNTER` (0x35)**, con la variable, `x` e `y`. El proyecto declara en
`rm2k-snes.toml`, `[events] counters`, que el común 9 es el contador de la
variable 48, y el compilador de eventos (`compile_counter`):

* compila **`CallEvent` al común 9** como `OP_COUNTER` en vez de pegar su
  cuerpo: 4 bytes por salto en vez de 1.345;
* compila **un `ShowPicture` de un dígito en las imágenes del contador** —las
  que el común 9 usa para dígitos, la 2 y la 3— como el mismo `OP_COUNTER`.
  Es lo que hacen las escenas de entrada (EV0001 y EV0005): la 48 en 99 y las
  dos imágenes con "9". Muestra el valor de la variable y no el de la imagen,
  que es lo mismo mientras la página muestre los dígitos del valor que acaba
  de poner: se asume, y está escrito en `compile_counter`;
* saca **dónde** del común: el medio de los centros de sus dos imágenes de
  dígitos, escalado a la pantalla de la consola, y el número centrado ahí
  —(41, 20), los dos glifos de 8x16 pegados—. Verifica que sean dos imágenes
  y cada una siempre en el mismo lugar; si no, corta la conversión.

La ROM (`counter_set`, en el banco 1, y `counter_oam`) recorta a 0..99, borra
la decena debajo de 10 y dibuja con los glifos del cronómetro, **debajo del
cronómetro y con su paleta sin teñir**, igual que el original no tiñe sus
imágenes. El contador se va al cambiar de mapa (`enter_map_no_events`); un
teleport al mismo mapa no lo toca, como en RM2k. `timer_oam` quedó partido
en `glyph_oam`, que dibuja un glifo, y los dos lo usan.

Por qué así y no las otras formas:

* **Compilar el común como es** (darle lugar a la 49): 1.345 bytes por
  llamada, 40 KB en el 95. Descartado arriba.
* **Una imagen de dígito = un glifo**, regla general sin declarar nada: igual
  necesita que el común compile, y encima suma los `ShowPicture`, ~110 por
  llamada. Y cada glifo centrado en su imagen deja un hueco entre la decena y
  la unidad, porque las imágenes miden el doble.
* **Declararlo en el proyecto** reinterpreta un común, y eso es una decisión
  del juego: por eso va en el `.toml` y no en el compilador, que no sabe de
  ABL. Lo que se toma a confianza es que el común 9 dibuja la 48 en dos
  dígitos sin cero adelante; lo que se verifica es dónde.

**Lo que no se hace:**

* **El rótulo `Fortitude`** (imagen 1): los glifos del cronómetro son dígitos
  y dos puntos. Sigue como deuda, aceptado sin hacerse.
* **El recorte de la variable**: el común escribe la 48 recortada; la ROM
  recorta sólo lo que muestra. Nadie más la lee, y la paralela 56 pregunta
  "<= 0", que da lo mismo.
* **Una partida guardada en el 95** vuelve sin contador hasta el próximo
  salto: las imágenes de RM2k viajan en la partida, y el contador no.
* **Encima de la ventana**: como el cronómetro y la imagen, prioridad 3. En
  RM2k la ventana tapa las imágenes; se nota sólo con un mensaje arriba con el
  contador puesto (el "What are you doing, Professor?" del EV0055).
