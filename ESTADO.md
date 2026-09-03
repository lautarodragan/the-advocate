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
Cerrada la mitad corrible del segundo, **el orden de la tabla de mapas**, con un
cuarto caso. Y relevados los tres que quedaban —el tope de ocho saltos, la
guarda de la paleta vacía y las 29 páginas a puro `FIN`—, que no pedían pruebas
nuevas sino medir: dos de los tres tenían la premisa mal escrita.

La lista queda entonces sin nada "sin correr por falta de ganas": lo que sobra
es de dos clases, o inalcanzable con los datos del juego, o compartido entre la
ROM y la referencia y por lo tanto no comprobable comparando. Las dos clases
están dichas con todas las letras abajo.

El hito 12 —el intérprete de eventos— quedó cerrado de los dos lados el
2026-09-02, en `f337a02` y `fe2767d`.

    just snes-hitos    50 comparaciones, todas en 0 pixeles de 57344

**Terminada la migración del harness a libretro in-process**, el 2026-09-03.
La tanda corría 19m30s y el 100% era el emulador en tiempo real mientras la
prueba lo esperaba durmiendo. Ahora:

    just snes-hitos              2m23s    19 casos, 56 comparaciones en 0
    just snes-hitos-paralelo 6   0m32s    lo mismo, repartido en procesos

Lo que se ganó además del tiempo, que era el punto: los cuadros salen de la
referencia y no de un número elegido a ojo, la prueba dejó de depender de la
carga de la máquina, y `snes-caminando` compara al héroe **a mitad de camino**
—cosa que antes no se hacía nunca, porque en el cuadro final está chocando
contra la pared y la única pose que se comparaba era la parada—.

Quedó una deuda acotada y con valor claro: **completar el frontend de libretro**.
Hoy anda sólo con snes9x; bsnes queda negro y mesen-s segfaultea, los dos porque
`tools/retro.py` implementa el mínimo del contrato. Con eso resuelto, la segunda
opinión sale gratis —`snes_correr.py --core` ya existe— y encima bsnes es el más
preciso y el que aleatoriza la RAM al encender, que es lo más parecido a la
consola de verdad.

**En curso: el intérprete corre cuadro a cuadro.** Hecho el 2026-09-03 de los
dos lados. Antes `cargar_mapa` ejecutaba todas las páginas de una sola pasada,
con la pantalla apagada, y las esperas se salteaban: el tiempo quedaba
colapsado y nada de lo que en RM2k pasa *durante* una página existía. Como el
46% de las páginas automáticas del juego terminan en un teletransporte, eso
además volvía imposible de verificar todo lo anterior al salto.

Ahora las páginas elegidas se encolan al cargar el mapa y el lazo principal las
va comiendo; las esperas esperan y el teletransporte corta el cuadro, como el
`return false` de easyrpg-player.

Y ya está verificado. Ninguna página del juego que compile tiene una espera, así
que `snes-espera` corre una **página inventada** —esperar N cuadros y después
teñir—, del mismo modo que `snes-encima` existe porque ningún evento del juego
llega a la prioridad 2: lo sintético es la entrada, no la comparación. Se mira
antes y después con margen y no el cuadro exacto del borde, porque el arranque
de la ROM incluye la subida al SPC700 —unos 42 cuadros cuando el mapa tiene
música— y la referencia no modela eso. Entre las dos capturas hay 57247 pixeles
de diferencia, así que si la espera no esperara se vería.

Falta lo que esto habilita: las rutas forzadas caminando y el clima.

El corte siguiente, sin empezar: **la cinemática de apertura**.
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
  verifica" en `rom/LEEME.md`.
* **Moverse por una ruta forzada: a 410 pixeles de coincidir.** Retomado el
  2026-09-03 con el intérprete ya corriendo en el tiempo, que es lo que hacía
  falta. La maquinaria está de los dos lados: la ROM la camina en
  `paso_de_ruta` —consume la ruta antes que el pad, como RM2k— y la referencia
  en `Estado.cuadro_de_ruta`. **Pero no coinciden, y el comando sigue sin
  aceptarse** en `_compilar`: emitir un opcode que los dos lados ejecutan
  distinto es peor que no tenerlo.
  Dónde quedó la depuración, para no rederivarlo: con una ruta
  `face_up, move_up x3` en el mapa 18, en el cuadro asentado **el héroe queda en
  la misma celda (10,6) y mirando para el mismo lado** —contra un
  `--hero-tile 10 6 --dir up` la diferencia es 410 pixeles, y contra las otras
  tres direcciones es mayor—, así que lo que difiere es **la columna del ciclo
  de caminata**: la ROM no vuelve a la pose parada al terminar la ruta. El
  sospechoso es que quede un paso a medias (`step_left` distinto de cero) y
  `animate_hero` siga ciclando.
  Ya se descartaron: el desfasaje de arranque (se barrió de 5 a 9 y el error no
  se mueve), el offset de pixeles del paso en curso, y la pose calculada por
  cuadros moviéndose. Y se arregló un error real de la ROM en el camino: `tax`
  con X de 16 bits se llevaba el byte alto del acumulador y la ruta leía basura,
  con lo que el héroe caminaba una celda de tres y no había ningún error.
* **Moverse por una ruta forzada (nota vieja).** Anotado el 2026-09-03. De los comandos de
  ruta de `MoveEvent` hoy se aceptan sólo los cuatro de girar y la espera;
  `move_up` y compañía no compilan. No es pereza: en RM2k el personaje camina
  celda por celda a lo largo de varios cuadros y hay que decidir qué pasa
  cuando lo bloquean, y **ninguna página del juego que compile lo ejercita** —de
  las 3509 rutas del juego, la única que compila es la del mapa 74, que sólo
  gira—. Implementarlo sin con qué compararlo es cómo sobrevivieron los cinco
  errores anteriores. La cinemática de apertura lo va a pedir: mueve al héroe
  tres celdas hacia arriba.
* **Que la página siga después de un teletransporte.** Anotado el 2026-09-03.
  El intérprete cortaba la página en el primer `Teleport`, con un comentario
  que decía "RM2k tampoco". Es falso: en
  `Game_Interpreter_Map::CommandTeleport` de easyrpg-player el motor reserva el
  salto, hace `index++` y devuelve false, o sea que corta el cuadro pero retoma
  en el comando siguiente después del cambio de mapa. Ya está arreglado de los
  dos lados, pero **no lo ejercita ninguna prueba**: de las 335 páginas
  automáticas del juego, las que hoy compilan y tienen comandos después de un
  teletransporte son **cero**. Lo va a ejercitar la cinemática de apertura, que
  tiene once comandos después del primero.
  Y queda una aproximación adentro: no se corren los eventos automáticos del
  mapa intermedio, que RM2k sí correría entre un salto y el siguiente. En la
  cinemática los dos van al mismo mapa; si aparece una que salte entre mapas
  distintos, hay que volver acá.
* **La tanda no puede ver la RAM sin inicializar.** Descubierto el 2026-09-03,
  jugando. `snes9x` —el core con el que corre toda la tanda— **arranca la RAM en
  cero**, y mednafen no. Una variable nueva que nadie inicializa da verde en las
  60 comparaciones y falla en mednafen y en hardware real. Ya pasó: `ruta_n` y
  `ruta_i` sin inicializar hacían que `move_hero` creyera que había una ruta
  forzada pendiente y no leyera el pad nunca; el héroe no se movía y la tanda no
  se enteraba.
  Y no fue la única: el tinte pedido por un evento se aplicaba con la pantalla
  encendida, así que entraba a medias —CGRAM no acepta escrituras mientras el
  PPU dibuja—. snes9x las acepta igual; mednafen no. Las dos las encontró taro
  jugando, con la tanda en verde.
  Mitigado el mismo día con `snes-mednafen`, que corre dos casos por el otro
  emulador y compara contra las mismas referencias: uno que tiñe desde un evento
  y uno que camina, que son las dos clases. Está en la tanda, así que se corre.
  No reemplaza a lo de abajo: mednafen es el parche barato y bsnes la solución,
  porque su `bsnes_entropy` habría atrapado el de la RAM solo.
  Es la trampa que el LEEME ya tenía anotada, ahora cobrada en serio. Y tiene una
  salida concreta: **bsnes tiene `bsnes_entropy`, que aleatoriza la RAM al
  encender**. Es la segunda razón para hacerlo andar —la primera era tener una
  segunda opinión—, y con eso la tanda vería esta clase de error sola.
* **Por qué bsnes devuelve una pantalla negra.** Abierto el 2026-09-03. Con
  `tools/retro.py`, el core de bsnes carga la ROM, suena el audio y `retro_run`
  avanza, pero el framebuffer viene en cero para cualquier cantidad de cuadros.
  Descartados: la entropía, `ppu_fast`, los defaults de las opciones y la
  respuesta a `GET_OVERSCAN`; durante `retro_run` sólo pide
  `GET_VARIABLE_UPDATE` y `GET_FASTFORWARDING`. Lo que sí está establecido es
  de quién es la culpa: **bajo RetroArch el mismo core con la misma ROM
  dibuja**, así que falta algo de nuestro frontend y no es un problema de la
  ROM. Importa porque bsnes es el más preciso de los tres y es la segunda
  opinión que haría que "los dos emuladores coinciden" valga de verdad. De paso
  quedó otra rareza sin explicar: bsnes reporta `retro_get_region` = PAL,
  50,007 fps, con una cabecera que dice `$01` = NTSC.
* **El orden de la tabla de mapas.** Cerrado a medias el 2026-09-03, y la
  mitad que queda no se puede cerrar comparando. Lo que sí se corre ahora es
  que la ROM resuelva un índice compilado que no sea 0 ni 1: `snes-hitos` corre
  el mismo evento del mapa 4 dos veces, con la tabla de dos y con `[4,7,19,1]`,
  donde el salto compila a 3. Bajarlo a mano a 2 manda la ROM al mapa 19 y
  mueve 55336 de los 57344 pixeles.
  Lo que no se puede probar así es **la convención**: cómo se arma la tabla
  —el de `--map-id` primero, después los de `--mapas` sin repetir— está escrito
  igual en el conversor y en la referencia, a propósito, porque si no
  compararían dos mundos distintos. Justamente por eso, equivocarla los
  equivoca a los dos juntos y la comparación sigue dando cero. Es el mismo
  agujero de siempre y no tiene salida por este lado: se revisa leyendo los dos
  lados, no corriéndolos.
* **El tope de ocho saltos.** Medido el 2026-09-03, y sigue sin correrse pero
  ahora se sabe por qué. Con los 328 mapas en la tabla —lo más largo que puede
  dar— hay **un solo** mapa cuya página automática teletransporta al entrar: el
  4 al 1. La cadena más larga es de un salto sobre ocho, y no hay ningún ciclo.
  Ojo con esto: no es estable. En cuanto entren los comandos que hoy hacen que
  una página no compile —los de la cinemática—, van a compilar más páginas
  automáticas y las cadenas pueden crecer. Vale la pena volver a correr la
  medición después de ese corte: está en el historial de la sesión como
  `saltos.py`, son veinte líneas.
* **La guarda de la paleta vacía** en `tenir_paleta`. Relevado el 2026-09-03,
  y la premisa que estaba escrita acá era falsa. El conversor **no** emite cero
  cuando un mapa no declara sprites: `poses` arranca siempre con el CharSet del
  héroe, así que siempre hay al menos una paleta de sprites, y la capa de
  encima también recibe una aunque esté vacía. Medido en los mapas 4, 18, 19,
  261 y 1, los tres contadores —fondo, encima, sprites— dan como mínimo 2, 16 y
  16; ninguno da cero. El mapa 7 tiene la capa de encima **completamente
  vacía** y aun así emite `ABOVE_CGRAM = 16`.
  O sea que hoy la guarda protege una condición que el conversor no puede
  producir: sacarla y capturar el mapa 7 da 0 pixeles de diferencia. Se deja
  igual —el error que arregló fue real, está en "Trampas del hardware" del
  `LEEME.md`, y un DMA de cero bytes transfiere 64 KB—, pero como código
  inalcanzable, no como camino sin probar. Si alguna vez el conversor deja de
  forzar esa paleta mínima, esto vuelve a la lista.
* ~~**Las 29 páginas que compilan a puro `FIN`.**~~ Medido el 2026-09-03, y la
  respuesta es más simple que el supuesto: **las 29 tienen cero comandos**. No
  es que todos sus comandos sean de los "ignorables" —no hay comandos—. Están
  en 25 mapas, y dos de ellos, el 18 y el 52, ya están en `snes-hitos`: el
  intérprete corre esas páginas en cada tanda, no es un camino muerto.

## Lo que se dejó afuera a propósito

* **Que un NPC frene al héroe.** La referencia tampoco lo modela, y es a
  propósito: modelar de este lado algo que la consola no hace inventa una
  diferencia. Los dos lados se mueven juntos o ninguno.
* **`PlayBGM`, aceptado sin hacerlo.** Decidido el 2026-09-03. Una página que
  cambie la música compila igual y la ROM sigue con el tema que venía sonando.
  Es distinto de los comandos "ignorables", que no hacen nada porque no hay nada
  que hacer: esto sí hace algo y nosotros no lo hacemos. Se acepta porque lo que
  deja sin hacer no aparece en la pantalla que se compara, y a cambio deja
  correr páginas que si no quedarían afuera enteras —la cinemática de apertura,
  entre ellas—.
  Vive en `ACEPTADOS_SIN_HACER` de `tools/eventos.py`, en una lista aparte de
  los ignorables justamente para que la diferencia no se pierda, y el conversor
  avisa por pantalla cuando emite una página con deuda. Hoy no avisa nunca:
  aceptarlo no desbloquea ninguna página, se midió. Detalle a no olvidar:
  `snes-check` compara el audio contra el MIDI del mapa, así que el día que una
  página cambie el tema esa prueba va a estar midiendo contra el equivocado.

* **La saturación del tinte.** El conversor sólo deja pasar la neutra, así que
  una página que la use no se emite. Aceptarla sin aplicarla sería el error de
  siempre: la referencia haría lo mismo mal.
* **Los builds numerados de `rom/build/`.** No están en git y no los produce
  ninguna receta salvo el 12. Armar uno a mano es cómo se terminó mirando el
  mapa 6 creyendo que era la demo del hito 12 —ver `AGENTS.md`—.
