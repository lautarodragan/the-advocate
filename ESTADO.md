# Dónde quedamos

Lo que existe **sólo mientras alguien trabaja**: qué se decidió y sigue
valiendo, qué espera respuesta de taro, qué no se probó todavía, qué no cubre
la tanda, y hacia dónde vamos.

Lo que **no** va acá: el relato de lo hecho. Eso está en `git log`, que en este
repo tiene mensajes largos justamente para eso, y lo durable está en
`README.md`. Este archivo llegó a tener dos mil líneas por append-only y se
volvió inusable; se borra sin culpa lo que ya esté en esos dos lados.

Se escribe **mientras se trabaja**, no al final.

El 2026-09-15 pasó de 2.703 líneas a menos de 800: se habían acumulado treinta
secciones fechadas de "taro reportó tal cosa, se arregló así", que es justo lo
que el párrafo de arriba dice que no va acá. Están enteras en el `git log`.

Última vez que se tocó: 2026-09-15.

**Ramas sin mergear**, para que no se pierdan de vista: `color-math-translucidos`
y `worktree-agent-a1910a15fe409b9b6` (la misma idea, del 2026-09-12: hacer los
translúcidos con el color math del PPU en vez de con trama). Todas las demás
ramas de sub-agente están mergeadas y sus worktrees borrados —eran 18 y ocupaban
7,1 GB—.


## La etapa en curso: partir el pipeline, y cero features hasta terminarla

Decidido el 2026-09-15, con estas palabras: **"cero nuevos features antes de
terminar toda esta etapa de refactors"**. Hasta que esto cierre, no se propone
ni se empieza una feature; si algo parece urgente, se dice y decide taro.

El porqué es suyo y conviene tenerlo entero, porque ordena las decisiones de
diseño de toda la etapa: el juego llegó más lejos de lo que esperaba, quiere
aplicarle las reglas de arquitectura que le gusta tener en cualquier proyecto,
y quiere **depender menos de IA y tener un buen mapa mental**, para lo cual
necesita cada cosa separada y definida. A eso suma que el 90% de lo que hicimos
es reutilizable por otros, y que *"un binario estáticamente vinculado que
recibe un input y genera un output se puede aprender a usar fácilmente, sin
entender sus detalles de implementación; y si encima tiene buen manejo de
argumentos y reporte de errores, cualquier IA puede aprender a usarlo
inmediatamente, sin gastar muchos tokens y con mínimo espacio para error"**.

De ahí sale el criterio que se le aplica a cada pieza nueva: **`--help` y los
mensajes de error son features, no prolijidad.** El modelo hecho es
`protocol/`: argumentos con clap, errores que nombran el archivo y lo que se
esperaba, y dos códigos de salida distintos (1 = algo quedó viejo, 2 = la
llamada está mal).

Los pasos, en orden, y ninguno bloquea al otro salvo 3→5→6:

1. **los conversores puros**, un proyecto por responsabilidad: `brr/` (muestras
   → BRR, con el lector de SoundFont) y `tiles/` (PNG → tiles y paletas). Son
   puros y lo sabemos **porque el conversor ya los cachea**. Los dos están
   hechos y conviven con su Python; lo que falta medido está más abajo;
2. **`w65/`**, el ensamblador de 65816. El contrato más limpio del repo;
3. **el asignador** —paletas, ARAM, VRAM— que es lo que queda de
   `snes_convert.py` cuando le sacás los conversores, más el secuenciador de
   MIDI al SPC700, que **no** es un conversor tonto: conoce el driver y usa
   `protocol/music.toml`;
4. **el compilador de eventos**: JSON → bytecode y tablas. No es Ditto y no
   puede serlo: Ditto es un transcodificador bidireccional y sin pérdida, y
   esto es un compilador unidireccional, con pérdida y atado a un target. Lo
   que sí sale de acá es `tools/lcf.py` + `tools/ditto_schema.py` (2.793
   líneas), que en Rust pasan a ser `use ditto`. Y `tools/rm2k.py` —534 líneas
   de semántica de RM2k— se **duplica** a Rust a propósito, con la copia de
   Python quedando sólo para la referencia, hasta que se vayan las dos juntas;
5. **el arnés del emulador**, y no antes: un arnés en Rust llamando a una
   referencia en Python es peor que cualquiera de los dos extremos. `retro.py`
   habla con el core por ctypes, así que ahí no hay nada nativo de Python;
6. **se elimina `tools/snes_expect.py`**, la referencia, y con ella la regla de
   que un cambio en la ROM y su cambio en la referencia van juntos.

**Las pruebas se quedan en Python**, y no es deuda: es diseño. Decisión de taro
—un lenguaje interpretado y menos estricto tiene ventajas ahí, y compilar para
correr la tanda suma tiempo sin aportar casi nada—, y tiene un efecto
estructural que conviene nombrar: mientras el conversor sea Rust y la
referencia Python, **la frontera del lenguaje hace imposible que compartan
código**, que es lo que hoy pasa y no debería (`snes_expect.py` le importa 25
funciones a `snes_convert.py`).

### Cómo se reemplaza la referencia, que es el paso 6

Golden files, confirmados **jugando** por taro, uno por uno. Lo que se pierde
hay que decirlo: un golden caza regresiones, no errores de nacimiento — una
feature que sale mal desde el día uno hornea el bug adentro del golden. Se
acepta porque la evidencia dice que la referencia tampoco los cazaba: los bugs
de esta semana —Delcentric, la colisión pegada del Hover-Tram, el HP de los
enemigos, la música, el menú de batalla— los encontró él jugando, no la tanda.
Donde la referencia sí se ganaba el sueldo era el pixel, que es justo donde un
golden funciona mejor.

Dos condiciones acordadas:

* **actualizar un golden tiene que ser un acto deliberado**, con la receta
  imprimiendo qué cambió y exigiendo un flag; la tanda **nunca** regenera. Es
  el único modo de falla real del esquema;
* **no se borra la referencia hasta que los goldens existan y estén
  bendecidos**. Capturar los 170 casos es barato; la bendición sólo la puede
  dar él.

Y lo que reemplaza a la referencia para las features **nuevas**: mirar las
capturas. taro quiere presupuesto para eso —"la IA es excelente para leer
imágenes"— pero **fuera de la tanda**, que con visión sería demasiado cara.

## El objetivo, y dónde estamos

**Los primeros diez minutos jugables**, que es lo que taro viene probando
vuelta a vuelta.

Al 2026-09-15: `just snes-hitos-foto` son **170 casos, todos en verde**, y
`just pruebas` **177 en verde y 1 `xfail`**. El `xfail` no es adorno, y desde
el 2026-09-13 se sabe de quién es: es un defecto de la **página de prueba** de
guardado y no del juego. Está abajo, en "Lo que la tanda no cubre".

Los cinco proyectos en Rust tienen sus propias tandas: `just w65-pruebas`,
`brr-pruebas`, `tiles-pruebas`, `protocolo-pruebas` y `ditto-pruebas`.

`demo-ciudad` se juega desde la apertura hasta la calle de Lashe City, con los
relámpagos, los autos y los NPCs andando, el agua moviéndose, la lluvia, el save
point animado y guardando, el menú de pausa, los ítems, el equipo y la tienda.
**Corre en la SNES de verdad con el FX Pak**, con la música por MSU-1 y los
efectos por el SPC700.

Las páginas automáticas que compilan enteras son **332 de 489** —`just
snes-destraba`—, y del juego entero **5198 de 5603 disparables (92,8%)**, que
eran 5170 antes de las dos preguntas de actor de una rama, y 5016 antes de la
clase 6 de `ControlVars`. El 5156 que decía acá era de antes del merge
`f336b63`; medido de nuevo el 2026-09-13 sobre `5461d6d`, la base es 5170.

**Cómo se cuenta, porque es fácil contarlo mal**: cada página de los 328 mapas
cuyo trigger la ROM soporta y que pasa `puede_dispararse`, por
`eventos.compilar_pagina`, con bloque de textos, con `Temas`, `Graficos` e
`Imagenes`, con todos los teletransportes resolubles —o sea el techo de una ROM
con la ventana puesta— y con **`eventos.indexar_variables` llamado antes**. Sin
eso último ninguna `ControlVars` compila y el total sale 300 páginas por debajo;
pasó el 2026-09-12 y los números de los dos primeros commits de ese día son
ésos.

**El denominador cambió y conviene saberlo**: acá venía escrito "2882 de 3473",
que cuenta sólo las páginas **con comandos**. Con ese criterio los mismos
números son 2936 de 3473, y antes de la clase 6 eran 2817 —no 2882: ese
absoluto no se pudo reproducir con ninguna combinación de argumentos de
`compilar_pagina`, así que lo que vale es la diferencia—. **La diferencia es la
misma con los dos criterios: +119 páginas.** Cuando un número de éstos se
reporte, conviene decir con cuál de los dos se contó.

Las ROMs que taro va probando a mano quedan en `pruebas-manuales/<nombre>/`,
cada una con su `LEEME.txt` diciendo qué mirar y con qué limitaciones se chocó.

## El estado de los cortes

Cinco proyectos independientes, todos en inglés y sin una mención a este juego.
Qué está enchufado y qué no, que es lo que cambia semana a semana:

    ditto/      lee y escribe los formatos de RM2k     enchufado: `data/` sale de acá
    protocol/   declara los dos bytecodes              enchufado: los cuatro generados
    w65/        el ensamblador de 65816                enchufado: las ROMs salen de acá
    brr/        códec BRR y lector de SoundFont        **no**: la ROM usa el de Python
    tiles/      imagen -> tiles, paletas y tilemap     **no**: ídem

Los tres enchufados tienen su prueba de que no cambiaron nada: las ROMs salen
byte por byte iguales a las de antes de cada corte. Los dos que no, tienen la
suya de que **podrían** enchufarse: 608 muestras y 455 PNG idénticos a los del
Python.

### Lo que hay que decidir

* **El desempate de `try_pack`.** Reparte los colores recorriendo
  `sorted(sets, key=-len)` sobre un `set` de `frozenset`, así que los empates
  —que son el caso normal— los desempata el orden de iteración de una tabla de
  hash, que no es parte de la entrada. Medido: **156 de 200 barajadas del mismo
  conjunto dan otro reparto**. La ROM de hoy sale siempre igual porque los
  hashes de enteros no varían entre corridas, así que no es una ROM que cambie
  sola: es un desempate del que dependemos sin haberlo elegido, y tiene costo
  —en una llamada medida obliga a fusionar dos colores que con un desempate
  determinista no haría falta fusionar—. `tiles/` desempata por los colores
  mismos: de 32 llamadas, 25 idénticas, 1 con las mismas paletas en otro orden,
  6 distintas y **ninguna peor**. O el asignador se queda con el determinista y
  se acepta que el tilemap de algunos mapas cambie —y hay que rebendecir esos
  PNG—, o hay que reproducir el orden de hash de CPython adentro de un crate
  que no debería saber que CPython existe.
* **Si se borra `tools/w65.py`.** Hoy es la segunda implementación que valida a
  la de Rust, y de eso vive `just w65-comparar`. Borrarlo gana simplicidad y
  pierde la única comparación que tenemos.

### Defectos de los originales, anotados y no arreglados

Ninguno se tocó al portar, porque arreglarlos cambiaría la salida y eso es
decisión aparte:

* **BRR, dos divergencias del hardware real** (verificadas contra `SPC_DSP.cpp`
  de bsnes): con shift 0 el chip pierde el bit bajo del nibble y nuestro modelo
  no —128 bloques de 85.629, amplitud ±7—, y el hardware envuelve a 16 bits
  donde el Python satura —0 casos en 1.370.064 muestras, latente si sube el
  pico—.
* **El control de rango de `.byte` del ensamblador está muerto desde que se
  escribió**: vive en `Data.emit` pero `emit_item` trunca por su cuenta sin
  mirarlo. Hoy no hay ningún `.byte` fuera de rango, así que revivirlo no
  movería la ROM. Si se revive, va en los dos ensambladores a la vez.
* **`jml etiqueta` no se puede escribir** sin `f:`, y **una etiqueta llamada
  `a` es inalcanzable** como operando: el decodificador la lee como el
  acumulador.
* **`try_pack` no rechaza un tile que no entra en ninguna paleta**: si queda
  una libre lo mete igual y devuelve un grupo de más de 15 colores, y entonces
  `convert_above` muere con `ValueError: negative count`. Ninguna imagen del
  juego tiene una celda así.

### El próximo cuello

`pruebas/consola.py:695` arma sus ROMs llamando a `tools/w65.py` **desde
Python**, no desde una receta, así que la migración del ensamblador no lo
alcanzó. Buena parte de `just pruebas` es eso. Migrarlo pide decidir quién
corre el `cargo build` cuando el que arranca es pytest y no `just`.


### La carrera, cuando llegue: 41 paralelos que comparan posiciones

Anotado el 2026-09-13, antes de que haga falta. Los mapas de la persecución en
auto —49, 52 y 54— tienen **41 eventos con página paralela cada uno**, el
triple que el HQ de los Lazer Teeth, y son los tres mapas con más de todo el
juego. Medidos en frío dan 0 paralelos activos y 60 fps: se encienden a medida
que la carrera avanza, así que el número de verdad todavía no se vio.

Cada obstáculo es un paralelo que compara su posición con la del héroe, que es
el mismo patrón que el minijuego del HQ. Con el costo que tenían el 2026-09-13
—unos 3.200 ciclos por paralelo y por cuadro— serían ~131.000 ciclos, más de
dos cuadros: la carrera correría a unos 20 fps. Con la página cacheada eso
debería desaparecer, y por eso **no se hizo nada especial acá**: primero medir
la carrera con el arreglo puesto.

Si aun así no alcanzara, taro dejó la idea: **la coordenada x del auto sólo
incrementa**, así que los obstáculos podrían ordenarse por x y mirarse sólo los
que están cerca, en vez de los 41 todos los cuadros.

### Lo próximo

**Está arriba, en "La etapa en curso": no hay features hasta terminar los
refactors.** Lo que quedó pedido o pensado y espera a que esa etapa cierre,
para no volver a pensarlo:

* **Curar fuera de la pelea** y **mostrar el HP como `20/20`** en el menú.
* **El rediseño de la escena de batalla**: fondo real y monstruos por separado,
  compuestos en VRAM al armar la pelea. Medido: unos 667 KB para el juego
  entero contra los 4,1 MB de hornear cada combinación.
* **`ShowInn` para el Bum**.
* **Los eventos-tile al fondo** para el lag del minijuego del HQ.
* **La carrera de Lashe City**, que tiene su propia sección acá arriba.
* **El dibujo de las animaciones de batalla**: está medido y sin empezar; el
  sonido y la luz sí están.

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

* **`ConditionalBranch`: cinco de las doce clases.** Switch, variable, oro,
   objeto y actor, y de la de actor tres de sus siete preguntas —está en el
   grupo, sabe la habilidad, tiene puesto el objeto—. El renglón de abajo es
   de cuando sólo había switch y se deja porque el porqué sigue valiendo; los
   números de hoy están arriba.

   Lo viejo: **sólo con condiciones de switch.** Son 21 páginas de
   las 24 que el comando destraba; las tres que faltan preguntan por el héroe
   en el grupo, y sin grupo variable esa rama daría siempre lo mismo: modelarla
   sin nada que la ejercite es inventarse una diferencia. Las variables suman
   cero, medido.

  Compila a dos opcodes: `OP_IF` —switch, polaridad y destino— y `OP_GOTO`, el
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

* **La orden 9 de ruta, `move_towards_hero`, se camina desde el 2026-09-12.**
  No es una orden nueva: `UpdateMoveRoute` hace `TurnTowardCharacter(hero)` y
  después `Move(GetDirection())`, o sea la 21 y un `move_*` pegados, así que
  los dos lados la resuelven con lo que ya tenían. Medido sobre el juego
  entero, **+33 páginas** —de 2802 a 2835—, y es la única que rendía: las otras
  nueve que faltan (al azar, huyendo del héroe, hacia adelante y los cinco
  giros en el lugar) suman **+1 entre todas**, así que no se hicieron. La cubre
  `npc-hacia-heroe`. Queda afuera en las **rutas propias de página**, que son
  dos del mapa 105 y ninguna prueba llega ahí; ver `ruta_propia`.
* **Las diagonales van sobre eventos y no sobre el héroe**, y siguen así: su
  paso está escrito una vez por dirección, y de las 26 rutas del juego con
  diagonales ninguna es del héroe. El conversor rechaza la página que lo
  intente.

* **`CallEvent` se compila en línea desde el 2026-09-12**, y con eso el
  Hover-Tram del mapa 9 se puede tomar. En RM2k es `Push<ExecutionType::Call>`,
  una pila de intérpretes; acá no hace falta ninguna, porque el llamado corre
  entero antes de que siga el que llamó, así que pegar su bytecode en el lugar
  da lo mismo. **Ninguna llamada de este juego es recursiva**, medido, y el
  anidamiento se topa en `LLAMADA_MAX`.

  Es la única de las cuatro piezas que **no toca la ROM ni la referencia**: los
  dos corren el mismo bytecode, así que no hay dos lados que se puedan separar.
  Por eso su caso se verifica en rojo de un solo lado, bajándole `LLAMADA_MAX`
  a la referencia.

  Lo medido: **cero páginas ganadas y cero perdidas** —2882 antes y después—,
  porque si el llamado no compila la llamada se saltea, que es lo que el port
  venía haciendo. Exigir que compilara costaría **183 páginas** de las 221 que
  compilan y llaman. Se hacen de verdad **10 llamadas** en cuatro mapas —el 9,
  el 11, el 114 y uno más— y se siguen salteando 216, casi todas a eventos
  comunes que se cortan en `ControlVars` y en los menús propios del original.
  El precio en cartucho es **+608 bytes de bytecode en todo el juego, +0,9%**,
  y se lo llevan tres mapas: el 11 (+344), el 9 (+195) y el 114 (+69).

* **La orden 34 sobre el héroe se hace desde el 2026-09-12**, y lo que la tenía
  afuera resultó no valer: su gráfico sale de la tabla de actores, pero las
  doce poses del actor están escritas **con la misma forma** que una entrada de
  `npc_poses`, así que la ROM le mueve el puntero a `hero_poses` y `place_hero`
  ni se entera. Son **+30 páginas** del juego —de 2835 a 2865— y 16
  automáticas, y entre ellas las tres del `EV0047` del mapa 8, con el que taro
  nunca pudo interactuar, y la del `Hover-Tram` del mapa 9, que le cambia el
  gráfico al héroe para subirlo. Lo que cuesta, las dos cosas declaradas y
  modeladas igual de los dos lados:

  * **Mientras el cambio está puesto, el héroe se dibuja con la paleta del
    gráfico nuevo**, que es una de las ocho de sprite del mapa, y no con la
    ranura propia del líder. `hero_cgram` se apaga al cambiar: dejarlo puesto
    le escribiría los quince colores de Talan encima a la paleta del gráfico,
    porque `aplicar_tinte` los sube **en la fila que dice `hero_pal`**.
  * **No sobrevive al cambio de mapa.** Las poses viven en el banco de sprites
    del mapa, así que el gráfico de allá no existe acá; la ROM lo repone en
    `elegir_grafico_heroe` y la referencia en `entrar_a_un_mapa`. En RM2k
    `Game_Player` se lo lleva. No se nota: la única página del juego que cambia
    el gráfico del héroe y después salta lo vuelve a poner en el comando
    siguiente al teletransporte.

  Y lo que cuesta en el cartucho, medido sobre `demo-ciudad`: el gráfico al que
  una ruta cambia al héroe entra al **banco de sprites del mapa**, como el de
  cualquier evento. En el mapa 9 son dos más —`Future2:7` y `Future1:0`— y con
  ellos un evento dibujado con un tile del chipset pasa a colgarse de una
  paleta ajena. **Las animaciones de batalla del mapa 9 no se dibujaban ya
  antes**: el control sin la 34 da el mismo aviso, así que ese mapa llenaba las
  ocho paletas por su cuenta.

  Lo cubren `grafico-heroe` y `heroe-invisible`, uno por rama —el gráfico que
  se ve y el `nobodyhere`, que esconde al héroe como esconde a un evento—.
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
  AGENTS.md nombra, y ésta sobrevivió semanas porque la partida seguía
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

* **El cartucho se queda en 4 MB.** Decidido con taro el 2026-09-13, con el
  número delante: la demo de 29 mapas, siete animaciones, la batalla y 19 temas
  pesa **2,52 MB, el 60%**. Para el juego entero **no alcanza** —`assets/README.md`
  tiene la cuenta: ~2,9 MB de mapas, sprites, colisión y música, más 2,7 MB de
  arte sin dibujar, y las 42 animaciones de batalla serían otros ~1,7 MB: unos 7
  MB—. Pero el paso siguiente no es agrandar el cartucho: **LoROM topa en 4 MB**
  y pasar de ahí es ExHiROM, o sea cambiar cómo se calcula cada dirección, con
  todo lo que eso rompe en hardware y no en el emulador. Lo barato está antes, y
  está medido en `assets/README.md`: el conversor **cuantiza por mapa**, así que
  dos mapas que comparten chipset reciben paletas distintas y el mismo dibujo
  termina siendo bytes distintos. Se revisa al llegar al 85-90% del cartucho.

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
* **El MSU-1 de `demo-titulo`**. taro reportó que esa ROM no carga la música de
  alta calidad y la otra sí. **En emulador las dos hacen exactamente lo mismo**,
  medido leyendo `MSU_HAY` y `MSU_SUENA` de la WRAM cuadro a cuadro, así que el
  defecto es de hardware solamente. El único candidato que produce ese síntoma:
  **bsnes no pone `AUDIO_BUSY` nunca** —`io.audioBusy` arranca en falso en
  `power()` y no se escribe en ningún lado—, así que el lazo de espera de
  `msu_arrancar` sale siempre en la primera vuelta **en todos los emuladores y
  en toda la tanda**. O sea que ese camino no tiene red: se prueba en hardware o
  no se prueba. Hay un arreglo de 14 bytes sin verificar.
* **El Game Over y el Rat King en el FX Pak**, que en emulador andan.
* **El título del cartucho sigue diciendo `ABL SNES MUSIC POC`**, que es lo que
  muestra el menú del FX Pak y lo que lee cualquier base de datos de ROMs. Es
  una línea del header, pero se ve en hardware.

Y una que conviene saber al medir audio a mano: **snes9x sí emula el MSU-1**.
Una ROM con sus `.pcm` al lado en `rom/build/` suena por pista también en la
tanda; el `.msu` no está en ningún build de las pruebas, así que no las afecta.

## Lo que la tanda no cubre

### Dos rojos abiertos, medidos y sin arreglar

* **Cuadro 500 de la escena del mapa 16: 43,86%** (25.153 de 57.344), en los
  dos cartuchos. Leyendo la WRAM, en el tick 490 la ROM tiene al héroe en 368 y
  la cámara en 248, y la referencia 378 y 258: **la ROM arranca el `MoveEvent`
  que sigue al tercer teletransporte interno cuatro ticks antes**, y la pantalla
  queda corrida ocho pixeles hasta que el teletransporte siguiente las vuelve a
  sincronizar. Se coló porque ningún caso de la tanda corre una página con un
  `Teleport` al mismo mapa.
* **El cronómetro llegando a cero**: el cuadro 60 da 252 pixeles (0,44%), todos
  en los dígitos, y da los mismos 252 sin el pan. Es una divergencia de un tick
  en el cuadro en que el cronómetro se apaga; `timer-cero` no la ve porque mira
  los cuadros 2, 40, 59 y 61 y **se saltea justo el 60**. Es cosmética.

* **La escena del Tram Officer divergía con la llamada salteada.** Medido el
  2026-09-12 al verificar `tram` en rojo: con `CallEvent` sin hacer **de los
  dos lados** —que es como estuvo hasta ese día— el cuadro 620 de esa escena da
  34,64% de pixeles distintos entre la ROM y la referencia. Con la llamada
  hecha da cero, así que la página que lo destapaba ya no pasa por ahí, pero
  **el camino sigue existiendo** para las 216 llamadas que se siguen salteando.
  El sospechoso es el cronómetro, que esa rama arranca. No se investigó.

* **Diez pixeles después del cuadro 47 en una ruta forzada del héroe en el
  mapa 6.** Encontrado de paso el 2026-09-12 armando los casos de la orden 34:
  el héroe baja cuatro celdas desde (22,12), la ruta termina en el cuadro 32, y
  del 47 en adelante hay **diez pixeles** de diferencia en dos tiles animados
  del chipset, como si uno de los dos lados cambiara de paso un cuadro antes.
  **No es de esa vuelta**: el control sin la orden 34 —la ruta `2 2 2 2` pelada—
  da exactamente lo mismo. El sospechoso es la fase de los tiles animados, que
  la referencia cuenta con `estado.ticks + fundidos` y la ROM con `vueltas`. No
  se investigó; los casos nuevos miran hasta el cuadro 40 para no pisarlo.

* **`plx`/`ply` pisan N y Z, y hubo cuatro lugares que lo ignoraban** (todos
  arreglados el 2026-09-12). El patrón es siempre el mismo: una rutina deja la
  respuesta en las banderas, se restaura el índice con `ply`, y el `beq` que
  sigue mira el índice —que nunca es cero— en vez de la respuesta. Lo tenían
  `tema_asegurar` (la música del título), el `ConditionalBranch` por variable
  —que entraba **siempre**, medido—, el `IsActorInParty` y el `SetTimer` desde
  una variable negativa. Los dos últimos **no los mide nadie todavía**: ninguna
  página de prueba los emite y ningún caso de la tanda los ejercita, así que el
  arreglo es lectura del manual del 65816 y no medición. Si aparece una página
  que use `IsActorInParty`, es el primer lugar donde mirar.

* **Nada de lo que se oye.** El silencio no cambia un pixel, así que la tanda da
  cero igual con la ROM muda. Eso dejó vivir un día al defecto de
  `tema_asegurar` —la pantalla de título sin música, 2026-09-12—. Lo mira ahora
  `pruebas/test_musica_paquete.py`, que le pregunta a la ROM si las muestras del
  tema que dice estar tocando están de verdad en la ARAM (`FAR_ARAM_DE` contra
  `tema_muestras`). Lo que **sigue** sin mirar nadie es que lo que sale del DSP
  suene a lo que tiene que sonar: eso es oído, y es de taro.

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


### El cartel del "One year previously"

Es el único `ShowPicture` que el port hace, y el caso fácil del sistema de
imágenes: aparece una sola vez, entre dos fundidos, sobre un mapa de un solo
tile, así que no le pelea VRAM ni colores a ningún ChipSet ni CharSet. El cómo
está en el README. Lo que hay que tener a mano para tocarlo:

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
