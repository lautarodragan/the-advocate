# Dónde quedamos

Lo que existe **sólo mientras alguien trabaja**: qué se decidió y sigue
valiendo, qué espera respuesta de taro, qué no se probó todavía, qué no cubre
la tanda, y hacia dónde vamos.

Lo que **no** va acá: el relato de lo hecho. Eso está en `git log`, que en este
repo tiene mensajes largos justamente para eso, y lo durable está en
`README.md`. Este archivo llegó a tener dos mil líneas por append-only y se
volvió inusable; se borra sin culpa lo que ya esté en esos dos lados.

Se escribe **mientras se trabaja**, no al final.

Última vez que se tocó: 2026-09-06.


## El objetivo, y dónde estamos

**Los primeros diez minutos jugables**, que es lo que taro viene probando vuelta
a vuelta en el emulador.

Los seis puntos que acordamos el 2026-09-05 —`FadeOutBGM`, las órdenes de ruta
30 y 31, `PanScreen`, las diagonales, `PlayBGM` con varios temas y la orden 34—
están **los seis hechos**, entre el 2026-09-05 y el 2026-09-06. Con eso la
escena de Talan —los 233 comandos de la página de contacto del evento 5 del
mapa 3— compila y corre, y `demo-apertura` lleva los mapas 4, 1, 2, 3, 5 y 6.

Las páginas automáticas que compilan enteras son **209 de 489**.

### Lo próximo, si no se decide otra cosa

1. **La divergencia de la escena de Talan, entre los cuadros 90 y 140.** Ahora
   que la escena corre de verdad la comparación dice algo: los cuadros 40, 60,
   80, 150, 200, 400, 700 y 1200 dan **cero** y los del medio hasta 60%. No es
   un corrimiento de cuadros —ROM 100 contra referencia 100 es la comparación
   que menos difiere de todas— así que es contenido distinto. Con ese
   porcentaje huele a la cámara corrida un par de pixeles, y ahí es donde corre
   el `PanScreen` de la escena; la sospecha es que arranca en cuadros distintos
   porque algo anterior tarda distinto. Resuelto eso, la escena tiene caso
   propio en la tanda.

2. **`ConditionalBranch`**, el desbloqueo más grande que queda: +24 páginas de
   las 209 que compilan hoy. Y lo caro no sirve: limitado a condiciones de
   **switch** se lleva 24 de las 27; agregarle variables suma cero, medido.
3. **La secuencia del "1 year earlier"**, que es lo que sigue en el juego y lo
   que hoy deja mudo a `hzstream`: la página que lo prende —evento 1, página 2
   del mapa 4— pide `ChangeItems`, `ShowPicture`/`MovePicture` y
   `ChangePartyMembers`.


## Decisiones tomadas que siguen valiendo

Las que hay que conocer para no rehacerlas ni contradecirlas. El porqué largo
de cada una está en `README.md`.

* **La página activa de un evento se congela hasta el refresco.** No se
  recalcula cada vez que alguien pregunta: es `Game_Event::page`, y sólo la
  reescribe `Game_Map::Refresh()`, al principio de `Game_Map::Update`. La ROM
  ya lo hacía —la guarda en la fila del NPC— y la referencia no; desde el
  2026-09-06 las dos guardan la instantánea. De ahí sale una regla que hay que
  respetar: **el lazo de la referencia no puede cortar con un refresco
  pendiente**, porque el cuadro que viene sí hace algo.

* **Las órdenes de ruta 26 a 29 sobre el héroe se aceptan y se tiran.** Fijar y
  soltar la mirada y subir y bajar la velocidad. Decidido con taro el
  2026-09-06: son un extra, como los efectos climáticos, y el juego se puede
  jugar sin ellas. Se tiran **al compilar**, como el sonido y la transparencia,
  así que la referencia tampoco las camina y los dos lados quedan iguales por
  construcción.

  El primer intento fue **rechazar la página entera**, y costaba demasiado: la
  escena de Talan tiene una ruta del héroe que empieza con la 28, así que la
  escena que motivó los seis puntos no compilaba y el jugador se quedaba
  encerrado en el pasillo del Emitter Room —taro lo encontró jugando—. Son 4
  páginas automáticas más ésa.

  Lo que se pierde es el cambio de ritmo: donde RM2k acelera al héroe, acá
  camina a la suya. Es visible y está aceptado. Arreglarlo de verdad es que su
  paso deje de ser fijo —hoy `WALK_SPEED`, ocho cuadros por celda, escrito a
  mano en `try_up` y sus tres hermanas— y pase al acumulador de 256 por celda
  que ya tienen los eventos; eso toca además caminar con el pad, la cámara y el
  plan de cuadros de los casos. En todo el juego son 178 rutas.

* **Las diagonales y la orden 34 van sobre eventos, no sobre el héroe.** El
  paso del héroe está escrito una vez por dirección y su gráfico sale de la
  tabla de actores; darle las dos cosas sería duplicar ese código. Medido: de
  las 26 rutas con diagonales ninguna es del héroe, y darle la 34 al héroe
  destrabaría diez páginas más. El conversor rechaza la página que lo intente,
  y ese corte **no es cosmético**: la 34 lleva operando, así que sin él la ROM
  leería el gráfico como si fuera una orden.
* **Los temas comparten un solo banco de muestras.** Un banco por tema pediría
  subirlo en cada `PlayBGM` —medio segundo— y eso habría que modelarlo en la
  referencia para que la comparación cuadro a cuadro siga significando algo.
  Modelar cuánto tarda una transferencia es justo lo que no se puede medir
  honestamente.
* **El arranque está dimensionado para el techo de ARAM**, no para el banco de
  hoy: `BOOT_CUADROS = 112` y `--arranque 115`. Cuesta 1,9 s de mapa congelado
  al encender y a cambio llenar la ARAM no cuesta nada. Lo que lo compraría de
  vuelta es un driver del SPC700 que reciba por los cuatro puertos en vez del
  uno del IPL.
* **Un gráfico que no entra en las ocho paletas de sprite no se dibuja**, de
  los dos lados y con la misma función. Vale para los eventos dibujados con un
  tile del chipset y, desde la orden 34, para los gráficos a los que una ruta
  cambia: ahí la orden esconde al evento en vez de cambiarlo. Forzarlos rompía
  tres mapas —el 108, el 114 y el 207—.
* **La tanda se corre sobre una foto del árbol.** `just snes-hitos-foto` la
  saca con `git stash create` y la corre en un worktree de `/extras`, así que
  editar mientras corre dejó de ser un problema. El riesgo que queda no es de
  git sino de cabeza —si la tanda sale en rojo con otro cambio ya encima, hay
  que separar cuál fue—, y lo desambigua el hash de la foto que la receta
  imprime: `git diff <foto>` dice qué se agregó después.

* **Los builds numerados de `rom/build/` no se arman a mano.** No están en git
  y no los produce ninguna receta salvo el 12. Armar uno a mano es cómo se
  terminó mirando el mapa 6 creyendo que era la demo del hito 12.


## Esperando respuesta de taro

* **`rom/build/demo-apertura-jugable/`**: es la copia pre-fundido que taro pidió
  el 2026-09-05 para que un test no se la pisara. Nunca dijo si la refresca o
  se borra.

* **Si las ocho décimas de arranque molestan.** Ver la decisión de arriba.


## Lo que taro todavía no probó

* **`rom/build/demo-apertura/`, rearmada el 2026-09-06** con todo lo de los
  seis puntos adentro: la puerta del Emitter Room que se abre y se cruza, la
  escena de Talan entera, los mapas 4, 1, 2, 3, **5** y **6**, y cuatro temas
  —`escape_newyork`, `TF3_1_awe`, `evilrhys`, `lufsorr`—. Se arma así:

      python3 tools/snes_convert.py --grupo 10 --map-id 4 --mapas 1 2 3 5 \
          --con-ventana -o rom/build/demo-apertura/mapdata.inc
      python3 tools/w65.py rom/src/main.s -I rom/build/demo-apertura \
          -o rom/build/demo-apertura/demo-apertura.sfc

  Las otras ROMs con nombre —`demo-musica`, `demo-cinematica` y el resto— son
  viejas y no se rearmaron.

* **La SNES de verdad, con el FX Pak.** Nada de esto se corrió en hardware.
  Dos cosas concretas para mirar ahí: el mapeo del cartucho de 512 KB, y el
  **redondeo del brillo de `INIDISP`** —mesen-s trunca donde bsnes y snes9x
  redondean, que es la primera vez que los tres cores no coinciden, y el
  hardware es el que desempata—.


## Lo que la tanda no cubre

`just snes-hitos-foto` son **85 casos, todos en verde**. Lo que no mira:

* **La escena de Talan**, que corre pero diverge entre los cuadros 90 y 140:
  ver arriba. No tiene caso hasta que eso se resuelva.

  Hubo uno el 2026-09-06 y se sacó, y vale contar por qué. Estaba en verde **por
  la razón equivocada**: la página no compilaba —la orden 28 sobre el héroe se
  rechazaba entonces— así que los dos lados no hacían nada y la comparación daba
  cero. Mil doscientos cuadros de nada. Lo delató algo suelto: la lista de temas
  del cartucho bajó de cuatro a tres, y `lufsorr` es el segundo tema de esa
  misma página.

  La lección, para el próximo caso largo: **antes de creerle a un cero hay que
  ver la página compilar**. Un caso que no ejercita nada da cero igual, y cuanto
  más largo el caso, más convincente se ve el cero.

* **El audio.** `just snes-bgm <tema>` graba cuarenta segundos y los compara
  contra el MIDI, y **no está en la tanda**: es visual. Los cuatro temas de la
  demo pasaron el 2026-09-06 —96%, 98%, 83% y 90%—, pero eso hay que volver a
  correrlo a mano.

  `evilrhys` es el ruidoso: dio 66%, 75% y 83% en tres corridas contra un techo
  de 95% que le da FluidSynth con el mismo MIDI. No es el banco compartido —sus
  escrituras melódicas son idénticas con banco propio—; es que tiene ocho
  canales melódicos para seis voces, así que dos no suenan nunca.

* **La convención de la tabla de mapas.** Cómo se arma —el de `--map-id`
  primero, después los de `--mapas` sin repetir— está escrito igual en el
  conversor y en la referencia, a propósito. Justamente por eso, equivocarla
  los equivoca a los dos juntos y la comparación sigue dando cero. Se revisa
  leyendo los dos lados, no corriéndolos. Lo que sí se corre es que la ROM
  resuelva un índice que no sea 0 ni 1.

* **El tope de ocho saltos encadenados.** Medido el 2026-09-03: con los 328
  mapas en la tabla hay **un solo** mapa cuya página automática teletransporta
  al entrar, la cadena más larga es de un salto y no hay ciclos. **No es
  estable**: cada comando nuevo hace compilar más páginas automáticas y las
  cadenas pueden crecer. Conviene volver a medirlo de vez en cuando.

* **La RAM sin inicializar, del todo.** `snes9x` —con el que corre casi toda la
  tanda— deja siempre la misma basura, así que una variable que nadie
  inicializa da verde. Lo mitigan `snes-mednafen` y `snes-bsnes`, que corren
  con la WRAM llena de basura al encender, pero la detección es
  **probabilística**: con un error de esta clase puesto a mano, el cuadro sale
  mal 11 corridas de 20. Si molesta, la salida es correr el caso de bsnes
  varias veces, que a veinte segundos por vez es barato.

  Dos errores de esta clase los encontró taro jugando, con la tanda en verde.

* **La guarda de la paleta vacía** en `tenir_paleta` protege una condición que
  el conversor no puede producir hoy: siempre emite al menos una paleta de
  sprites y una de la capa de encima. Se deja —el error que arregló fue real y
  un DMA de cero bytes transfiere 64 KB— pero como código inalcanzable, no como
  camino sin probar. Si el conversor deja de forzar esa paleta mínima, vuelve a
  la lista.


## Lo que se dejó afuera a propósito

* **El panorama del mapa 2** —los puntitos sobre azul cuando se enciende la
  pantalla grande— pide una tercera capa de fondo y el modo 3 tiene dos.
* **Los otros tipos de movimiento de las rutas propias**: al azar, vertical,
  horizontal y hacia el héroe. Son 106 páginas. Y el giro en el lugar.
* **El fundido de la transparencia de una ruta**: se acepta y se tira, porque
  la SNES no atenúa un sprite por partes sin color math.
* **Los cuadros que el lazo pierde de vez en cuando** —la primera vuelta de una
  ROM con muchas páginas, y la vuelta en que termina un fundido—. No cambian
  ningún pixel comparado, y son lo único que le falta a la escena del ascensor
  para tener caso propio en la tanda.
