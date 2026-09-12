# Dónde quedamos

Lo que existe **sólo mientras alguien trabaja**: qué se decidió y sigue
valiendo, qué espera respuesta de taro, qué no se probó todavía, qué no cubre
la tanda, y hacia dónde vamos.

Lo que **no** va acá: el relato de lo hecho. Eso está en `git log`, que en este
repo tiene mensajes largos justamente para eso, y lo durable está en
`README.md`. Este archivo llegó a tener dos mil líneas por append-only y se
volvió inusable; se borra sin culpa lo que ya esté en esos dos lados.

Se escribe **mientras se trabaja**, no al final.

Última vez que se tocó: 2026-09-12.


## El objetivo, y dónde estamos

**Los primeros diez minutos jugables**, que es lo que taro viene probando vuelta
a vuelta.

Al 2026-09-12: `just snes-hitos-foto` son **123 casos, todos en verde**, y `just
pruebas` **83 en verde y 1 `xfail`**. El `xfail` no es adorno: es un defecto
medido de guardar con la pantalla de título puesta, y está abajo.

`demo-ciudad` se juega desde la apertura hasta la calle de Lashe City, con los
relámpagos, los autos y los NPCs andando, el agua moviéndose, la lluvia, el save
point animado y guardando, el menú de pausa, los ítems, el equipo y la tienda.
**Corre en la SNES de verdad con el FX Pak**, con la música por MSU-1 y los
efectos por el SPC700.

Las páginas automáticas que compilan enteras son **272 de 489**, y del juego
entero compilan **2329 de 3473**.

### El dibujo de las animaciones de batalla: medido, sin empezar

De lo que taro pidió para la intro, los efectos de sonido y los destellos están
hechos —README, "El paquete de audio de cada mapa" y "Las animaciones de
batalla"—. Falta **el dibujo**, y esto es lo medido el 2026-09-11:

En todo el juego son 388 `ShowBattleAnimation` en 81 mapas, con 42 animaciones
distintas. Las más usadas son chicas: la 141 (144x144), la 168, la 1 y la 132
(96x96). Las de la intro son las peores: la 79 y la 82 llegan a 512x192 y
488x336 con zoom de hasta 400%, y la 62 a 384x384.

Cada cuadro se puede prerenderizar —las celdas escaladas y compuestas— y subir
como sprites, con estos límites: VRAM de sprites libre en los mapas 2 y 3, 101 y
162 tiles (una caja de 96x96 son 144); una paleta de sprites más en mapas que ya
usan las ocho; 34 tiles de sprite por línea, que una animación ancha se come; y
el DMA de un cuadro de 96x96 son 4,6 KB cada dos cuadros. Los colores —hasta
38— se reducen a 15. **Las grandes no entran enteras de ninguna forma.**

**Una deuda encontrada de paso, anterior a todo esto:** la página de prueba no
arranca en el Emitter Room con `--switch 13 --mapas 4` —`auto_n` queda en cero y
la bandera del evento de prueba apagada—, mientras la referencia sí la corre. Es
lo que impidió armar un caso con la escena grande del mapa 3. No se investigó
más.

### Los translúcidos, horneados (2026-09-12)

El "Trans" de una página de RM2k —el evento al 160 de 255 sobre lo que tenga
detrás— ya no va tramado: **la mezcla la calcula el conversor contra el fondo
real y queda horneada en el gráfico**. Se puede porque los 70 translúcidos del
juego son **estáticos** (medido: `move_type` 0 y ninguna ruta propia), así que
la cuenta da siempre lo mismo. README, "Los eventos translúcidos van horneados";
el precio, en `assets/LIMITACIONES.md`. Lo cobra `fuego`.

De las 70 páginas se hornean **39**: las otras 31 se dibujan con un tile del
chipset y **todas llevan el tile 0**, que en RM2k es "sin gráfico" —así que el
`EV0068` del mapa 8 no se dibuja tampoco en el original—.

Lo que cuesta, todo medido: el objeto **queda opaco** (4 de 39 se superponen con
otro evento), 2 de 39 están sobre agua animada y adentro de su cuadro va a
quedar quieta, y dos eventos con el mismo CharSet sobre fondos distintos piden
dos paletas. Las paletas entran en los 35 mapas: sólo se mueven tres y ninguno
se cae.

**El save point va aparte y opaco**, por decisión de taro del 2026-09-12: ni
trama ni mezcla, el gráfico entero con sus colores. Es una divergencia
deliberada de RM2k —su página es `translucent`— y la referencia la modela igual.

**Antes de esto se probó el color math**, que es la transparencia de verdad de
la consola, y **taro lo rechazó**: el objeto dejaba de animar —35 de los 39
animan, y 33 son el save point— y el héroe se veía *a través*, que es lo único
que el orden de prioridades del modo 3 permite. Vive en la rama
`color-math-translucidos` (`6e0e355`), anda, y está contado en el README: "El
color math, implementado y descartado". Dejó dos cosas aprovechables —el canal
de HDMA que apaga la mezcla sobre la ventana de mensaje, y que **snes9x redondea
distinto que bsnes y mesen-s** en la suma de color math—.

### Los quince colores de un sprite: elegidos de nuevo (2026-09-12)

taro reportó tres síntomas —las caras de Talan y Core grises, Talan gris, y el
save point que *"pasó de azul/celeste/blanco a gris"*— y eran tres causas
distintas, las tres arregladas. El porqué durable está en el README, "Los
quince colores de un sprite": el criterio de fusión pasó a ser **el par que
menos se note** en vez del color menos usado, la paleta se cuenta sobre **las
poses que el evento puede mostrar** y no sobre las doce del bloque, y un CharSet
puede **pesar** para que no le toque la paleta prestada.

Medido sobre los 328 mapas: **-5,1% de colores fusionados, ningún gráfico
fusiona más que antes, ningún mapa se cae.** Error por pixel opaco: Talan -61%,
Core -63%, y las caras, que venían por un camino peor, entre -75% y -92%.

Lo que queda abierto:

* **Quién más merece peso.** `PESO_DE_GRAFICO` tiene dos renglones —`savept` y
  `Future1`— y se llena con lo que taro vea jugando. En el mapa 8, darle su
  paleta al save point se la saca a `People1:0`; si eso molesta más, es cambiar
  un renglón.
* **La referencia ignora los `topes` del cronómetro.** `snes_expect.pose_image`
  cuantiza siempre a quince colores, pero en un mapa que llene las ocho paletas
  el conversor puede bajar a un personaje a catorce para hacerle lugar al
  cronómetro. **Es anterior a todo esto y ninguna prueba lo cubre**: los casos
  con cronómetro de la tanda no caen en ese mapa. Hoy en `demo-ciudad` pasa una
  sola vez —`People4:4`—, pero es una discrepancia ROM/referencia por diseño y
  conviene cerrarla.
* **Contar un cuadro en vez de tres en los quietos: descartado con el número.**
  taro lo descartó el 2026-09-12 razonando que no daría nada, y la medición
  sobre los 61 casos del juego que animan quietos le dio la razón: **cero**
  diferencia de colores.

### El MSU-1 (2026-09-12)

Los ocho temas de las demos salen de pistas PCM al lado de la ROM. El porqué y
el cómo están en el README, "El MSU-1"; lo que hay que saber para trabajar:

* **Sin los archivos `.msu`/`.pcm` la ROM suena como siempre, por el SPC700**, y
  ése es el camino que corren la tanda y todas las pruebas. Verificar el camino
  *con* MSU-1 pide grabar audio, y se hace aparte.
* **Las pistas no salen de `snes-demos`**: son `just snes-msu <demo>`, aparte,
  porque pesan 10,6 MB por minuto —195 MB por ROM— y para jugar no hacen falta.
* **En la tarjeta los tres archivos van juntos y con el mismo nombre base.**
  Renombrar el `.sfc` sin renombrar el resto apaga el MSU-1, sin romper nada.
* **Los efectos de sonido no pueden ir por MSU-1**, y no es una decisión: es un
  único stream estéreo. Se quedan en el SPC700, que a cambio tiene la ARAM más
  holgada.
* **La pista suena a `$D8` y no a `$FF`** (`MSU_VOLUMEN_MAX`). El MSU-1 se
  **suma** a la salida del SPC700: con la música al tope no queda margen y la
  suma clavaba el techo cuando sonaba un efecto. Si algún día hay que moverlo,
  es esa constante y el fundido escala contra ella.

Lo que queda abierto:

* **El punto de loop.** El MSU-1 vuelve al principio del archivo, así que un
  tema con introducción la repite en cada vuelta. Los ocho loopean enteros.
* **El clipping del Emitter Room no se pudo reproducir acá.** taro lo escuchó
  ahí; lo medido y corregido es la apertura. Todas las corridas se quedaron en
  el mapa 1, porque la apertura no avanza sola y los números de `apertura` en
  `rom/hitos.txt` son **ticks**, no cuadros de hardware. Conviene volver con
  `snes-cinematica` bien usado.
* **Los 35 temas que las demos no tocan**, que serían 923 MB si algún día van
  todos.

### Lo próximo, si no se decide otra cosa

Al 2026-09-12, en orden.

1. **Cerrar las tres vueltas que están en el aire**, cada una en su worktree:
   el pre-horneado de los translúcidos (rama `prehorneado-translucidos`, que va
   a quedar), el save point opaco con su paleta, y el cartel de "One year
   previous". Las tres tocan `snes_convert.py`, así que hay conflictos de git
   que resolver al mergear.

2. **El gris de los personajes.** taro lo reportó el 2026-09-12: las caras de
   Talan y Core, y el save point, se ven grises. Una paleta de sprite guarda 15
   colores y `Future1` —Talan, Core, Kersh, Manta— tiene 43 a 47 por personaje;
   `ABLFaces`, 22 a 28 por cara. O sea que el hardware obliga a tirar colores y
   lo único que se elige es **cuáles 15**. Hoy los elige `merge_least_used`, que
   fusiona el color menos usado: un brillo de pocos pixeles pierde siempre
   contra un gris que cubre superficie. Tres puntas, medidas: contar sólo las
   poses que el evento muestra —`sprite_colors` cuenta las doce aunque el port
   ya guarde una sola: en `savept` son 41 colores contra 27, o 13 según la
   pose—, un criterio de fusión mejor, y el "peso" por gráfico que propuso taro.
   **Descartado por él**: analizar evento por evento si alguna vez anima, que
   ahorraría un cuadro y probablemente ningún color.

3. **El `xfail` de guardar tras cambiar de mapa.** Es un artefacto de la página
   de prueba, no del juego: el caso con el save point de verdad —`savepoint-guarda`—
   da cero, y taro guardó y cargó jugando. El sospechoso es el doble
   `cargar_mapa` del título contra el refresco de páginas. El `reason` del
   `xfail` en `test_titulo.py` tiene la medición entera; no hace falta
   repetirla acá.

4. **El dibujo de las animaciones de batalla.** El sonido y los destellos están
   hechos; el dibujo no. Lo medido está en su sección, arriba.

5. **El tile testigo del mapa 4**, que propuso taro: que un mapa vacío no se
   confunda con una pantalla rota, porque ya pasó más de una vez que una
   captura negra fuera un PPU mal configurado. **Por el conversor y bajo un
   flag**, con la referencia sacándolo de la misma función, y no editando
   `Map0004.lmu`: el juego original es lo que hace comparable este port contra
   easyrpg, y un mapa retocado ahí contamina toda medición futura sin avisar.

6. **Lo que sigue faltando de Lashe City**: la condición por cronómetro —una
   página en todo el juego— y el `CallEvent` del Hover-Tram.

7. **Lo que falta del sistema de ítems**: los libros, los materiales y los
   especiales, y `ChangeEquipment` —sólo en los mapas 30 y 151—. Las medicinas
   piden HP que cambien, o sea parámetros de actor y niveles, que no existen.
   La consola y su evento común quedan afuera por decisión de taro del
   2026-09-11: la idea es un sistema propio del port en vez de las imágenes del
   original.


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

* **Las órdenes de ruta 26 y 27 sobre el héroe se aceptan y se tiran.** Fijar y
  soltar la mirada. Decidido con taro el 2026-09-06: son un extra y el juego se
  puede jugar sin ellas. Se tiran **al compilar**, así que la referencia tampoco
  las camina y los dos lados quedan iguales por construcción. Las 28 y 29 —la
  velocidad— sí se hacen, y con ellas el paso del héroe dejó de ser fijo: cuenta
  medias unidades de RM2k y **queda a la velocidad que la ruta le dejó**, como
  en RM2k, que repone la frecuencia al terminar pero no la velocidad.

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

* **La tecla de acción mira las dos celdas, y cada una pide la capa
  contraria.** `CheckEventTriggerHere` quiere `GetLayer() != Layers_same` y
  `CheckEventTriggerThere` quiere `== Layers_same`. No es simetría de adorno: un
  evento de la capa del héroe le cierra el paso, así que nunca se podría parar
  encima; uno de otra capa no lo frena y se le camina por arriba. El filtro vive
  en la ROM y no en el conversor, porque la misma página vale o no según qué
  celda la esté mirando.

* **Se dibujan todos los eventos, aunque sea con una paleta ajena.** Es de taro:
  *"si no podemos incluir todos los eventos, el proyecto entero se cae"*. El que
  no consigue paleta propia se cuelga de la que menos colores le falte, y cada
  color ausente va al más cercano por luma. **La referencia hace la misma
  aproximación**, o la comparación mediría dos programas distintos. Los números
  están en `assets/LIMITACIONES.md`.

* **Los líderes posibles comparten una ranura de CGRAM.** Lidera uno a la vez,
  así que darle paleta propia a cada uno es tenerla ocupada por alguien que no
  está en pantalla. La excepción es el líder que además es NPC de ese mapa —Kersh
  en los mapas 1 y 6, Talan en el 3—, que se lleva la suya porque las dos filas
  se usan a la vez.

* **El cronómetro no tiene paleta propia**: entra en la de cualquier personaje
  que use trece colores o menos. Tenerla aparte costaba un evento sin dibujar en
  el mapa 2 —la celda del medio de la puerta que Core rompe—, y un evento que no
  se dibuja igual ocupa lugar en `npcs_dibujables`.

* **Una puerta al mismo mapa no recarga el mapa.** Recargar vuelve a leer del
  cartucho las posiciones de los eventos, y con eso se pierde lo que los haya
  movido aunque el jugador nunca haya salido. Los dos lados comparan contra el
  mapa anterior, que es el `map_changed` de `Game_Player::PerformTeleport`.

* **Atravesar paredes vale también para el salto**, no sólo para la caminata:
  `CheckOrMakeWayEx` corta con `if (self.GetThrough()) return true;` antes de
  mirar la pasabilidad, y `BeginMoveRouteJump` pasa por ahí. Pero **no es salirse
  del mapa**: el chequeo de límites va antes, así que el que atraviesa se queda
  clavado en la última columna.

* **Agotar el presupuesto de teletransportes es un error, no un caso.** Al
  agotarse, la ROM llama a `entrar_en_panico` y la referencia levanta
  `DemasiadosSaltos`. Un salto descartado en silencio es la forma de falla que
  el CLAUDE.md nombra, y ésta sobrevivió semanas porque la partida seguía
  andando, sólo que en el mapa equivocado.

* **Las ROMs para probar a mano viven en `pruebas-manuales/<fecha>-<commit>/`**,
  en el repo y gitignorado, desde el 2026-09-12: taro las saca desde el host, y
  sacarlas de `/extras` pedía un `podman cp` cada vez. Lo anterior a esa fecha
  quedó en `/extras/builds/`. **Cuidado con el disco**: un build con las ocho
  pistas de MSU-1 son 383 MB, y éste es el disco de taro y no un volumen
  descartable; conviene dejar el último y borrar los anteriores.

* **Los gráficos están todos medidos y viven en `assets/`.** El titular, para no
  tener que abrirlo: **el juego entra en 4 MB**. Son unos 2,9 MB entre mapas,
  sprites, tiles y música, más 2,7 de arte que todavía no dibuja nadie.

* **Los líderes posibles son una aproximación.** El conversor simula los
  `ChangePartyMembers` de las páginas que compilan para saber qué actores pueden
  ir primeros. Si alguna vez un personaje se dibuja sin gráfico, es el primer
  lugar donde mirar; `pruebas/test_lideres.py` cuida la parte que ya falló.

* **Los builds numerados de `rom/build/` no se arman a mano.** No están en git
  y no los produce ninguna receta salvo el 12. Armar uno a mano es cómo se
  terminó mirando el mapa 6 creyendo que era la demo del hito 12.


## Lo que taro probó, y lo que falta probar

Al 2026-09-12. Lo viejo se borra a medida que deja de ser noticia: lo que anda y
ya nadie discute no necesita renglón.

**Probado en hardware, con el FX Pak:**

* **El audio entero**, el 2026-09-12: la música por MSU-1 y los efectos de
  sonido sonando juntos. *"Anda de 10"*.
* **Un MSU-1 ajeno** —el Link to the Past con música de CD— para descartar su
  tarjeta y su firmware como sospechosos. Anda perfecto.
* Antes: la ROM de 1 MB, y después la de 2 MB con FastROM.

**Probado en emulador:**

* **Mesen** tiene MSU-1 y **mednafen no**, lo cual resultó útil: mednafen es el
  control natural de que el camino sin pista sigue andando.
* El **pre-horneado** de los translúcidos le gustó para los fuegos. El **color
  math** lo rechazó: sin animación y con el héroe viéndose a través.

**Lo que falta probar, y a nadie más se le puede pedir:**

* **Guardar en el FX Pak de punta a punta**: guardar, **apagar la consola** y
  volver a encender esperando aterrizar donde se guardó. En mednafen la partida
  llega al disco; el flashcart tiene que escribir la SRAM a su tarjeta al
  apagar, y eso es justo lo que puede portarse distinto. No consta que se haya
  hecho.
* **El diagnóstico `diag3` corregido**, en `pruebas-manuales/msu-diagnostico/`.
  La versión anterior escribía CGRAM fuera del vblank y ensuciaba la pantalla en
  hardware —bandas diagonales y formas—, así que **sus colores no valen**. El
  FX Pak contesta "no encuentro la pista" con nuestros archivos y todavía no se
  sabe por qué, siendo que la ROM del juego sí la encuentra.
* **El título del cartucho sigue diciendo `ABL SNES MUSIC POC`**, que es lo que
  muestra el menú del FX Pak y lo que lee cualquier base de datos de ROMs. Es
  una línea del header, pero se ve en hardware.

## Lo que la tanda no cubre

* **El destello de un evento sobre la paleta de otro.** En la consola
  `FlashSprite` es un tinte de CGRAM: `pintar_flash` sube la paleta entera del
  personaje, así que tiñe todo lo que la comparta. La referencia lo aplica sobre
  la **imagen** del sprite, que es lo que hace RM2k. Son dos cosas distintas y
  ninguno de los 123 casos lo ve, porque ninguno tiene un segundo sprite visible
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

El más largo de los 123 casos es `talan`: mil doscientos cuadros de la escena
entera del Emitter Room. Lo que la tanda no mira:

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

* **snes9x perdona lo que el hardware no, y van cuatro.** La carga de la SRAM
  —un modo de direccionamiento—, el PPU que se quedaba con los registros del
  título, y dos más; **tres los encontró taro jugando, con la tanda en verde**.
  El caso extremo quedó medido: sacando el `jsr ppu_init` que arregla el
  segundo, snes9x sigue dando **cero pixeles de diferencia**. Lo mitigan
  `snes-mednafen` y `snes-bsnes`, y el reset de snes9x **no borra la WRAM**, así
  que una prueba que dependa de que algo no sobreviva a un reinicio tiene que
  ensuciarla a mano.

* **El brillo del fundido, según el core.** Medido el 2026-09-06 sobre los
  dieciséis niveles: en 0 y 15 los tres coinciden; entre 1 y 14 snes9x y bsnes
  coinciden exactamente y **mesen-s difiere en 30% a 48% de los pixeles**, un
  paso para abajo. O sea que difiere exactamente mientras dura un fundido y en
  ningún otro momento. La trampa práctica: el justfile toma el core de `CORE`,
  así que correr la tanda con `CORE=mesen-s` pondría en rojo todo cuadro que
  caiga en un fundido **sin que haya ningún bug**. taro miró un fundido en la
  SNES y le pareció bien, así que se da por bueno el redondeo de snes9x y bsnes;
  lo que se cerró es la decisión, no el número —nunca se comparó contra una
  captura del hardware—.

* **La guarda de la paleta vacía** en `tenir_paleta` protege una condición que
  el conversor no puede producir hoy: siempre emite al menos una paleta de
  sprites y una de la capa de encima. Se deja —el error que arregló fue real y
  un DMA de cero bytes transfiere 64 KB— pero como código inalcanzable, no como
  camino sin probar. Si el conversor deja de forzar esa paleta mínima, vuelve a
  la lista.


### El cartel del "One year previously" (2026-09-12)

taro lo pidió ese día, y con el porqué puesto: es **el caso fácil** del sistema
de imágenes —aparece una sola vez, entre un fundido y otro, sobre un mapa de un
solo tile, así que no le pelea VRAM ni colores a ningún ChipSet ni CharSet—.
Hecho y verificado: `snes-cinematica 4 7 "470 550 660 800 880" 115 cartel 1 ""
21` está en `rom/hitos.txt` y los cinco cuadros dan **cero**.

El cómo está en el README, "El cartel de 'One year previously'". Lo que conviene
tener a mano para tocarlo:

* **Un cartel por ROM**, y quién se queda con la ranura lo decide
  `Imagenes.elegir` mirando todos los mapas en el orden de la tabla, antes de
  compilar nada. Con "el primero que pase" los dos lados podían elegir
  distinto, porque la referencia compila los mapas en un orden que depende de
  si la ROM lleva ventana.
* **El fundido es de tono y no de transparencia.** Los dos `MovePicture` dejan
  `top_trans` en cero y mueven (r, g, b). Y **la duración viene en décimas**:
  los 35 del primero son 210 cuadros. Eso subió la página del "1 year earlier"
  de 105 décimas a 160, y por eso `test_un_ano_antes.py` pasó de 900 cuadros a
  1200.
* **Quince colores de los 226 del PNG**, y el degradé del resplandor se
  escalona. Es lo cosmético declarado de esta vuelta; falta que taro lo
  confirme jugando.
* **El estado vive en `$7E30E8`, en la RAM lejana**, porque en el banco 0 no
  entraba: la BSS estaba en **7680 de 7680**. Lo que siga pidiendo RAM del
  banco 0 va a tener que aflojar algo.
* **`armar_paleta` deja Y en 32.** Llamarla desde un opcode sin `phy` le mueve
  el cursor al intérprete. Costó el primer rojo y no se veía como un cartel
  roto: la página seguía corriendo, sólo que otra.

**Lo que no cubre nada**: el cartel sobre una pantalla que destelle. En RM2k las
imágenes sí reciben el `FlashScreen` —`affected_by_flash` viene prendido— y acá
no, porque su paleta queda fuera del rango que el destello recorre. Ninguna
página del juego destella con un cartel puesto, así que es deuda declarada y no
un camino a medias.

**Lo que costaría el sistema entero** está medido y en el README: 34
`ShowPicture` en el juego, 20 carteles distintos, 7 comandos de 34 que el
modelo de hoy sabe hacer, y cinco imágenes de 320x240 exactos que **con objetos
no se pueden hacer** —serían 56 de los 128 de OAM y 32 de los 34 tiles por
línea—. Ésas piden prestarle una capa al cartel, y con eso el mapa se recarga
al borrarlo.

## Lo que se dejó afuera a propósito

* **El panorama del mapa 2** —los puntitos sobre azul cuando se enciende la
  pantalla grande— pide una tercera capa de fondo y el modo 3 tiene dos.
* **Los otros tipos de movimiento de las rutas propias**: al azar, vertical,
  horizontal y hacia el héroe. Son 106 páginas. Y el giro en el lugar.
* **El fundido de la transparencia de una ruta**: se acepta y se tira, porque
  la SNES no atenúa un sprite por partes sin color math.
* **La ráfaga de entrada del mapa 8**: dos cuadros perdidos al entrar,
  invisibles jugando porque el fundido los absorbe —su reloj son cuadros de
  hardware—. Medido: las dos primeras vueltas se pasan del presupuesto de 262
  líneas por 1,45x y de la tercera en adelante sobra la mitad del cuadro; el
  grueso es crear las ranuras de ruta de los paralelos. Es optimización, no
  corrección, y por eso no se hizo.

* **Los cuadros que el lazo pierde de vez en cuando** —la primera vuelta de una
  ROM con muchas páginas, y la vuelta en que termina un fundido—. No cambian
  ningún pixel comparado, y son lo único que le falta a la escena del ascensor
  para tener caso propio en la tanda.
