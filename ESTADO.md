# Dónde quedamos

Lo que existe **sólo mientras alguien trabaja**: qué se decidió y sigue
valiendo, qué espera respuesta de taro, qué no se probó todavía, qué no cubre
la tanda, y hacia dónde vamos.

Lo que **no** va acá: el relato de lo hecho. Eso está en `git log`, que en este
repo tiene mensajes largos justamente para eso, y lo durable está en
`README.md`. Este archivo llegó a tener dos mil líneas por append-only y se
volvió inusable; se borra sin culpa lo que ya esté en esos dos lados.

Se escribe **mientras se trabaja**, no al final.

Última vez que se tocó: 2026-09-07.


## El objetivo, y dónde estamos

**Los primeros diez minutos jugables**, que es lo que taro viene probando vuelta
a vuelta en el emulador.

Los seis puntos que acordamos el 2026-09-05 —`FadeOutBGM`, las órdenes de ruta
30 y 31, `PanScreen`, las diagonales, `PlayBGM` con varios temas y la orden 34—
están **los seis hechos**, entre el 2026-09-05 y el 2026-09-06. Con eso la
escena de Talan —los 233 comandos de la página de contacto del evento 5 del
mapa 3— corre y **está verificada** en mil doscientos cuadros, y
`demo-apertura` lleva los mapas 4, 1, 2, 3, 5 y 6.

Las páginas automáticas que compilan enteras son **272 de 489**.

### Lo próximo, si no se decide otra cosa

1. **Los gráficos: está todo medido y vive en `assets/`.** El sub-proyecto de
   convertir el arte de RM2k a la consola se fue de acá porque es de otra
   naturaleza —hay que elegir qué se lleva y con qué paleta, no traducir un
   formato—. En `assets/README.md` están las mediciones y la estrategia, y en
   `assets/medir.py` los scripts que las sacan, así que se pueden repetir.

   El titular, para no tener que abrirlo: **el juego entra en 4 MB**. Son unos
   2,9 MB entre mapas, sprites, tiles y música, más 2,7 de arte que todavía no
   dibuja nadie. Deduplicar es viable con **una paleta por chipset** —33 de 42
   entran tal cual—, y el costo de esa decisión es artístico y no de espacio:
   algunos mapas van a compartir una paleta más ancha de la que necesitan.

2. **El mapa 8 no entra en el cartucho.** Es lo que frena la demo hoy: el
   exterior del pad de Talan pesa unos 140 KB y con el resto se pasa —632092
   bytes contra 491520—. Ni siquiera el mínimo que llega ahí, 4-1-2-3-7-8,
   entra: 564928. Así que salir de la casa de Talan pide **agrandar la ROM**,
   que hoy es de 512 KB y cuyo mapeo tampoco se probó en hardware.
3. **Los líderes posibles son una aproximación, y se nota.** El conversor
   simula los `ChangePartyMembers` de las páginas que compilan para saber qué
   actores pueden ir primeros, porque las poses del héroe no se cargan en
   caliente. Desde el 2026-09-07 el grupo se reinicia **en cada mapa**, que es
   lo que corresponde —la tabla de actores es por mapa—, pero sigue sin saberse
   con qué grupo se llega a cada uno. Si alguna vez un personaje se dibuja sin
   gráfico, es el primer lugar donde mirar; `pruebas/test_lideres.py` cuida la
   parte que ya falló.

4. **`ChangePartyMembers` de verdad**, si alguna página que compile cambia de
   líder: el gráfico del héroe sale del primero del grupo, así que hoy quedaría
   con la cara equivocada. Ninguna lo hace todavía.


## Decisiones tomadas que siguen valiendo

Las que hay que conocer para no rehacerlas ni contradecirlas. El porqué largo
de cada una está en `README.md`.

* **Un caso largo en cero no prueba nada por sí solo.** El caso `talan` estuvo
  una vez en verde sin ejercitar nada —la página no compilaba, los dos lados no
  hacían nada— y mil doscientos cuadros de cero se ven muy convincentes. Antes
  de creerle a un cero hay que **ver la página compilar**, y mejor todavía,
  verlo dar rojo con algo roto a propósito. Lo delató algo suelto: la lista de
  temas del cartucho bajó de cuatro a tres.

* **La página activa de un evento se congela hasta el refresco.** No se
  recalcula cada vez que alguien pregunta: es `Game_Event::page`, y sólo la
  reescribe `Game_Map::Refresh()`, al principio de `Game_Map::Update`. La ROM
  ya lo hacía —la guarda en la fila del NPC— y la referencia no; desde el
  2026-09-06 las dos guardan la instantánea. De ahí sale una regla que hay que
  respetar: **el lazo de la referencia no puede cortar con un refresco
  pendiente**, porque el cuadro que viene sí hace algo.

* **Los eventos disparan con dos bits cada uno, no con una cola.** Es el
  `waiting_execution` de `Game_Event`: `FLAG_AUTO` dice si la página activa del
  evento es una automática que compiló y `FLAG_ESPERA` si tiene una página
  esperando turno, la haya puesto el barrido de las automáticas, la tecla de
  acción o un contacto. Reemplazó a una cola de ocho punteros que se llenaba y
  descartaba —y que pasada la octava interacción leía sus propios contadores
  como bytecode—.

  De ahí salen dos cosas que antes no pasaban: una automática **se repite**
  mientras siga siendo la activa, y una que se vuelve activa con el mapa ya
  cargado **arranca**. Lo segundo es lo que dejaba muerta la segunda mitad del
  recuerdo de CORE y MANTA, y como la ROM y la referencia se equivocaban igual,
  la comparación daba cero.

* **El refresco corre en tres momentos y está partido en dos mitades.** No es
  una optimización de gusto: es lo que lo hace entrar en un cuadro.

      al salir del intérprete   elige sólo los eventos con automáticas
      al empezar el cuadro      elige todas las páginas activas
      ídem, después             recarga rutas y gráficos de los NPCs

  Lo primero es el `if (GetNeedRefresh()) Refresh();` del final de
  `Game_Interpreter::Update`, y de él depende que el idioma de RM2k funcione:
  una página que prende el switch que la desactiva deja de ser la activa antes
  de que se decida qué corre después. Sin eso perdía ocho cuadros en el mapa 2
  arrancándose a sí misma.

  EasyRPG además refresca **antes de cada comando**. Acá no hace falta y sale
  caro —cinco cuadros en la cinemática de apertura, que prende switches de a
  montones—: ningún opcode de los que hay lee cuál es la página activa de un
  evento. El día que aparezca uno que sí, esto vuelve al lazo.

  Y la mitad cara —recargar filas de OAM y ranuras de ruta— se posterga al
  cuadro siguiente porque no se ve hasta que se dibuje.

* **La página de prueba se apaga sola**, prendiendo el switch 1023 en su primer
  comando, con una segunda página vacía que lo pide. Es el idioma con el que
  las páginas del juego se desactivan, y no lo ejercitaba nada; sin él, ahora
  que las automáticas se repiten, la página de prueba reiniciaría su propia
  ruta para siempre. Su evento es el primer índice libre del mapa y no un
  número alto: los barridos de la ROM van de cero a `ev_total`.

* **`ConditionalBranch` sólo con condiciones de switch.** Son 21 páginas de
   las 24 que el comando destraba; las tres que faltan preguntan por el héroe
   en el grupo, y sin grupo variable esa rama daría siempre lo mismo: modelarla
   sin nada que la ejercite es inventarse una diferencia. Las variables suman
   cero, medido.

  Compila a dos opcodes: `OP_SI` —switch, polaridad y destino— y `OP_IR`, el
  salto sin condición que va donde estaba el `else`. **El destino es absoluto
  dentro de la página**, así que en la ROM saltar es asignar el cursor; quién
  es ese destino lo resuelve el conversor, que es el único que ve la página
  entera, emitiéndolo en blanco y parcheándolo al cerrar la rama. El
  anidamiento sale de una pila y no de mirar la indentación como
  `SkipToNextConditional`: él recorre una lista lineal, acá los bloques ya
  vienen anidados.

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


## Decisiones tomadas el 2026-09-07

**El presupuesto de teletransportes se repone cuando el jugador tiene el
control, y agotarlo es un error, no un caso.** `saltos_restantes` existe para
que dos mapas que se apunten entre sí no cuelguen a la consola. Estaba mal de
las dos maneras posibles: sólo lo reponía `cargar_mapa`, que a esa altura
llamaba únicamente una **puerta** —un comando `Teleport` carga el mapa por
`cargar_mapa_sin_eventos`—, así que los ocho se gastaban para toda la partida; y
al agotarse, el salto se **descartaba en silencio**. Ahora se repone en
`eventos_tick` cada cuadro en que no hay nada corriendo ni esperando, que es el
mismo alcance que tiene en la referencia —`saltos` es local a `entrar_al_mapa`—,
y al agotarse la ROM llama a `entrar_en_panico`: deja el código en `panico` y
parpadea la pantalla para siempre. La referencia levanta `DemasiadosSaltos`.

Lo pidió taro y tiene razón por encima del caso: un salto descartado sin avisar
es la forma de falla que el CLAUDE.md nombra, y ésta sobrevivió semanas porque
la partida seguía andando, sólo que en el mapa equivocado.


## Esperando respuesta de taro

* **`rom/build/demo-apertura-jugable/`**: es la copia pre-fundido que taro pidió
  el 2026-09-05 para que un test no se la pisara. Nunca dijo si la refresca o
  se borra.

* **Si las ocho décimas de arranque molestan.** Ver la decisión de arriba.


## Lo que falta para salir del pad de Talan

El 2026-09-07 taro llegó al pad y lo jugó: controla a Talan, corre la cinemática
y puede hablarle a la cama, la PC y los caños. Quedan tres cosas, y son tres
problemas distintos.

1. **La puerta no compila porque falta el mapa 8.** `TalDoorTop` teletransporta
   a `[8, 11, 56]` y el 8 no está en el cartucho; el conversor ya lo avisa por
   nombre. Con el 8 adentro el mapa 7 pasa de 9 a 10 páginas de 10.

   Y el que bloquea no es el tamaño de la ROM, como se venía suponiendo: **el
   mapa 8 pide 9 paletas de sprite y la consola tiene 8**, así que el conversor
   corta con error. Sin el cronómetro son 8 disponibles y sin él 7. Esto cae
   justo sobre el punto 1 de `assets/README.md` —la estrategia de paletas— y lo
   convierte en el camino crítico de los diez minutos, no en una tangente.

2. **El insta-shave necesita `ShowChoice`** (código 10140, el "Yes/No"). Es lo
   único que falta del mapa 7. En todo el juego es el primer bloqueo de 36
   páginas; lo que de verdad manda a esa escala es `ControlVars`, con 548.

3. **El cronómetro ya anda**: era el `--con-timer` que faltaba en el build. Ver
   la receta de abajo.


## Lo que taro todavía no probó

* **La salida del pad de Talan, con el presupuesto de saltos arreglado.** El
  2026-09-07 taro quedó encerrado en un mapa vacío del que no se podía salir,
  sin control y con `hzstream` fundiéndose y empezando de nuevo en ciclo. El
  volcado de la WRAM que pasó —`/extras/demo-apertura - SnesWorkRam.dmp`— dijo
  que no estaba en el pad sino en el **mapa 4**, "Blank (Leave START here)", que
  es vacío a propósito: por eso "no renderizaba" nada más que el héroe, con
  `brillo` en 15. El mapa 4 es un **despachante** —cinco páginas automáticas,
  una por switch, cada una teletransportando a otro lado— y la escena del escape
  del mapa 3 devuelve ahí. Su salto al pad se estaba perdiendo por el
  presupuesto agotado, y como la página es automática y el switch 21 sigue
  prendido volvía a arrancar sola para siempre. Hay que rearmar
  `demo-apertura` y volver a jugar la secuencia entera.

* **`rom/build/demo-apertura/`, rearmada el 2026-09-06** con el disparo de
  páginas rehecho —ver la decisión de abajo— y con el **mapa 6 adentro**, que
  antes no estaba: la línea de este archivo
  que decía "los mapas 4, 1, 2, 3, 5 y 6" era falsa y el `--mapas` nunca lo
  llevó. Sin el 6, las cuatro páginas automáticas del mapa 5 daban **cero
  ejecutables** —tres de ellas teletransportan al 6— y el recuerdo de CORE y
  MANTA no arrancaba: el héroe quedaba caminando invisible por la casa. taro
  lo encontró jugando el 2026-09-06. Ahora el 5 y el 6 tienen una ejecutable
  cada uno. Se arma así:

      python3 tools/snes_convert.py --grupo 10 --map-id 4 --mapas 1 2 3 5 6 7 \
          --con-ventana --con-timer -o rom/build/demo-apertura/mapdata.inc
      python3 tools/w65.py rom/src/main.s -I rom/build/demo-apertura \
          -o rom/build/demo-apertura/demo-apertura.sfc \
          --simbolos rom/build/demo-apertura/demo-apertura.sfc.sym

  El `--con-timer` no estaba y por eso el 2026-09-07 taro no veía el
  cronómetro: la cuenta corría —`timer_activo` en 1— pero `TIMER_BASE` era 0 en
  los siete mapas, o sea que los dígitos no estaban en VRAM y el dibujo se
  salteaba entero. El flag cuesta una paleta de sprite, de 8 a 7. Y el
  `--simbolos` tampoco estaba: sin él las pruebas de estado no pueden mirar
  esta ROM.

  Lleva además la escena de Talan entera, la puerta del Emitter Room, y cuatro
  temas —`escape_newyork`, `TF3_1_awe`, `evilrhys`, `lufsorr`—. El banco de
  muestras quedó en 61569 B de los 64512 de ARAM: agregar un mapa más con tema
  propio ya no entra sin sacar algo.

  Las otras ROMs con nombre —`demo-musica`, `demo-cinematica` y el resto— son
  viejas y no se rearmaron.

* **La SNES de verdad, con el FX Pak.** Nada de esto se corrió en hardware, y
  **queda parado por un tiempo**: el CRT de taro dejó de andar el 2026-09-06.
  Dos cosas para mirar cuando vuelva: el mapeo del cartucho de 512 KB y el
  redondeo del brillo de `INIDISP`, que es lo de abajo.

* **El brillo de `INIDISP`: mesen-s contra los otros dos, medido.** El
  2026-09-06 se compararon los tres cores cuadro por cuadro sobre el fundido de
  entrada al mapa 1 de `demo-apertura`, que recorre los dieciséis niveles:

      brillo 0 y 15           los tres coinciden, cero pixeles de diferencia
      brillo 1 a 14           snes9x y bsnes coinciden exactamente;
                              mesen-s difiere en 30% a 48% de los pixeles

  O sea que difiere **exactamente mientras dura un fundido** y en ningún otro
  momento, que es lo que confirma que el asunto es el escalado y nada más. Y
  difiere para abajo: da un paso menos —3 contra 2, 11 contra 10, a 15 bits— y
  nunca más. Es "trunca donde los otros redondean"; la fórmula exacta no sale
  de esta medición porque la escena lleva además un tinte en CGRAM, así que el
  pixel no es color puro por brillo.

  **La trampa práctica:** el justfile toma el core de la variable `CORE`, así
  que correr la tanda con `CORE=mesen-s` es un comando —y pondría en rojo todos
  los cuadros que caigan en un fundido, sin que haya ningún bug. La tanda usa
  snes9x, y `snes-bsnes` y `snes-mednafen` la respaldan.

  Dos de tres no desempata: el hardware es el que decide, y para eso hay que
  esperar al CRT. A ojo, taro no distingue mednafen de mesen y los dos le
  parecen bien.


* **Las pruebas de estado son la otra mitad de la red, no un reemplazo.**
  `just pruebas` corre pytest sobre `pruebas/`: se le pregunta a la ROM en qué
  mapa está, qué switch tiene prendido, qué evento corre. No miran la pantalla.

  El reparto es por dónde se queda ciega cada una. La tanda de pixeles cobra
  los errores de PPU —una paleta mal repartida, una prioridad de OAM— y no
  puede cobrar nada donde la referencia se equivoca igual que la ROM. Las de
  estado no ven un pixel, pero no dependen de que la referencia esté bien: el
  recuerdo de CORE y MANTA que no arrancaba daba **verde en los 87 casos** y da
  rojo en una línea acá. Medido: con la ROM de antes del arreglo,
  `test_el_recuerdo_cruza_a_la_ciudad` dice mapa 5 en vez de 6.

  Ninguna dirección de RAM está escrita a mano: salen de la tabla que deja
  `w65.py --simbolos`, que además exporta las constantes del ensamblador
  —`BOOT_CUADROS`, `FLAG_AUTO`, `EV_MAX`—. Renombrar una variable en `main.s`
  hace fallar la prueba diciendo qué símbolo falta, en vez de leer en silencio
  la dirección de al lado.

  Decidido con taro el 2026-09-06: **los casos nuevos se escriben acá**, y la
  tanda de pixeles se mantiene pero deja de crecer.


## Lo que la tanda no cubre

`just snes-hitos-foto` son **88 casos, todos en verde**, y el más largo es
`talan`: mil doscientos cuadros de la escena entera del Emitter Room. Lo que la
tanda no mira:

* **Que un mapa acepte muchas interacciones seguidas** — ya no, desde el
  2026-09-06: el caso `hablar-repetido` son diecisiete toques de A sobre el
  mismo evento del mapa 7, o sea nueve aperturas de mensaje, y mira el cuadro
  360. Es el primer caso que pasa de la octava interacción, que era justo donde
  se rompía la cola. Verificado que **da rojo con la ROM de antes del anillo**,
  en el cuadro 360 y sólo ahí: un caso nuevo que no da rojo con el bug puesto
  no prueba nada.

  Lo que sigue sin cubrir es la otra mitad del mismo agujero: los bugs que taro
  encontró jugando ese día aparecen después de una cinemática larga, y ninguna
  caminata de la tanda encadena una cinemática con interacciones sueltas
  después.

* **La cadena del recuerdo, después del mapa 6.** El caso `manta` la compara
  hasta ahí —3900 cuadros, del mapa 5 al 6, con 34 toques de A—, y sigue: el 6
  salta al 3 y el 3 al 4. Eso no lo mira nadie todavía.

* **Los primeros veinte cuadros de un mensaje.** La ROM compone la ventana
  cuadro a cuadro y la referencia la pone de golpe. **Cuánto tarda depende del
  texto**: medido, 9 cuadros con el mensaje de prueba y 17 a 19 con los del
  recuerdo de CORE y MANTA. Antes acá decía "nueve" a secas, y eso era el
  número de un solo caso.

  De ahí salen dos cuidados, y los dos costaron un rojo: ningún cuadro que se
  compare puede caer adentro de esa ventanita, y **ningún toque de A tampoco**.
  La ROM ignora el botón mientras `msg_abierto` esté en cero, la referencia
  no, y a partir de ahí las dos corren escenas distintas. Al armar una lista de
  toques hay que dejar treinta cuadros desde que el mensaje se abre, no veinte:
  con veinte, el toque del cuadro 1976 llegó **uno** antes de tiempo.

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
