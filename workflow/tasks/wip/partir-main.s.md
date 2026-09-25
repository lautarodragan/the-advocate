---
name: "Partir main.s"
description: "main.s, que es un solo archivo de más de treinta mil líneas, en varios"
---

**Partir `rom/src/main.s`**, que son más de treinta mil líneas en un
archivo —cuántas, `wc -l`—.

Probado en chico —una sección afuera con `.include`, mismo md5—; 
las fronteras ya existen: marcas de sección y `.proc`. 

Tres trampas: 
- el `.segment` cruza el `.include`, 
- las etiquetas anónimas se resuelven textualmente, 
- y reordenar sí cambia la ROM aunque partir no.

## Plan

Escrito el 2026-09-25 sobre `43bd1aa`, para que lo critique un agente y lo
ejecute otro. Lo medido está medido ese día sobre ese commit; los números de
línea no se copian acá porque se mueven: los imprime
`python3 tools/ensamblado/partir_main.py --ver`.

### Lo medido

* **Partir no cambia un byte.** Con `tools/ensamblado/partir_main.py` (está en
  esta rama), las tres ROMs —`release`, `test-main` y `test-special`— y sus
  tres `.sym` salen byte por byte iguales. Se armaron con `ensamblar.py` contra
  los mismos `mapdata.inc`/`musicdata.inc`/`memoria.cfg` de cada cartucho, así
  que el conversor queda afuera de la comparación a propósito: no lee `main.s`.
* **El `.dbg` cambia y no importa.** Cambian sus filas `file` (una por archivo)
  y `line`; las `sym`, sin sus referencias a líneas, son iguales. Ya hoy no es
  reproducible —guarda la ruta absoluta y el mtime de cada fuente— y su único
  lector es `ensamblar.simbolos()`, que saca de ahí el `.sym`, que es lo que
  leen las pruebas. Un depurador que lo use va a mostrar archivo y línea
  nuevos, que es lo que se quiere.
* **Las tres trampas de la tarea no son de corte sino de lectura y de
  reorden.** `.include` es texto para `ca65`, así que nada se reinicia en el
  borde de un archivo. Probado cortando a propósito donde peor cae:
  - entre un `bcc :+` y su `:`, **adentro** de `.proc elegir_con_filtro`: ROM igual;
  - adentro de un `.proc`, justo después de un `.a16` y antes de un `lda #`:
    ROM igual —el ancho de registro cruza el `.include`—;
  - los archivos del plan que empiezan sin `.segment` (55) heredan el del
    anterior: ROM igual.

  El script igual **se niega** a cortar adentro de un bloque (`.proc`,
  `.macro`, `.if`…) o entre una anónima y su uso, porque eso sí es ilegible.
* **Reordenar sí cambia la ROM**, como decía la tarea. Intercambiar
  `control.s` con `spc700.s` —dos vecinos del banco 0— cambia unos doscientos
  bytes y una docena de símbolos; mover `poner_switch` a `variables.s`, unos
  mil novecientos bytes y un centenar de símbolos. Por eso esta pasada no
  mueve nada.
* **Un `.segment` redundante al principio de cada archivo no cambia nada**:
  agregado a los 55 que no lo tienen, ROM y `.sym` iguales.
* **Límites de `ca65`**: 41 niveles de `.include` anidados ensamblan sin
  quejarse (el plan usa uno). Un `.include` hecho desde un subdirectorio se
  busca primero en el directorio del archivo que incluye, no en el de
  `main.s`.
* **Tres pruebas se rompen con el corte**, y las tres por leer `main.s` como
  texto: las dos de `test_sustituciones.py` y
  `test_ningun_opcode_de_la_rom_quedo_sin_declarar`. Con el cambio de
  herramientas de abajo, las catorce de esos tres archivos
  (`test_sustituciones`, `test_protocolo`, `test_ensamblar`) pasan sobre el
  árbol partido. `just pruebas` entero **no** se corrió: había otros dos
  agentes usando la CPU.
* **`git blame`**, medido en un clon con el corte commiteado, comparando
  línea por línea el blame de cada archivo nuevo contra el del `main.s` de
  antes:

  | cómo | qué contesta |
  |---|---|
  | `git blame` | todo "fue el corte" |
  | `--ignore-rev <corte>` | todo "fue el corte" igual: no hay un archivo con el mismo nombre en el padre adonde pasarle la culpa |
  | `-C`, `-C -C`, `-C -C -C` | casi todo "fue el corte": sólo encuentra el final de `main.s` |
  | `-C --minimal` | ya no culpa al corte, pero asigna mal media ROM |
  | **`-C --diff-algorithm=histogram`** | **todas las líneas con el mismo commit que da el `main.s` de antes con las mismas opciones** |

  El porqué de la diferencia: con Myers, las líneas repetidas —`rts`,
  `.endproc`, `;`, blancos— se aparean con las primeras que encuentra en un
  archivo de treinta mil líneas, y los trozos quedan más cortos que el mínimo
  de `-C`. Histogram ancla en las líneas únicas. `git -c
  diff.algorithm=histogram blame -C` da lo mismo, pero como `.git/config` es
  de sólo lectura acá, eso lo tendría que configurar taro del lado del host.
  Y `-C` con histogram ve **más atrás** que el blame de hoy sobre `main.s`:
  atraviesa también las mudanzas viejas adentro del archivo, como la de la
  tienda al banco 1.

### La partición

Un archivo por tramo contiguo, en el orden de hoy. `main.s` queda con su
prólogo (`.p816`, `.smart`), los `.include` en orden, y el tramo de los
generados escrito tal cual: los dos `.inc` de `tools/protocol/`, `musicdata.inc`
y `mapdata.inc`, y las dos constantes que dependen del conversor
(`VENTANA_LINEAS_TEXTO`, `TEXTO_BUF_BYTES`). Así `main.s` muestra **dónde
entran los datos del cartucho**, que es lo único que no es un subsistema.

El ancla es lo que busca el script: el corte cae en la marca de sección, o al
principio del comentario que precede al `.proc`.

| archivo | segmento | ancla | qué hay |
|---|---|---|---|
| `registros.s` | — | `INIDISP =` | puertos, PPU, DMA y HDMA |
| `ram_lejana.s` | — | marca "la RAM del banco 1" | el mapa de la RAM lejana, habilidades, ventana, tiras, destellos |
| *(queda en `main.s`)* | — | `.include "event_opcodes.inc"` | los generados y dos constantes |
| `pagina_cero.s` | ZEROPAGE | `.segment "ZEROPAGE"` | toda la página cero |
| `arranque.s` | CODE | `.proc reset` | `reset`, NMI, vblank, puesta a cero del PPU, `ppu_init` y el pedacito de TABLAS |
| `cargar_mapa.s` | CODE | `.proc cargar_mapa_sin_eventos` | volcado del mapa, `eventos_tick`, fundidos |
| `paginas_de_eventos.s` | CODE | `.proc leer_pagina` | qué página corre, paralelos, ranuras, condiciones, esperas |
| `interprete.s` | CODE | `.proc correr_codigo` | el bucle del bytecode y `pelea_arrancar` |
| `variables.s` | CODE | `.proc var_apuntar` | variables, azar, elección |
| `tinte.s` | CODE | `.proc tabla_canal` | tinte, saturación, subida de paletas |
| `grupo.s` | CODE | `.proc en_el_grupo` | el grupo y el gráfico del héroe |
| `ruta_del_heroe.s` | CODE | `.proc paso_de_ruta` | la ruta forzada del héroe, `hay_rutas`, `poner_switch` |
| `cargar_graficos.s` | CODE | `.proc dma_origen` | `load_map`, sprites, OAM, poses en caliente, capa de encima, NPC |
| `rutas_de_eventos.s` | CODE | `.proc ruta_para_evento` | las rutas forzadas de los eventos |
| `tecla_de_accion.s` | CODE | `.proc evento_en_celda` | la tecla de acción y el contacto |
| `destello_de_personaje.s` | CODE | `.proc flash_empezar` | `FlashSprite` |
| `eventos_caminando.s` | CODE | `.proc animar_ruta_ev` | los eventos que se dibujan caminando |
| `partida.s` | CODE | marca "guardar y cargar la partida" | la SRAM |
| `titulo.s` | CODE | marca "la pantalla de título" | |
| `ranuras.s` | CODE | marca "la pantalla de ranuras" | ranuras y su texto por actor |
| `menu.s` | CODE | marca "el menú de pausa" | menú, `ChangeSpriteAssociation`, elección de actor |
| `pantallas_de_texto.s` | CODE | marca "las pantallas de texto" | `pant_*` |
| `batalla_puentes.s` | CODE | marca "la batalla" | los puentes `ba_t_*` del banco 0 y el audio de la pelea |
| `lluvia.s` | CODE | marca "la lluvia" | |
| `msu1.s` | CODE | marca "el MSU-1" | |
| `paquete_de_audio.s` | CODE | marca "el paquete de audio de cada mapa" | ARAM, muestras, temas |
| `efectos_de_sonido.s` | CODE | marca "los efectos de sonido" | con las dos macros `SE_*_VOZ` |
| `items.s` | CODE | marca "la pantalla de ítems" | y `volver_al_mapa`/`volver_de_batalla` |
| `quietos_que_animan.s` | CODE | marca "los eventos quietos que animan igual" | y `sonido_de_codigo`, `sonido_tocar`, `destello_de_codigo` |
| `imagen.s` | CODE | marca "el cartel del ShowPicture" | |
| `animacion_de_batalla.s` | CODE | marca "la animación de batalla" | la animación y su dibujo |
| `giro_hacia_el_heroe.s` | CODE | marca "el giro hacia el héroe" | |
| `npcs.s` | CODE | `.proc subir_pose_npc` | poses y orden de los NPC |
| `celdas.s` | CODE | `.proc celda_vecina_existe` | `puede_celda` y sus vecinas |
| `destello_de_pantalla.s` | CODE | marca "el destello de pantalla" | |
| `camara.s` | CODE | marca "la cámara corrida sin el héroe" | paneo, sacudida, `follow_camera` |
| `ventana_del_mapa.s` | CODE | marca "la ventana móvil del mapa" | el streaming del tilemap |
| `mensajes.s` | CODE | marca "la ventana de mensaje" | ventana y compositor de texto |
| `vblank.s` | CODE | marca "lo que va sí o sí dentro del vblank" | `flush_video` y las tiras |
| `animacion_del_chipset.s` | CODE | marca "la animación del ChipSet" | |
| `heroe.s` | CODE | `PASS_DOWN =` | caminar, pasabilidad, animación de caminata |
| `cronometro.s` | CODE | marca "el cronómetro" | |
| `oam.s` | CODE | marca "armado de OAM" | `build_oam`, saltos, `place_*`, `emit_object` |
| `control.s` | CODE | marca "lectura del control" | `read_pad` |
| `spc700.s` | CODE | marca "carga al SPC700" | la carga por el IPL |
| `ram_baja.s` | BSS | `.segment "BSS"` | toda la BSS |
| `musica.s` | CODE | `.proc irq_musica` | el reproductor del stream |
| `banco1.s` | FAR | `.segment "FAR"` | el encabezado del banco 1 y lo que bajó del banco 0 |
| `nivel.s` | FAR | marca "el nivel y el máximo en el menú" | |
| `medicina.s` | FAR | marca "una medicina desde el menú" | |
| `equipo_desde_eventos.s` | FAR | marca "el equipo y las habilidades desde un evento" | y `menu_hp_escribir` |
| `batalla.s` | FAR | `.proc ba_azar` | aritmética, armar la pelea, golpe, turno, pantalla |
| `batalla_items.s` | FAR | marca "usar un ítem en la pelea" | |
| `batalla_habilidades.s` | FAR | marca "ejecutar una habilidad" | ejecutar y listar habilidades |
| `batalla_lazo.s` | FAR | marca "el lazo de la pelea" | y la experiencia |
| `batalla_tropa.s` | FAR | marca "las páginas de evento de la tropa" | |
| `batalla_escena.s` | FAR | marca "la escena de la pelea" | |
| `batalla_correr.s` | FAR | `.proc batalla_correr` | la pelea entera, con su lazo de cuadros |
| `banco_de_la_pantalla.s` | FAR | marca "el banco de la pantalla, también fuera del banco 0" | sube la fuente, el tilemap y las paletas de todas las pantallas de texto |
| `encuentros.s` | FAR | marca "los encuentros al azar, fuera del banco 0" | |
| `pantalla_de_equipo.s` | FAR | marca "el equipo y la tienda, fuera del banco 0" | |
| `tienda.s` | FAR | marca "la tienda" | |
| `cabecera.s` | FAR, HEADER, VECTORS | `.align $8000` | el cierre del banco 1, cabecera y vectores |

**Por qué ésta.** El criterio es el de la tarea: que un humano encuentre algo
por el nombre del archivo, y que dos ramas de subsistemas distintos no toquen
el mismo. Casi todos los cortes caen en las marcas `; --- … ---` que ya
existen, que son las fronteras que el propio código declara; los que caen en
un `.proc` son donde una marca junta cosas que no tienen que ver —"la
saturación del tinte" termina con el grupo, la ruta del héroe y `load_map`;
"el giro hacia el héroe" termina con las poses de NPC y `puede_celda`—. Dos
marcas no sirven de ancla porque están repetidas ("el héroe", "el PPU", "el
compositor de texto"): de ahí `PASS_DOWN =` y `.proc reset`. La granularidad
es fina a propósito: juntar dos vecinos es borrar un ancla, separarlos después
es más caro. Con la historia de la última semana (líneas vivas por commit, con
`git blame` sobre `43bd1aa`), lo que más se toca es `interprete.s` de lejos,
después `ram_lejana.s`, `cargar_mapa.s` y `arranque.s`: el corte no resuelve
el choque en `interprete.s` —ver la segunda etapa—.

**Plano, sin subdirectorios.** Funcionan —probado—, pero un `.include`
adentro de un subdirectorio se resuelve contra ese subdirectorio, y el orden
lo sigue dando la lista de `main.s`: carpetas por subsistema sugerirían una
independencia que no hay. Los prefijos (`batalla_*`) agrupan lo mismo en `ls`.

**Extensión `.s`.** `rom/src/` hoy tiene una regla implícita: `.inc` es
generado (los dos de `tools/protocol/`, y `mapdata.inc`/`musicdata.inc` en
`rom/build/`). `.s` para lo escrito a mano la mantiene. El chequeo de
`ensamblar.py` es **por nombre** (`GENERADOS`), no por extensión, así que los
archivos nuevos no lo disparan con ninguna de las dos; lo que protege esa
regla —que un archivo de `rom/src/` tape uno del `-I`— sigue igual, porque
ninguno se llama como un generado. Lo que la extensión `.s` puede sugerir es
que cada uno se ensambla solo, como en un proyecto de `ca65` con varios
objetos: no, son todos texto de un solo `main.s`, y eso lo dice el comentario
de `main.s` en el commit de prosa.

### Lo que depende de que haya un solo archivo

* **`cartuchos.huella()`** hashea `rom/src/main.s` solamente. Partido, editar
  `tienda.s` dejaría el cartucho "al día" y las pruebas correrían contra una
  ROM vieja **sin avisar**. Cambia a todo `rom/src/` recursivo —no a lo que
  `main.s` incluye: un archivo nuevo se agrega y se incluye en el mismo
  cambio—. De paso cubre `event_opcodes.inc` y `music_opcodes.inc`, que hoy
  sólo están cubiertos de rebote por los `.py` generados junto con ellos.
* **Las pruebas que leen el fuente**: `test_sustituciones.py` (`SUB_MAX`,
  `sub_clave`, `sub_valor`) y `test_protocolo.py` (los `#OP_*` usados, y que
  ninguno esté declarado a mano). Pasan a leer
  `ensamblar.texto_de_la_fuente(MAIN)`. Ojo con la tentación de leer
  `rom/src/*`: incluiría `event_opcodes.inc`, y la prueba de "ningún `OP_`
  declarado a mano en la ROM" daría rojo por los del generado. Por eso la
  función nueva sigue los `.include` que terminan en `.s` y nada más.
* **`ensamblar.py`** no necesita cambiar para armar: `main.s` sigue siendo la
  entrada. Suma las dos funciones:

      INCLUDE = re.compile(r'^\s*\.include\s+"([^"]+)"', re.M)

      def fuentes(principal):
          """`principal` y los `.s` que incluye, en el orden de `ca65`."""
          directorio = os.path.dirname(os.path.abspath(principal))
          rutas = [principal]
          with open(principal, encoding="utf-8") as archivo:
              texto = archivo.read()
          for nombre in INCLUDE.findall(texto):
              if nombre.endswith(".s"):
                  rutas += fuentes(os.path.join(directorio, nombre))
          return rutas

  y `texto_de_la_fuente(principal)`, que las pega. En `huella()`:

      partes = (sorted(r for r in glob.glob(os.path.join(RAIZ, "rom", "src", "**"),
                                            recursive=True) if os.path.isfile(r))
                + ensamblar.binarios() + …)

  Probado sobre el árbol partido. Conviene además **una prueba** de que todo
  lo que devuelve `fuentes()` está en la huella —sacando la lista de partes a
  una función—, porque si no, que la huella cubra los archivos nuevos es un
  camino que ninguna prueba ejecuta.
* **Opcional**: el chequeo de `GENERADOS` podría pasar a ser "ningún archivo
  del directorio `-I` existe también en `rom/src/`", que no depende de una
  lista. No hace falta para el corte.
* **`main.s:NNNN`** aparece una sola vez en todo el árbol: `AGENTS.md`, "La
  trampa que más veces mordió", que cita `main.s:7997` y **ya estaba vieja**:
  el `cmp #0` de la ranura 0 está en `cuadro_de_ruta_ev`. Se cita por símbolo.
* **"`símbolo` en main.s"** aparece en unos cuarenta archivos fuera de
  `rom/src/` (`grep -rln 'main\.s' --exclude-dir=.git --exclude-dir=build .`).
  Los que describen la estructura sí cambian: `README.md` (el árbol de
  archivos del audio), `docs/port/pipeline.md`, `docs/port/events.md`, los
  comentarios del `justfile` sobre `ensamblar`, el docstring de
  `ensamblar.py` ("al lado de `main.s`" pasa a "en `rom/src/`") y dos
  párrafos de `AGENTS.md` —`huella()` en "Mientras corren las pruebas…" y
  la trampa del `.inc` generado—. Los demás citan un **símbolo**, que es el
  ancla que no envejece: ver la duda 9.
* **Adentro de `rom/src/`**: los comentarios que ubican algo por posición
  ("ver allá abajo", "al final del archivo") y cuyo destino quedó en otro
  archivo. `partir_main.py --colgadas` da la lista de los que citan un
  símbolo; es una lista de trabajo con falsos positivos ("la celda de
  arriba"), y no ve los que no citan nada: hay que completarla con
  `grep -n 'archivo\|allá abajo\|más arriba' rom/src/*.s`, mirando sobre todo
  los primeros y últimos párrafos de cada archivo. El caso seguro es
  `batalla_puentes.s`: "ver `batalla_correr`, al final del archivo".
* **El comentario de arriba de `main.s`** dice "PoC de audio: reproduce un
  tema en loop, sin dibujar nada": es de cuando esto era la prueba de audio.
  Es el lugar natural para explicar que el orden de los `.include` es el
  orden en la ROM, y que cada archivo hereda el segmento y los anchos del
  anterior.

### Commits, en orden

1. **Este**, ya en la rama: `tools/ensamblado/partir_main.py` y el plan. El
   script no hace nada hasta que se lo corre.
2. **Herramientas**: `fuentes()`/`texto_de_la_fuente()`, `huella()` sobre
   `rom/src/`, las dos pruebas y la prueba nueva de la huella. Sobre el
   `main.s` entero `fuentes()` devuelve `[main.s]`, así que este commit se
   verifica solo: `just pruebas` en verde. Cambia la huella, así que todos
   los cartuchos se rearman; las ROMs tienen que salir iguales porque no se
   tocó ningún fuente.
3. **El corte**: `python3 tools/ensamblado/partir_main.py`, `git add -A
   rom/src`, y nada más en ese commit —ni una línea de prosa—. Que sea sólo
   la salida del script es lo que lo hace revisable: el que revisa lo
   reproduce en vez de leer sesenta mil líneas de diff (ver abajo). Es
   también lo que mejor le sirve a `blame -C`: un commit que sólo mueve.
4. **Opcional, mecánico**: un `.segment` explícito al principio de cada
   archivo que no lo tenga (ver la duda 5). ROM igual, medido.
5. **Prosa**: todo lo de la sección anterior. Lo guía el diff de 3, y no lo
   verifica nada más que leerlo. **Y borra `partir_main.py`** (corrección D
   del crítico): una rama vieja lo saca de
   `git show <corte>^:tools/ensamblado/partir_main.py`, que es la versión
   exacta que produjo el corte.

El script se puede volver a correr si `main` se movió entre que se planeó y
que se ejecuta: busca anclas y no números de línea. Si un ancla desapareció o
se duplicó, se niega, y se ajusta la tabla `TRAMOS`. Antes de commitear,
`--ver` muestra la primera línea de cada archivo, y conviene mirarlas: un
corte que empiece a mitad de un comentario es un ancla que quedó mal.

### Cómo se verifica

Para el commit 3, las tres cosas, y el mensaje dice cuáles se corrieron:

1. **Reproducible**: desde un árbol limpio en el padre del corte,
   `python3 tools/ensamblado/partir_main.py && git add -A rom/src && git diff --cached --stat <corte>`
   no muestra nada. (Sin el `git add`, `git diff` no ve los archivos nuevos
   sin seguir y da un falso rojo: corrección A del crítico.) Es la verificación de que el commit es la salida del script
   y nada más, y la que puede hacer cualquiera sin leer el diff.
2. **Byte por byte**: antes del corte, `just cartuchos` y copiar
   `rom/build/release/abl.sfc`, `rom/build/tests/{main,special}/prueba.sfc` y
   sus `.sym` a un directorio del scratchpad; después, `just cartuchos` otra
   vez y `cmp` de los seis. **Mirar que de verdad se rearmaron** —que
   `cartuchos` imprima las tres líneas de `ensamblar` o que cambien los
   `sello.txt`—: si no se rearman, se comparan los viejos consigo mismos y da
   igual siempre. Sin el conversor, más rápido e igual de concluyente: armar
   con `ensamblar.py` el árbol de antes y el de después contra los mismos
   generados de `rom/build/*/`, que es lo que se hizo para este plan.
3. **`just pruebas`** en verde, y la tanda: con la ROM idéntica no puede
   cambiar ninguna golden, así que cualquier rojo es de herramientas o
   heredado.

Los `.dbg` no se comparan, por lo dicho arriba.

### `git blame`

**No va a `.git-blame-ignore-revs`.** El criterio de `AGENTS.md` lo cumple
—sin efecto, demostrado—, pero medido no sirve: los archivos nuevos siguen
diciendo "fue el corte", porque ignorar un commit le pasa la culpa al mismo
archivo en el padre y acá no existe; y a `main.s` lo empeora, porque cada
`.include` nuevo aparece atribuido a un commit viejo cualquiera. Y como la
config del repo ya tiene `blame.ignoreRevsFile`, el daño sería por omisión.

Lo que sí va, en el commit de prosa, a "`git blame` y los cambios mecánicos"
de `AGENTS.md`: que para `rom/src/` es **`git blame -C
--diff-algorithm=histogram <archivo>`**, con lo medido. `git log --follow` no
cruza el corte —ningún archivo nuevo es la mitad de `main.s`— y `git log -S`
sigue funcionando igual, porque busca por contenido en todos los archivos.

### Las ramas abiertas

Un merge directo de una rama vieja con el corte da un conflicto en `main.s`
entero: git ve un archivo de treinta mil líneas reemplazado por uno de cien.
La receta, probada en un clon con una rama que cambiaba una línea de la
tienda y agregaba un `.proc` entre dos tramos:

    CORTE=<el commit del corte>
    git merge "$CORTE^"
    git merge-base --is-ancestor "$CORTE^" HEAD || { echo "falta main hasta el corte"; exit 1; }
    git diff --quiet "$CORTE^" "$CORTE" -- . ':!rom/src' || { echo "el corte no es sólo el script"; exit 1; }
    git show "$CORTE^:tools/ensamblado/partir_main.py" > <scratchpad>/partir_main.py
    python3 <scratchpad>/partir_main.py --dir rom/src && git add -A rom/src && git commit -m "Partir main.s, reaplicado sobre la rama"
    git merge -s ours "$CORTE"
    git diff --name-status "$CORTE" HEAD -- rom/src   # ni una A ni una D
    git merge main                                     # lo que vino después, normal

Es la versión con las guardas mecánicas del crítico (corrección B). El script
se saca de `$CORTE^` porque en `main` se borra en el commit de prosa, y es la
versión exacta que produjo el corte. El `--dir rom/src` hace falta porque,
corrido desde el scratchpad, el script calcula la raíz del repo a partir de
dónde está él.

Las guardas son lo que hace seguro al `-s ours`, que descarta callado todo lo
que el otro lado trae y la rama no:

* `merge-base --is-ancestor`: si la rama no contiene todo lo anterior al
  corte, `-s ours` lo tira.
* `git diff --quiet … ':!rom/src'`: el corte tiene que ser **sólo** la salida
  del script. Si trajera cualquier otra cosa —prosa, la huella, un
  `.segment`—, `-s ours` la borraría en cada rama vieja. Por eso el commit del
  corte no lleva nada más.
* `--name-status … rom/src` sin `A` ni `D`: la rama partió en los mismos
  archivos que el corte. Una `A` o una `D` quiere decir que las anclas cayeron
  distinto. Las `M` son lo de la rama.

En la prueba del plan, el resultado fue exactamente los dos cambios de la
rama, en `tienda.s` y en `control.s`.

**Si la rama cambió el texto de un ancla** —una marca de sección que el
script busca—, el script se niega (pasó en la primera prueba, que editaba
justo la marca de la tienda). **No se toca `TRAMOS`**, que haría que la rama
parta distinto que `main`: se revierte ese cambio en la rama, se corta, y se
lo vuelve a aplicar en el archivo nuevo.

Conviene hacer el corte con la menor cantidad posible de ramas abiertas, y
avisarle a las que haya. El 2026-09-25 corren dos agentes que no tocan
`main.s`, pero el del MSU-1 puede tocar `tools/ensamblado/cartuchos.py`, que
el commit 2 también toca cerca de `huella()`.

### Segunda etapa, aparte

Mover cambia la ROM: cada movimiento se verifica con `just pruebas` y la
tanda **sin ninguna golden cambiada** —el comportamiento no cambia, sólo las
direcciones—, y el `.sym` cambia en los símbolos corridos. Sólo se puede
mover **dentro del mismo segmento**: pasar algo del banco 0 al 1 cambia cómo
se lo llama (`jsr` contra `jsl`, el banco de datos) y es un cambio de código,
no una mudanza. Lo que el corte deja en un archivo que no es el suyo:

* `poner_switch` en `ruta_del_heroe.s` → `variables.s` (medido: cambia la ROM);
* `volver_al_mapa`, `volver_de_batalla` y `poses_npc_olvidar` al final de `items.s`;
* `sonido_de_codigo`, `sonido_tocar` y `destello_de_codigo` al final de
  `quietos_que_animan.s` → `efectos_de_sonido.s` y `destello_de_personaje.s`;
* `menu_hp_escribir` en `equipo_desde_eventos.s` (FAR; `menu.s` es banco 0:
  no se puede juntar sin cambiar la llamada);
* `exp_sumar` y `aprender_del_nivel` en `batalla_lazo.s` → `nivel.s` (los dos FAR);
* `titulo_subir_menu`, `hp_inicial_poner` y `actor_nivel_de` en `banco1.s`;
* comentarios huérfanos pegados arriba de una marca, que son del tramo
  anterior o de nada: antes de "la pantalla de ranuras" (sobre
  `titulo_subir_menu`, que se mudó) y antes de "usar un ítem en la pelea".

Y el que más valdría y no es una mudanza: **`interprete.s` es un solo
`.proc correr_codigo`** con todos los manejadores de opcode adentro, y es el
archivo que más commits toca. Partirlo es cortar **adentro** del `.proc`
—`.include` de un archivo por familia de opcodes—, que es byte por byte
igual (probado: el corte de prueba entre `bcc :+` y su `:` cayó adentro de un
`.proc`), pero deja archivos que empiezan a mitad de un scope, con etiquetas
locales de otro archivo. Es una decisión de legibilidad aparte.

### Dudas para el crítico

1. **La granularidad.** Sesenta y dos archivos, algunos de cuarenta líneas
   (`control.s`, `items_banco1.s`). La alternativa gruesa sale de borrar
   anclas en `TRAMOS`; la medición no cambia.
2. **Los nombres.** Sobre todo los pares que se pueden confundir:
   `destello_de_personaje.s`/`destello_de_pantalla.s`, `items.s`/`items_banco1.s`,
   `equipo.s`/`equipo_desde_eventos.s`, `batalla.s`/`batalla_puentes.s`, y los
   que nombran por el contenido dominante y no por todo (`grupo.s`, `npcs.s`,
   `celdas.s`, `banco1.s`).
3. **El tramo que queda en `main.s`.** Los generados y dos constantes; la
   alternativa es un `generados.s` y que `main.s` sea sólo la lista.
4. **`.s` contra `.inc`**, arriba.
5. **El `.segment` explícito por archivo** (commit 4). A favor: quien abre
   `nivel.s` sabe que está en el banco 1 sin mirar `main.s`. En contra: sugiere
   que el archivo es independiente, y no lo es —los anchos `.a8`/`.i16` y el
   orden siguen viniendo del anterior—, y es una línea más en cada archivo que
   una rama vieja tiene que atravesar.
6. **La receta con `-s ours`**, que es la parte con más filo del plan.
7. **Que el script quede commiteado en `tools/`** hasta que no haya ramas
   viejas, en vez de en el scratchpad: la huella cubre `tools/*/*.py`, así que
   su commit rearma los cartuchos.
8. **No usar `.git-blame-ignore-revs`**, contra lo que sugiere la tarea.
9. **"`símbolo` en main.s" fuera de `rom/src/`**: dejarlo, pasarlo a
   "`símbolo` en `rom/src/`" o nombrar el archivo. Nombrar el archivo es lo
   más útil hoy y lo primero que envejece con la segunda etapa; el símbolo
   solo se encuentra con `grep -n '^símbolo:\|\.proc símbolo' rom/src/*.s`.

### Lo que resolvió el crítico

Criticado el 2026-09-25 sobre `c71666e`, que midió de nuevo lo de arriba
(ROMs y `.sym` iguales por `ensamblar.py` y por `just cartuchos`; `just
pruebas` en verde sobre el árbol partido con el cambio de herramientas, y
exactamente 3 rojas sin él; sin el cambio de `huella()`, editar `tienda.s` no
cambia la huella; `blame -C --diff-algorithm=histogram` da 0 líneas distintas).
Sus cambios, que son obligatorios:

* **A.** La verificación de reproducible lleva `git add -A rom/src` y
  `--cached`: ya corregido arriba.
* **B.** La receta de las ramas abiertas lleva guardas mecánicas: ya
  corregida arriba. De ahí sale que **el commit del corte es la salida del
  script y nada más**.
* **C.** El commit de herramientas lleva una prueba de que todo lo que
  devuelve `fuentes()` está en la huella, y se demuestra que falla con el
  `huella()` de antes.
* **D.** El script se borra en el commit de prosa, no "más adelante".
* **Nombres**: `items_banco1.s` → `banco_de_la_pantalla.s` y `equipo.s` →
  `pantalla_de_equipo.s` (ya en la tabla y en `TRAMOS`). El resto queda.
* **El commit 4** —`.segment` explícito por archivo— va.

## Bitácora

**2026-09-25, ejecución.** Sobre `cd4adf8`.

1. Plan y script: el cherry-pick de `5377d8b` con los nombres y las
   correcciones A, B y D. `partir_main.py --ver` encuentra todas las anclas.
2. Herramientas: el parche del plan, y la lista de archivos de `huella()`
   sacada a `cartuchos.archivos_de_la_huella(fuente)` para poder probarla.
   La prueba de C, `test_todo_lo_que_arma_la_rom_esta_en_la_huella`, mira el
   árbol de verdad y uno armado a mano con un `main.s` que incluye un
   `tienda.s`; el segundo es el que cobra hoy, cuando `main.s` todavía no
   incluye ningún `.s`. Con el `huella()` de antes —sólo `main.s`— en una
   copia, da rojo: `Left contains one more item: '…/tienda.s'`.
