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
`tools/protocol/`: argumentos con clap, errores que nombran el archivo y lo que se
esperaba, y dos códigos de salida distintos (1 = algo quedó viejo, 2 = la
llamada está mal).

Los pasos, en orden, y ninguno bloquea al otro salvo 3→5→6:

1. **los conversores puros**, un proyecto por responsabilidad: `tools/gunter/` (muestras
   → BRR, con el lector de SoundFont) y `tools/voodoo/` (PNG → tiles y paletas). Son
   puros y lo sabemos **porque el conversor ya los cachea**. Los dos están
   hechos y conviven con su Python; lo que falta medido está más abajo;
2. **el ensamblador**: fue `w65/` y desde el 2026-09-16 es `ca65` + `ld65`,
   con el mapa de memoria que escribe el conversor;
3. **el asignador** —paletas, ARAM, VRAM— que es lo que queda de
   `snes_convert.py` cuando le sacás los conversores, más el secuenciador de
   MIDI al SPC700, que **no** es un conversor tonto: conoce el driver y usa
   `tools/protocol/music.toml`;
4. **el compilador de eventos**: JSON → bytecode y tablas. No es Ditto y no
   puede serlo: Ditto es un transcodificador bidireccional y sin pérdida, y
   esto es un compilador unidireccional, con pérdida y atado a un target. Lo
   que sí sale de acá es `tools/rpgmaker/lcf.py`, que en Rust pasa a ser
   `use ditto` —y ahí vuelven los nombres de los enums, que hoy `data/` no
   trae—. Y `tools/rpgmaker/rm2k.py` —534 líneas
   de semántica de RM2k— se **duplica** a Rust a propósito. El motivo original
   de dejar la copia de Python era la referencia, que ya no está; lo que la
   sostiene ahora es que las pruebas siguen en Python y la leen. Acá es también
   donde hay que decidir qué pasa con lo que queda del modelo de
   `tools/port/eventos.py`, que es de lo que habla el párrafo siguiente.

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

Lo que quedó de `tools/port/eventos.py` es lo que hay que portar en la vuelta del
compilador de eventos, y cuánto es lo dice `wc -l tools/port/eventos.py`: acá había
un número escrito y ya se había quedado viejo dos veces seguidas mientras el
barrido seguía.

**Las pruebas se quedan en Python**, y no es deuda: es diseño. Decisión de taro
—un lenguaje interpretado y menos estricto tiene ventajas ahí, y compilar para
correr las pruebas suma tiempo sin aportar casi nada—. Pasar el arnés a C se
descartó el 2026-09-18 con el número delante: medido con cProfile, de 13 s de
`test_tanda_paginas.py` casi todo es el core emulando y cargándose —que ya es
C— y lo que es Python no llega a un segundo. El efecto estructural que
esto tenía —que mientras el conversor fuera Rust y la referencia Python la
frontera del lenguaje les hiciera imposible compartir código— **se terminó al
irse la referencia**: lo que queda del lado de Python son las pruebas y el
modelo de RM2k de `tools/port/eventos.py`, que es del mismo lado que el conversor.

### Qué reemplazó a la referencia, que era el paso 6

Tres cosas, y conviene tener las tres juntas porque ninguna sola alcanza:

* **las goldens**, capturas congeladas de la ROM en `pruebas/golden/tanda/`.
  Cazan regresiones, no errores de nacimiento: una feature que sale mal desde el
  día uno hornea el bug adentro de su golden. **Actualizar una es un acto
  deliberado** —va a git, se mira, y el commit dice por qué el render cambió; la
  tanda nunca regenera—, y ése es el único modo de falla real del esquema. El
  porqué largo está en `pruebas/golden/tanda/LEEME.md` y en `AGENTS.md`;
* **`pruebas/rpgmaker/test_cores.py`**, que corre el mismo cartucho en snes9x y en bsnes
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
sus casos son pruebas de pytest en `pruebas/*/test_tanda*.py`, contra las goldens.
**Ya no hay ningún `xfail`**: el que quedaba —el de la *página de prueba* de
guardado, que no llegaba a guardar si la partida cambiaba de mapa— dejó de
reproducirse el 2026-09-20 y no porque se haya arreglado nada, sino porque el
cartucho que lleva la pantalla de título pasó a arrancar en el mapa 4. Quedó
como prueba normal, con el diagnóstico entero adentro, en
`pruebas/rpgmaker/test_titulo.py`.

Los cuatro proyectos en Rust tienen sus propias tandas: `just gunter-pruebas`,
`voodoo-pruebas`, `protocolo-pruebas` y `ditto-pruebas`.

**El justfile tiene una sola demo desde el 2026-09-20**: `just demo` arma
`rom/build/abl/abl.sfc`, la cadena entera con pantalla de título, que es lo que
taro juega. Con ella se fueron las cinco recetas que armaban ROMs para mirar
algo a mano —`demo-vipers`, `demo-cofres`, `demo-trampa`, `demo-piedras` y
`musica`—: lo que probaban ya lo cobra la tanda, y la regla es la misma que se
llevó a `destraba` —lo que no es ni pipeline ni prueba no vive en el justfile—.
Quedan `demo`, `demo-carrera` —que no comparte un solo mapa con la otra— y
`msu`, que desde ese día no vuelve a renderizar la pista que no cambió.

`abl` se juega desde la apertura hasta la calle de Lashe City, con los
relámpagos, los autos y los NPCs andando, el agua moviéndose, la lluvia, el save
point animado y guardando, el menú de pausa, los ítems, el equipo y la tienda.
**Corre en la SNES de verdad con el FX Pak**, con la música por MSU-1 y los
efectos por el SPC700.

**Cuántas páginas compilan ya no lo mide nada**: lo hacía `just destraba`, que
se fue el 2026-09-19 porque no era ni pipeline ni prueba. Lo último medido: las
páginas automáticas que compilan enteras eran **350 de 489** —el 2026-09-15; el
332 que decía acá y el 281 y el 314 que decía el README eran los tres viejos—, y del juego entero **5198 de 5603 disparables (92,8%)**, que
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

    tools/ditto/      lee y escribe los formatos de RM2k      enchufado: `data/` sale de acá
    tools/protocol/   declara los dos bytecodes               enchufado: los cuatro generados
    tools/gunter/     Gunter: BRR y lector de SoundFont       enchufado: las muestras salen de acá
    tools/voodoo/     Voodoo: imagen indexada -> tiles        enchufado: las capas de los mapas

**Se consumen desde el PATH** —`just herramientas` los instala y
ningún script ni prueba llama a `cargo`—; el porqué está en `AGENTS.md`.

Cada uno de los cuatro tiene su prueba de que no cambió nada: las ROMs salen
byte por byte iguales a las de antes de cada corte. `tools/voodoo/` tiene la suya de
que **podría** enchufarse —455 PNG idénticos a los del Python— y lo único que lo
frena es el desempate de `try_pack`: ver `wishlist/desempate-try-pack.md`.

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

**Los pasos 1 a 4 están hechos** —el tinte que sobrevivía al cambio de mapa,
enchufar los conversores y borrar los de Python, las recetas de la tanda
pasando a pytest, y las goldens reemplazando a la referencia—; el relato de
cada uno lo tiene el registro. Lo que dejaron y sigue valiendo:

* **una segunda implementación no se sostiene**: si el port se equivoca la ROM
  cambia y las goldens se ponen rojas, así que la comparación ya la hace el
  criterio de aceptación, y tener dos sólo obliga a tocar las dos;
* **las trampas del arnés viven en el docstring de su caso** —la celda (22,8)
  de `tecla`, el cuadro que se saltea en `ruta-evento`, el `--toques-hardware`
  que ignoraba `--apretar-a`—. No están en ningún otro lado;
* **lo que queda pendiente del 4 es la bendición de las goldens**, y está
  arriba en "Qué reemplazó a la referencia".

5. **El acomodo de bancos sale del ensamblador.** ✅ el 2026-09-16, salvo dos
   casos que quedaron medidos. Lo hacía `.bloque`, una directiva nuestra: el
   conversor le decía al ensamblador "lo que sigue mide N bytes, rellená hasta
   el próximo banco si no entra", y existe porque un DMA que cruza de banco lee
   la WRAM en vez de la ROM. `ld65` no sabe acomodar bloques de tamaño
   variable, así que la decisión la toma ahora el conversor —el único que
   conoce los tamaños— en `tools/ensamblado/bancos.py`, y al ensamblador le llega relleno
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
   banco desde el 2, repartido por `tools/ensamblado/bancos.py`; y el `.cfg` lo escribe
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

8. **El asignador corre primero, y `tools/voodoo/` convierte lo que ya entra.** ✅ el
   2026-09-17, con la ROM byte por byte igual en cada sub-paso.
   Rediseñado por taro el 2026-09-17; lo que sigue reemplaza al "enchufar
   `tools/voodoo/`" que había acá.

   **La frontera**: Voodoo no toma decisiones artísticas —dada una imagen que
   el formato puede representar, la representa sin tocar un pixel, y si no
   puede, falla—; el asignador sí —decide qué se pierde: fusionar colores,
   empaquetar paletas, repartir CGRAM entre capas, sprites y mapas—. La
   prueba para cualquier función es **"¿cambia algún pixel de lo que se
   ve?"**. Con hardware infinito el asignador seguiría existiendo, pero chico:
   los presupuestos desaparecen, los límites del formato —15 colores por tile
   de 4bpp— no.

   **El pipeline**: render → **asignador** (el cartucho entero de una vez) →
   **PNG indexados de 8 bits con índices absolutos de CGRAM** más un
   manifiesto → **`voodoo`** → conversor → `ca65` + `ld65`. En una capa de
   4bpp, `índice >> 4` es la paleta y `índice & 15` el color; así no hace
   falta metadata —un PNG no puede decir "mis índices arrancan en N", y un
   chunk propio lo borra el primer editor que lo guarde—. Cada PNG lleva la
   CGRAM entera, **duplicada a propósito**: `voodoo` junta las entradas que
   usa cada imagen y **corta si dos le dan distinto color a la misma**. Las
   imágenes del asignador quedan en `rom/build/<cartucho>/asignador/`, para
   mirarlas y retocarlas sin armar la ROM.

   **`--merge` se va de `voodoo`**, y con él el empaquetado de paletas y
   `--first-palette`: son del asignador, que por ahora sigue en Python y más
   adelante va a ser un proyecto en Rust aparte, con `voodoo` como biblioteca.
   Mantener un "asignador tonto" en `voodoo` se descartó: habría dos
   respuestas a "qué color se pierde".

   **Lo que esto gana**: como el asignador sigue siendo el de Python, con el
   mismo desempate, las paletas no cambian, y `voodoo` sólo corta, deduplica y
   espeja. **Enchufarlo no mueve ninguna golden**: los bytes pueden cambiar —el
   orden de los tiles— y los pixeles no. El desempate nuevo, que era lo único
   que iba a mover la ROM a propósito, se va con el asignador a Rust.

   | | qué | criterio |
   |---|---|---|
   | 8a ✅ | `voodoo` recibe PNG indexado en espacio CGRAM; se van `--merge`, el empaquetado, `--first-palette` e `inspect` | pruebas de `voodoo` |
   | 8b ✅ | `voodoo` recibe varios dibujos que comparten pool, con los que animan en corridas al final | pruebas de `voodoo` |
   | 8c ✅ | el asignador emite la capa de encima como PNG indexado y `voodoo` la convierte | ninguna golden se mueve: la ROM salió igual |
   | 8d ✅ | lo mismo con el fondo y sus dibujos | ninguna golden se mueve: la ROM salió igual |
   | 8e ✅ | se borra lo que `voodoo` reemplazó; lo que queda de `pixeles.py` va al módulo del asignador | la ROM igual a la de 8d |

   Los sprites no pasan hoy por `voodoo` en ningún lado: quedan para después.

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

   **Medido el 2026-09-17: la compresión no es lo que frena.** La unión que
   pide la regla —los mapas de las pruebas más los de `abl`— son 41.
   Sin el 66 y el 261 (ver abajo), **los datos de los otros 39 entran**; lo que
   no entra es el **banco 0**, por 361 bytes, y la tabla más grande que el
   conversor pone ahí es `anim_tabla`, 16 bytes por mapa. Se reproduce con:

       python3 tools/port/snes_convert.py --grupo 10 --map-id 4 \
           --con-timer --con-titulo -o rom/build/unico/mapdata.inc \
           --mapas 1 2 3 5 6 7 8 9 10 11 12 13 14 16 17 18 19 20 21 23 26 28 \
                   29 30 32 33 34 36 52 70 73 74 119 121 133 255 269 348
       python3 tools/ensamblado/ensamblar.py rom/src/main.s -I rom/build/unico \
           -o rom/build/unico/unico.sfc

   **Dos límites que el cartucho único destapó**, y que el juego entero va a
   pedir resolver igual: la ventana no entra en la VRAM de un mapa grande como
   el 66, y **la pantalla de ranuras junta las caras de todos los actores que
   pueden estar en el grupo** —con el 66 se pasaba por 28 tiles de 448—. El
   segundo se destrabó el 2026-09-20 componiendo el texto del actor con
   glifos: lo que crece por actor es la cara y nada más. El de la ventana
   sigue, y se arregla subiendo cosas cuando hacen falta.

   Lo que sí frena, y es de diseño, son las opciones que hoy son **del
   cartucho entero** y las pruebas usan distintas:

   * **La ventana de mensaje.** El mapa 66 no la puede llevar —no le queda
     VRAM— y es justamente el que las pruebas usan como "mapa sin ventana"
     (`SIN_VENTANA` en `pruebas/conftest.py`). Con la ventana en todo el
     cartucho, el 66 no convierte.
   * **El grupo.** El mapa 261 se prueba con `--grupo 11`; con el de
     `abl` el actor 11 puede liderar, comparte paleta con un NPC del
     mapa, y el conversor corta porque un destello los haría brillar a los
     dos. `--descartar-eventos` no lo cubre.
   * **Las páginas de prueba**: unos veinte flags del conversor —de
     `--pagina-de-prueba` a `--batalla-de-prueba`— metían bytecode distinto en
     cada cartucho. Con uno solo tienen que estar todas adentro y elegirse al
     correr. (Se fueron con el 9d: hoy cada una es un archivo.)
   * Y `--descartar-eventos`, que la tanda pasaba en 14 cartuchos. (Se fue
     con el 9e: ninguno lo necesitaba ya.)

   Qué se arma desde el 9f lo imprime `just cartuchos --lista`.

   **Decidido por taro el 2026-09-17**, para cada una:

   * **La ventana es obligatoria en todo mapa.** Primero se decidió que fuera
     por mapa, y se implementó; taro lo revirtió antes del commit: un mapa sin
     ventana de texto no existe en la práctica, así que soportarlo es darle
     forma a un estado que no debería darse. Lo que el 66 muestra es un
     **límite de VRAM** —la ventana no le entra— que cualquier mapa grande del
     juego va a tener, y se arregla haciéndola entrar, no sacándola. Hasta
     entonces **el 66 queda afuera del cartucho único**. (La implementación
     descartada, por si algo sirve: la ROM preguntaba por `M_VRAM_VENTANA` del
     registro, que ya vale 0 en los repartos sin ventana, y el conversor
     reintentaba la conversión anotando el mapa.)
   * **El grupo de cada prueba lo arma la página de prueba**, con
     `ChangePartyMembers`, como lo haría el juego: taro prefirió eso a un
     gancho en la ROM que existiera sólo para las pruebas. Fue
     `--grupo-de-prueba` en el conversor hasta el corte 3 del 9d, y desde ahí
     son los `ChangePartyMembers` del caso; sus líderes y sus caras entran en
     todos los mapas. Para
     que la página corra **antes** que las del juego —el 21 agrega a Talan al
     entrar, y con la página al final el líder salía otro— su evento va
     primero: un evento vacío en el índice 0, y los blancos que pasaban las
     pruebas se corrían con `eventos.blanco_de_prueba` —desde el corte 3 del
     9d los eventos van por su id de RM2k y no hay nada que correr—. El conflicto del 261
     se resolvió contando como otro gráfico —`rm2k.COPIA_SUFIJO`— a los NPCs
     que dibujan con el de un líder, en los mapas donde algo destella al
     héroe. Con eso el cartucho único arma con 40 mapas; el 66 sigue afuera.
   * **Hay un cartucho de pruebas**, que es el de juego más las páginas de
     prueba. Primero se decidió que fueran una tabla elegida por la RAM; con
     la idea del juego golden pasan a ser eventos de RM2k —ver "Hacia dónde
     va"—.

   | | qué | criterio |
   |---|---|---|
   | 9a ✅ | `anim_tabla` sale del banco 0 | la ROM se mueve y ninguna golden |
   | 9b ✅ | la ventana deja de ser opcional: se va `--con-ventana`, y las pruebas "sin ventana" pasan a un mapa que la tiene | se volvieron a aprobar 30 goldens, todas miradas |
   | 9c ✅ | el grupo lo arma la página de prueba, y el 261 entra | ninguna golden se movió |
   | 9d ✅ | las páginas de prueba pasan a ser eventos de RM2k —ver "Hacia dónde va"—, en tres cortes: (1) la página se arma con comandos de RM2k y se exige que compile a los mismos bytes; (2) varias páginas en un cartucho, elegidas por una variable; (3) las definiciones salen de los flags a datos | ninguna golden se movió, y los `mapdata.inc` de la tanda salieron idénticos en cada corte |
   | 9e ✅ | lo que queda de flags por cartucho —`--inicio`, `--descartar-eventos`, los datos de prueba— | se regeneraron diez goldens, las diez por fase de animación: esperan que taro las mire |
   | 9f ✅ | una receta arma el cartucho de pruebas una vez, y las pruebas reciben su ruta | ninguna prueba arma nada; cambian cinco goldens, una de fase y cuatro de contenido que el cartucho único trae: taro las miró |

   **9e, decidido por taro el 2026-09-18**, sobre lo que midió un sub-agente
   (rama `worktree-agent-a0e54b96ce9bbc0ac`, `medicion-9e/`; capturas en
   `/extras/capturas/9e/lado/`):

   * **Cada caso arranca con un `Teleport` de RM2k** a su mapa y su celda, en
     vez de `--map-id`/`--inicio` por cartucho. El conversor compila cada caso
     con el contexto de su mapa de destino —24 de los 149 casos nombran
     eventos de su mapa—, y el arnés pone sus relojes en cero al llegar en vez
     de sumar un corrimiento fijo: el salto cuesta siempre 70 ticks, pero en
     cuadros de hardware va de 74 a 139 según lo que se cargue en el negro.
   * **Las animaciones del mapa no avanzan mientras el mundo está congelado**
     en un fundido, que es lo que hace easyrpg-player —en una transición
     `Player::Update(false)` no llama a `IncFrame`—. En su propio commit;
     mueve `talan-400` y `manta-1200`, la fase del agua después de un
     teletransporte.
   * **`--descartar-eventos` se va**: los 14 cartuchos que lo usan salen byte
     por byte iguales sin él.
   * **Lo que no entra en el cartucho único va en uno aparte**, chico:
     entonces los casos del actor 21 —con ellos la pantalla de ranuras juntaba
     462 tiles de 448; desde el 2026-09-20 entran y volvieron al de
     pruebas—, `--heroe-encima` y los dos rellenos de mensajes, que cuidan una
     disposición del cartucho y no una imagen.
   * Encontrado midiendo, sin causa aislada: **después de un `Teleport` desde
     otro mapa, el cofre del caso `cofre` no aparece aunque la variable 123
     vale 8.** Es un camino que hoy no ejecuta ninguna prueba. (Aislada en el
     9e: ver abajo.)

   **9e, hecho.** Lo que hay que saber para escribir un caso que corre en otro
   lugar:

   * **empieza con un `Teleport`** a su mapa y su celda, y nada más dice dónde
     corre. El cartucho de pruebas lleva todos los mapas y arranca en el 6
     —`MAPA_DE_ARRANQUE` en `pruebas/arnes/cartuchos.py`—. La página vive igual en
     el evento 0 del mapa de arranque, pero **se compila con el contexto del
     destino** —`mapa_del_caso` en snes_convert.py—, y a ese mapa van lo que
     el conversor decide por mapa a partir de los casos: quién camina, los
     gráficos de `--grafico-de-prueba`, los dígitos del cronómetro;
   * **el arnés espera la llegada** y cuenta desde ahí: `Partida` corre hasta
     la vuelta siguiente a la que apaga el fundido y pone en cero los ticks y
     los cuadros de hardware. Lo sabe porque `cartucho` leyó el caso; mirar si
     la ROM está fundiendo no alcanza, porque el mapa 4 funde solo;
   * **un caso que varias pruebas usan en lugares distintos se copia**, uno por
     lugar: por eso existen `parado-*`, `pisar` y `hablar-*`, que eran
     `grupo-11`, `switch-24` y `switch-25`.

   Lo que cambió en la ROM, cada cosa en su commit y con su porqué:

   * **las animaciones del mapa no avanzan en un fundido** —`vueltas_congeladas`
     en main.s—. Movió cinco goldens y no dos: la medición contaba la primera
     roja de cada prueba, y `talan` y `manta` tienen varias capturas;
   * **una carga de mapa limpia los tilemaps**. Lo que caía afuera del mapa
     quedaba del anterior, y `ShakeScreen` contra el borde lo destapaba: lo
     encontraron `sacudir-borde` y `tram-viaje` en cuanto llegaron con un
     `Teleport`;
   * **una escritura a una variable después de saltar a otro mapa pide
     refresco siempre** —`Eventos.afuera`—: era el cofre. El refresco se
     decide al compilar con las variables que miran las páginas del mapa, y
     la página ya no corría en ese mapa. A los casos no les hace falta —se
     compilan con el contexto del destino—; cubre las páginas del juego, y
     ninguna que compile hoy pasa por ahí.

   Y **cinco goldens tienen un tick más de fase en las animaciones**
   —`core-puerta`, `talan-200`, `fuego-20`, `sacudir-borde-11`—: el tick en
   que la página corre en el 6 antes de saltar, que en RM2k también cuenta.
   Todo lado a lado en `/extras/capturas/9e-c/` y `/extras/capturas/9e-arranque/`.

   **9f, hecho.** Las pruebas no arman nada: `just pruebas` corre primero
   `just cartuchos` —`pruebas/arnes/cartuchos.py`—, que arma en serie los cartuchos
   de `rom/build/pruebas-unico/` si algo de lo que los arma cambió, y las
   pruebas piden su caso por el nombre, `tanda.partida("<caso>")`. Si el
   cartucho es de otros fuentes, el arnés se niega a correr y dice qué receta
   correr. Qué caso va en cuál lo imprime `just cartuchos --lista`.

   **Cómo se agrega un caso**: un archivo en `pruebas/casos/`, y la prueba lo
   pide por el nombre. Entra solo en el cartucho de pruebas. Si corre en otro
   mapa que el 6, empieza con un `Teleport` a su mapa y a su celda; para el
   grupo de la tanda en un mapa sin nada más están los `grupo-11-en-<mapa>`, y
   para el del juego los `en-<mapa>`, con la celda donde el héroe caía cuando
   ese mapa era el de arranque de su cartucho.

   **Son tres y no uno**, y cada uno tiene su porqué en `CARTUCHOS`:

   * `pruebas`, los 40 mapas arrancando en el 6, con todo lo que entra;
   * `juego`, los 40 mapas arrancando en el 4, con cronómetro **y con la
     pantalla de título**: el recorrido, el save point, la apertura, el cartel
     y todo lo del título. Llegar al 4 con un `Teleport` no es arrancar ahí
     —la cinemática sale con otra rampa y otro tinte—, y el cronómetro en
     todos los mapas le saca una paleta a cada uno;
   * `chico`, lo que no entra o cuida una disposición del cartucho: **los
     casos con los actores 12 y 13 en el grupo** —decisión de taro:
     en el de pruebas podían liderar y le cambiaban los colores al mapa 13—,
     `--heroe-encima`, los encuentros cada 8 pasos, el relleno de textos de
     200 y el **borde de banco del bloque de textos**, que lo pone el caso
     `empujon`. **Las dos lluvias volvieron al de pruebas** el 2026-09-20, al
     arreglarse el primer defecto de abajo, y el relleno de textos vino de
     `cruza` con el segundo.

   `ChangeEncounterSteps` no está implementado, así que los encuentros de
   prueba siguen siendo un flag del cartucho chico.

   **El cartucho `titulo` se fue el 2026-09-20**, y con él
   `test_titulo_es_el_mismo_juego`. Era el de pruebas con la pantalla delante
   y con sus mismos mapas y casos, y esa igualdad era su razón de ser: aquella
   prueba lo comparaba contra el de pruebas. Se midió antes de tocarlo, con un
   cartucho armado sólo para eso, que **el título no mueve una sola golden**:
   las cuatro de la pantalla salen idénticas arrancando en el 4 en vez de en
   el 6, y las diecisiete de `cinematica`, `apertura` y `cartel` —congeladas
   sin título— salen byte por byte iguales sacadas a través de él. La prueba
   que se fue comparaba dos capturas **negras** —57.344 pixeles de un solo
   color—, así que la pregunta "¿son la misma ROM?" la contestan mejor esas
   diecisiete, que pasan por el título y se ven. Ahorra 42 segundos de `just
   cartuchos`: 1m55 a 1m13, medido con el caché caliente.

   **El quinto cartucho, `cruza`, se fue el 2026-09-20.** Existía sólo por
   `--relleno-de-mensajes`: bytes muertos delante del bloque de textos para
   que un cuadro cayera del otro lado del borde de 32 KB de un banco de
   LoROM, que es donde `msg_empezar` y el compositor se equivocaban. Hacían
   falta dos cartuchos porque cada relleno ponía el **mismo** cuadro en otro
   lugar. Desde que un caso es un evento de RM2k, sus textos van al mismo
   bloque y van delante de los de los mapas, así que el empujón lo da un caso
   —`empujon`, texto generado que no se dibuja nunca— y con **uno solo** los
   dos cuadros de la página automática del 255 caen en lugares distintos: el
   primero a caballo del borde y el segundo entero del otro lado. Los dos
   `--relleno-de-mensajes` se fueron del conversor con él.

   Y lo que hasta ese día no verificaba nadie: que el cuadro **siga**
   cruzando. Las goldens de `texto`, `texto-cruza` y `texto-lejos` son la
   misma imagen —ésa es la propiedad—, así que un bloque que se acomode
   distinto las deja en verde igual. Ahora `test_texto` lee el cuadro del
   `.sfc` con `tanda.cuadro_de_texto` y lo pide explícitamente.

   **Lo que el cartucho único cambió de las goldens**, cinco, cada causa
   aislada armando el cartucho viejo con una sola cosa del nuevo: `3-down-56`
   es de fase —la llegada por `Teleport`, como las del 9e— y las otras cuatro
   son contenido que traen los 40 mapas: `8-right`, una puerta que ahora lleva
   al 16; `tram-320`, páginas del 9 que compilan porque su destino está; y
   `tram-900` y `tram-1200`, el viaje del tranvía que sigue hasta el 16. taro
   las miró. Lado a lado en `/extras/capturas/9f/`.

   **Los dos defectos que el cartucho único destapó están arreglados** desde
   el 2026-09-20, cada uno en su commit y sin mover una sola golden. Lo que
   queda escrito es lo que no está en el diff:

   * ~~**las gotas de lluvia en un mapa con cronómetro no se tiñen**~~. La
     paleta de los dígitos la vuelve a subir `subir_timer_pal` sin teñir, y
     eso es correcto —en RM2k el cronómetro va encima del tinte,
     `Priority_Timer` 140 contra `Priority_Screen` 90—; la lluvia va debajo
     —`Priority_Weather`, 80— así que no puede compartirla. `gotas_de_lluvia`
     la saltea, como ya salteaba las ranuras de líder. **En `abl` no
     se veía**: los dígitos y las gotas comparten paleta en catorce de sus
     veintinueve mapas, pero no en el 1, que es donde llueve. Lo que cuesta,
     medido: el mapa 18 de `abl` se queda sin gotas por falta de
     paleta, y en el cartucho de pruebas no se pierde ninguno;
   * ~~**la lista "Use Item" de la pelea no dibuja los nombres**~~, y **no
     era de la ROM ni tenía que ver con el 255**: el índice se arma y se lee
     de a dieciséis bits de punta a punta. Era `--relleno-de-textos`, que
     metía sus textos muertos delante de todos, y el nombre de un ítem no
     sale de una tabla sino de la cuenta `3k`. Descartado el 255 midiendo:
     con relleno 100 —nombres del 100 al 168— desaparecen los mismos 521
     pixeles. En `abl` tampoco se veía: 62 ítems son los textos 0 a
     183, y lo que pasa del 255 son los términos de la batalla, que
     `ba_orden_txt` ya nombra con dos bytes;
   * **en el cartucho de pruebas la primera vuelta del lazo termina tres
     cuadros más tarde** que en uno de un mapa. `Partida` lo espera antes de
     mirar el `Teleport`, pero lo que cuenta cuadros de hardware desde el
     arranque —`consola_cruda`, `toques_hardware`— cuenta desde un poco antes
     del primer tick. Ninguna golden lo distingue hoy;
   * **las goldens `titulo-juego` y `titulo-juego-sin` son negras enteras**,
     desde antes del 9f: la prueba que compara la ROM con título contra la
     misma sin él compara dos pantallas negras. No se tocó.

   Lo que quedó igual: `ir_al_mapa` sigue —escribe el pedido en la RAM y anda
   en cualquier cartucho que lleve el mapa—, y **el mapa de arranque sigue
   siendo el 6**, que no es el bueno para el juego golden: querría uno vacío,
   sin páginas propias que corran en ese primer tick. La carrera del caché
   de disco no se vio: el build es en serie.

   **9d, corte 1, hecho, y se fue con el 3.** Armaba la página escrita a mano
   también como comandos de RM2k y exigía que `compilar_pagina` diera los
   mismos bytes. Era la red que ataba las dos formas mientras convivieron; con
   la escrita a mano borrada no tiene qué atar.

   **9d, corte 2, hecho.** Un cartucho lleva varias páginas de prueba: cada
   caso va detrás de un `--caso`, cada caso es una página del
   evento de prueba, y la elige `eventos.VARIABLE_DE_CASO`, que el arnés
   escribe antes del primer cuadro con `Partida(caso=k)`. Es una variable y no
   un switch por caso —como decía el plan— porque switches libres quedan
   dieciocho; la página k pide que valga al menos k, que es la condición de
   página de RM2k 2000. Lo que el conversor saca de los casos para el
   cartucho entero —líderes, miembros, ítems, tropas, lluvia, cronómetro,
   variables, animaciones, mensajes— sale de la unión de los casos.
   `pruebas/test_casos.py` arma uno con cuatro y pide a cada caso **la golden
   de su cartucho propio**. Desde el 9f eso es la tanda entera, y
   `test_casos.py` se fue.

   **9d, corte 3, hecho.** Un caso es un archivo de `pruebas/casos/`: la lista
   de comandos de una página de RM2k, en el mismo JSON de Ditto que `data/`
   —`{"event_commands": [...]}`, o sea una página con la condición y el
   trigger en su default, que los pone el conversor—. El conversor lo recibe
   con `--comandos-de-prueba`, le antepone el `ControlSwitches` que la apaga y
   lo compila con `compilar_pagina` y el contexto del mapa; lo que el cartucho
   saca de los casos lo barren las mismas funciones que barren las páginas del
   mapa. Los flags de caso, `pagina_de_prueba` y la comparación del corte 1 se
   fueron. Lo que hay que saber para escribir uno:

   * **el grupo va adentro del caso**, con `ChangePartyMembers`: el de la
     tanda es `grupo-11`, que es la página 0 del cartucho de pruebas, y un
     caso propio arma el suyo; `nada` y los `en-<mapa>` dejan el del juego;
   * **los eventos van por su id de RM2k**, no por el índice en el mapa: los
     resuelve `Eventos`, igual que en una página del juego;
   * **la orden 34 de una ruta lleva el nombre del CharSet** —el largo y una
     letra por entero, como lo escribe RM2k— y el gráfico tiene que estar en
     el banco del mapa: eso lo sigue pidiendo `--grafico-de-prueba`, que es
     del cartucho y va al banco de los mapas donde corren los casos;
   * **la clave del cartucho lleva lo que dice el archivo**, no sólo su
     nombre, así que editarlo rearma;
   * **las pruebas de estado que calculan lo esperado** —`test_items`,
     `test_equipo`, `test_hp_de_batalla`…— tienen el dato también en Python,
     y un comentario dice de qué archivo es copia. No lo cuida nada más.

   Mudarlos al juego golden es mover archivos y ponerles la condición.

   Lo que se puede esperar de comprimir, medido: la parte usada de
   `abl` —3,12 MB— deflatea a **791 KB, un 75% menos**. El grueso del
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

   Lo que en este lugar decía que la tanda armaba 176 cartuchos casi iguales
   es el 9f, y está hecho.

10. **Partir `rom/src/main.s`**, que son 30.300 líneas en un archivo. **Va
    último**: es el único paso que no destraba ninguno de los otros, y `main.s`
    se sigue moviendo con los pasos 5 a 9. Probado en chico —una sección afuera
    con `.include`, mismo md5—; las fronteras ya existen, 82 marcas de sección
    y 450 `.proc`. Tres trampas: el `.segment` cruza el `.include`, las
    etiquetas anónimas se resuelven textualmente, y **reordenar sí cambia la
    ROM** aunque partir no.

**Las dos cadenas son independientes**: 5 → 6 es el acomodo de bancos, 7 → 8 es
el reparto de paletas. Se pueden hacer en paralelo.

**Hay una sola demo, `abl`, siempre con pantalla de título**, porque es la que
taro juega. La ROM sin título sirve de control —así se aisló que el reporte de
MSU-1 "la que tiene título no carga la música de alta calidad" era el arranque
con título— y por eso se arma cuando hace falta, con `--con-titulo` de menos
en la receta, en vez de vivir en el justfile.

**Y un número que cierra una pregunta vieja:** un cartucho con todos los mapas
es imposible. **29 mapas ocupan el 74,4% de los 4 MB** y el juego tiene 328.


**Está arriba, en "La etapa en curso": no hay features hasta terminar los
refactors.** Lo que quedó pedido o pensado y espera a que esa etapa cierre,
para no volver a pensarlo:

* **Curar fuera de la pelea** y **mostrar el HP como `20/20`** en el menú.
* **El rediseño de la escena de batalla**: fondo real y monstruos por separado,
  compuestos en VRAM al armar la pelea. Medido: unos 667 KB para el juego
  entero contra los 4,1 MB de hornear cada combinación.
* **Lo que le falta a la posada, que es todo de lo que se ve**: no hay
  ventana de oro al lado del saludo, "Yes" no sale en gris cuando no alcanza
  —elegirlo equivale a "No"— y no hay fundido ni música de posada, que es
  `Scene_Map::CallInn`. Compilan 17 de las 18 páginas del juego; la del 348
  sigue cortada por una elección con rama de cancelar.
* **El `ChangeHP` que resta no compila.** El que suma entró en `OP_HEAL`, y
  `ResetAfterBattles` tiene uno de los que restan, así que ese evento común
  sigue sin compilar.
* **Los eventos-tile al fondo** para el lag del minijuego del HQ.
* **La carrera de Lashe City**, que tiene su propia sección acá arriba.
* **El dibujo de las animaciones de batalla**: está medido y sin empezar; el
  sonido y la luz sí están.

## El margen de ROM y de RAM, medido

Lo que dejaron la liberación del banco 0 del 2026-09-19 y la de la BSS del
2026-09-20, que es lo que hay que saber antes de pedir más lugar. **Los
números de cuánto sobra hoy se miden, no se copian de acá**: cómo, en
`AGENTS.md`, y ojo con que el cartucho que manda es `titulo`.

**La trampa de mudar al banco 1, que va a volver a aparecer con cada mudanza**:
un dato que se va allá y se lee con direccionamiento absoluto pasa a leer el
banco 0, porque el banco de datos sigue en cero. La última vez fue un solo
`lda mensaje_de, x`, y la tienda abría sin el saludo.

**Lo que queda sin mover, medido, por si hace falta más ROM** (bytes netos del
banco 0, contando puentes y entradas): las ranuras y guardar ~1500 con 10
puentes, la pantalla de ítems ~1000 con 10, el menú de pausa y la elección de
actor ~970 con 9, la pantalla de título ~350 con 12. Y dos que rinden más pero
**son camino caliente y no se tocan sin decidirlo**: el giro hacia el héroe
~1700 y la saturación del tinte ~1560. En el banco 1 entran todas: le quedan
unos 21 KB.

**La pila no se puede bajar dos veces.** `PILA` bajó de 256 a 128 el
2026-09-20 —decisión de taro— y eso no movió un solo byte de la ROM, porque la
BSS se asigna de `$0100` para arriba. Los 128 que quedan son el margen que
cuida `pruebas/herramientas/test_pila.py`, no lugar disponible: la prueba
marca la zona con centinelas antes del primer cuadro —después de
`retro_load_game` y antes del primer `retro_run`, así que el `reset` entra en
la medición y no le cuesta un byte a la ROM—, corre los ocho caminos más
hondos que conocemos y avisa a la mitad de `PILA`. El tope está en las peleas,
que cruzan al banco 1 con `jsl`. Lo que **no** cubre es un camino que ninguna
prueba ejecute, que es por lo que el umbral no está pegado al tope.

**Lo demás de la BSS sigue sin salida barata**: lo grande que hay ahí es
`texto_buf` (1968 B), `npc_buf` (1664), `oam`, `cgram_sombra` y `pal_buf` (512
cada uno) y el estado de los eventos, y todo eso o se toca por cuadro o es
origen de un DMA. La ventana de `$2180` no se indexa, así que ninguno pasa a la
RAM lejana sin reescribirlo; el camino que sí existe es el de la pelea —correr
con el banco de datos en `$7E`— y para `texto_buf` eso es reescribir el
compositor de texto, que es el lazo más interno del repo.

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
* **El MSU-1 con pantalla de título**. taro reportó que la ROM con título no
  carga la música de alta calidad y la de sin sí. **En emulador las dos hacen exactamente lo mismo**,
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

**Dónde la ROM no hace lo que RM2k hace está en `divergencias/`**, un archivo
por divergencia, con su medición y cómo reproducirla. Acá queda lo otro: lo que
ninguna prueba mira, aunque nadie diga que esté mal.

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
  `pruebas/rpgmaker/test_musica_paquete.py`, que le pregunta a la ROM si las muestras del
  tema que dice estar tocando están de verdad en la ARAM (`FAR_ARAM_DE` contra
  `tema_muestras`). Lo que **sigue** sin mirar nadie es que lo que sale del DSP
  suene a lo que tiene que sonar: eso es oído, y es de taro.

* **El cursor de `ShowChoice`.** La tanda sólo aprieta A, así que arriba, abajo
  y B no los toca ningún caso de ella. Los cubre `pruebas/rpgmaker/test_elegir.py`.
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

* **El Dalia's Blast de las catacumbas**, el `EV0001` paralelo que espera la
  A con `KeyInputProc [176,1,0,1,0]`, tiene el mismo patrón que el motor de las
  piedras: medido el 2026-09-19, sus 23 páginas (mapas 281 a 283 y 324 a 344)
  **compilan**, pero ningún cartucho —ni los de las pruebas ni los de las
  demos— lleva esos mapas, así que ninguna prueba mira que cerrar un mensaje
  ahí no dispare la ráfaga. Si entran en un cartucho, ésa es la prueba que
  falta.

* **El audio no lo mira nada automático.** Las medidas contra el MIDI —`just
  bgm`, `audio-check` y `referencia`— se fueron el 2026-09-19 con todo lo que no
  era ni pipeline ni pruebas; la última vez que se corrieron, el 2026-09-06, los
  cuatro temas de la demo dieron 96%, 98%, 83% y 90%. Lo que queda es el oído de
  taro. Ver "Cómo se verificaba el audio" en el README.

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
  `pruebas/rpgmaker/test_cores.py`, que corre los mismos cartuchos en `bsnes` con la WRAM
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
  `pruebas/rpgmaker/test_cores.py`, y el reset de snes9x **no borra la WRAM**, así que
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
sin hacer lo dice `ACEPTADOS_SIN_HACER` en `tools/port/eventos.py`.

**Lo que quedó acá son los límites medidos que condicionan decisiones**; lo que
nos gustaría hacer y nadie está haciendo se fue a `wishlist/` el 2026-09-20 —el
presupuesto de muestras por paquete, la música del lado del SPC700, el sistema
de imágenes, las órdenes de ruta que faltan, las otras transiciones de RM2k, un
evento que camina y cambia de gráfico, el panorama del mapa 2, el ataque y el
decaimiento, y una muestra por instrumento—, y lo que la colisión con los
eventos no modela se fue a
`divergencias/lo-que-la-colision-con-los-eventos-no-modela.md`, porque es
descripción de dónde diferimos de RM2k y no trabajo a medias.

* **El acolchado de bloques.** Agrandar el cartucho **es un cambio de mapeo que
  ningún caso de la tanda ve**: los tres emuladores cargan el archivo del doble
  sin preguntar, así que lo prueba el cartucho real. Y no es la única salida:
  el acolchado que dejan los `.bloque` llega a **20 KB** —un bloque de 18 KB que
  no entra en lo que queda del banco deja 12 KB vacíos— y un enlazador que
  acomode los bloques en los huecos los recuperaría. No se hizo porque el
  crecimiento sigue: cada personaje que cambia de pose son 6 KB.

  Las dos ideas de taro para apretar assets que vivían adentro de este límite
  están en `wishlist/paletas-sobre-todas-las-imagenes.md` y
  `wishlist/hornear-la-decoracion-en-un-chipset.md`.
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

  La salida **no** es un desfase a mano —eso es un número que se ajusta hasta
  que dé verde— sino aflojarlos, o leer `cuadros_perdidos`, que ya viaja en la
  salida de cada captura.

  Lo que esto bloqueaba **se destrabó solo el 2026-09-16**, cuando la golden
  pasó a ser una captura de la propia ROM: darle caso propio a la escena del
  ascensor del mapa 2 es gratis y está en
  `wishlist/caso-propio-para-la-escena-del-ascensor.md`.
* **Los teletransportes que siguen sin resolverse.** Los que están adentro de
  cinemáticas con variables y condiciones que todavía no modelamos. El del
  mapa donde el juego arranca ya no: es automático, entra con los cinco
  comandos que la ROM entiende, y `Blank (Leave START here)` ahora se sale
  solo.
* **El techo de resolución del banco de muestras.** El cartucho lleva
  **varios** temas: los que pidan los `PlayBGM` compilados, compartiendo un
  solo banco de muestras —ver `decisiones/un-solo-banco-de-muestras.md`—. El
  techo no es la cantidad de temas —el banco se achica solo— sino la
  resolución: con los treinta y pico del juego entero **cada instrumento
  quedaría en una miga, y sin aviso**. Ver "Varios temas en el cartucho".

  Lo que subiría ese techo es un **driver que sepa recibir datos**: hoy las
  muestras se suben una sola vez al arrancar con el protocolo del IPL, que manda
  un byte por acuse y desaparece al saltar al driver. Con un banco por tema el
  costo sería medio segundo de transferencia en cada `PlayBGM` —lo que lo
  descartó fue eso más tener que modelarlo en la referencia, y esa mitad ya no
  está—; con los cuatro puertos en vez de uno, en cambio, se acorta el arranque,
  que hoy es `BOOT_CUADROS`, dimensionado para una ARAM llena.
* **La cinemática de apertura, entera.** La corre el caso `cinematica`
  —`test_cinematica` en `pruebas/abl/test_tanda_escenas.py`, que es donde está
  lo que el arnés tiene que saber de ella—, y la compara hasta el final con los
  quince toques de A que la cierran: el tinte se apaga, Core y
  Manta aparecen, el droide camina, Kersh explica su alias, y la página termina
  con dos `ChangeEventLocation` y un switch. De ahí el juego sigue con el
  jugador al mando, y eso ya no lo mira ninguna receta. Lo que la comparación
  **no** cubre es nada en movimiento en un cuadro en que la ROM venga atrasada;
  el toque de A resincroniza los dos lados.
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

## Hacia dónde va: un juego de prueba, y ABL en su propio repo

Idea de taro, el 2026-09-17. **No se hace ahora**, pero las decisiones de hoy no
tienen que alejarnos de ella.

**Dos capas de pruebas en vez de una:**

* **Conformidad del motor**, contra un juego de RM2k hecho a propósito —el
  "juego golden"—: un mapa por funcionalidad, chico y determinista, y el juego
  entero es el golden. Es la regla del cartucho único resuelta de raíz, y es
  la especificación de qué soporta el port. Portar otro juego lo reusa entero.
* **Aceptación de ABL**: que sus primeros minutos se jueguen y se vean así.
  Sigue haciendo falta, porque los errores más caros salieron de contenido
  real que nadie escribiría a propósito. **El juego golden crece con esos**:
  cada error que aparezca en un juego real se abstrae y se suma como un caso.

**Y dos repos**: lo que no depende de ABL —el motor, las herramientas, el juego
golden— se puede publicar, porque el juego golden usa material de dominio
público o con licencia que lo permita. ABL queda en el suyo, y si alguna vez
hay que bajarlo, se baja sin arrastrar lo valioso.

**Lo que esto pide hoy:**

* **El paso 9d cambia de forma**: las páginas de prueba no van a una tabla
  especial de la ROM sino que pasan a ser **eventos de RM2k**, datos que el
  conversor lee como cualquier otro. Son el embrión del juego golden, y así
  se mudan moviendo archivos; el conversor pierde los veinte flags que existen
  sólo para las pruebas. Generarlos con Ditto, desde JSON, evita depender de
  RM2k en una máquina virtual. **Hecho** el 2026-09-18: son
  `pruebas/casos/`, en el JSON de Ditto.
* **El conversor no sabe nada de ABL**: lo propio del juego —el grupo inicial,
  qué mapas van— vive en recetas o en un manifiesto, no en `tools/`.
* **Las pruebas nombran por símbolo o por comportamiento**, no por número de
  mapa de ABL, donde se pueda.
* **Lo que el juego golden no puede heredar sin revisar**: el RTP de Don Miguel
  es de Enterbrain; las muestras salen de los SoundFonts de
  `/extras/soundfonts`, cuya licencia hay que mirar una por una; y la fuente
  del sistema de RM2k tiene dueño. Los MIDIs de ABL son música de otros
  juegos: quedan del lado de ABL.

**Un paso intermedio, sin juego golden todavía** —de taro, el 2026-09-18—: las
pruebas se separan en carpetas por **qué** prueban, aunque todas sigan usando
ABL como material. **Hecho** el 2026-09-19, después del 9f:

    pruebas/rpgmaker/      lo que el motor tiene que hacer igual que RM2k
    pruebas/abl/           lo propio del juego: el recorrido, las piedras,
                           el recuerdo, el cartel, las escenas y cinemáticas
    pruebas/herramientas/  las que no corren ninguna ROM
    pruebas/arnes/         consola, tanda, cartuchos y recorrido

Cada una tiene su receta —`just pruebas-rpgmaker`, `pruebas-abl`,
`pruebas-herramientas`— y `just pruebas` sigue corriendo todo. Lo que no se
movió, a propósito: `conftest.py` queda en `pruebas/`, que es donde pytest lo
carga para las tres carpetas, y `golden/` y `casos/` son de las dos clases;
moverlos es de cuando existan los dos repos. `retro.py` sigue en `tools/`, en
`tools/emulador/`.

Lo que quedó del lado dudoso, y conviene revisar al armar el juego golden:

* **`rpgmaker/` es más "motor" que "RM2k"**: `test_cores`, `test_compositor`,
  `test_paralelos` y `test_musica_paquete` cuidan propiedades del port —la
  WRAM sin inicializar, el buffer del texto, el presupuesto del cuadro, las
  muestras en la ARAM— y no comportamiento de RM2k. Van con el motor igual.
* **`abl/test_tanda_escenas.py` tiene casos que ejercitan comandos
  genéricos** —`elegir`, `tienda`, `savepoint-guarda`, las puertas— con
  páginas del juego, y `factoria`, que es el tercer reparto de VRAM. Partirlo
  por caso pedía duplicar la función de la familia; se partió sólo por
  familia: `hablar` se fue a `rpgmaker/test_tanda_hablar.py`.
* **`herramientas/` se decidió por la forma** —no corre ROM— y varias miran
  el conversor sobre mapas de ABL: `test_lideres`, `test_destello_paleta`,
  `test_timer_paleta`, `test_encuentros`. `test_bancos` lee la tabla de
  símbolos del cartucho armado, sin correrlo. Si van "con su herramienta",
  el lugar natural es al lado de `tools/`, y eso se decide cuando `tools/`
  se reparta entre los dos repos.

**`tools/` quedó repartido en carpetas por responsabilidad** el 2026-09-19,
pedido de taro, sin reescribir código: los proyectos de Rust bajaron de la
raíz, y cada `.py` fue a un paquete de Python de verdad, que se importa por su
nombre (`from rpgmaker import lcf`). De abajo hacia arriba, y ninguna importa
de una de más arriba:

    rpgmaker/    lcf, event_codes, rm2k
    comun/       cache_disco
    ensamblado/  bancos, ensamblar
    emulador/    retro, bsnes-wram.patch
    render/      render_map, chipset, charset
    audio/       snes_music, midi, musica, sdsp, spc700, muestras_brr,
                 snes_samples, music_opcodes, msu
    port/        eventos, event_opcodes, batalla, pantallas, imagen, titulo,
                 ventana, fuente, escena, animacion, asignador, tiles_bin,
                 snes_convert
    ditto/, tiles/, gunter/, protocol/   los proyectos de Rust

**`port/` no está partido todavía**: tiene tres ciclos de imports adentro
—`eventos` ↔ `batalla`, `batalla` ↔ `pantallas`, `eventos` ↔ `imagen`— y
partirlo es trabajo de criterio. Ver `tools/README.md`.

## Lo que no es pipeline ni pruebas: se fue el 2026-09-19

La regla es de taro: *"yo no estoy usando nada manualmente, así que si algo no
es ni parte del pipeline ni parte de las pruebas, puede irse"*. Es la limpieza
previa a repartir `tools/` en carpetas. Qué se fue lo dicen los tres commits
de ese día —herramientas y recetas, lo muerto adentro de lo que queda, y la
prosa—; lo que queda acá es lo que **se quedó sin estar claro**, para que
decida taro:

* **`destraba`, `play` y `rom/Containerfile`**: decidido por taro el mismo día,
  se fueron.
* **`tools/rpgmaker/gen_ditto_schema.py`** no lo corría ninguna receta y era de
  donde salía `tools/rpgmaker/ditto_schema.py`, que sí es pipeline. Cerrado el
  2026-09-20 dándolo vuelta: el esquema lo **publica Ditto** —`ditto schema`—
  y Python lo leía; el generador se borró. Ese mismo día se cerró del todo:
  `data/` pasó a ser la vista resuelta y el esquema dejó de tener un lector de
  este lado, así que `ditto_schema.py`, su JSON, `just esquema` y
  `test_esquema.py` se fueron también.
* **`assets/medir.py`** se fue, y con él la forma de repetir los números de
  `assets/README.md`. El README ahora lo dice y da el commit de donde sacarlo.
* **Las cuatro esquinas de la cámara** y **el audio contra el MIDI** quedaron
  sin quien los mire: los cobraban `mapa` y `bgm`/`audio-check`, y no estaban en
  `just pruebas`. El README lo dice en cada lugar.

## Lo que se dejó afuera a propósito

* **El panorama del mapa 2** —los puntitos sobre azul cuando se enciende la
  pantalla grande— pide una tercera capa de fondo y el modo 3 tiene dos. Lo
  que compraría está en `wishlist/panorama-del-mapa-2.md`.
* **Los otros tipos de movimiento de las rutas propias**: al azar, vertical,
  horizontal y hacia el héroe. Son 106 páginas. Y el giro en el lugar, que del
  lado de las rutas forzadas es `wishlist/ruta-girar-sin-moverse.md`.
* **El fundido de la transparencia de una ruta**: se acepta y se tira, porque
  la SNES no atenúa un sprite por partes sin color math. Las ocho rutas del
  juego que lo piden están en `wishlist/ruta-transparencia.md`.
* **La ráfaga de entrada del mapa 8**: dos cuadros perdidos al entrar,
  invisibles jugando porque el fundido los absorbe —su reloj son cuadros de
  hardware—. Medido: las dos primeras vueltas se pasan del presupuesto de 262
  líneas por 1,45x y de la tercera en adelante sobra la mitad del cuadro; el
  grueso es crear las ranuras de ruta de los paralelos. Es optimización, no
  corrección, y por eso no se hizo.

* **Los cuadros que el lazo pierde de vez en cuando** —la primera vuelta de una
  ROM con muchas páginas, y la vuelta en que termina un fundido—. No cambian
  ningún pixel comparado. Acá decía además que eran lo único que le faltaba a
  la escena del ascensor para tener caso propio, y **eso dejó de ser cierto el
  2026-09-16**, cuando la golden pasó a ser una captura de la propia ROM: ver
  "Lo que falta del port" y `wishlist/caso-propio-para-la-escena-del-ascensor.md`.
