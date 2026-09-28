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
