# Dónde quedamos

Lo que existe **sólo mientras alguien trabaja**: qué se decidió y sigue
valiendo, qué espera respuesta de taro, qué no se probó todavía, qué no cubre
la tanda, y hacia dónde vamos.

Lo que **no** va acá: el relato de lo hecho. Eso está en `git log`, que en este
repo tiene mensajes largos justamente para eso, y lo durable está en
`README.md`. Este archivo llegó a tener dos mil líneas por append-only y se
volvió inusable; se borra sin culpa lo que ya esté en esos dos lados.

Se escribe **mientras se trabaja**, no al final.

Última vez que se tocó: 2026-09-09.


## El objetivo, y dónde estamos

**Los primeros diez minutos jugables**, que es lo que taro viene probando vuelta
a vuelta en el emulador.

Al 2026-09-09, corridas de nuevo sobre `fae54fb` sin nada encima: `just
snes-hitos-foto` son **96 casos, todos en verde** y `just pruebas` son **39 en
verde**. Ese mismo día la ROM corrió por primera vez en la **SNES de verdad**
con el FX Pak, con el cartucho ya expandido a 1 MB, y anduvo. `demo-ciudad` se juega desde la apertura hasta la
calle de Lashe City, con los relámpagos, los autos y los NPCs andando, **el agua
moviéndose** y el save point animado y guardando.

Los seis puntos que acordamos el 2026-09-05 —`FadeOutBGM`, las órdenes de ruta
30 y 31, `PanScreen`, las diagonales, `PlayBGM` con varios temas y la orden 34—
están **los seis hechos**, entre el 2026-09-05 y el 2026-09-06. Con eso la
escena de Talan —los 233 comandos de la página de contacto del evento 5 del
mapa 3— corre y **está verificada** en mil doscientos cuadros, y
`demo-apertura` lleva los mapas 4, 1, 2, 3, 5 y 6.

Las páginas automáticas que compilan enteras son **272 de 489**, y del juego
entero compilan **2329 de 3473**.

### En qué estamos ahora (2026-09-09)

taro pidió dos cosas y elegimos hacerlas **en serie y no con sub-agentes**: las
dos tocan `snes_convert.py`, `main.s` y `snes_expect.py`, que son justo los
archivos donde un merge mal hecho no se ve, y el cuello de botella es verificar
—dos tandas a la vez se pelean por CPU—.

1. **La animación de los tiles del ChipSet: hecha, verificada y jugada.** El
   porqué largo está en `README.md`, "El agua se mueve". taro la jugó el
   2026-09-09: *"esas animaciones cambian mucho esos mapas, se ven mucho más
   vivos"*.

   Lo medido antes de escribir una línea: en el **mapa 5** —el recuerdo de Core
   y Manta— cambia el **52% de la pantalla**, y ahí es donde se ve. En el
   **Emitter Room, que es lo que taro pidió, casi nada**: sus 4899 celdas de
   agua están dibujadas iguales en los tres dibujos del ChipSet y lo único que
   se mueve son 9 tiles del grupo "animados", 400 pixeles.

2. **El save point animado y guardando a disco: hecho.** Alcance acordado con
   taro: **una sola ranura y sin menú** —guarda y listo, y al encender se carga
   si hay partida—. El porqué largo está en `README.md`, "El save point".

   La animación de un evento quieto sale del reloj del juego, porque no hay
   dónde guardarle un contador; y cuesta **doce tiles de sprite por evento**,
   así que un mapa con más de cuatro no anima ninguno. Los dos límites están en
   `assets/LIMITACIONES.md`.

   Lo cubre `pruebas/test_guardar.py` —cuatro pruebas, tres dan rojo con
   `guardar_partida` cortado a propósito— y un caso nuevo de la tanda para la
   animación. **La tanda de pixeles no cubre guardar y no puede**: guardar no
   cambia un pixel.

   **Jugado el 2026-09-09**, y guardar quedó verificado del otro lado del
   emulador: mednafen escribió `demo-ciudad.<hash>.srm`, 8 KB, en
   `~/.mednafen/sav`. Falta el EverDrive, que es la única parte que no se puede
   ver acá adentro.

### Lo próximo, si no se decide otra cosa

1. De la lista de abajo, lo que sigue por tamaño es la condición de **ítem** de
   Lashe City —45 eventos, pide inventario— y las **variables** de RM2k.

2. **Lo que sigue faltando de Lashe City**, por tamaño: la condición de **ítem**
   —45 eventos, pide inventario—, las **variables** de RM2k —5000, y no entran
   en el banco 0: van a la RAM del banco 1, que ya se usa para los intérpretes
   paralelos— y el mapa **Lashe City Interiors** con sus tres teletransportes,
   que taro pidió.

3. **La animación del save point** (`animation_type` 3, "Fixed Dir/Continuous"),
   que taro pidió el 2026-09-07: es el punto 2 de arriba y está en curso.

4. **El giro de los eventos al hablarles.** Hoy contestan mirando para donde
   estaban; es una deuda declarada en `assets/LIMITACIONES.md`, con el diseño de
   la ranura de VRAM que haría falta ya escrito.

5. **La ráfaga de entrada del mapa 8**, ahora que la tanda no la cobra: son dos
   cuadros perdidos al entrar, invisibles jugando porque el fundido los absorbe.
   Está perfilada más abajo. Es optimización, no corrección.

6. **Los gráficos: está todo medido y vive en `assets/`.** El titular, para no
   tener que abrirlo: **el juego entra en 4 MB**. Son unos 2,9 MB entre mapas,
   sprites, tiles y música, más 2,7 de arte que todavía no dibuja nadie.

7. **Los líderes posibles son una aproximación.** El conversor simula los
   `ChangePartyMembers` de las páginas que compilan para saber qué actores
   pueden ir primeros. Si alguna vez un personaje se dibuja sin gráfico, es el
   primer lugar donde mirar; `pruebas/test_lideres.py` cuida la parte que ya
   falló.

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


**`ShowChoice`, y el cursor sin un solo tile nuevo.** La ventana con opciones es
la ventana de mensaje de siempre, y el cursor no se dibuja: el conversor emite
**un cuadro de texto por opción** —los mismos renglones, el `>` en otro lado— y
moverlo es recomponer la ventana con otro desplazamiento. Cuesta unas decenas de
bytes por elección y ahorra un tile de sprite, una paleta y el código de
dibujarlo; en la consola un cursor tiene que ser un sprite, y los del mapa ya
están repartidos entre los personajes. Recomponer un renglón de cinco
caracteres son dos cuadros, así que se ve como un cursor que se mueve.

El bytecode es `OP_ELEGIR`, con la misma forma que `OP_SI`: destinos absolutos
dentro de la página, resueltos por el conversor, que es el único que ve la
página entera. El cuerpo de cada opción termina en un `OP_IR` al final de la
elección, emitido en la opción **siguiente** —ahí se sabe que la anterior
terminó— y no en el `END` del cuerpo, para no depender de la indentación.

**El movimiento del cursor no lo cubre la tanda de pixeles y no se modela en la
referencia.** La tanda sólo sabe apretar A, así que arriba, abajo y B son
caminos que no puede ejercitar; escribir del otro lado código que ninguna prueba
corre es exactamente cómo sobrevivieron los tres errores del intérprete. Lo
cubre `pruebas/test_elegir.py`, que aprieta cualquier botón. La tanda cubre la
otra mitad, que es cómo se ve.


**El spike de desacoplar los gráficos: hecho, y lo que midió vale más que lo que
ahorró.** Los bloques de datos pasan por `Materiales`, tienen nombre propio en
vez del número del mapa que los pidió, y los idénticos se emiten una sola vez.
El primer paso salió **byte por byte igual** en seis configuraciones del
conversor, que es una red más fina que la tanda para un refactor.

Encender la deduplicación ahorra **0,1 KB**, y todo son bloques vacíos. Ése es
el resultado: separar el material de los mapas no ahorra nada por sí solo. Lo
que lo explica está medido en `assets/README.md` —seis mapas del mismo chipset
comparten hasta 122 tiles de 150 **como dibujo** y 2 como bytes—, así que todo
el ahorro está del otro lado, en las paletas.

Vale igual porque es la infraestructura que la estrategia de paletas necesita:
sin bloques con identidad propia no hay dónde poner un tile que sea de dos
mapas. Y porque convirtió la frase "es un problema de paletas disfrazado" en un
número.

Y dejó una lección sobre las dos redes. El primer paso se verificó comparando
bytes y las seis configuraciones dieron idéntico; el segundo **rompió**
`snes-varios`, porque `tabla_de_paginas` seguía rearmando `evcodigo_<mapa>` con
el número del mapa y dos mapas pasaron a compartir el bloque. Comparar bytes no
podía verlo —esas seis configuraciones no tenían dos mapas con el mismo código
de eventos— y la tanda lo cobró en el primer intento. Ninguna de las dos redes
sobra.


**La ventana de mensaje se muda a la paleta 0, y el fondo recupera media
CGRAM.** Iba en la paleta más baja de las capas de encima de toda la ROM, y al
fondo se le daba sólo el bloque que quedaba debajo: 47 colores, mientras las
paletas 4, 5 y 6 no las usaba nadie. BG1 va a 8 bits y direcciona CGRAM en
directo, así que no le hacía falta ninguna alineación; le hacía falta que la
ventana no le partiera el espacio al medio.

Con la ventana abajo de todo —nueve entradas, el color de fondo más sus ocho
colores— el fondo queda contiguo desde la 9 hasta su propia capa de encima. En
`demo-apertura` el presupuesto pasa de 47 a 55, 71, 87 o 103 según el mapa, y
los colores fusionados de **97 a cero**. Ningún mapa pierde un color.

Se cayeron dos cosas que existían sólo por la paleta flotante: la reconversión
de mapas en `main()` y el rastreo de la paleta en la referencia, que obligaba a
convertir todos los mapas de la tabla para dibujar uno.

Detalles del arreglo, por si alguno vuelve a morder:

* `subir_paletas` subía la paleta del mapa desde la entrada 0 y le pisaba la
  ventana. Ahora arranca en `CGRAM_BASE`.
* Los colores de la ventana se contaban con `sum(1 for w in cram if w)` y son
  **ocho, no siete**: uno es negro puro y su palabra es cero. Con siete
  reservadas el texto salía con un color que nadie había subido —79 pixeles—.
  `convert_ventana` ahora mira el índice más alto que usa y corta si no entra.
* El tinte no toca la ventana **por dónde arranca el rango** y no por acordarse.


**El cronómetro comparte paleta, y el cartucho pasa a 1 MB.** Los dígitos usan
dos colores —negro y rojo puro— y se llevaban una de las ocho paletas de sprite
para ellos solos. Ese número no es contabilidad: `npcs_dibujables` decide con él
**qué eventos se dibujan**, y un evento que no se dibuja igual ocupa. Con siete,
el mapa 2 perdía el evento 30, que es la celda del medio de la puerta que Core
rompe: taro llegó a la cinemática, la puerta no cambió de tile y no pudo pasar.

Ahora entran en la paleta de cualquier personaje que tenga trece o menos, con el
mismo primer-ajuste que ya se usaba para los eventos dibujados con un tile del
chipset. Y al recuperar esos eventos la ROM se pasaba por 8 KB, así que
`ROM_BANKS` pasó a 32: el área de datos ahora se deriva de ahí en vez de estar
escrita a mano, y la cabecera dice `$0A`.

**Y descartar un evento dejó de ser silencioso.** Era un `print` entre otros
cincuenta y por eso costó una tarde.

El ruido va en el conversor y no en la ROM a propósito, aunque taro pidió que
"crasheara el juego": un descarte se decide **al convertir**, y para cuando la
consola corre el evento ya no está en ninguna tabla. Hacerla explotar al cargar
el mapa sería lo mismo que no armar la ROM, pero más tarde y sin poder decir
cuál evento.

Y no corta con **todos** los descartes, porque eso tampoco protegería: hoy hay
decorativos que no entran en varios mapas, así que todas las recetas tendrían
que pedir seguir y el corte quedaría apagado en todas partes. El tope es
`cambia_de_grafico`: un evento con una sola página que no se dibuja se pierde y
ya —el `CoreBlood` del mapa 3, los cuatro `Link`—, pero uno que **cambia de
gráfico entre páginas** es un mecanismo, y sin dibujarse deja una pared
invisible donde el juego esperaba una puerta. El evento 30 del mapa 2 era de
esa clase, así que el corte lo habría agarrado.

Dos builds lo declaran con `--descartar-eventos`, y los dos tienen un mecanismo
roto de verdad que arregla el trabajo de paletas y no un flag:

* **`demo-apertura`**: los eventos 31 y 32 del mapa 2, los costados de la misma
  puerta que Core rompe. Hoy la puerta funciona porque el 30, el del medio, es
  el que abre el paso.
* **`snes-convert`**, que usa `snes-heroe 8`: `PawnDoorTop` del mapa 8.


**Una puerta al mismo mapa ya no recarga el mapa.** Un `Teleport` al mismo mapa
lo distinguía desde antes —`hubo_salto` compara con `mapa_actual`— pero una
**puerta** —una página de contacto cuyo único comando es un teletransporte, que
el conversor compila a una tabla aparte— recargaba siempre. Recargar vuelve a
leer del cartucho las posiciones de los eventos, y con eso se pierde lo que los
haya movido aunque el jugador nunca haya salido del mapa.

taro lo vio en la puerta de arriba a la izquierda del mapa 2: abrirla manda el
`LBDoorTop` a (94,97) y truequea el `LBDoorBottom` con el `MovinDoor`, así que
el hueco queda negro; al volver reaparecían las franjas amarillas. Los dos
cuartos que jugando parecen dos mapas son el mismo mapa 2.

**La referencia lo tenía peor: recargaba en los dos caminos.** Su lazo llamaba a
`entrar_a_un_mapa` en cada vuelta, también sin cambio de mapa, así que ni el
`Teleport` de ida estaba bien modelado. No se veía porque ningún caso de la
tanda mueve un evento y después salta adentro del mismo mapa. Ahora los dos
lados comparan contra el mapa anterior, que es el `map_changed` de
`Game_Player::PerformTeleport`.

Lo cubre `pruebas/test_puerta_misma.py`, con una tercera ROM compartida que
lleva el mapa 2 solo —alcanza, porque los teletransportes son internos—.


**Los líderes posibles comparten una ranura de CGRAM.** Lidera uno a la vez, así
que reservarle una paleta de sprite a cada uno es tenerla ocupada por alguien
que no está en pantalla. Ahora la tabla de actores lleva los quince colores de
cada líder y la ROM los sube a la ranura al cargar el mapa y al cambiar el
grupo, **por el camino del tinte** para que se tiñan con todo lo demás.

La excepción es el líder que además está como NPC en ese mapa: ése se lleva
paleta propia, porque su fila la usa al mismo tiempo que el héroe. Pasa con
Kersh en los mapas 1 y 6 y con Talan en el 3; ahí no se gana nada, pero tampoco
se rompe. En los otros seis del PoC se gana una paleta.

Dos cosas que destraba:

* **El mapa 2 deja de descartar los eventos 31 y 32**, que son los costados de
  la puerta doble que taro veía con "cachos". Era su tercer bug cosmético.
* **El mapa 8 entra en las ocho paletas**, que era el bloqueo para salir del
  pad de Talan. Falta una sola cosa: los dos colores del cronómetro. El negro ya
  está en siete de las ocho paletas y falta el rojo puro, con las ocho llenas a
  quince. Lo más barato medido es bajar a `BLVehicles:5` de 15 a 14 colores:
  **105 pixeles de 4648, 2,26%**, con un salto de 4 sobre 31; los otros
  candidatos cuestan 11% o más.


**La tecla de acción mira las dos celdas.** `Game_Player::CheckActionEvent`
prueba la del héroe y la de adelante, y **cada una pide la capa contraria**:
`CheckEventTriggerHere` quiere `GetLayer() != Layers_same` y
`CheckEventTriggerThere` quiere `== Layers_same`. No es simetría de adorno: un
evento de la capa del héroe le cierra el paso, así que nunca se podría parar
encima; uno de otra capa no lo frena y se le camina por arriba.

Sólo estaba la de adelante, y estaba escrito como hueco conocido en
`puede_dispararse`. taro lo encontró jugando el 2026-09-07: la puerta que sale
del pad de Talan es `TalDoorTop`, evento 3 del mapa 7, **de acción y capa 2**, y
se abre parándose encima. Debajo está `TalDoorBottom`, de la capa del héroe, que
bloquea; por eso hay que llegar desde arriba.

El filtro de capa pasó a la ROM y ya no lo resuelve el conversor: la misma
página vale o no según qué celda la esté mirando, así que rechazarla al compilar
no alcanzaba.


**El oro, y dos clases más de `ConditionalBranch`.** `OP_SI` ganó adelante un
byte con **la clase de condición, con el número de RM2k tal cual**, y con eso
entran dos que no piden estado nuevo o casi:

* **"el actor está en el grupo"** —el `grupo` ya estaba—, +9 páginas. Sólo el
  sub-tipo 0: de los 155 comandos del juego que preguntan por un héroe, 57 son
  de ése; 78 preguntan por el equipo y 20 por una habilidad, y eso pide
  estadísticas de actor que no llevamos.
* **el oro**, +7 páginas, junto con `ChangeGold`, que hasta ahora se aceptaba y
  no se hacía.

En total **2313 → 2329 páginas**. Dos que se midieron y se descartaron: la
orientación del héroe y el cronómetro destraban **cero** —esas páginas están
frenadas por otra cosa igual—.

El oro son tres bytes: el tope de RM2k son 999999 y este juego usa el valor
entero. Se recorta a [0, 999999] como `Game_Party::GainGold`.

Y un detalle que casi se escapa: **`>=` y `<=` no son una la negación de la
otra**, porque en la igualdad se cumplen las dos. El primer intento calculaba
`oro >= x` y le daba vuelta el bit según la polaridad, que está mal exactamente
en el borde. La ROM las calcula por separado, y el banco de prueba pasa por ahí:
el `DetourOfficer` del mapa 8 es un peaje que pregunta `oro >= 500` y cobra 500,
así que con 500 justos tiene que cobrar.


**El que atraviesa paredes cae donde sea, también saltando.**
`Game_Map::CheckOrMakeWayEx` corta con `if (self.GetThrough()) return true;`
apenas pasa el chequeo de límites, **antes** de mirar la pasabilidad, y el salto
de una ruta pasa por ahí: `BeginMoveRouteJump` llama a `MakeWay`. Nuestro
`puede_caer` miraba sólo la pasabilidad.

Lo encontró taro el 2026-09-07 en el recuerdo de Core y Manta: Core se movía
arriba de su piedra y no saltaba nunca. Las celdas de las piedras están cerradas
de verdad —(31,18) tiene los cuatro bits en cero—, que es el punto: son piedras
en el agua. Su ruta arranca con `atravesar_on`, así que tenía permiso.

Lo incómodo del caso: **la caminata sí lo respetaba** y el salto no. La misma
regla implementada en un camino y olvidada en el otro, y por eso costaba verlo.


## Decisiones tomadas el 2026-09-08

**Se dibujan todos los eventos, aunque sea con una paleta ajena.** Es de taro:
*"si no podemos incluir todos los eventos, el proyecto entero se cae"*. El
gráfico que no consigue paleta propia se cuelga de la que menos colores le
falte y cada color ausente va al más cercano por luma. Los números y el caso
que los justifica están en `assets/LIMITACIONES.md`; lo que destraba es el mapa
8 —que pedía trece paletas de ocho— y el Hover-Tram.

La referencia hace la **misma** aproximación: `pose_image` recibe la paleta
prestada y elige el color más cercano con la misma cuenta. Sin eso la
comparación medía dos programas distintos, y lo cobró el caso `talan` con 332
pixeles.

**El reparto de VRAM se rebalanceó**, porque dibujar todo llevó al mapa 8 de 192
a 347 tiles de sprite y ningún reparto le daba 400 de fondo y 347 de sprite a la
vez. La capa de encima bajó de 256 tiles a 128 —la mediana de los 328 mapas es
**1 tile** y 326 entran en 128—, los tilemaps se mudaron a `VRAM_MAP = $5800` y
`VRAM_ABOVE_MAP = $7800`, y `VENTANA_TILE_BASE` sale del reparto en vez de estar
escrito a mano.

### El cuadro del tinte estaba a una línea de barrido de perderse

Y el primer evento de más se lo llevó puesto. Medido con una sonda que engancha
`OPVCT` al final del lazo principal: una vuelta normal termina en la línea 61 de
262, y la vuelta en que corre `aplicar_tinte` terminaba en la **224**, con
vblank arrancando en la 225. Un cuadro perdido, y la pantalla queda sin teñir un
cuadro contra la referencia.

El gasto era `armar_paleta`: 151 colores por vez —el mapa, la capa de encima,
las ocho paletas de sprite y el líder— a 205 ciclos cada uno. Con la saturación
neutra, que es casi siempre, el color no necesita los tres canales juntos ni
salir de los dieciséis bits: el lazo corto lo baja a ~123 y la vuelta termina en
la 188. Quedan 37 líneas de margen donde había una.

### El cronómetro iba un cuadro adelante, y un cuadro perdido lo tapaba

`timer_tick` corría **después** de `eventos_tick`, y en `Game_Map::Update`
—easyrpg, `game_map.cpp:1304`— `UpdateTimers()` corre **antes** de
`UpdateForegroundEvents`. O sea que la página que arranca el cronómetro no
debería llevarse un cuadro en el mismo cuadro en que lo arranca, y acá se lo
llevaba. La ROM quedaba un cuadro adelante para siempre; se ve sólo en los
cuadros en que parpadean los dos puntos o cambia un dígito.

Nadie lo cobraba porque `snes-timer` tiñe la pantalla, el tinte costaba el
cuadro perdido de acá arriba, y ese cuadro tapaba justo este uno de más. **Los
dos errores juntos daban cero**, que es exactamente el modo en que la
comparación falla en silencio. Se destapó al arreglar el presupuesto, no al
buscarlo.

## Decisiones tomadas el 2026-09-08, tarde

taro jugó `demo-ciudad` y trajo nueve síntomas de Lashe City. Medidos, son
**cuatro causas**, y la más grande no estaba en su lista:

| causa | tamaño en el juego entero |
|---|---|
| páginas de acción frenadas porque el evento tendría que **girar** | 1572 páginas, 1224 eventos, 220 mapas |
| trigger **Parallel Process** | 353 páginas, 86 mapas |
| eventos afuera por **condición de ítem** | 45 eventos (14 más por variable, 1 por cronómetro) |
| un evento que **camina y además aparece** con la página | el `Bum` y el `Mechanic` |

**El giro se declara como deuda y la página corre igual.** De las 1572,
compilan enteras **1535 en 214 mapas**: es, de lejos, lo más grande que se
destrabó de una vez. El evento contesta mirando para donde estaba. Lo que falta
para hacerlo bien —una ranura de VRAM por mapa— está en
`assets/LIMITACIONES.md`.

**Caminar y aparecer dejaron de ser el mismo bit.** No hacía falta uno nuevo: la
fila ya dice si camina (`+9`), así que la ROM copia de la página todo menos el
tile y la paleta. El bit 4 de `+13`, que fue el primer intento, **está ocupado**
—con ruta propia esos cinco bits son las banderas de la ruta— y usarlo escondió
al droide del mapa 2 en seis casos de la tanda.

### Lo que sigue faltando en Lashe City

* **Parallel Process**: `Car1`, `Car2`, `Car4`, `EV0004` y `EV0005` no se
  mueven. El intérprete ya existe; falta la clase de disparo.
* **Condición de ítem**: `PawnDoorBottom`, `GangMember1`, `EV0039`, `EV0040` y
  `EV0041` se caen enteros —no se dibujan, no frenan y no disparan—. Pide
  inventario, que no hay. `EV0041` **no** es el caso de la puerta del pad, como
  parecía: es esto.
* **Lashe City Interiors** no está en la ROM, así que `EV0055`, `EV0033` y
  `EV0057` no compilan. taro lo pidió para la próxima vuelta.

## Parallel Process, y la ráfaga de entrada que dejó a la vista

Hecho el 2026-09-08. Cada evento con página paralela tiene **su propio
intérprete**: corre todos los cuadros, aparte del de primer plano, con un
mensaje abierto y con otra página en curso, y cuando su página termina el cuadro
siguiente la vuelve a empezar —el `Push` que RPG_RT hace antes de cada
`Update`—. De las 353 páginas paralelas del juego **compilan 36**, en 25 mapas;
el resto pide variables. El tope simultáneo es el mapa 8, con nueve.

**El paso de cada evento va pegado a su intérprete**, no al final de la vuelta:
`Game_Event::Update` corre el intérprete paralelo y a continuación llama a
`Game_Character::Update()` (easyrpg, `game_event.cpp:580`), evento por evento.
La diferencia se ve cuando una página paralela le fuerza una ruta a **otro**
evento: en Lashe City el `Car4` le pisa la suya al `Car2` en cada cuadro —los
dos apuntan al id 3 de RM2k, que ahí es el `Car2`—, y corriendo todos los
intérpretes antes que todos los pasos el pisotón gana y el `Car2` no camina
nunca. taro lo vio jugando y lo confirmó contra EasyRPG y contra el RPG Maker
original: los cuatro autos andan siempre.

**La RAM del banco 1.** El estado de los intérpretes no entraba: la BSS del
banco 0 estaba en 7680 de 7680 y el ZEROPAGE tenía doce bytes libres. Va a
`$7E:2000` por la ventana que la WRAM tiene en el bus B —WMADD más `$2180`, la
misma que ya usaba la fuente—. No se puede indexar, así que sirve para lo que se
guarda y se recorre de a poco; es lo que van a necesitar las variables de RM2k,
que son cinco mil.

### Tres casos de la tanda en rojo, y es un solo defecto de antes

`just snes-hitos` queda en **3 rojos de 93**, y los tres son la misma cosa:
**cuadros que la ROM pierde al entrar a un mapa**. Medido en HEAD, sin nada de
esto:

* el mapa 8 pierde **1** cuadro al entrar —2 con los paralelos—,
* el salto del mapa 4 al 1 pierde **7**.

Estaban desde antes y no molestaban porque durante esos cuadros no se movía
nada. Los eventos paralelos sí se mueven, así que ahora la comparación arranca
corrida. Los tres casos:

* `snes-heroe 8` y `snes-hablar 8 ... bum`: los dos cuadros del mapa 8.
* `snes-mednafen`: bajo snes9x el mismo caso (`snes-evento`) da **cero**; con
  siete cuadros perdidos los dos emuladores caen en distinto punto del ciclo del
  relámpago del mapa 1, y un destello a pantalla completa convierte un cuadro de
  diferencia en la pantalla entera.

### La ráfaga de entrada, perfilada

**Lo primero: el fundido ya la absorbe.** Su reloj es `boot_cuadros`, o sea
cuadros de hardware y no vueltas del lazo —ver `empezar_fundido`—, así que la
carga del mapa puede tardar seis o siete cuadros adentro del negro sin correr
nada. Verificado: el salto del mapa 4 al 1 pierde **7 cuadros** y `snes-evento`
da **cero** igual. O sea que en el juego esto no se ve nunca: a un mapa siempre
se entra por una puerta o un teletransporte, y eso es un fundido.

**Sólo molesta al arrancar derecho en un mapa pesado**, que es lo que hacen las
ROMs de un solo mapa de la tanda. Ahí el que tendría que absorber es el arranque
—`BOOT_CUADROS` más tres— y es fijo.

Medido con una sonda que anota `boot_cuadros` y el contador de barrido al final
de cada vuelta, arrancando en el mapa 8 (el presupuesto son **262 líneas**):

    vuelta 0    370 líneas
    vuelta 1    386
    vuelta 2+   147 a 170       ← el régimen entra cómodo

O sea que las dos primeras se pasan por **1,45x**, y de la tercera en adelante
sobra la mitad del cuadro. En líneas, quién se las lleva:

                          vuelta 0   régimen
    paralelos_tick           218        80
      de eso, correr_codigo  164        30    ← crear las ranuras de ruta
    build_oam                 46        54
    el paso interleaveado      3         0    ← el arreglo de los autos es gratis

Lo que **no** es: un refresco por cuadro no pierde ni un cuadro, y encadenar 1,
2, 4 u 8 páginas automáticas da lo mismo. `capa_activa` y `npc_de_evento`
tampoco aparecen.

Para bajar de 262 hay que sacar ~110 líneas de la vuelta 0 y ~124 de la 1. La
mayor parte de la 1 es el primer plano: sin los paralelos igual mide 306.

**Intentado y descartado:** resolver `capa_activa` en O(1) leyendo `eleg_por_ev`
en vez de recorrer las 73 páginas. Cambia el comportamiento —la vuelta 0 sube a
541— así que hay algo del camino rápido que no es equivalente, y hay que
entender qué antes de volver a intentarlo.

## La tanda dejó de ser sensible al rendimiento

Hecho el 2026-09-08, y es la respuesta a una pregunta de taro: *¿tenemos un bug
que depende de que algo esté optimizado?* No. La ROM computa la misma secuencia
de estados vaya rápido o lento; lo que cambia con una vuelta que se pasa del
cuadro es **cuándo** se ve cada uno, que es lag y es lo que le pasa a RPG_RT en
una máquina lenta. Lo que estaba mal era **el instrumento**: la comparación
suponía "cuadro N de la captura = tick N de la referencia".

**Qué es un tick.** El paso lógico de RM2k. En easyrpg el lazo es
`while (Game_Clock::NextGameTimeStep())` (`player.cpp:245`): corre N pasos de
lógica y después **un** `Player::Draw()`, en un solo hilo. La lógica va a
DEFAULT_FPS y el dibujo a lo que la máquina aguante. Acá un tick es una vuelta
del lazo principal, y un cuadro de hardware avanza **cero o un tick, nunca dos**:
el lazo empieza con `wait_vblank`. EasyRPG se pone al día corriendo más lógica;
nosotros no podemos, así que nos atrasamos. Las dos computan lo mismo.

**Cómo se cuenta.** La ROM lleva `vueltas`, y `snes_correr.py` avanza de a un
cuadro leyéndolo hasta llegar al tick que quiere: `retro_run()` no sabe de
ticks. El cuadro N de la referencia es el tick **N+1**, medido en los mapas 6 y
7 —que no pierden ningún cuadro— y **fijo, no muestreado**: muestrearlo fue el
primer intento y falla justo donde importa, porque en el mapa 8 los cuadros que
se pierden caen adentro de la ventana del arranque.

**El fundido pasó a contar ticks.** Va junto y no es opcional: la referencia lo
cuenta así (`estado.fundido` sube una vez por `cuadro()`), y si la ROM lo
contara en cuadros de hardware los dos relojes se irían. Cuesta que un fundido
dure unos cuadros más de reloj de pared cuando la carga del mapa se pasa, que es
justo lo que da lo mismo.

**Lo que destapó**, todo pre-existente:

* `snes-espera` corría con `--arranque 0` y comparaba el cuadro 60 **de reset**
  contra el tick 60 de la referencia. Daba verde porque en los dos lados no
  pasaba nada todavía. Con el arranque normal da cero de verdad.
* **bsnes no expone la WRAM**: `retro_get_memory_data` devuelve nulo, y el
  comentario de `retro.py` decía que los tres cores la implementaban. Ahí el
  reloj cae al camino viejo —contar cuadros—, que sirve porque esos casos corren
  mapas livianos.
* `snes-mednafen` captura por **reloj de pared** —mednafen de verdad, no un
  core— así que no se puede alinear por tick. Pasó a los 6 segundos: a los 5 el
  fundido todavía no había terminado, y a los 7 se le viene encima el relámpago
  del mapa 1, que cae a los 7,1.

### Los 3 rojos del mapa 8: cerrados

* `mecanico` y `bum`: **arreglado**. No era la ventana dejando basura sino el
  vblank: `subir_linea` son 1920 bytes de un solo DMA —casi cuatro poses— y con
  las cinco de siempre no entra, así que la cola del renglón se escribía con la
  pantalla ya encendida y no se escribía. Se ve como una franja fija, y sólo en
  un mapa con muchos eventos moviéndose. Apareció con los paralelos, que sumaron
  nueve personajes que se mueven. El arreglo es el mismo recorte que ya hacían
  el tinte y el destello: con un renglón esperando, `vq_tope` baja a 1.
* `snes-heroe 8`, caminando a la izquierda: **cerrado el 2026-09-09**, y eran
  dos defectos encadenados, los dos de la referencia.

  El de fondo: **los intérpretes paralelos no corrían en el camino colapsado**,
  así que un evento que camina desde su propia página paralela se quedaba
  clavado donde arrancó. Los paralelos pasaron a ser del mapa y no del
  `Interprete` de turno —viven en `Estado`, como `FAR_PAR_ESTADO` en la
  consola—, la entrada les da su paso y la caminata vive sus ocho cuadros por
  celda. De ahí salió además que el plan ya no diga "cuánto dura la caminata"
  sino **cuántos ticks vivió la referencia**, margen incluido.

  Y el que quedaba, 175 pixeles: **atravesar paredes no es salirse del mapa**.
  El `Car3` camina a la derecha con `walk_everywhere` puesto, llega a la última
  columna —la 74 de 75— y ahí la consola lo deja clavado hasta que otro evento
  lo reubica; la referencia lo sacaba del mapa. En
  `Game_Map::CheckOrMakeWayEx` el `IsValid` va **antes** que el
  `if (self.GetThrough()) return true;`, y la ROM ya lo modelaba así en
  `puede_celda`: era la referencia la que estaba de más.

  Cómo se llegó, que es lo que no conviene volver a caminar: la entrada de la
  referencia son 4 ticks y la de la ROM 0, y **eso no era la causa** —darle
  entre 0 y 6 ticks mueve el número de 475 a 518, nunca cerca de cero—; barrer
  la captura entre los ticks 292 y 320 no baja de 257, así que tampoco era un
  desfasaje de tiempo; y el patrón final de dos ticks rojos de cada cinco
  apuntaba a `ANIM_PARADO[4]` pero la animación no tenía nada que ver: el
  contador subía hasta `ANIM_CONTINUA` porque el evento estaba **quieto**.
  Leyendo `ruta_ev` y `ev_pos_buf` en la WRAM se vio quieto en la columna 74, y
  con una sonda de una línea en `poner_ruta` —revertida— se descartó al
  intérprete paralelo: repone la ruta todos los cuadros.

  Verificado: `just pruebas` en 35 verdes y `just snes-hitos-foto` en **93
  casos, todos en verde**.

## bsnes: la WRAM, arreglada y compilada acá

bsnes upstream devuelve nulo en `retro_get_memory_data` para **todos** los ids
—`bsnes/target-libretro/libretro.cpp:1039`— así que el reloj de ticks no lo
podía usar. El comentario del propio archivo dice por qué: *"there is no
safe/sensible way to use the memory interface without severe hackery. Rely on
higan to load and save SRAM"*. O sea que la razón es la **SRAM**, que es lo que
un frontend guarda y carga.

`RETRO_MEMORY_SYSTEM_RAM` es otra cosa: es la RAM de trabajo, la que los
frontends leen para cheats, RetroAchievements y depuración, y no participa de
cómo se guarda la SRAM. Así que exponerla **sólo a ella** respeta el motivo que
ellos dan, y ése es el argumento del PR.

El parche son dos hunks —incluir `sfc/sfc.hpp` en vez de sólo
`sfc/interface/interface.hpp`, que igual lo incluye al final, y devolver
`SuperFamicom::cpu.wram` con su `sizeof`— y está en `/extras/bsnes-wram/`:

    wram.patch                    el diff
    bsnes_libretro.parcheado.so   el build con el arreglo
    bsnes_libretro.original.so    el de pacman, por si hay que volver

**El core instalado en `/usr/lib/libretro/` es el parcheado.** Con él, `bsnes`
declara 131072 bytes de WRAM y el reloj de ticks lee `vueltas` igual que en
snes9x: mismos números, `vueltas = tick + 1`. `just snes-bsnes` pasa sus cuatro
comparaciones en cero.

Para compilarlo hicieron falta `gcc` y `make` de pacman, que el contenedor no
tenía porque el port es Python puro. El clon está en
`/extras/ref/bsnes-libretro`, **con el parche aplicado**: ya no es una copia
limpia del upstream.

## Lo que taro trajo de jugar el 2026-09-09

* **El peaje del `DetourOfficer` anda, y la mitad que él no pudo probar no se
  puede probar jugando.** Preguntó si con 500 creds o más lo dejaría pasar.
  Medido sobre los ocho mapas de `demo-ciudad`: el único `ChangeGold` que
  **suma** es el +100 de la escena del despertar en el pad —evento 4 del mapa
  7— así que por el camino jugable no se llega nunca a 500, y el peaje siempre
  rechaza. La rama que sí se cumple la cubre
  `pruebas/test_oro.py::test_el_peaje_cobra_si_alcanza_y_no_da_la_vuelta_si_no`,
  con 500 justos, 700, 499 y 0. No hay nada que arreglar; lo que hay es un
  camino del juego que no se puede caminar todavía.

* **Apretar A sobre el save point no muestra nada, y es por diseño**: una sola
  ranura y sin menú. Está abajo, en lo que espera respuesta.


## Esperando respuesta de taro

* **Si el save point tiene que avisar que guardó.** Hoy no dice nada: la
  ranura es una sola y no hay menú, así que no hay nada que elegir ni que
  mostrar. RM2k abre su menú de quince y por eso allá se ve algo. Un
  *"Partida guardada"* sale barato —la ventana de mensaje ya existe y el
  conversor sabe emitir un `OP_MENSAJE`— pero es un texto que el juego no
  tiene, así que lo inventaríamos nosotros. taro lo preguntó el 2026-09-09.

* **`rom/build/demo-apertura-jugable/`**: es la copia pre-fundido que taro pidió
  el 2026-09-05 para que un test no se la pisara. Nunca dijo si la refresca o
  se borra.

* **Si las ocho décimas de arranque molestan.** Ver la decisión de arriba.


## Salir del pad de Talan: hecho

El 2026-09-07 taro llegó al pad, y el 2026-09-08 pudo salir. Los tres puntos que
faltaban están: el mapa 8 entra en la ROM —ver la decisión de las paletas
prestadas—, `ShowChoice` anda con cursor, vuelta y cancelar con B, y el
cronómetro también.

## `rom/build/demo-ciudad/`: jugada el 2026-09-09, y en hardware

Rearmada el 2026-09-08 y **jugada** el 2026-09-09 —el agua, el save point y
el peaje del `DetourOfficer`, más arriba— y corrida en la SNES de verdad con
el FX Pak. Es la ROM viva del proyecto: cualquier cosa que se quiera ver
jugando sale de acá. Es `demo-apertura` **más el mapa 8** —Lashe City, la
calle a la que da el pad de Talan— y por lo tanto la primera ROM en la que se
puede salir del pad: con el 8 adentro, la puerta `TalDoorTop` compila.

Desde el 2026-09-08 el mapa 8 **dibuja sus 68 eventos**, seis de ellos con una
paleta ajena: `@tile:BLchp1:111`, `@tile:BLchp1:117` —la puerta del pad—,
`@tile:BLchp1:53`, `Chara2:0`, `People4:0` y `savept:0`, o sea el save point.
Se ven con los colores cambiados y se ven; ver `assets/LIMITACIONES.md`.

Va **con cronómetro**: para hacerle lugar al rojo de los dígitos, `Future1:7`
baja de 15 a 14 colores (14,07% de sus pixeles). Se arma así:

    python3 tools/snes_convert.py --grupo 10 --map-id 4 --mapas 1 2 3 5 6 7 8 \
        --con-ventana --con-timer \
        -o rom/build/demo-ciudad/mapdata.inc
    python3 tools/w65.py rom/src/main.s -I rom/build/demo-ciudad \
        -o rom/build/demo-ciudad/demo-ciudad.sfc \
        --simbolos rom/build/demo-ciudad/demo-ciudad.sfc.sym

A quién bajarle un color lo elige el conversor, y sólo cuando de verdad no
tiene dónde: ni una paleta con lugar **ni una ranura libre**. Mirar sólo lo
primero le bajaba dos colores a `People4:5` en el mapa 5 —16,85% de sus
pixeles— cuando ese mapa usa cuatro paletas de las ocho.

Y el candidato tiene que estar **sólo en este mapa**: el banco de poses es de la
ROM entera, así que cuantizar a alguien distinto en dos mapas no da una imagen
fea sino un corte al emitir. Pasó con `Future1:4` la primera vez que se escribió.

El resto de los mapas donde el cronómetro puede aparecer no paga nada: de los
diez, en ocho entra en una paleta que ya tiene lugar.

### El Hover-Tram (mapa 13): entra

Pedía **once paletas de sprite de las ocho** —27 pasajeros de una sola página
cada uno, dibujados con diez sprites distintos, todos a la vez—. Desde que el
que no consigue paleta propia se cuelga de una ajena, el mapa convierte con
**dos** gráficos prestados: `BLPeople:0` y `Future1:2`. No hace falta ni
descartar pasajeros ni fusionar paletas, que eran las dos salidas caras.

Sin probar todavía: la ROM con el mapa adentro.

## Lo que taro probó y anda

El 2026-09-07, sobre `demo-apertura` en mednafen:

* **La apertura entera hasta el ascensor**, incluida la cinemática en la que
  Core rompe la puerta, que era la que estaba rota.
* **El Insta-Shave**, o sea `ShowChoice` con su cursor.
* **El cronómetro**, contando bien. Llegar a cero todavía no hace nada: en RM2k
  eso dispara un evento común con la condición "cronómetro en 0", y los eventos
  comunes no están.
* **Los mapas se ven mejor**, y hay un caso concreto: la sangre de Core en el
  piso era marrón y ahora es roja. Es el efecto de que el mapa 2 pasara de
  fusionar 13 colores a fusionar ninguno —ver la ventana de mensaje en la
  paleta 0—. `merge_least_used` fusiona el menos usado con su vecino más
  cercano por luma, y un rojo de unos pocos pixeles era justo el candidato a
  que lo absorbiera un marrón. No se buscó ni se predijo: es lo que el número
  anunciaba.


## Lo que taro todavía no probó

* **~~La salida del pad de Talan~~: probada y anda** —ver "Salir del pad de
  Talan: hecho", arriba—. Se deja el diagnóstico porque el mecanismo se repite:
  el 2026-09-07 taro quedó encerrado en un mapa vacío del que no se podía salir,
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
          --con-ventana --con-timer --descartar-eventos \
          -o rom/build/demo-apertura/mapdata.inc
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

* **La SNES de verdad, con el FX Pak: corrió, y anda.** taro lo probó el
  2026-09-09 y su veredicto fue *"anda todo bien, igual que en el emulador, al
  menos"*. Es la primera vez que se corre en hardware desde que el CRT volvió, y
  cae después de los cambios fuertes —entre ellos que el cartucho pasó de 512 KB
  a 1 MB—, así que lo que queda cerrado es lo que más pesaba: **el mapeo del
  cartucho expandido**. El header lo respalda, verificado sobre
  `rom/build/demo-ciudad/demo-ciudad.sfc`: mapmode `$20` (LoROM), tipo `$02`
  —ROM + RAM + batería—, tamaño declarado `$0A` = 1024 KB, que es exactamente lo
  que mide el archivo, SRAM `$03` = 8 KB, y el checksum del header coincide al
  byte con la suma real de la ROM (`$03DB`). Nada de eso quedó a medias tirando
  del tamaño para arriba.

  **Lo que el hardware todavía no desempató**, porque taro miró y no midió:

  - **El redondeo del brillo de `INIDISP`** —mesen-s contra los otros dos, acá
    abajo—. "Igual que en el emulador" es una señal a favor de snes9x y bsnes,
    que es donde corre la tanda, pero el fundido dura una fracción de segundo y
    la diferencia es un paso de quince: a ojo no se ve. Desempatarlo de verdad
    pide una captura del hardware, no una impresión.
  - **Guardar en el FX Pak.** En mednafen la partida llegó al disco —8 KB de
    `.srm`—, y en el flashcart es justo lo que puede portarse distinto: el
    cartucho tiene que escribir la SRAM a su tarjeta al apagar. La prueba es
    guardar, **apagar la consola**, y volver a encender esperando que arranque
    donde se guardó. No consta que se haya hecho.

* **El título del cartucho sigue diciendo `ABL SNES MUSIC POC`.** Es lo que el
  menú del FX Pak muestra y lo que lee cualquier base de datos de ROMs; quedó de
  la etapa en que la ROM era una prueba de audio. Es cosmético y de una línea del
  header, pero se ve en hardware, que es donde ahora estamos mirando.

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

* **El destello de un evento sobre la paleta de otro.** En la consola
  `FlashSprite` es un tinte de CGRAM: `pintar_flash` sube la paleta entera del
  personaje, así que tiñe todo lo que la comparta. La referencia lo aplica sobre
  la **imagen** del sprite, que es lo que hace RM2k. Son dos cosas distintas y
  ninguno de los 89 casos lo ve, porque ninguno tiene un segundo sprite visible
  compartiendo la paleta del que destella. Lo cuida `test_destello_paleta.py`,
  que exige que nadie comparta la paleta de un líder posible. **Protege al líder
  y no al que destella**: el blanco se decide corriendo y el héroe es el único
  que se puede saber al convertir, así que un destello sobre otro evento
  filtraría igual.

* **El cursor de `ShowChoice`.** La tanda sólo aprieta A, así que arriba, abajo
  y B no los toca nadie de ese lado; por eso la referencia tampoco los modela.
  Los cubre `pruebas/test_elegir.py`. Lo que la tanda sí compara es la ventana
  dibujada, en el caso `elegir`: el cuadro 140 tiene que decir `('> Yes', '  No')`
  y el 210 la respuesta de la rama que corrió. Que diga qué texto es no es
  adorno —lo imprime `snes_expect.py`—: cuatro cuadros en cero también sería el
  resultado si la página no compilara de los dos lados.

`just snes-hitos-foto` son **96 casos, todos en verde**, y el más largo es
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
