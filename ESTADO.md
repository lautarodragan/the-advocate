# Dónde quedamos

Lo que existe **sólo mientras alguien trabaja**: qué se decidió y sigue
valiendo, qué espera respuesta de taro, qué no se probó todavía, qué no cubre
la tanda, y hacia dónde vamos.

Lo que **no** va acá: el relato de lo hecho. Eso está en `git log`, que en este
repo tiene mensajes largos justamente para eso, y lo durable está en
`rom/LEEME.md`. Este archivo llegó a tener dos mil líneas por append-only y se
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
mapa 3— compila entera, y `demo-apertura` lleva los mapas 4, 1, 2, 3 y 5.

Las páginas automáticas que compilan enteras son **209 de 489**.

### Lo próximo, si no se decide otra cosa

1. **El desfase de un cuadro de la página de contacto**, que es lo único que
   separa a la escena de Talan de estar verificada. Ver abajo.
2. **La secuencia del "1 year earlier"**, que es lo que sigue en el juego y lo
   que hoy deja mudo a `hzstream`: la página que lo prende —evento 1, página 2
   del mapa 4— pide `ChangeItems`, `ShowPicture`/`MovePicture` y
   `ChangePartyMembers`.


## Decisiones tomadas que siguen valiendo

Las que hay que conocer para no rehacerlas ni contradecirlas. El porqué largo
de cada una está en `rom/LEEME.md`.

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
* **Los builds numerados de `rom/build/` no se arman a mano.** No están en git
  y no los produce ninguna receta salvo el 12. Armar uno a mano es cómo se
  terminó mirando el mapa 6 creyendo que era la demo del hito 12.


## Esperando respuesta de taro

* **Sobre el héroe, la ROM ignora las órdenes de ruta 26 a 29 y la referencia
  no.** Fijar y soltar la mirada, subir y bajar la velocidad. `paso_de_ruta`
  las saltea con un comentario que dice "acá no llegan", y llegan: `Ruta` es la
  misma clase para el héroe y para los eventos.

  Medido: el juego tiene 163 rutas sobre el héroe con la orden 28 y 148 con la
  29; de las páginas que **hoy compilan**, siete tienen una, y una de ésas es
  el evento 1 del **mapa 7, Talan's Pad**, adonde el juego va después de esto.
  Ninguna prueba lo cobra porque ningún caso mira esas páginas.

  No lo arreglé porque no es un comando que falte sino dos lados que dejaron de
  hacer lo mismo, y la velocidad del héroe pide además que su paso deje de ser
  fijo —hoy son `WALK_SPEED` y ocho cuadros por celda—. **Dónde entra lo decide
  taro.**

* **`rom/build/demo-apertura-jugable/`**: es la copia pre-fundido que taro pidió
  el 2026-09-05 para que un test no se la pisara. Nunca dijo si la refresca o
  se borra.

* **Si las ocho décimas de arranque molestan.** Ver la decisión de arriba.


## Lo que taro todavía no probó

* **`rom/build/demo-apertura/`, rearmada el 2026-09-06** con todo lo de los
  seis puntos adentro: la puerta del Emitter Room que se abre y se cruza, la
  escena de Talan entera, los mapas 4, 1, 2, 3 y **5**, y cuatro temas
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

`just snes-hitos-paralelo` son **85 casos, todos en verde**. Lo que no mira:

* **La escena de Talan.** Compila y corre, y los dos lados **no coinciden**.
  Armada a mano —mapa 3 con el 1, el 2, el 4 y el 5, el héroe en (38,69), el
  switch 13 puesto para que la página de contacto esté activa, y una ruta
  forzada de una sola orden que lo hace subir— los cuadros 1 a 9 dan cero y el
  10 da 34%. El cuadro 10 de la ROM es idéntico al tick 9 de la referencia:
  **la ROM dispara la página de contacto un cuadro más tarde**.

  El primer comando de esa página es un `Teleport` al mismo mapa, o sea que
  arranca un fundido, y por eso un cuadro de corrimiento se ve como un tercio
  de la pantalla. Dónde mirar: `paso_de_ruta` en `snes_expect.py` decide
  `llego` en el mismo tick en que el paso termina, y en la ROM el orden del
  lazo pone `fundido_tick` **antes** de `eventos_tick`, así que lo que la
  página arranca se ve recién en la vuelta siguiente. Arreglarlo es decidir
  cuál de los dos tiene razón contra `Game_Player::UpdateMovement`.

  No lo cobra `ruta-pisa` ni `ruta-pisa-cola` porque comparan los cuadros 50 y
  200, cuando ya se acomodó todo: es la trampa del camino que ninguna prueba
  ejecuta, pero en la ventana de tiempo en vez de en el código.

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
