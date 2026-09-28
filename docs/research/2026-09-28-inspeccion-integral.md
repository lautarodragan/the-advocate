# Inspección integral del repositorio

**Fecha:** 2026-09-28  
**Árbol evaluado:** `e06740a` más esta inspección  
**Alcance:** arquitectura, fuentes, datos, proceso de build, pruebas,
documentación, mantenibilidad, dependencias, operación y riesgos. Es una foto:
los números de este documento describen ese árbol y no se deben actualizar.

## Dictamen ejecutivo

El repositorio es **técnicamente sólido y excepcionalmente consciente de sus
propios modos de falla**. La arquitectura está explicada, las decisiones
difíciles tienen dueño, el estado del trabajo no se mezcla con la documentación
estable y las pruebas ejercitan tanto el estado interno como el resultado
visual. En particular, la fuente única de opcodes, el build por cartucho, las
goldens deliberadas, la comparación entre cores y las comprobaciones de
memoria son defensas específicas contra errores que ya ocurrieron, no una capa
genérica puesta por costumbre.

No lo evaluaría todavía como un proyecto fácil de reproducir fuera del ambiente
habitual ni como una base sencilla para sumar colaboradores. Los mayores riesgos
son operativos y de concentración:

1. **No hay una instalación declarativa del entorno Python ni un chequeo de
   preflight.** En una máquina con Python y pytest, la colección falla recién al
   importar Pillow; `just` tampoco está disponible necesariamente. El README
   enumera familias de herramientas, pero no fija ni verifica el conjunto
   instalable.
2. **La tanda completa no corre en CI en este árbol.** No hay configuración de
   CI versionada. La calidad depende de que el ambiente de desarrollo conserve
   herramientas, assets externos, cores parcheados y conocimiento operativo.
3. **El conversor está demasiado concentrado.** `tools/port/snes_convert.py`
   tiene 9.322 líneas y `tools/port/eventos.py`, 5.515; el propio backlog ya
   reconoce tanto las responsabilidades mezcladas como las globales que chocan.
4. **La validación integral quedó bloqueada en esta inspección por el entorno,
   no por un fallo observado del producto.** Se pudieron comprobar sintaxis y
   los proyectos Rust, pero no armar ni ejecutar la ROM.
5. **No hay licencia ni política de distribución visibles.** Esto no afecta el
   funcionamiento, pero sí vuelve ambigua la reutilización del código y exige
   revisar aparte el estatus de datos, parches y capturas derivados del juego.

La recomendación es **no reescribir la arquitectura**. Conviene preservar las
defensas actuales y atacar primero la reproducibilidad, después partir el
conversor por límites ya identificados, y recién entonces ampliar alcance o
optimizar.

## Cómo se inspeccionó

Se leyeron `README.md`, `AGENTS.md`, `DITTO.md`, los README de `workflow/`,
`docs/`, `tools/`, `data/` y `pruebas/`, el `justfile`, `pruebas/UNTESTED.md`,
los manifiestos Rust, el estado de tareas, decisiones y divergencias, y el
historial reciente. Se recorrió el inventario de archivos y tamaños, y se
buscaron marcadores explícitos de deuda.

Comandos de la foto:

```sh
git status --short --branch
git log -12 --format='%h %ad %s' --date=short
git ls-files
git ls-files '*.py' '*.rs' '*.s' | xargs wc -l
find workflow/tasks/doing workflow/tasks/testing -maxdepth 2 -type f -print
find workflow/tasks/todo workflow/tasks/wishlist workflow/divergencias \
    -maxdepth 1 -type f -print
python3 -m compileall -q tools pruebas
python3 -m pytest pruebas --collect-only -q
git diff --check
cargo fmt --all -- --check
```

Para cada uno de `tools/protocol`, `tools/gunter`, `tools/ditto`,
`tools/voodoo` y `tools/lz2` se corrió además:

```sh
cargo test --locked
```

No se llamó a `just pruebas`: el ejecutable `just` no estaba instalado, y la
colección directa de pytest se detuvo antes en `ModuleNotFoundError: PIL`.
Tampoco estaban visibles `ca65`, `ld65` ni un core libretro en los lugares
consultados. Por eso esta evaluación no afirma que la ROM del árbol observado
arme ni que la tanda esté verde.

## Arquitectura y límites

### Lo mejor resuelto

* **El pipeline tiene capas reconocibles.** RPG Maker se transforma una sola
  vez en datos legibles; render, audio, conversión, ensamblado y emulación
  tienen carpetas propias. Los proyectos que no conocen el juego están
  aislados como herramientas Rust.
* **Los JSON son una fuente de build auditable.** El volcado resuelto evita que
  cada consumidor vuelva a implementar defaults del formato, mientras la vista
  exacta conserva el camino de vuelta byte por byte.
* **Las decisiones de hardware están localizadas.** LoROM, modo 3, banco de
  datos, bloques que no deben cruzar bancos, VRAM, CGRAM y WRAM no aparecen
  como constantes mágicas desconectadas: hay documentación y validaciones
  asociadas.
* **La generación bilateral del protocolo elimina deriva.** La declaración
  TOML produce constantes para Python y ensamblador y, en eventos, la tabla de
  salto. Es una frontera pequeña y verificable entre dos lenguajes.
* **El ensamblado dividido conserva el orden físico.** Que `main.s` incluya los
  subsistemas evita convertir una reorganización textual en una mudanza de ROM
  accidental.

### Concentración y acoplamiento

La principal deuda estructural está en `tools/port/`. Su README declara tres
ciclos de imports y que todavía no se decidió el dueño de varias
responsabilidades. El tamaño medido confirma el costo: el conversor concentra
9.322 líneas y el compilador de eventos 5.515. No es sólo una cuestión estética:
una modificación puede afectar asignación gráfica, serialización, audio,
eventos y disposición de memoria desde un mismo módulo.

El backlog ya contiene las tareas `las-responsabilidades-de-snes-convert.md` y
`las-variables-globales-chocan.md`. Son la dirección correcta. La partición
debería hacerse en dos commits por etapa: primero extracción mecánica con ROM
idéntica, después cambios de interfaces o criterio. Los límites con mejor
retorno probable son:

1. modelo inmutable de entrada y opciones del cartucho;
2. planificación de recursos (bancos, VRAM, CGRAM, audio);
3. emisión de tablas y assets;
4. reporte/diagnósticos del build.

No conviene empezar por una jerarquía abstracta ni por mover helpers sueltos:
eso repartiría el archivo sin eliminar los ciclos ni las globales.

### Datos y tamaño del árbol

En la foto había 120.182 líneas entre Python, Rust y ensamblador: 56.464,
20.808 y 42.910 respectivamente. El archivo versionado más grande era
`data/db/troops.json` (9,1 MB) y `data/` ocupaba 31 MB. Esto es coherente con la
decisión de versionar una representación legible del juego, pero tiene dos
consecuencias:

* las revisiones necesitan distinguir cambios de fuente, cambios derivados y
  cambios deliberados de snapshots;
* cualquier automatización futura debe evitar regenerar masivamente `data/`,
  parches o goldens como efecto colateral.

La política actual ya lo hace bien: cada familia tiene un comando explícito y
el diff es el artefacto a revisar.

## Pruebas y calidad

### Diseño de cobertura

La estrategia es una fortaleza central. Hay redes complementarias:

* pruebas de estado sobre WRAM, VRAM, SRAM, ARAM y registros;
* pruebas visuales contra goldens congeladas;
* comparaciones contra dibujos producidos por herramientas;
* propiedades e ida y vuelta de conversores;
* snes9x contra bsnes para descubrir dependencia de memoria sin inicializar;
* recorrido largo y recorridos alternativos del juego;
* pruebas unitarias de las herramientas Rust.

`pruebas/README.md` funciona además como índice exigido por una prueba: evita
que la documentación de cobertura se despegue silenciosamente de los archivos.
`pruebas/UNTESTED.md` es corto y concreto: enumera caminos reales, por qué no
están cubiertos y qué caso permitiría cubrirlos.

La disciplina de no actualizar goldens automáticamente y de comparar a 15 bits
es correcta. Reduce tanto falsos positivos por representación como el riesgo
de aceptar un cambio visual sólo porque ambos lados de una implementación
compartieron el mismo error.

### Resultado de esta inspección

* `python3 -m compileall -q tools pruebas` terminó bien.
* `git diff --check` terminó bien.
* Los cinco proyectos Rust terminaron sus pruebas con `cargo test --locked`.
* Los cinco proyectos Rust tienen diferencias contra el `rustfmt` de este
  ambiente; el chequeo de formato no está hoy limpio ni figura como puerta del
  repo. Puede ser deriva de versión del formateador, por lo que no se
  reformatearon fuentes como parte de esta evaluación documental.
* `python3 -m pytest pruebas --collect-only -q` no llegó a colectar: faltaba
  Pillow.
* El build y la ejecución de la ROM no se pudieron evaluar en este ambiente.

Esto alcanza para afirmar que no se encontraron errores de sintaxis y que las
herramientas Rust están sanas bajo su toolchain bloqueado. **No alcanza para
afirmar cobertura efectiva ni salud del producto completo.**

### Huecos y riesgos

1. La comparación entre cores es probabilística por diseño: conviene repetirla
   varias veces en una corrida periódica, sin convertir toda la tanda rápida en
   una prueba lenta.
2. Las goldens protegen contra regresión, no contra una implementación
   inicialmente equivocada. El juego manual de las tareas en `testing/` sigue
   siendo una etapa necesaria, no ceremonial.
3. El audio final sigue requiriendo oído humano; las pruebas cubren estructura,
   escritura al DSP, picos y asignación, pero no percepción.
4. `UNTESTED.md` registra caminos sin cobertura. Cada uno debería convertirse
   en tarea cuando el contenido necesario entre a un cartucho, no antes.
5. No hay una puerta automática externa al ambiente del mantenedor. Un commit
   puede llegar a compartirse sin que otro sistema confirme la tanda.

## Inspección detallada de las pruebas actuales

### Inventario y forma

Un recorrido por AST de `pruebas/**/test_*.py` encontró, en esta foto, 113
archivos y 569 funciones cuyo nombre empieza con `test_`; 86 funciones están
parametrizadas y hay 1.418 `assert` sintácticos. Estos números no miden calidad
ni cantidad de casos efectivos —una parametrización produce varios casos y un
helper puede hacer una comprobación sin `assert`—, pero sirven para entender la
forma del conjunto. Se obtuvieron con:

```sh
python3 - <<'PY'
import ast, pathlib
archivos = list(pathlib.Path("pruebas").rglob("test_*.py"))
arboles = [ast.parse(p.read_text()) for p in archivos]
tests = [n for a in arboles for n in ast.walk(a)
         if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
print(len(archivos), len(tests),
      sum(isinstance(n, ast.Assert) for a in arboles for n in ast.walk(a)))
PY
```

La distribución es razonable: `rpgmaker/` prueba semántica del motor,
`abl/` prueba recorridos y contenido, `herramientas/` prueba el pipeline sin
emular y `arnes/` concentra la interacción. No hay una proliferación de mocks:
la mayoría de las comprobaciones atraviesa datos reales, una ROM real o
formatos reales. Es una buena elección para un port cuyo riesgo principal está
en las fronteras.

### Defectos y puntos ciegos concretos

#### Una captura nueva del recorrido puede no comparar nada

`Recorrido.foto` guarda la captura y llama a `_contra_golden`, pero si no existe
la golden correspondiente, `_contra_golden` vuelve sin fallar. Hay una defensa
contra el corrimiento de numeración —falla si encuentra el mismo nombre con
otro número—, pero no hay un manifiesto que distinga «captura pendiente de
bendecir» de «golden borrada o nunca agregada». En ambos casos la prueba queda
verde.

Esto fue una decisión explícita para permitir agregar hitos antes de bendecir
sus imágenes, no un accidente. Aun así, es el punto ciego más importante del
arnés: una prueba de recorrido puede aparentar cobertura visual y estar mirando
sólo su estado. La solución no es obligar a regenerar goldens, sino hacer
explícito el estado:

* una lista versionada de capturas pendientes, que sólo se permita en tareas en
  `testing/`; o
* una opción `--permitir-goldens-faltantes` para el flujo de creación, con la
  tanda normal fallando si falta cualquiera.

También hace falta una comprobación inversa de goldens huérfanas. El índice
actual verifica archivos `test_*.py` contra el README, pero no casos contra
tests ni goldens contra nombres consumidos.

#### Dos pruebas se saltean según artefactos presentes

Los únicos `pytest.skip` directos encontrados están en
`test_fork_mapas.py`: uno si no hay mapas forkeados y otro si un PNG generado
no existe. El segundo está adentro del recorrido de chipsets; el primer archivo
ausente saltea la función completa, incluso si había otros artefactos que sí se
podían revisar. En el ambiente esperado probablemente estén todos, pero el
resultado «verde con skips» no demuestra lo mismo que «verde completo».

Conviene separar las dos intenciones:

* si el artefacto es requisito de la receta normal, su ausencia debe fallar con
  el comando que lo produce;
* si la prueba es realmente opcional, debe llevar un marker estable y la tanda
  oficial debe fallar ante skips inesperados o publicar su cuenta de manera
  visible.

No conviene reemplazar esos skips por `xfail`: la ausencia no es un defecto
conocido del producto, sino que cambia qué se llegó a comprobar.

#### La comparación entre cores tiene detección probabilística

La prueba de snes9x contra bsnes está bien diseñada para memoria sin
inicializar, pero una sola corrida no garantiza encontrarla: el propio archivo
documenta que la basura debe caer en un valor dañino. El conjunto elige casos
de alto valor —movimiento, mensajes, transiciones, escenas y peleas—, aunque no
hay repetición ni semilla registrada como parte de la interfaz de la prueba.

La tanda rápida puede conservar una pasada. Un job periódico debería repetir
este subconjunto, registrar cuántas corridas hizo y conservar la primera semilla
o estado que divergió. «Repitió N veces» debe salir del comando o del reporte,
no quedar como un número permanente en documentación viva.

#### Las pruebas de dibujo comparten parte del oráculo con el productor

Varias pruebas `*_dibujo.py` calculan la imagen esperada con módulos de
`tools/port/` (`titulo`, `pantallas`, `escena`, `batalla`). Esto es útil: compara
la ejecución 65816 contra una implementación Python y localiza diferencias
mejor que una golden. Pero no es una referencia independiente cuando ese mismo
módulo también decide o prepara los datos que entran a la ROM. Una regla
equivocada compartida puede dar verde en ambos lados.

El repositorio ya mitiga esto con goldens y juego manual. La recomendación no
es duplicar todo el renderer, que recrearía el problema de dos implementaciones
que hay que mover juntas. Cada prueba de dibujo debe declarar cuál de estas
cosas es su oráculo:

1. **formato/hardware:** esperado pequeño escrito a mano o derivado de una
   especificación;
2. **datos del juego:** esperado calculado desde el LDB/LMU pero sin llamar la
   función productiva que se quiere probar;
3. **consistencia entre implementaciones:** modelo Python contra ROM, siempre
   complementado por una golden o una observación manual inicial.

`test_batalla_escena_dibujo.py` es un buen ejemplo parcial: reescribe el orden
de dibujo en vez de pedir `escena.orden_de_dibujo`, y explica por qué. Ese
criterio debería aplicarse sólo a las reglas bajo prueba, sin copiar por reflejo
helpers estables de decodificación.

### Fallas de arquitectura del arnés

#### Los tests no son paquetes y ya hubo una colisión real

`pytest.ini` inserta `pruebas/arnes` y `tools` en `sys.path`, mientras los
directorios de pruebas no tienen `__init__.py`. `conftest.py` documenta un fallo
ya ocurrido: dos conftest se cargaron con el mismo nombre y uno tapó al otro.
Además, varios tests importan helpers directamente desde otros módulos
`test_*`, por ejemplo eventos de tropa desde `test_tropa` y `test_victoria`, y
los recorridos encadenan constantes y funciones entre archivos de prueba.

Esto crea dependencias invisibles entre unidades de colección: renombrar un
test, seleccionar sólo una carpeta o introducir dos nombres iguales puede
romper imports sin que haya cambiado el comportamiento probado. La corrección
es mover **sólo los helpers realmente compartidos** a módulos de `arnes/` por
dominio (`batalla`, `menu`, `recorrido`, MSU) e importar esos módulos con un
nombre inequívoco. Convertir cada test en una clase o crear un helper por cada
función de tres líneas sería abstracción innecesaria.

#### `Partida` concentra demasiados dominios

`pruebas/arnes/consola.py` tiene 1.127 líneas y `Partida` conoce arranque,
título, ranuras, SRAM, reloj, input, actores, inventario, mapas, audio, páginas
y medidas de rendimiento. Esta concentración hace cómodo escribir una prueba,
pero también vuelve el arnés una segunda API monolítica del juego: un cambio de
representación puede obligar a tocar tests de dominios no relacionados.

No hace falta esconder `Partida` detrás de interfaces genéricas. Sí conviene
extraer lectores sin estado y fachadas estrechas que ya aparecen como grupos
naturales:

* `EstadoPartida`: switches, variables, actores, inventario y mapa;
* `AudioROM`: directorios de muestras, temas, streams y escrituras esperadas;
* `Guardado`: SRAM, firma y ranuras;
* dejar en `Partida` reloj, consola, input y navegación de alto nivel.

Esas fachadas deben compartir `Consola` y `Simbolos`, no crear consolas propias.
El objetivo es reducir razones de cambio, no aumentar capas durante la ejecución.

#### Hay tres relojes, pero la espera no tiene una interfaz común

Las pruebas distinguen correctamente ticks del juego, cuadros de hardware y
turnos de pelea. Sin embargo, muchos archivos vuelven a implementar bucles
`for range(tope)`, consulta de condición, avance de un cuadro y
`AssertionError`. Los topes llegan a ser grandes en los recorridos, y el mensaje
final depende de cada copia. Hay helpers buenos (`Recorrido.esperar`,
`Pelea.esperar`), pero no alcanzan a pruebas de hardware y transiciones.

La abstracción que falta no es un `wait_until` que oculte el reloj. Deben ser
dos primitivas explícitas:

```python
esperar_ticks(partida, condicion, tope, descripcion)
esperar_cuadros(consola, condicion, tope, descripcion, antes_de_cada=None)
```

La pelea puede envolver la segunda para agregar su modo. Así cada llamada dice
qué tiempo consume, conserva mensajes específicos y evita que una prueba use
por error `Partida.correr` cuando el tick está congelado. Los recorridos, por su
complejidad y autofire, deben conservar su helper especializado.

#### Falta una clasificación ejecutable por costo y requisitos

Las recetas separan por dominio (`rpgmaker`, `abl`, `herramientas`), pero pytest
casi no usa markers para distinguir pruebas rápidas, ROM, dos cores, audio,
assets externos o recorrido largo. Incluso `pruebas-herramientas` depende de
`cartuchos` porque una prueba de bancos lee un build. Esto hace que la unidad de
feedback sea más grande de lo necesario y dificulta expresar una CI pública
sin assets.

Conviene agregar pocos markers de capacidad, no una taxonomía extensa:

* `rom`: necesita cartucho armado y core;
* `dos_cores`: necesita snes9x y bsnes parcheado;
* `corpus`: necesita juego/RTP;
* `lenta`: útil para selección local, nunca como sinónimo de opcional.

Los markers deben verificarse: una prueba que abre una ROM o consulta
`GAME_DIR` sin declararlo debería fallar en un chequeo de arquitectura. Luego
puede existir una tanda hermética de herramientas que no arme cartuchos y otra
integral que no excluya nada.

### Duplicación: cuál sacar y cuál conservar

El análisis por AST sólo encontró un cuerpo de helper exactamente duplicado:
`_msu_del_cartucho` en `test_msu.py` y `test_msu_datos.py`. Esto indica que no
hay copia masiva literal. Los nombres repetidos (`entrar`, `palabra`, `esperar`)
en general representan dominios o receptores distintos y no justifican por sí
solos una abstracción.

Sí hay duplicación conceptual en tres lugares:

1. **Entrada y manejo de pelea.** Varios tests implementan «correr cuadros
   hasta que abra», además de `Pelea.abrir` y helpers de `arnes/batalla.py`.
   Conviene ofrecer una entrada que acepte si se inicia hablando, por página o
   por encuentro, y mantener fuera la preparación específica de cada caso.
2. **Lectura de bytes y palabras.** Hay versiones en `Partida`, `Pelea` y
   pruebas sueltas. La diferencia entre dirección de bus, offset de WRAM y
   símbolo es importante; deben unificarse por tipo de dirección, no en una
   función que adivine qué recibió.
3. **Pantallas de menú.** Ítems, equipo, tienda y End Game repiten «entrar,
   mover cursor, comparar». `arnes/menu.py` ya es el lugar correcto para los
   movimientos comunes; la imagen esperada y las aserciones del dominio deben
   quedar en cada test.

No conviene deduplicar recorridos narrativos sólo porque repiten el camino hasta
un mapa. Sus helpers compartidos (`de_stash_a_ag7`, constantes de ramas) son
útiles para tiempo de ejecución, pero hacen que una modificación al prólogo
pueda alterar muchas pruebas. Cada helper de recorrido debe terminar en un
estado comprobado y documentar qué precondiciones deja; si sólo ahorra líneas y
no establece un contrato, es mejor repetir los pasos relevantes.

### Abstracciones innecesarias o riesgosas

No se encontraron jerarquías de clases, factories genéricas o mocks complejos
que sobren. El riesgo de sobreabstracción está hacia adelante:

* no crear una DSL única para eventos, menús, pelea y recorrido; sus relojes y
  condiciones de terminación son distintos;
* no encapsular las direcciones de memoria hasta hacer invisible si se lee ROM,
  WRAM o ARAM: esa diferencia es parte de lo probado;
* no parametrizar pruebas narrativas sólo para reducir funciones si eso vuelve
  opaco qué rama falló;
* no mover constantes esperadas al código productivo: una sola definición es
  deseable para el protocolo, pero incorrecta para un oráculo independiente.

La abstracción más cuestionable hoy no está en pytest sino en reutilizar tests
como API: `video.py` descubre funciones de `test_recorrido_golden.py` y las
ejecuta con `python -O` para quitar sus asserts. Está explicado y permite no
duplicar jugadas, pero acopla una herramienta de entrega a nombres de tests y al
efecto global de `-O`. A medio plazo, las jugadas deberían ser funciones sin
asserts en un módulo de escenarios; los tests las llaman y verifican, y el video
las llama y graba. Eso conserva un solo recorrido sin convertir el archivo de
pruebas en biblioteca pública.

### Qué está especialmente bien y no debe “limpiarse”

* Una consola nueva por prueba evita contaminación y hace seguro xdist.
* `Cartucho` rechaza builds viejos en vez de producir resultados irrelevantes.
* Los símbolos salen del ensamblador: no hay direcciones de RAM copiadas a
  mano.
* La prueba autouse de capturas idénticas detecta casos que aparentan avanzar y
  no ejercitan nada; sus excepciones están justificadas una por una.
* Las pruebas que dependen de datos del juego primero fijan sus precondiciones
  (tropa, miembros, páginas, acciones), por lo que un cambio del corpus falla
  cerca de la causa.
* La separación entre comparación exacta de tanda y tolerancia del recorrido
  refleja determinismo distinto; unificar sus umbrales perdería información.
* Los casos que leen WRAM y los que miran pixeles son redundancia deliberada y
  valiosa, no duplicación accidental.

### Orden recomendado para mejorar la suite

1. Hacer que toda captura del recorrido tenga golden o una excepción explícita
   y temporal; comprobar también goldens huérfanas.
2. Convertir skips por artefacto ausente en fallos diagnósticos o markers
   verificados, y hacer visibles los skips de la tanda oficial.
3. Mover helpers importados desde `test_*` a `arnes/`, empezando por batalla y
   los recorridos compartidos; no mover helpers usados por un solo archivo.
4. Agregar esperas explícitas por ticks y por cuadros, y migrar sólo los bucles
   que repiten exactamente ese protocolo.
5. Separar de `Partida` lectores de audio y guardado, sin cambiar la API de las
   pruebas en el mismo commit mecánico.
6. Agregar markers mínimos y una tanda sin ROM realmente hermética.
7. Extraer las jugadas que usa `video.py` a escenarios reutilizables.
8. Añadir un job repetido de dos cores y, después, mutation testing focalizado
   en compilación de eventos, condiciones de páginas y aritmética de batalla.

No priorizaría una métrica de cobertura por líneas para el ensamblador: diría
poco sobre caminos de hardware. Mutation testing selectivo o instrumentación de
opcodes ejecutados responderían mejor qué ramas nunca se ejercitan.

## Reproducibilidad y operación

### Estado actual

Hay buenas bases: los cinco proyectos Rust tienen `Cargo.lock`, las
herramientas se consumen desde `PATH`, el build rechaza generados mal ubicados,
los cartuchos declaran su contenido en un punto y la caché incorpora la huella
de los productores.

La brecha está en preparar una máquina nueva. No hay `pyproject.toml`, archivo
de requisitos ni lock del entorno Python; tampoco hay una receta de diagnóstico
que enumere, sin construir, qué falta. El README menciona Python, un core,
cc65 y las herramientas del repo, pero la tanda también necesita módulos como
Pillow y pytest-xdist, además de utilidades de audio para ciertos caminos.

### Recomendación prioritaria

Agregar un **preflight versionado** y llamarlo antes del trabajo caro. Debe:

* comprobar versión compatible de Python y módulos importables;
* comprobar `ca65`, `ld65`, herramientas Rust instaladas y cores requeridos;
* comprobar `ABL_GAME_DIR` y `ABL_RTP_DIR` sólo para las recetas que los usan;
* explicar el comando de instalación o la variable que falta;
* no codificar rutas propias de un ambiente;
* poder correrse separado, por ejemplo como `just diagnostico`.

Después, declarar dependencias Python con versiones o rangos deliberados. Un
lock reproducible es preferible, pero incluso un manifiesto mínimo sería una
mejora sustancial. Hay que conservar la decisión de que los scripts del juego
no invoquen Cargo durante una tanda.

## Documentación y proceso

La documentación está por encima de lo habitual:

* separa estado, decisiones vigentes, divergencias, estudios fechados y docs
  que deben reflejar el presente;
* explica dónde vive cada verdad y evita duplicar métricas cambiantes;
* los commits recientes son pequeños, descriptivos y enlazan tareas;
* el flujo `todo` → `doing` → `testing` → `done` reconoce explícitamente la
  validación manual;
* el `git blame` mecánico y el corte de `main.s` tienen instrucciones
  reproducibles.

El costo es una barrera de entrada alta: `AGENTS.md` contiene mucho conocimiento
operativo esencial y varias reglas nacidas de incidentes. No recomiendo
resumirlo perdiendo precisión. Sí conviene que un preflight y los comandos
codifiquen todo lo verificable; el documento debería conservar sólo decisiones
y trampas que una herramienta no puede expresar.

En la foto había tareas en las cuatro fases activas y un backlog amplio. Eso
demuestra continuidad, pero también hace importante mantener la regla actual:
una tarea tomada se marca antes de tocar código y las tareas terminadas que
requieren juego no se presentan como completamente validadas.

## Seguridad, procedencia y distribución

No se encontraron descargas o ejecución de red escondidas en el camino
inspeccionado; las dependencias Rust están bloqueadas y los assets externos no
se guardan junto al juego original. Aun así, este punto no fue una auditoría de
seguridad del contenido ni de cada dependencia.

Riesgos a resolver antes de publicar o aceptar contribuciones amplias:

* **Licencia:** no hay `LICENSE`/`COPYING`; por omisión, terceros no tienen una
  concesión clara para reutilizar el código.
* **Procedencia:** `data/`, `parches/` y las goldens pueden contener material
  derivado. Hace falta una política explícita que diga qué se puede distribuir,
  no sólo que el juego y el RTP originales están fuera del repo.
* **Cadena de suministro:** cc65 y los cores son piezas ejecutables externas.
  El ambiente documenta cómo se obtuvieron, pero para reproducibilidad fuerte
  convendría fijar revisiones y publicar huellas verificables o una receta de
  construcción controlada.
* **CI con secretos/assets:** una futura CI no debería subir el corpus privado
  ni snapshots producidos en fallos como artefactos públicos por omisión.

## Prioridades propuestas

### P0 — hacer verificable una máquina nueva

1. Crear el preflight y ejecutarlo al comienzo de las recetas relevantes.
2. Declarar las dependencias Python.
3. Documentar con precisión la instalación del runner (`just`) y de los cores.
4. Ejecutar desde un ambiente limpio: build, tanda completa, repetición de
   cores y `SIN_CACHE=1`, conservando los comandos y resultados.

### P1 — bajar el radio de impacto

1. Resolver las responsabilidades de `snes_convert` con extracciones mecánicas
   verificadas por identidad de ROM.
2. Eliminar o encapsular las globales que chocan antes de paralelizar más el
   conversor.
3. Introducir fronteras de datos explícitas entre planificación y emisión.
4. Mantener cada cambio de criterio separado de la mudanza mecánica.

### P1 — automatización externa

1. Una CI pública o privada para `compileall`, `git diff --check` y los cinco
   proyectos Rust, que no requieren el juego.
   Esa CI debería fijar la versión de `rustfmt` antes de aplicar su formato.
2. Una CI privada o job local reproducible para armar cartuchos y correr la
   tanda con los assets necesarios.
3. Un job periódico que repita la comparación de cores y reporte inestabilidad.

### P2 — gobernanza

1. Elegir licencia para el código propio.
2. Documentar qué artefactos derivados pueden redistribuirse.
3. Definir una política de actualización de dependencias y cores fijados.
4. Convertir los huecos de `UNTESTED.md` en tareas sólo cuando sean ejecutables.

## Conclusión

El proyecto no necesita más capas de proceso: ya tiene un sistema de trabajo
coherente y defensas profundas. Su problema principal es que buena parte de esa
calidad sólo puede demostrarse dentro de un ambiente acumulado. La inversión
con mayor retorno es convertir ese ambiente implícito en requisitos
diagnosticables y reproducibles. Hecho eso, el siguiente salto es reducir el
radio de impacto del conversor sin alterar bytes. El resto —más contenido,
optimizaciones y cobertura adicional— se beneficiará directamente de esas dos
mejoras.
