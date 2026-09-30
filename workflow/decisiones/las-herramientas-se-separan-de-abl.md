# Las herramientas se separan de ABL, en dos repos

De taro, el 2026-09-28, al leer el research
`docs/research/el-mapa-de-las-herramientas-de-python.md` (Quebracho), que
tiene el plan de seis pasos y las preguntas con sus opciones.

- **El plan es el de seis pasos del research.**
- **Se separa antes del juego golden**, que es la opción b) de la pregunta 1:
  el repo de herramientas sale sin pruebas de ROM propias, y las corre el
  repo de ABL hasta que exista el juego golden. El research recomendaba
  esperar al juego golden para el corte; taro eligió no esperar.
- **El lado agnóstico es un solo repo**: las herramientas de RM2k, el
  conversor y el motor de SNES juntos.
- **El repo de herramientas va en inglés**, como los proyectos de Rust.
  Cuándo se traduce —antes del corte o al reescribir cada parte— no se
  decidió todavía.
- **Los límites del motor medidos sobre ABL se quedan fijos** (`ITEMS_N`,
  `ENC_RATE`, `FADE_TOTAL`, los anchos…), con un comentario que diga
  que se midieron contra A Blurred Line. En una segunda etapa pasan a ser
  parámetros, y los mide una herramienta sobre el juego ya volcado a JSON.
  La idea de taro es que **la estimación no se separe de la implementación**:
  si un binario es el que decide cómo repartir paletas, la medición sale de
  ese mismo binario, y no de un "medir-juego" aparte que duplique la regla.
  Es "Parse, Don't Validate" aplicado a algo más complejo.
- **La historia de git se conserva si es gratis.** Si cuesta, se discute.
- **Cómo consume ABL a las herramientas**: primero, todo en el mismo repo
  con dos raíces (el paso 5 del plan). Después, lo estable como ejecutables
  en el PATH. **Submódulos de git, nunca**: a taro no le gustan. Además, hoy
  no hay una buena forma de asociar un mismo ambiente de trabajo a dos repos.
- **El motor viaja con las herramientas, con la misma versión.** Lo decidió
  taro el 2026-09-29. Conceptualmente es el RPG_RT.exe de RM2k, con una
  diferencia: no se puede distribuir ensamblado, porque se ensambla junto con
  los `.inc` de cada juego, que definen constantes y flags de las que depende
  el código. Por eso se distribuye como fuente adentro del paquete de la
  suite: como archivos de datos del paquete y, cuando el que ensambla sea de
  Rust, embebido en ese binario, que lo escribe al directorio de build antes
  de llamar a `ca65`. La idea de taro es que un `pacman -S` alcance, sin git
  ni descargas.
  - **No se versiona aparte:** el conversor y el motor comparten un contrato
    (el formato de los `.inc` y los opcodes de `tools/snes/protocol/`), así que un
    motor viejo necesita también el conversor de su época.
  - **El juego declara con qué versión de la suite se arma**, en su archivo de
    proyecto (el del paso 3), y las herramientas se niegan a armar con otra.
    Es lo que ata las goldens de ABL a una versión del motor.
  - **Un administrador de versiones al estilo nvm o rustup queda para cuando
    haya más de un juego**, y va a instalar suites enteras, no runtimes
    sueltos.
  - Lo que un juego quiera apartarse de RM2k sigue yendo por flags, que
    pasan al archivo de proyecto.
- **El motor se llama runtime y se muda a `tools/runtime/`; `rom/` pasa a
  ser la raíz de A Blurred Line**, con `data/`, `parches/`, `pruebas/` y
  `build/`. Lo decidió taro el 2026-09-29: se distingue el runtime genérico
  del proyecto. ABL no necesita los `.s`, y el runtime no necesita los
  `.inc` de gráficos ni de audio. La raíz queda con `rom/`, `tools/`,
  `docs/` y `workflow/`. **El orden:** primero un `tools/justfile` con las
  recetas de las herramientas, después el paso 2 del plan (un solo lugar que
  sabe dónde está cada cosa), y recién ahí la mudanza, en un commit mecánico
  con las ROMs byte por byte iguales.
- **Instalar es de las herramientas; verificar es de ABL.** Charlado con
  taro el 2026-09-29. `herramientas` y `herramientas-locales` van en
  `tools/justfile`: instalar desde el fuente pide saber dónde está cada cosa
  en `tools/`, que es lo que ABL no puede saber. Es el `make install` de un
  proyecto, o el `npm link`. Lo que ABL necesita es **saber que tiene lo que
  le hace falta, en la versión que declara**: una receta suya, por ejemplo
  `verificar-herramientas`, cuando exista el archivo de proyecto con la
  versión. La guarda que frena a un worktree sin su `bin/` es el primer
  pedazo.
- **`rm2k-render` es el dueño de todo lo que es dibujar gráficos de RPG
  Maker, sin saber nada de la SNES.** Charlado con taro el 2026-09-29. Hoy
  dibuja las capas de un mapa y los ChipSets; va a crecer con los CharSets
  (poses, translúcidos), las animaciones de pelea, los enemigos y fondos de
  batalla, las FaceSets, el System y el cartel de `ShowPicture`, que hoy
  dibuja el conversor en Python. Comparten una base —cargar una imagen de
  RM2k con su color clave, mezclar por alfa, recortar hojas— que ya está en
  su `picture.rs`. No se parte en un proyecto por asset: eso pediría otro
  crate para la base, y serían varios chicos donde alcanza uno. Su límite es
  la capa: nada de paletas de 16 colores ni de tiles de 8x8, que son del
  Adeleine y de `voodoo`.
- **El asignador se llama Adeleine.** De taro, el 2026-09-29, al charlar si
  tenía sentido separarlo de Voodoo (lo tiene: es la regla de AGENTS.md de
  que Voodoo no decide colores). Es un crate propio, `tools/snes/adeleine/`,
  al lado de Voodoo y no adentro, desde el 2026-09-29; el conversor lo
  llama por `tools/port/adeleine.py` y deja lo que decidió en
  `rom/build/<cartucho>/adeleine/`.
- **ABL sólo conoce ejecutables del PATH, no `tools/`.** Es la idea de taro
  para el primer paso: el `justfile` no sabe que existe Python, y los `.py`
  que se ejecutan pasan a ser ejecutables de verdad, con hashbang y
  `chmod +x`. Una prueba simple con grep hace fallar la tanda si algo del
  lado de ABL nombra la ruta de `tools/`.
- **Los comentarios del motor que nombran a ABL se quedan por ahora**, por
  cuidado. Tampoco se toca todavía lo que se emite al `.inc` ni los `help=`.

Lo que quedó abierto:

- **`cartuchos.py`** (pregunta 6): taro no ve una responsabilidad clara en
  ese archivo. Mezcla datos de ABL, que podrían ir a un `.toml`, con la
  clave del caché y cosas de pruebas. Le parece que no debería existir:
  lo reemplazarían un par de recetas del `justfile`, los datos en un
  `.toml`, y una clave de caché que no dependa del hash de un binario sino
  de su versión (por ejemplo, que cada binario la emita, o guardar
  `gunter --version`). En la misma línea, `tiles_bin.py` y `comprimir.py`
  parecen envoltorios de `voodoo` y `lz2` sin mucho sentido. Queda por
  decidir si se sube a la raíz y después se desarma, o al revés.
- **`decisiones/` y `divergencias/`** (pregunta 8): algunas son de ABL y
  otras no. Hay que revisarlas una por una.
