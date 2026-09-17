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

Última vez que se tocó: 2026-09-16.

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
2. **el ensamblador**: fue `w65/` y desde el 2026-09-16 es `ca65` + `ld65`,
   con el mapa de memoria que escribe el conversor;
3. **el asignador** —paletas, ARAM, VRAM— que es lo que queda de
   `snes_convert.py` cuando le sacás los conversores, más el secuenciador de
   MIDI al SPC700, que **no** es un conversor tonto: conoce el driver y usa
   `protocol/music.toml`;
4. **el compilador de eventos**: JSON → bytecode y tablas. No es Ditto y no
   puede serlo: Ditto es un transcodificador bidireccional y sin pérdida, y
   esto es un compilador unidireccional, con pérdida y atado a un target. Lo
   que sí sale de acá es `tools/lcf.py` + `tools/ditto_schema.py` (2.793
   líneas), que en Rust pasan a ser `use ditto`. Y `tools/rm2k.py` —534 líneas
   de semántica de RM2k— se **duplica** a Rust a propósito. El motivo original
   de dejar la copia de Python era la referencia, que ya no está; lo que la
   sostiene ahora es que las pruebas siguen en Python y la leen. Acá es también
   donde hay que decidir qué pasa con lo que queda del modelo de
   `tools/eventos.py`, que es de lo que habla el párrafo siguiente.

**Y con la referencia se fue su modelo.** Quedaban 51 definiciones que no
llamaba nadie —las cuentas que replicaban lo que hace la ROM: el brillo de un
fundido, la curva de un salto, el nivel de un destello— y taro decidió el
2026-09-16 que se fueran, contra la opción de dejarlas como documentación. El
argumento que ganó: **documentación con forma de código se pudre sin que nadie
lo note**. Un comentario que miente se nota leyéndolo; una función muerta que
miente, no, porque no se ejecuta y ninguna prueba la toca. Lo que decían quedó
absorbido por los comentarios de `main.s` que las citaban, o dicho como regla
sin nombrar a nadie.

**Y el 2026-09-16 se fue también `ejecutar`**, que era la mitad intérprete de
ese modelo: se había quedado con un solo llamador, un test que compilaba un
`OP_TELEPORT` para leer `estado.salto`. Lo que lo precipitó fue pasar el avance
del cursor a `opcode_size`: dos de las ramas que se iban —`OP_MESSAGE` y
`OP_CHOICE`— no sólo avanzaban, cortaban el cuadro, y sin su rama el intérprete
seguía de largo sin que ninguna prueba lo cobrara. Entre devolver el corte y
borrar lo que ya no tenía usuario, taro eligió lo segundo. `Estado` se queda:
`snes_convert.py` la usa para saber quién puede liderar el grupo en cada mapa.

Lo que quedó de `tools/eventos.py` es lo que hay que portar en la vuelta del
compilador de eventos, y cuánto es lo dice `wc -l tools/eventos.py`: acá había
un número escrito y ya se había quedado viejo dos veces seguidas mientras el
barrido seguía.

**Las pruebas se quedan en Python**, y no es deuda: es diseño. Decisión de taro
—un lenguaje interpretado y menos estricto tiene ventajas ahí, y compilar para
correr las pruebas suma tiempo sin aportar casi nada—. El efecto estructural que
esto tenía —que mientras el conversor fuera Rust y la referencia Python la
frontera del lenguaje les hiciera imposible compartir código— **se terminó al
irse la referencia**: lo que queda del lado de Python son las pruebas y el
modelo de RM2k de `tools/eventos.py`, que es del mismo lado que el conversor.

### Qué reemplazó a la referencia, que era el paso 6

Tres cosas, y conviene tener las tres juntas porque ninguna sola alcanza:

* **las goldens**, capturas congeladas de la ROM en `pruebas/golden/tanda/`.
  Cazan regresiones, no errores de nacimiento: una feature que sale mal desde el
  día uno hornea el bug adentro de su golden. **Actualizar una es un acto
  deliberado** —va a git, se mira, y el commit dice por qué el render cambió; la
  tanda nunca regenera—, y ése es el único modo de falla real del esquema. El
  porqué largo está en `pruebas/golden/tanda/LEEME.md` y en `AGENTS.md`;
* **`pruebas/test_cores.py`**, que corre el mismo cartucho en snes9x y en bsnes
  y compara las dos capturas entre sí. Es lo único que puede ver un error que
  snes9x no ve, y por eso el parche de WRAM de bsnes pasó a importar más;
* **que taro juegue.** Es lo que sostiene la corrección, y no es una frase: los
  bugs de la semana en que esto se decidió —Delcentric, la colisión pegada del
  Hover-Tram, el HP de los enemigos, la música, el menú de batalla— los encontró
  él jugando y no la tanda.

**Lo que falta de esto**: las goldens se congelaron con la tanda en verde, o sea
que lo que hornean es lo que la ROM dibujaba ese día, y **nadie las bendijo una
por una**. La bendición sólo la puede dar él, y el precedente está: al arreglar
el tinte que sobrevivía al cambio de mapa aparecieron tres goldens con el tinte
horneado adentro y **dos de ellas pasaban**.

Y lo que reemplaza a la referencia para las features **nuevas**: mirar las
capturas. taro quiere presupuesto para eso —"la IA es excelente para leer
imágenes"— pero **fuera de la tanda**, que con visión sería demasiado cara.

## El objetivo, y dónde estamos

**Los primeros diez minutos jugables**, que es lo que taro viene probando
vuelta a vuelta.

Cuántas pruebas hay y cuántas pasan lo imprime **`just pruebas`**, que desde el
2026-09-16 las corre todas: la tanda de regresión dejó de ser una tanda aparte y
sus casos son pruebas de pytest en `pruebas/test_tanda*.py`, contra las goldens.
Hay **un `xfail`**, y no es adorno: desde el 2026-09-13 se sabe de quién es —es
un defecto de la **página de prueba** de guardado y no del juego—. Está abajo,
en "Lo que la tanda no cubre".

Los cuatro proyectos en Rust tienen sus propias tandas: `just brr-pruebas`,
`tiles-pruebas`, `protocolo-pruebas` y `ditto-pruebas`.

`demo-ciudad` se juega desde la apertura hasta la calle de Lashe City, con los
relámpagos, los autos y los NPCs andando, el agua moviéndose, la lluvia, el save
point animado y guardando, el menú de pausa, los ítems, el equipo y la tienda.
**Corre en la SNES de verdad con el FX Pak**, con la música por MSU-1 y los
efectos por el SPC700.

Las páginas automáticas que compilan enteras son **350 de 489** —medido el
2026-09-15 con `just destraba`; el 332 que decía acá y el 281 y el 314 que
decía el README eran los tres viejos—, y del juego entero **5198 de 5603 disparables (92,8%)**, que
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

Cuatro proyectos independientes, todos en inglés y sin una mención a este juego.
Qué está enchufado y qué no, que es lo que cambia semana a semana:

    ditto/      lee y escribe los formatos de RM2k     enchufado: `data/` sale de acá
    protocol/   declara los dos bytecodes              enchufado: los cuatro generados
    brr/        códec BRR y lector de SoundFont        enchufado: las muestras salen de acá
    tiles/      imagen -> tiles, paletas y tilemap     **no**: la ROM usa `pixeles.py`

**Se consumen desde el PATH** —`just herramientas` los instala y
ningún script ni prueba llama a `cargo`—; el porqué está en `AGENTS.md`.

Cada uno de los cuatro tiene su prueba de que no cambió nada: las ROMs salen
byte por byte iguales a las de antes de cada corte. `tiles/` tiene la suya de
que **podría** enchufarse —455 PNG idénticos a los del Python— y lo único que lo
frena es el desempate de `try_pack`, acá abajo.

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

Acordado con taro el 2026-09-15, en este orden. Todo adentro de la etapa de
refactors: **no hay features hasta que cierre**.

**Al 2026-09-16 están hechos el 1, el 3 y el 4, y el 2 a medias.** O sea que lo
que queda, en orden, es: enchufar `tiles/` —bloqueado por una decisión, no por
trabajo—, que taro bendiga las goldens, `ca65` con el asignador, agrupar los
cartuchos, y partir `main.s` al final. Los dos primeros no dependen de nadie y
se pueden empezar hoy.

1. ~~El tinte que sobrevive al cambio de mapa~~ **hecho el 2026-09-15**:
   `Partida.ir_al_mapa` destiñe la pantalla, la trampa se fue de `AGENTS.md`, y
   al hacerlo aparecieron **tres goldens con el tinte horneado adentro** —uno
   fallaba, dos pasaban—. taro los miró y los bendijo.
2. ~~Enchufar `brr/` y `tiles/`, y borrar los de Python~~ **a medias, el
   2026-09-16**: se fueron `sf2.py`, `brr.py`, `brr_check.py` y `w65.py`, y con
   ellos `just snes-validar`. **Falta `tiles/`**, que sigue conviviendo con
   `tools/pixeles.py` porque lo frena el desempate de `try_pack` —ver "Lo que
   hay que decidir"—.

   El argumento que cerró la discusión, y que vale para lo que falta: dejar una
   segunda implementación no se sostiene, porque si el port se equivoca **la ROM
   cambia y las goldens se ponen rojas**, así que la comparación ya la hace el
   criterio de aceptación. Tener dos sólo obliga a tocar las dos. Cómo se
   comparaban queda en el `git log`.
3. ~~Las recetas de la tanda pasan a pytest~~ **hecho el 2026-09-16**. La tanda
   dejó de existir como tanda: sus casos son pruebas de `pruebas/test_tanda*.py`
   y comparan contra las goldens. Se fueron `rom/hitos.txt`, las recetas
   `hitos`, `hitos-paralelo` y `hitos-foto`, el prefijo `snes-` de las recetas
   que quedaron, `tools/snes_crop.py` y la receta `mednafen` con
   `rom/mednafen.sh`. Lo que era el caso `bsnes` es ahora
   `pruebas/test_cores.py`, comparando snes9x contra bsnes.

   Lo que quedó decidido y hay que respetar de acá en adelante:

   * **corre secuencial, sin `pytest-xdist`** —primero simplificar, el
     paralelismo después—;
   * **la clave del directorio de cada cartucho es el hash de (grupo, flags)**,
     porque un directorio por caso son ~900 MB. De ahí sale que `mapdata.inc`
     haya dejado de ser estado global para las pruebas;
   * el caso `elegir` **compara sólo píxeles**;
   * las trampas que vivían en el comentario de cada receta se mudaron al
     docstring de su caso —la celda (22,8) de `tecla`, el cuadro que se saltea
     en `ruta-evento`, el `--toques-hardware` que ignoraba `--apretar-a`—. Son
     del **arnés** y no del caso, y no están en ningún otro lado.

   Y una idea de taro que sigue pendiente: **separar armar la ROM de correr las
   pruebas**, pasándole la ruta del cartucho a la suite como argumento. Con eso
   el test deja de saber compilar y pasa a ser sólo "corré esto y compará", que
   es lo que hace evidente qué se está probando. Encaja con agrupar los
   cartuchos, que es el punto 5.

4. ~~Los golden files, y con ellos la referencia afuera~~ **hecho el
   2026-09-16**. Las goldens son **capturas de la ROM** y no lo que la
   referencia calculaba, y por eso se comparan en cero pixeles exactos y sin
   máscara: lo que ninguna referencia podía modelar —cuál sprite descarta el PPU
   cuando un scanline se pasa de 34 tiles de objeto— el emulador sí lo sabe, y
   con eso se fueron 25 máscaras y 1.496 líneas que la tanda miraba y
   descartaba.

   **Lo que queda pendiente es la bendición**, y está arriba en "Qué reemplazó a
   la referencia": se congelaron con la tanda en verde, nadie las miró una por
   una, y sólo taro puede hacerlo. Para que no sea una tarde de mirar imágenes
   conviene mostrarlas agrupadas por mapa, una vez cada una.
5. **El acomodo de bancos sale del ensamblador.** ✅ el 2026-09-16, salvo dos
   casos que quedaron medidos. Lo hacía `.bloque`, una directiva nuestra: el
   conversor le decía al ensamblador "lo que sigue mide N bytes, rellená hasta
   el próximo banco si no entra", y existe porque un DMA que cruza de banco lee
   la WRAM en vez de la ROM. `ld65` no sabe acomodar bloques de tamaño
   variable, así que la decisión la toma ahora el conversor —el único que
   conoce los tamaños— en `tools/bancos.py`, y al ensamblador le llega relleno
   explícito. La ROM salió byte por byte igual, que era el criterio. Cuántas
   declaraciones hay y cuántas rellenan lo imprime cualquier `just demo`.

   Quedaron dos `.bloque` escritos a mano en `main.s`, que dependían del
   cartucho; los resolvió el paso 6.

6. **El ensamblador pasa a ser `ca65` + `ld65`, y `w65/` se borra.** ✅ el
   2026-09-16. Decidido por taro el 2026-09-15: prefiere un proyecto
   mantenido, popular y con once años de historia antes que sostener el
   nuestro. La razón original de escribir uno propio —no compilar fuentes de
   internet en esta caja— era una interpretación mía llevada al extremo sin
   preguntarle.

   **El layout, decidido por taro el 2026-09-16: un área de memoria por
   banco**, que es la forma estándar de `ld65`. El código a mano de fuera del
   banco 0 va en `FAR`, fijo en el banco 1; lo generado, en un `BANKnn` por
   banco desde el 2, repartido por `tools/bancos.py`; y el `.cfg` lo escribe
   el conversor para que el banco donde arranca lo generado esté escrito una
   sola vez. Descartada: que lo generado termine pegado a un banco, porque uno
   de los `.bloque` a mano seguía sin resolverse y el código a mano seguía
   moviéndose por cartucho.

   Se hizo en cinco commits, cada uno verificable solo: el layout con `w65`
   (6a, que movió bytes y se verificó con las goldens y la tabla de símbolos),
   y después cuatro que no movieron ninguno —las fuentes en la forma de
   `ca65`, el reparto en segmentos, el `.cfg`, y el cambio de ensamblador—.
   **La ROM de `ca65` + `ld65` salió byte por byte igual a la de `w65`.**

   **Lo que quedó sin red**, y conviene tener presente: `w65` comprobaba que
   cada salto llegara a su etiqueta con los registros al ancho que ella
   declara, y `ca65` no. Está explicado en "Lo que se perdió con el
   ensamblador propio", en el README.

7. **El reparto de paletas sale de las primitivas.** ✅ el 2026-09-17, en
   tres commits con la ROM byte por byte igual. Resultó más chico de lo que
   decía acá: los sprites ya recibían su reparto de `npcs_dibujables`, y lo
   que sobraba era un segundo asignador muerto adentro de `build_characters`.
   Lo que sí estaba metido era el nudo entre las dos capas: dónde arrancaba la
   de encima era una salida de su empaquetado, y de eso salía el presupuesto
   del fondo. Hoy `_convert_layers` decide las tres cosas —las paletas de la
   capa de encima con `repartir_encima`, dónde arranca, y la paleta del fondo
   con `build_palette`— y `convert_above` y `convert` sólo emiten.

8. **El asignador corre primero, y `tiles/` convierte lo que ya entra.**
   Rediseñado por taro el 2026-09-17; lo que sigue reemplaza al "enchufar
   `tiles/`" que había acá.

   **La frontera**: `tiles` no toma decisiones artísticas —dada una imagen que
   el formato puede representar, la representa sin tocar un pixel, y si no
   puede, falla—; el asignador sí —decide qué se pierde: fusionar colores,
   empaquetar paletas, repartir CGRAM entre capas, sprites y mapas—. La
   prueba para cualquier función es **"¿cambia algún pixel de lo que se
   ve?"**. Con hardware infinito el asignador seguiría existiendo, pero chico:
   los presupuestos desaparecen, los límites del formato —15 colores por tile
   de 4bpp— no.

   **El pipeline**: render → **asignador** (el cartucho entero de una vez) →
   **PNG indexados de 8 bits con índices absolutos de CGRAM** más un
   manifiesto → **`tiles`** → conversor → `ca65` + `ld65`. En una capa de
   4bpp, `índice >> 4` es la paleta y `índice & 15` el color; así no hace
   falta metadata —un PNG no puede decir "mis índices arrancan en N", y un
   chunk propio lo borra el primer editor que lo guarde—. Cada PNG lleva la
   CGRAM entera, **duplicada a propósito**: `tiles` junta las entradas que
   usa cada imagen y **corta si dos le dan distinto color a la misma**. Las
   imágenes del asignador quedan en `rom/build/<cartucho>/asignador/`, para
   mirarlas y retocarlas sin armar la ROM.

   **`--merge` se va de `tiles`**, y con él el empaquetado de paletas y
   `--first-palette`: son del asignador, que por ahora sigue en Python y más
   adelante va a ser un proyecto en Rust aparte, con `tiles` como biblioteca.
   Mantener un "asignador tonto" en `tiles` se descartó: habría dos
   respuestas a "qué color se pierde".

   **Lo que esto gana**: como el asignador sigue siendo el de Python, con el
   mismo desempate, las paletas no cambian, y `tiles` sólo corta, deduplica y
   espeja. **Enchufarlo no mueve ninguna golden**: los bytes pueden cambiar —el
   orden de los tiles— y los pixeles no. El desempate nuevo, que era lo único
   que iba a mover la ROM a propósito, se va con el asignador a Rust.

   | | qué | criterio |
   |---|---|---|
   | 8a ✅ | `tiles` recibe PNG indexado en espacio CGRAM; se van `--merge`, el empaquetado, `--first-palette` e `inspect` | pruebas de `tiles` |
   | 8b ✅ | `tiles` recibe varios dibujos que comparten pool, con los que animan en corridas al final | pruebas de `tiles` |
   | 8c ✅ | el asignador emite la capa de encima como PNG indexado y `tiles` la convierte | ninguna golden se mueve: la ROM salió igual |
   | 8d | lo mismo con el fondo y sus dibujos | ninguna golden se mueve |
   | 8e | se borra lo que `tiles` reemplazó; lo que queda de `pixeles.py` va al módulo del asignador | la ROM igual a la de 8d |

   Los sprites no pasan hoy por `tiles` en ningún lado: quedan para después.

9. **Un solo cartucho para todas las pruebas.** Regla de taro, el 2026-09-16:
   *"nunca dos builds distintos para incluir distintos datos"*. No hace falta
   que lleve todos los mapas del juego, pero **cada mapa que se suma al
   proyecto se suma para todos los builds**.

   Hoy casi cada caso arma el suyo: **176 directorios y 874 MB**, con la clave
   ya siendo el hash de los argumentos —o sea que agrupar por hash no agrupa—.
   Con un cartucho único, el banco 0 pasa a tener **un** número en vez de uno
   por caso, `mapdata.inc` deja de ser estado global, y las pruebas dejan de
   compilar: se les pasa la ruta del cartucho, que es la idea de taro de que el
   test no sepa armar nada.

   **Y puede pedir compresión primero.** La unión de mapas que las pruebas
   necesitan hoy son **32**, y `demo-ciudad` con 29 ya usa el **74,4%** del
   cartucho —con el mapa 52, que es de los grandes, entre los que faltan—. No
   está medido si entra: el intento de armarlo quedó a medias. Si no entra, la
   compresión sube de prioridad y va **al final de esta etapa, antes de
   cualquier feature**, que es lo que taro decidió.

   Lo que se puede esperar de comprimir, medido: la parte usada de
   `demo-ciudad` —3,12 MB— deflatea a **791 KB, un 75% menos**. El grueso del
   cartucho son gráficos, que es lo compresible, y descomprimir al cargar un
   mapa es la técnica de la consola. Ojo con medirlo mal: el `.sfc` entero da
   97% porque el millón de ceros de relleno comprime a nada, y el `mapdata.inc`
   da 89% porque es **texto** —números decimales con comas—, no los bytes que
   viajan en la ROM.

   Lo que el mapa ya ahorra sin comprimir, para no rehacerlo: no se guarda el
   tilemap sino la **celda de 16×16 de RM2k**, con sus cuatro celdas de fondo,
   sus cuatro de la capa de encima y su pasabilidad juntas —512 bloques
   distintos en todo el juego—. En el mapa 52 eso es 40.000 B contra 160.000, y
   **borró la tabla de colisión entera**. Medido aparte: **el 85,3% de la capa
   de encima es el tile vacío**, así que si hiciera falta más, el primer lugar
   donde mirar es un RLE sobre la grilla de bloques, no los ceros de la capa.

   Lo de abajo queda absorbido por lo de arriba: son 176 directorios y 874 MB en `rom/build/tanda/`, con la clave ya
   siendo el hash de (grupo, flags) —o sea que el hash solo no agrupa—.
   Agruparlos a mano en unos pocos da tres cosas: el banco 0 pasa a tener un
   número por cartucho en vez de uno por caso, `mapdata.inc` deja de ser estado
   global, y la tanda deja de rearmar lo mismo. Y encaja la idea de taro de
   **pasarle la ruta del cartucho a la suite**, para que el test deje de saber
   compilar. Mueve goldens.

10. **Partir `rom/src/main.s`**, que son 30.300 líneas en un archivo. **Va
    último**: es el único paso que no destraba ninguno de los otros, y `main.s`
    se sigue moviendo con los pasos 5 a 9. Probado en chico —una sección afuera
    con `.include`, mismo md5—; las fronteras ya existen, 82 marcas de sección
    y 450 `.proc`. Tres trampas: el `.segment` cruza el `.include`, las
    etiquetas anónimas se resuelven textualmente, y **reordenar sí cambia la
    ROM** aunque partir no.

**Las dos cadenas son independientes**: 5 → 6 es el acomodo de bancos, 7 → 8 es
el reparto de paletas. Se pueden hacer en paralelo.

**Lo que se decidió no hacer:** dejar de armar `demo-ciudad`. Es la misma
receta que `demo-titulo` con `--con-titulo` de más, o sea un subconjunto, pero
esta semana difirieron de verdad —el reporte del MSU-1 fue "la que tiene título
no carga la música de alta calidad, la otra sí"— y `demo-ciudad` fue el control
que permitió aislar que era el arranque con título. Cuesta un minuto.

**Y un número que cierra una pregunta vieja:** un cartucho con todos los mapas
es imposible. **29 mapas ocupan el 74,4% de los 4 MB** y el juego tiene 328.


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
  ya lo hacía —la guarda en la fila del NPC— y la referencia no, hasta que el
  2026-09-06 las dos pasaron a guardar la instantánea. De ahí queda una regla
  para cualquier lazo que corte a mano: **no se corta con un refresco
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
  puede jugar sin ellas. Se tiran **al compilar**, así que no llegan al
  cartucho y no hay nada a medias. Las 28 y 29 —la
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

  Es la única de las cuatro piezas que **no toca al intérprete**: lo que cambia
  es el bytecode que se emite, no quién lo corre. Cuando existía la referencia
  su caso se verificaba en rojo bajándole `LLAMADA_MAX` a un solo lado; hoy, sin
  segundo lado, lo que queda es la golden.

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
    `elegir_grafico_heroe`. En RM2k
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

  Lo cubren `grafico-heroe` y `heroe-invisible`, uno por rama —el gráfico que se
  ve y el `nobodyhere`, que esconde al héroe como esconde a un evento—. * **Los
  temas comparten un solo banco de muestras.** Un banco por tema pediría subirlo
  en cada `PlayBGM` —medio segundo, o sea treinta cuadros de juego frenado—. La
  razón que lo cerró en su momento era además que había que modelarlo en la
  referencia, y modelar cuánto tarda una transferencia es justo lo que no se
  puede medir honestamente; **esa mitad se cayó con la referencia** y lo que
  queda en pie es el medio segundo. Si alguna vez se reabre, es por ahí. * **El
  arranque está dimensionado para el techo de ARAM**, no para el banco de hoy:
  `BOOT_CUADROS = 112` y `--arranque 115`. Cuesta 1,9 s de mapa congelado al
  encender y a cambio llenar la ARAM no cuesta nada. Lo que lo compraría de
  vuelta es un driver del SPC700 que reciba por los cuatro puertos en vez del
  uno del IPL. * **Un gráfico que no entra en las ocho paletas de sprite no se
  dibuja.** Lo decide el conversor, con una sola función. Vale para los eventos
  dibujados con un tile del chipset y, desde la orden 34, para los gráficos a
  los que una ruta cambia: ahí la orden esconde al evento en vez de cambiarlo.
  Forzarlos rompía tres mapas —el 108, el 114 y el 207—. * **La tecla de acción
  mira las dos celdas, y cada una pide la capa contraria.**
  `CheckEventTriggerHere` quiere `GetLayer() != Layers_same` y
  `CheckEventTriggerThere` quiere `== Layers_same`. No es simetría de adorno: un
  evento de la capa del héroe le cierra el paso, así que nunca se podría parar
  encima; uno de otra capa no lo frena y se le camina por arriba. El filtro vive
  en la ROM y no en el conversor, porque la misma página vale o no según qué
  celda la esté mirando.

* **Se dibujan todos los eventos, aunque sea con una paleta ajena.** Es de taro:
  *"si no podemos incluir todos los eventos, el proyecto entero se cae"*. El que
  no consigue paleta propia se cuelga de la que menos colores le falte, y cada
  color ausente va al más cercano por luma. Los números están en
  `assets/LIMITACIONES.md`.

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
  agotarse, la ROM llama a `entrar_en_panico` en vez de seguir. Un salto
  descartado en silencio es la forma de falla que
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

### Tres divergencias medidas contra la referencia, y sin arreglar

**Ojo con cómo se leen desde el 2026-09-16.** Eran diferencias entre la ROM y la
referencia en Python, y la referencia ya no está: hoy **ninguna de las tres da
rojo**, porque la golden es la captura de la propia ROM y hornea adentro el
comportamiento que la referencia discutía. O sea que no son rojos abiertos sino
**lugares donde sabemos que la ROM no hace lo que RM2k hace, y nada lo cobra**.
Quedan escritas por eso, y porque si alguna vez se arreglan hay goldens que se
van a mover.

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
  dos lados** —que es como estuvo hasta ese día— el cuadro 620 de esa escena
  daba 34,64% de pixeles distintos entre la ROM y la referencia. Con la llamada
  hecha daba cero, así que la página que lo destapaba ya no pasa por ahí, pero
  **el camino sigue existiendo** para las 216 llamadas que se siguen salteando.
  El sospechoso es el cronómetro, que esa rama arranca. No se investigó.

* **Diez pixeles después del cuadro 47 en una ruta forzada del héroe en el
  mapa 6.** Encontrado de paso el 2026-09-12 armando los casos de la orden 34:
  el héroe baja cuatro celdas desde (22,12), la ruta termina en el cuadro 32, y
  del 47 en adelante hay **diez pixeles** de diferencia en dos tiles animados
  del chipset, como si uno de los dos lados cambiara de paso un cuadro antes.
  **No es de esa vuelta**: el control sin la orden 34 —la ruta `2 2 2 2` pelada—
  da exactamente lo mismo. El sospechoso era la fase de los tiles animados, que
  los dos lados contaban con relojes distintos. **Eso dejó de poder
  investigarse así**: la referencia se borró el 2026-09-16 y con ella sus dos
  contadores, y hoy la golden hornea lo que hace la ROM, así que la divergencia
  no existe como rojo. Si el paso de los tiles animados llegara a estar mal, lo
  dice el ojo y no la tanda. Los casos siguen mirando hasta el cuadro 40.

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
  personaje, así que tiñe todo lo que la comparta. RM2k lo aplica sobre la
  **imagen** del sprite. Son dos cosas distintas y
  ningún caso de la tanda lo ve, porque ninguno tiene un segundo sprite visible
  compartiendo la paleta del que destella. Lo cuida `test_destello_paleta.py`,
  que exige que nadie comparta la paleta de un líder posible. **Protege al líder
  y no al que destella**: el blanco se decide corriendo y el héroe es el único
  que se puede saber al convertir, así que un destello sobre otro evento
  filtraría igual.

* **El cursor de `ShowChoice`.** La tanda sólo aprieta A, así que arriba, abajo
  y B no los toca ningún caso de ella. Los cubre `pruebas/test_elegir.py`.
  Lo que la tanda sí compara es la ventana dibujada, en el caso `elegir`: cuatro
  cuadros contra sus goldens, el de la elección abierta y el de la respuesta de
  la rama que corrió. **Compara sólo píxeles**, decidido con taro el 2026-09-16;
  antes además imprimía qué texto decía la ventana, y eso se aceptó perder al
  irse la referencia. El riesgo que cubría sigue siendo real —cuatro cuadros en
  cero también sería el resultado si la página no compilara—, y contra eso vale
  lo de arriba: antes de creerle a un cero hay que ver la página compilar.

El caso más largo de la tanda es `talan`: mil doscientos cuadros de la escena
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
  cuadro a cuadro, y mientras la compone ignora el botón. **Cuánto tarda depende
  del texto**: medido, 9 cuadros con el mensaje de prueba y 17 a 19 con los del
  recuerdo de CORE y MANTA. Antes acá decía "nueve" a secas, y eso era el número
  de un solo caso.

  De ahí salen dos cuidados, y los dos costaron un rojo: ningún cuadro que se
  compare puede caer adentro de esa ventanita, y **ningún toque de A tampoco**.
  La ROM ignora el botón mientras `msg_abierto` esté en cero, así que un toque
  que caiga ahí simplemente no pasa y la escena sigue por otro lado. Al armar
  una lista de toques hay que dejar treinta cuadros desde que el mensaje se
  abre, no veinte: con veinte, el toque del cuadro 1976 llegó **uno** antes de
  tiempo.

* **El audio.** `just bgm <tema>` graba cuarenta segundos y los compara
  contra el MIDI, y **no está en la tanda**: es visual. Los cuatro temas de la
  demo pasaron el 2026-09-06 —96%, 98%, 83% y 90%—, pero eso hay que volver a
  correrlo a mano.

  `evilrhys` es el ruidoso: dio 66%, 75% y 83% en tres corridas contra un techo
  de 95% que le da FluidSynth con el mismo MIDI. No es el banco compartido —sus
  escrituras melódicas son idénticas con banco propio—; es que tiene ocho
  canales melódicos para seis voces, así que dos no suenan nunca.

* **La convención de la tabla de mapas.** Cómo se arma —el de `--map-id`
  primero, después los de `--mapas` sin repetir— está escrito igual en el
  conversor y en la ROM, a propósito. Justamente por eso, equivocarla equivoca
  el cartucho y la golden que salió de él, y la comparación sigue dando cero. Se
  revisa leyendo, no corriendo. Lo que sí se corre es que la ROM
  resuelva un índice que no sea 0 ni 1.

* **El tope de ocho saltos encadenados.** Medido el 2026-09-03: con los 328
  mapas en la tabla hay **un solo** mapa cuya página automática teletransporta
  al entrar, la cadena más larga es de un salto y no hay ciclos. **No es
  estable**: cada comando nuevo hace compilar más páginas automáticas y las
  cadenas pueden crecer. Conviene volver a medirlo de vez en cuando.

* **La RAM sin inicializar, del todo.** `snes9x` —con el que corre casi toda la
  tanda y con el que se capturaron las goldens— deja siempre la misma basura,
  así que una variable que nadie inicializa da verde. Lo mitiga
  `pruebas/test_cores.py`, que corre los mismos cartuchos en `bsnes` con la WRAM
  llena de basura al encender y compara las dos capturas entre sí, pero la
  detección es **probabilística**: con un error de esta clase puesto a mano, el
  cuadro sale mal 11 corridas de 20. Si molesta, la salida es correr ese archivo
  varias veces, que es barato.

  Dos errores de esta clase los encontró taro jugando, con la tanda en verde.

* **snes9x perdona lo que el hardware no, y van cuatro.** La carga de la SRAM
  —un modo de direccionamiento—, el PPU que se quedaba con los registros del
  título, y dos más; **tres los encontró taro jugando, con la tanda en verde**.
  El caso extremo quedó medido: sacando el `jsr ppu_init` que arregla el
  segundo, snes9x sigue dando **cero pixeles de diferencia**. Lo mitiga
  `pruebas/test_cores.py`, y el reset de snes9x **no borra la WRAM**, así que
  una prueba que dependa de que algo no sobreviva a un reinicio tiene que
  ensuciarla a mano.

  **Y esto pesa más desde que las goldens son capturas de snes9x**: la tanda
  entera compara snes9x contra snes9x, así que `test_cores.py` es lo único que
  queda capaz de decir "anda acá y no en la consola".

* **El brillo del fundido, según el core.** Medido el 2026-09-06 sobre los
  dieciséis niveles: en 0 y 15 los tres coinciden; entre 1 y 14 snes9x y bsnes
  coinciden exactamente y **mesen-s difiere en 30% a 48% de los pixeles**, un
  paso para abajo. O sea que difiere exactamente mientras dura un fundido y en
  ningún otro momento. La trampa práctica: las recetas que capturan toman el
  core de `CORE`, así que sacar una captura con `CORE=mesen-s` y compararla
  contra una golden pondría en rojo todo cuadro que caiga en un fundido **sin
  que haya ningún bug**. taro miró un fundido en la
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
  distinto, porque los mapas se compilan en un orden que depende de si la ROM
  lleva ventana.
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

## Lo que falta del port

Mudado del README el 2026-09-15: es lo que está a medias, o sea de este
archivo. Lo derivable no está acá y no debería volver: qué comandos se aceptan
sin hacer lo dice `ACEPTADOS_SIN_HACER` en `tools/eventos.py`, y cuánto
destraba cada uno, `just destraba`.

* **El presupuesto de muestras, por paquete y no por banco.** Hoy el banco
  compartido entero tiene que entrar en los 64 KB de ARAM, y eso era el límite
  de verdad **antes** del paquete de audio por mapa: ahora en la ARAM viven el
  directorio y un paquete, no el banco, y con todos los temas de la demo
  aportando el hardware entra de sobra: lo dice el informe del conversor. Lo
  que no entra es la calidad: repartir los 40 KB de `ARAM_BUDGET` entre casi el
  doble de programas baja la tasa mediana a la mitad **para todos**, incluidos
  los que hoy suenan bien. Lo que lo resuelve es darle a cada programa lo que
  su peor paquete puede pagar en vez de una parte del banco entero; mientras no
  esté, los temas que no aportan suenan incompletos y el recorte va por
  prioridad: ver "Varios temas en el cartucho".
* **La música, del lado del SPC700.** Hoy la toca el 65816 desde una IRQ —ver
  "La música no espera al lazo"—, y funciona, pero cuesta hasta veinte líneas
  por cuadro y obliga a las reglas de la interrupción. El paso que sigue,
  acordado con taro el 2026-09-11, **no** es un secuenciador en el SPC700 como
  los de los juegos comerciales, sino uno chico que lea el mismo stream de hoy
  desde un buffer circular en la ARAM, a su propio ritmo, y que el 65816 sólo
  mantenga lleno. El conversor y `audio-check` no cambian, y los efectos de
  sonido pasarían allá también. Se encara cuando haga falta el margen del lazo,
  o si en la consola el audio muestra algo que el emulador no.
* **El sistema de imágenes, más allá del cartel.** La ROM dibuja **un**
  `ShowPicture` por cartucho: ver "El cartel de 'One year previously'", y ahí
  están los números de lo que costaría el resto —34 comandos en el juego, 20
  carteles distintos, y cinco de ellos de 320x240 exactos, que con objetos no
  se pueden hacer—. Los que no entran se siguen aceptando sin hacerse.
* **Las órdenes de ruta que faltan.** Son quince las que la ROM entiende —mover
  en los cuatro sentidos, girar en los cuatro, esperar, saltar, atravesar
  paredes y parar o seguir la animación— y `play_sound_effect` se acepta sin
  hacerlo, y la **transparencia** también: subirla y bajarla de a un octavo son
  las órdenes 40 y 41, y las ocho rutas del juego que las usan son las cuatro
  pantallas del mapa 2 atenuándose mientras Manta hackea, que sin eso dejaban
  afuera la escena entera; se pierde el fundido, que sobre tiles de fondo la
  SNES no hace barato. Una ruta que se queda sin órdenes por esto no se emite:
  RM2k la consume entera en el cuadro y no deja nada que esperar. Falta **fijar
  la mirada** —las órdenes 26 y 27, que sobre el héroe se aceptan y se tiran
  por decisión y no por olvido: ver ESTADO.md—. **Moverse hacia el héroe** —la
  orden 9, +33 páginas— y **cambiar el gráfico del héroe** —la 34, +29— se
  hacen; las otras nueve órdenes de movimiento que faltan suman +1 entre todas,
  medido, y por eso siguen afuera. La velocidad ya está, con las rutas propias
  de las páginas; **subir y bajar la frecuencia** —las órdenes 30 y 31—, ver
  "La frecuencia se sube y se baja a mitad de una ruta"; las **diagonales**
  —las órdenes 4 a 7, +7 páginas—; y **cambiar el gráfico
  sobre un evento** —+25 páginas—, ver "Cambiar el gráfico a mitad de una
  ruta". Las tres últimas van sobre eventos y no sobre el héroe. Sigue siendo
  lo que más corta, aunque bastante menos.

  Y una que apareció midiendo eso: **las órdenes 26 y 27 sobre el héroe** —fijar
  y soltar la mirada— se tiran al compilar, y eso está decidido. Lo que fue un
  problema de verdad, y quedó arreglado, eran las 28 y 29 —subir y bajar la
  velocidad—: la ROM las ignoraba sobre el héroe y la referencia no, porque
  `Ruta` es la misma clase para el héroe y para los eventos. En el juego hay 163
  rutas sobre el héroe con la orden 28 y 148 con la 29; de las páginas que hoy
  compilan, siete tienen una, y una de ésas es el evento 1 del **mapa 7, Talan's
  Pad**, que es adonde va el juego después del Emitter Room. **Ninguna prueba
  mira una de esas páginas**, así que el arreglo no lo cobra nadie. **Las 28 y
  29 sobre el héroe se hacen**: su paso dejó de ser fijo —`step_left` cuenta
  medias unidades de RM2k, 128 por celda, y baja `paso_medio_por_vel` por
  cuadro— y la velocidad vive en `FAR_HERO_VEL`, viaja en la partida y queda
  como la dejó la última ruta, que es lo que hace RM2k: sólo la frecuencia se
  repone. Las 26 y 27 se siguen tirando.

  Y aparte, **girar sin moverse** (`turn_90_degree_right` y sus hermanas): no
  está afuera por costo sino por dónde arranca el giro. RM2k gira sobre la
  dirección que el personaje ya tenía, y para un evento que todavía no giró
  ésa es la que trae su página, que la ruta no lee. **Encarar al héroe** y la
  **frecuencia** ya están: ver "La frecuencia de la ruta,
  y encarar al héroe".
* **El acolchado de bloques.** Agrandar el cartucho **es un cambio de mapeo que
  ningún caso de la tanda ve**: los tres emuladores cargan el archivo del doble
  sin preguntar, así que lo prueba el cartucho real. Y no es la única salida:
  el acolchado que dejan los `.bloque` llega a **20 KB** —un bloque de 18 KB que
  no entra en lo que queda del banco deja 12 KB vacíos— y un enlazador que
  acomode los bloques en los huecos los recuperaría. No se hizo porque el
  crecimiento sigue: cada personaje que cambia de pose son 6 KB.

  Y dos ideas de taro para cuando haga falta apretar assets, anotadas para no
  perderlas: **paletas calculadas sobre todas las imágenes del juego** a la
  vez —CharSets, ChipSets y texto—, unificando los negros y grises casi
  iguales entre imágenes, con un impacto visual mínimo; y **hornear en un
  ChipSet propio a los sprites que son decoración**, como el público del
  Auditorio, que no se mueve nunca. Ninguna de las dos se encara ahora.
* **Lo que la colisión con los eventos no modela.** Está
  —ver "La colisión con los eventos"— y deja afuera `overlap_forbidden`, 17
  páginas del juego; el conflicto de un evento con gráfico de tile contra su
  propio bloque; que un evento de contacto de la capa del héroe dispare al
  chocar con él —`CheckCollisonOnMoveFailure`—; y que una ruta forzada que
  no se puede saltear **reintente** el paso bloqueado en vez de saltearlo,
  que es lo que hace `UpdateMoveRoute` con `skippable` apagado. Lo último es
  lo que más cerca está de verse: en la apertura la colisión no frena ningún
  paso, medido, pero el droide del mapa 2 vive de eso.
* **El cartucho es de 4 MB**: `ROM_BANKS` es 128 y la cabecera dice `$0C`. Es
  el techo de LoROM, así que de acá no se crece: lo que siga pidiendo cartucho
  tiene que recuperar acolchado o compartir tiles entre mapas.

  **Los dos últimos bancos del archivo no se usan**, y ésa es la parte que hay
  que entender antes de tocar esto. `lorom_address` le da a cada byte del
  archivo la dirección `banco:8000`, y en la consola **los bancos $7E y $7F son
  la WRAM**: un dato ubicado ahí se leería como memoria de trabajo. Se llega a
  ellos por el espejo $FE/$FF, pero entonces un puntero de 24 bits que cruce de
  $7D:FFFF al siguiente —lo que hace `advance`— aterrizaría en la WRAM en vez de
  saltar al espejo, y sería un error silencioso en el peor lugar: un stream de
  música o una tira de mapa leyendo basura a mitad de camino. Así que el archivo
  mide 4 MB justos, que es lo que la cabecera declara y lo que el FX Pak espera,
  y `BANCOS_PROHIBIDOS` hace que el asignador se detenga 64 KB antes.

  La SRAM no se entera de nada: en LoROM vive en la **mitad baja** de los
  bancos $70 a $7D, y el cartucho usa la alta.
* **Los cuadros que el lazo pierde en sus picos.** Ya no los produce el
  teletransporte —el fundido se come la carga, ver "El fundido de los
  teletransportes"— pero siguen: la primera vuelta de una ROM con muchas
  páginas se pasa del cuadro, y también la vuelta en que un fundido termina y
  la página retoma.

  **Lo que esto bloqueaba se destrabó solo el 2026-09-16**: la referencia no
  modelaba los cuadros perdidos, así que a partir de ahí la ROM iba N cuadros
  atrás y sólo se la podía comparar con la pantalla quieta, y eso era lo único
  que le faltaba a la escena del ascensor del mapa 2 para tener caso propio.
  Contra una golden no hay N: la captura los tiene adentro. Vale la pena
  probarlo antes que cualquier otra cosa de esta lista, porque es gratis.

  Lo que **sigue** siendo cierto es que los picos existen y que la salida no es
  un desfase a mano —eso es un número que se ajusta hasta que dé verde— sino
  aflojarlos, o leer `cuadros_perdidos`, que ya viaja en la salida de cada
  captura.
* **Las otras transiciones de RM2k.** El fundido está, que es la que este
  juego usa —`transition_out` y `transition_in` valen 0 en su base—, pero
  `Transition::Type` tiene 38 y un evento puede pedir cualquiera con
  `EraseScreen`/`ShowScreen`. Las de bloques, persianas y barridos no son un
  brillo maestro: piden tapar la pantalla por regiones, que en la consola es
  otra máquina.
* **Los teletransportes que siguen sin resolverse.** Los que están adentro de
  cinemáticas con variables y condiciones que todavía no modelamos. El del
  mapa donde el juego arranca ya no: es automático, entra con los cinco
  comandos que la ROM entiende, y `Blank (Leave START here)` ahora se sale
  solo.
* **El resto de los temas.** El cartucho lleva **varios**: los que pidan los
  `PlayBGM` compilados, compartiendo un solo banco de muestras. El techo no
  es la cantidad de temas —el banco se achica solo— sino la resolución: con
  los treinta y pico del juego entero cada instrumento quedaría en una miga,
  y sin aviso. Ver "Varios temas en el cartucho".

  Lo que subiría ese techo es un **driver que sepa recibir datos**: hoy las
  muestras se suben una sola vez al arrancar con el protocolo del IPL, que manda
  un byte por acuse y desaparece al saltar al driver. Con un banco por tema el
  costo sería medio segundo de transferencia en cada `PlayBGM` —lo que lo
  descartó fue eso más tener que modelarlo en la referencia, y esa mitad ya no
  está—; con los cuatro
  puertos en vez de uno, en cambio, se acorta el arranque, que hoy es
  `BOOT_CUADROS`, dimensionado para una ARAM llena.

  Y un efecto que conviene tener presente: `audio-check` compara el audio contra
  el MIDI **del mapa**, así que donde el tema lo pone un evento hay que
  nombrarlo. Para eso está `just bgm <tema>`.

* **La cinemática de apertura, entera.** Corre con ventana
  —`rom/build/demo-apertura/`, con los mapas 4, 1, 2 y 3 y `escape_newyork`
  sonando; el 3 va para que el ascensor del mapa 2 lleve a algún lado, que si no
  su página no compila— y el caso `apertura` de la tanda la compara hasta
  el final con los quince toques de A que la cierran: el tinte se apaga, Core y
  Manta aparecen, el droide camina, Kersh explica su alias, y la página termina
  con dos `ChangeEventLocation` y un switch. De ahí el juego sigue con el
  jugador al mando, y eso ya no lo mira ninguna receta. Lo que la comparación
  **no** cubre es nada en movimiento en un cuadro en que la ROM venga atrasada;
  el toque de A resincroniza los dos lados.
* **Lo que le falta al juego entero.** Cuántas de las páginas automáticas con
  comandos compilan enteras, y cuántas destrabaría cada comando que falta, lo
  imprime **`just destraba`**, y ése es el único lugar del que hay que
  sacarlo: los números que estuvieron escritos acá envejecieron sin avisar, y
  llegaron a contradecirse entre sí en dos archivos del repo.

  **Ese número hay que leerlo con cuidado, y por eso `tools/destraba.py` muestra
  dos columnas.** Contar qué comando corta *primero* cada página no mide lo que
  se destraba: una página cortada por un cuadro de texto puede estar cortada
  además por otras cuatro cosas. Y aceptar un código entero cuenta lo que se
  destrabaría con el comando hecho **para todos los casos que el juego usa**, que
  es un techo: sobre `MoveEvent`, contar las rutas que la ROM no va a saber
  caminar y los blancos que no existen infla el número frente a contar sólo las
  órdenes que ya hace. Los candidatos que todavía no tienen filtro son techos.

  Y una nota que sigue valiendo: de las páginas con `MoveEvent`, la mayoría
  mueve **otro evento** y no al héroe, o sea que piden que los NPCs caminen, que
  es una feature aparte de la ruta forzada que ya anda.
* **El mapa entero en un cartucho.** Los 328 mapas suman 3,7 MB y LoROM llega a
  4, así que hoy entra un puñado por ROM y se elige al compilar. La salida
  probable es compartir los tiles entre los mapas que usan el mismo chipset:
  son 43 chipsets para 328 mapas.
* **Mapas con más de ocho personajes distintos.** Los sprites van en 4 bits y
  hay ocho paletas para ellos, una por CharSet. Yun Town usa diez y Sorbe
  Village once, así que no convierten. Los dos venían tapados detrás del
  problema de las paletas de la capa de encima, que ya está resuelto. Los
  eventos dibujados con un tile del chipset se empaquetan
  y los que no entran se dejan de dibujar en vez de cortar el mapa: ver "Los
  eventos dibujados con un tile del chipset".
* **Un evento que camina y cambia de gráfico con la página.** Ver "El
  gráfico sigue a la página": el conversor corta. Y con eso, `change_graphic`
  en una ruta sigue afuera.
* **El panorama.** El mapa 2 tiene uno —`screen`, puntitos sobre azul que
  desplaza en diagonal solo— y se nota faltando cuando la pantalla grande se
  enciende. El modo 3 tiene dos capas de fondo y las dos están
  tomadas, el mapa y la capa de encima con la ventana; un panorama pide una
  tercera o el modo 1, que la conversión no usa. No es prioridad.

  De ahí sale que **`ChangePBG` se acepte y se tire**: si no hay panorama, no
  hay nada que cambiarle. Se tira al compilar, como las órdenes de ruta 26 y 27,
  así que no hay nada que quede a medias. Aparece **una sola vez en todo el
  juego** —siete comandos en la página del viaje en el Hover-Tram, donde el
  paisaje de la tarde corre por detrás y cambia de velocidad al arrancar y al
  frenar— y sin él esa página no compila: o sea que lo que esto compra es el
  viaje entero, y lo que cuesta es que las ventanillas se vean quietas. * **El
  ataque y el decaimiento** siguen saliendo de las ocho familias de `sdsp.py`,
  elegidas a ojo cuando el banco era sintético. El SoundFont trae los suyos por
  instrumento y todavía no se leen. (El release ya no: ver arriba.) * **Una
  muestra por instrumento.** Un piano real está multi-muestreado cada pocas
  notas; nosotros tomamos la del do central y transponemos. En los extremos del
  teclado eso se nota.

## Una mejora de velocidad gratis que apareció midiendo

La capa de encima llama a `tile_colors` **894.000 veces** —medido el
2026-09-16 sobre `demo-ciudad` con `SIN_CACHE=1`— porque los colores de cada
tile se recalculan en el segundo recorrido en vez de guardarse del primero. Es
un diccionario de una línea. (El análisis de por qué `tiles/` no entraba, que
estaba acá, lo reemplazó el paso 8.)

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
