# Dónde quedamos

Lo que existe **sólo mientras alguien trabaja**: qué se decidió y sigue
valiendo, qué espera respuesta de taro, qué no se probó todavía, qué no cubre
la tanda, y hacia dónde vamos.

Lo que **no** va acá: el relato de lo hecho. Eso está en `git log`, que en este
repo tiene mensajes largos justamente para eso, y lo durable está en
`README.md`. Este archivo llegó a tener dos mil líneas por append-only y se
volvió inusable; se borra sin culpa lo que ya esté en esos dos lados.

Se escribe **mientras se trabaja**, no al final.

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
   puros y lo sabemos **porque el conversor ya los cachea**;
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

**Los primeros diez minutos jugables**, que es lo que taro viene probando vuelta
a vuelta.

Al 2026-09-14: `just snes-hitos-foto` son **170 casos, todos en verde** y `just
pruebas` son **169 en verde y 1 `xfail`, sin rojos**. El `xfail` no es adorno, pero desde el 2026-09-13 se sabe de quién es: es un
defecto de la **página de prueba** de guardado y no del juego, y está abajo.

**Ditto** (`ditto/`) hace `.ldb`/`.lmu`/`.lmt` ⇄ JSON en los dos sentidos, con
la vuelta byte por byte en **330 de 330** archivos del juego (`just
ditto-vuelta-entera`), y desde el 2026-09-14 **es de donde sale `data/`**, que
es lo que lee el conversor. También es un **proyecto independiente en inglés**:
adentro de `ditto/` no hay una sola mención a ABL, a la SNES ni al port, el
corpus se lo pasa el justfile en `DITTO_CORPUS` —sin esa variable las pruebas
que lo necesitan se saltean con un mensaje— y lo que ata a Ditto con este repo
está en **`DITTO.md`**, en la raíz y en castellano. Lo que le falta a la
herramienta está en `ditto/README.md`, ya en inglés. El default de cada campo
va **una sola vez y al lado del campo** en el esquema generado, y está medido
hasta dónde aguanta la regla de omisión: un chunk escrito con su valor default
se pierde —son 3 bytes—, pero ni RPG Maker 2000 ni EasyRPG lo escriben, así que
no se tocó el esquema. La salida barata, por si aparece una tercera
herramienta, está anotada en `ditto/README.md` y sin implementar.

Y desde el 2026-09-14, **los tres pasos del plan de Ditto están hechos**: Ditto
omite los defaults también en el JSON, vuelca el juego entero como árbol de
archivos, **`data/` es ese volcado** y **`tools/lcf.py` lo lee**. El conversor,
la referencia en Python y las pruebas ya no abren un solo `.lmu` para armar una
ROM; del juego original siguen saliendo los PNG y los MIDI, que es lo que
`--game-dir` nombra. `just datos` regenera `data/` —674 archivos, 19.445.521
bytes— y el que manda después es el `git diff`: si el juego no cambió, da
vacío.

Los defaults **ya no se escriben en `lcf.py`**: salen de
`tools/ditto_schema.py`, que genera `tools/gen_ditto_schema.py` desde el
esquema de Ditto, con el chunk, el default, el enum, el `PersistIfDefault` y el
struct anidado de cada campo. Los 51 llamadores de
`lcf.Map`/`Database`/`TreeMap` quedaron **intactos**; los tres que cambiaron
—`eventos.py`, `destraba.py` y `test_encuentros.py`— metían la mano por debajo
de la capa, a los chunks crudos de `db.fields`.

**El criterio de aceptación se cumplió con una diferencia, y es un arreglo.**
`demo-ciudad` y `demo-titulo`, armadas antes y después, difieren en **dos
bytes** de la tabla `sabe_hab`: `Learning.skill_id` vale 1 y no 0 cuando el
archivo no lo trae, y le pasa a Alex —el actor 1, del RTP, que este juego no
usa—. Con ese default puesto de vuelta en 0 el `mapdata.inc` sale byte por byte
idéntico, así que **ningún otro dato se movió**. Todo esto, con sus números,
está en **`DITTO.md`**.

Dos cosas más de esa vuelta. Una: `Music::name` y `Sound::name` tenían en Ditto
el default `"(OFF)"` **con las comillas**, porque el generador citaba dos veces
un literal de C++ que ya venía citado del CSV; arreglado, son 61 KB menos de
volcado, y la vuelta sigue en 330 de 330 —los dos campos son
`PersistIfDefault`, por eso no se había notado—. Y dos: apareció que
`test_ninguna_tropa_filtra_por_terreno` **no medía nada** —leía el chunk 0x13
de la base, que es `animations` y no `troops`— y que **doce tropas de los
encuentros al azar sí filtran por terreno**. La simplificación del port aguanta
igual, pero por otro motivo: ninguna excluye un terreno que su mapa pise de
verdad. La prueba ahora mide eso.

## El códec de audio, portado a `brr/` (2026-09-15)

`brr/` es el tercer proyecto independiente del repo, después de `ditto/` y
`protocol/`: un binario en Rust que codifica PCM a BRR —el formato de muestras
del SPC700— y que lee SoundFonts para sacar de ahí las muestras. Es el port de
`tools/brr.py` y `tools/sf2.py`, que **siguen existiendo y siguen siendo los
que arman la ROM**: nada del conversor los dejó de usar, y la convivencia es a
propósito hasta que el port esté probado de verdad.

Lo medido, que es lo único que autoriza a reemplazarlos algún día: se
interceptó cada llamada a `brr.encode` de una conversión entera de
`demo-ciudad` —los 29 mapas de la receta— y salieron **608 muestras
distintas**. Las 608 dan **byte por byte iguales** entre el Python y el Rust.
No es una muestra: es el conjunto completo de las que esa ROM usa. El lector de
SoundFont se comparó aparte contra el de Python sobre cinco bancos
—`Microsoft GS Wavetable Synth`, `FluidR3_GM`, `MuseScore`, `AWE32` y
`32MBGM`—, 984 programas y golpes, comparando nombre, tasa, nota raíz, cents,
loop **y el PCM crudo**: cero diferencias.

De paso, dos divergencias contra el DSP de verdad que **ya estaban en el
Python** y que el port conserva idénticas a propósito, porque arreglarlas
cambiaría el audio:

* El chip decodifica en media escala (`(nibble << shift) >> 1`, y al final
  `(int16_t)(s * 2)`; ver `SPC_DSP.cpp` de bsnes en `/extras/ref`), así que con
  **shift 0 pierde el bit bajo del nibble** y el modelo de `brr.py` no. En el
  corpus son 128 bloques de 85629, todos muy callados: inaudible, pero real.
* Al pasarse de 16 bits el chip **envuelve** y el Python **satura**. En las
  1370064 muestras del corpus esto **no pasa ni una vez**, así que hoy no
  cambia nada; el margen lo da que `snes_samples.normalize` deja el pico en
  0x6800.

Y una diferencia de interfaz, no de bytes: `brr.encode` acepta callado un
`loop_block` más allá del final de la muestra, y el binario lo rechaza diciendo
cuántos bloques hay. Hoy ningún llamador lo hace.

Tarda **2,0 s contra 29,9 s** en codificar las 608, y eso incluye arrancar el
proceso 608 veces; medido con otro agente compitiendo por CPU, así que el
número es un piso.

## El ensamblador en Rust (2026-09-15)

`w65/` es el port a Rust de `tools/w65.py`, el ensamblador de 65816 que arma
la ROM. Es el cuarto proyecto independiente, después de `ditto/`,
`protocol/` y `brr/`, y sigue sus mismas reglas: **adentro no hay una sola mención a
este juego ni a la SNES** —es un ensamblador de 65816 y nada más—, y los dos
códigos de salida son 1 si el fuente no ensambla y 2 si la llamada está mal.

**Los dos conviven, y las recetas que arman ROMs siguen llamando al de
Python.** El criterio de aceptación se cumplió: `just w65-comparar` ensambla el
mismo `main.s` con los dos y la ROM y la tabla de símbolos salen **byte por
byte iguales**, verificado con los `mapdata.inc` de `demo-ciudad` y de
`demo-titulo` —los únicos dos que el `main.s` de hoy acepta; el resto de
`rom/build/` es viejo y lo rechaza el de Python también—. Los caminos que
fallan también coinciden: sobre `demo-carrera`, `demo-apertura` y `demo-musica`
los dos cortan en la misma línea por la misma razón.

Tarda **0,40 s contra 11,0 s**, con 302 MB de pico contra 1,2 GB. `just
w65-pruebas` son 67 casos que no dependen del juego: fuentes chicos escritos
adentro de la prueba, y sobre todo los mensajes de error.

**Los flags cambiaron de nombre al inglés** —`--include`, `--symbols`,
`--no-checksum`—, así que migrar el justfile es un paso aparte y todavía sin
hacer.

Tres cosas que aparecieron del original y **no se tocaron**, para no mover la
ROM:

* **El control de rango de `.byte` está muerto.** Vive en `Data.emit`, pero
  `Assembler.emit_item` atiende a `Data` por su cuenta y trunca sin mirar, así
  que el guardián que se puso por el defecto de `ba_orden_txt` no corre desde
  entonces. Medido: hoy no hay ningún `.byte` fuera de rango en `demo-ciudad`,
  o sea que revivirlo no cambiaría la ROM. Si se revive, va **en los dos
  lados**.
* **`jml etiqueta` no se puede escribir**: `jml` sólo tiene modo largo y un
  operando pelado se decodifica siempre como absoluto o página directa. Hay
  que poner `jml f:etiqueta`.
* **Una etiqueta o constante llamada `a` es inalcanzable como operando**: el
  decodificador lee `a` como el acumulador antes que como un símbolo.

**Lo que sigue**: migrar las recetas al binario de Rust y recién ahí borrar
`tools/w65.py`.

## El bytecode declarado en un solo lado (2026-09-15)

`protocol/events.toml` declara los 40 opcodes —su número y los bytes que los
siguen— y de ahí salen generados y commiteados `tools/event_opcodes.py` y
`rom/src/event_opcodes.inc`. Antes el número lo elegía `tools/eventos.py` y le
llegaba al intérprete **adentro de `mapdata.inc`**, o sea dentro de los datos
de un mapa: el que emite los bytes le declaraba al que los implementa qué
significan. De ahí salieron las dos colisiones de opcodes del 2026-09-13 y las
tres copias del largo de cada instrucción, una de las cuales se quedó vieja y
puso doce casos de la tanda en rojo. Ahora el largo **se deriva** del layout
declarado y no se escribe en ningún lado; `just protocolo --check` falla si un
generado quedó viejo.

Las dos ROMs de `just snes-demos` salen **byte por byte iguales** a las de
antes, medido dos veces contra un worktree de `main` limpio. Están en
`pruebas-manuales/protocolo/` con su LEEME: no hay nada nuevo que mirar, y
justamente por eso conviene jugarlo un rato —es un cambio que toca el
compilador y el intérprete a la vez—.

**Y el renombre ya está hecho** (`5ba5d05`): los 40 opcodes se llaman en
inglés, que es el idioma de su declaración. Son 506 usos en 18 archivos y 32 de
los 40 cambian. Dos no son la traducción obvia porque el stream del SPC700
tiene sus propios `OP_DSP`, `OP_WAIT` y `OP_END` a mano en main.s y comparten
el espacio de símbolos: `OP_FIN` quedó `OP_DONE` y `OP_ESPERAR` quedó
`OP_DELAY`. Las ROMs siguen byte por byte iguales.

Y las etiquetas del intérprete también (`ec94369`): la etiqueta es el nombre
del opcode en minúsculas y lo que cuelga de ella la sigue, así que `op_lugar`
pasó a `op_place` y `op_tienda_listo` a `op_shop_done`. Son 37 de 45 etiquetas
y 121 usos. El resto de main.s —`ruta_frec`, `mapa_actual`, `celda_bloqueada`—
sigue en castellano: lo que se movió es el vocabulario que viene de
`protocol/events.toml` y nada más.

Y el stream del SPC700 también (`f141b87`), que estaba peor: sus tres opcodes
estaban escritos a mano **de los dos lados** —`tools/snes_music.py` escribe el
stream, `main.s` lo lee— sin nada que atara las copias. Ahora son
`protocol/music.toml`.

Eso obligó a generalizar el generador, y ahí apareció que **tenía las rutas de
salida clavadas al layout de este repo**: hoy es `protocol DECLARACIÓN --python
X --asm Y [--check]`, con `--help` y errores que nombran el archivo, el opcode
y lo que se esperaba. Los generados pasaron a `event_opcodes` y
`music_opcodes`, y su API a inglés (`OPCODE_SIZE`, `opcode_size`), porque son
la salida de una herramienta en inglés y no fuente de este árbol.

Y de ahí **el generador pasó a Rust con clap** (`protocol/src/`), que es lo que
taro quiere de una herramienta: un binario que recibe input y da output, con
`--help` y errores que una IA o una persona aprenden sin leer la
implementación. Sale con 1 si algo está desactualizado y con 2 si la llamada
está mal, que son cosas distintas para quien lo automatice. Las 14 pruebas de
`just protocolo-pruebas` son sobre todo **los mensajes de error**: un generador
que se explica mal es uno que la gente deja de usar y vuelve a escribir los
números a mano. Compilar la ROM no necesita cargo —lo generado está en git—;
sólo cambiar un opcode.

Los dos bytecodes caen en el mismo espacio de símbolos del ensamblador: pueden
compartir número pero no nombre, y eso lo cuida una prueba.

**Lo que sigue**: los cortes que quedaron
pensados en la charla del 2026-09-14: separar los conversores tontos de PNG y
MIDI del asignador de paletas y de ARAM, el compilador de JSON a datos de ROM
como binario propio, y el corredor de libretro —`snes_correr` + `snes_compare`
+ `retro.py`— que no tiene una línea de este juego adentro.

Y con eso se borró el volcado viejo de Python: `tools/export_json.py`,
`tools/lcf_bin.py` —el lector de binarios, que es el `lcf.py` de antes—,
`tools/gen_schema.py` y `tools/lcf_schema.py`. Son 3.133 líneas que quedaron
sin dueño el día que `data/` pasó a ser el volcado de Ditto: lo único que
aportaban era una lectura más corta del juego, y lo que no daban es con qué
volver a escribir el binario. **Ya no hay un segundo lector del formato.**

**La ROM de esta vuelta** está en `pruebas-manuales/hq-graficos/`: `demo-ciudad`
con el arreglo de la cinemática de los Neon Vipers, y `demo-vipers` —un cartucho
de un mapa— para ver esa escena sin caminar media Lashe City. Su `LEEME.txt`
dice cuál sirve para reproducir el defecto y cuál no, y por qué.

**La anterior** está en `pruebas-manuales/piedras/`: el minijuego de
las piedras del Lazer Teeth HQ, con un cartucho de un solo mapa que arranca
parado abajo de la reja y con `demo-ciudad` al lado para el control. Su
`LEEME.txt` dice qué apretar y en qué orden.

Y **la del lag del HQ** está en `pruebas-manuales/lag-hq/`: el mismo mapa, que
pasó de 30,00 a 59,80 fps. Su `LEEME.txt` dice adónde ir y qué otras escenas
conviene jugar para ver que las páginas siguen cambiando cuando deben.

**Y la de antes** está en `pruebas-manuales/2026-09-13-68539a8/`,
con los tres arreglos y las tres ROMs —la ciudad con sus pistas, la carrera, y
la carrera con el volante prendido a mano, que espera el veredicto de taro—.
La anterior, con la que él encontró los tres bugs, está en
`pruebas-manuales/2026-09-13-f30be91/`,
con las cuatro vueltas juntas: `demo-ciudad.sfc` con las ocho pistas de MSU-1 y
`demo-carrera.sfc` con la persecución en auto. Su `LEEME.txt` dice qué mirar y
en qué orden. Las de cada pieza por separado, por si hace falta aislar algo:

* `pruebas-manuales/habilidades/` — las habilidades especiales de la batalla:
  dos peleas sueltas que se abren solas y la demo entera. Su `LEEME.txt` dice
  qué sabe cada personaje y qué falta, empezando por los SP, que no se ven en
  la pantalla de la pelea.
* `pruebas-manuales/tram-y-hq/` — el viaje en el tranvía jugable de punta a
  punta y la página que reordena el escondite de los Lazer Teeth. Pide
  **probar guardar**: `partida_tabla` se mudó de banco.
* `pruebas-manuales/escapes-de-texto/` — un cuadro de texto que se cierra solo.

La de la vuelta anterior está en `pruebas-manuales/vars-y-rutas/`, con las
coordenadas de un personaje y el teletransporte de dos bytes; y la de antes, con
las cuatro piezas del mediodía, en `pruebas-manuales/desbloqueos/`.

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

### Las voces que faltan no son del runtime: son del banco compartido (2026-09-14)

taro lo reportó jugando en la SNES: *"la música parece perder calidad
progresivamente. Lo empecé a notar en el auditorio, en la oficina del director
ya es muy evidente —suenan solo dos o tres voces—, luego en los back alleys
pareciera tener una voz menos, y en los rat tracks creo que ya le queda una
sola voz o ni suena"*. Y después, lo que lo cierra: *"se escucha igual el tema
en la oficina del director con alta calidad o calidad clásica"*.

**No es progresivo y no es del runtime: es un tema distinto por mapa, y a cada
uno le falta lo suyo.** Lo que se cae son las notas cuyo **programa de General
MIDI no está en el banco compartido**: `build_events` las saltea con un
`continue` y no llegan al stream. Medido sobre los 21 temas de `demo-ciudad`,
contando notas del MIDI que sobreviven:

    mapa 17  Delcentric Factory   hzstream       100,0%   (y tiene pista de MSU-1)
    mapa 18  Auditorium           Astpgmarch      64,4%
    mapa 19  Talan and the Dir.   Gaden           63,6%
                                  3D-Galax        43,4%
    mapa 20  Sector 30 Back All.  wb3shop         72,5%
    mapa 26  Rat Tracks B2        KSSMKEND        42,0%
                                  vswar           69,2%
    mapa 28  Sector 27 Back All.  Lunar_Pyramid   70,4%
    mapa 32  Sector 27 Warehouse  dcbest          27,5%
    mapa 36  LasheCityVehicle     golden_axe-…    12,2%

Los **doce primeros temas de la lista están al 100%**. Los nueve del final son
exactamente los que `build_varios` saca de aportantes cuando el banco no entra
en la ARAM, y los saca **desde el final de la lista** —que es más o menos el
orden de los mapas—, y de ahí sale la ilusión de degradación progresiva. No lo
es: el 20 suena mejor que el 19, y taro lo dijo así sin saberlo.

**Por qué suena igual con MSU-1 y sin él, que es lo que parecía imposible:**
ninguno de esos temas tiene pista. `PISTAS_MSU` son ocho y le tocan a los temas
0, 1, 2, 4, 5, 6 y 7 más el del título; del 8 en adelante `tema_msu` es `$FF`.
O sea que en la oficina del director **las dos corridas de taro fueron el mismo
camino, el del SPC700**, y por eso les falta lo mismo. Medido en la ROM y no
deducido, con bsnes y los ocho `.pcm` al lado:

    musica-17-hzstream   MSU_HAY=1  MSU_SUENA=1   la pista suena
    musica-19-Gaden      MSU_HAY=1  MSU_SUENA=0   el MSU-1 está y no suena

Y `Gaden` es el caso concreto: usa siete canales, con los programas 58, 49, 49,
49, percusión, 46 y 52. Al banco no entraron ni el 58 ni el 49 ni el 52, así
que **quedan dos de siete**. Eso es el "suenan solo dos o tres voces", y se ve
también desde adentro del cartucho: el stream de `Gaden` nombra **dos**
muestras, y con `--banco-entero` nombra **cinco**.

Lo único que sigue sin encajar es su *"los samples son mejores"*: ahí los dos
cartuchos producen el mismo sonido.

**No es el soundfont.** Se midió: los veinte programas que faltan —58, 49, 52,
18, 92, 94, 45, 96, 102, 26, 56, 16, 39, 112, 91, 99, 118, 32, 36 y 50— están
**todos** en `Microsoft GS Wavetable Synth.sf2`. Lo que falta es lugar en la
ARAM, no la muestra.

**Y tampoco es el paquete de audio ni el desalojo.** Se recorrió `demo-ciudad`
con `pruebas/consola.py` teletransportando de mapa en mapa y preguntándole a la
ROM qué muestras tiene arriba: de 21 a 32 muestras en la ARAM según el mapa, y
**cero** faltantes del tema que estaba sonando en todos ellos. `FAR_QUIERE` y
`paquete_cargar` hacen lo suyo bien.

#### El lever para decidirlo de oído: `--banco-entero`

`build_varios` toma ahora un `tope`, y el conversor un `--banco-entero` que lo
saca. Medido sobre los mismos 21 temas:

    hoy                  58 muestras, 57517 B, tasa mediana 11521 Hz, 9 temas mutilados
    con --banco-entero   95 muestras, 67376 B, tasa mediana  8109 Hz, 0 temas mutilados

O sea: **o los doce primeros perfectos y los nueve últimos con la mitad de las
notas, o los veintiuno enteros y todos un 30% más chillones.** Con
`--banco-entero` el banco ya no entra en la ARAM de una vez, y eso está bien:
ahí vive **un paquete de mapa por vez**, no el banco. Los dos siguen al 100%
menos `Astpgmarch` (88,6%) y `vswar` (82,2%), que pierden golpes de percusión
porque el presupuesto de la batería es lo que sobra.

**Cuál de las dos suena peor lo tiene que decir taro**, y para eso están las
ROMs de `pruebas-manuales/audio/`.

#### Y la salida que taro eligió: pista de MSU-1 para los 21

El 2026-09-14 decidió el alcance: *"El juego tiene mucha música. Tal vez no sea
factible usar PCM para todo, pero sí o sí quiero todos los temas que suenan
hasta salir de Lashe City"*. Hecho: `PISTAS_MSU` pasó de 8 a **22** entradas y
cubre los 21 temas de `demo-ciudad` más el del título. **Los números del 1 al 8
no se movieron**, que es lo que deja válidos los `.pcm` que ya están en la
tarjeta; los catorce nuevos van del 9 en adelante.

Dos de los catorce no son de ningún mapa y por eso se habían escapado de todo
barrido anterior: salen del LDB, no de un `PlayBGM`. `title_music` —que ya
tenía la 8— y **`battle_music`, `T_VGFighterMAX_Masako`**, que suena en todas
las peleas.

**Lo que darle pista al de batalla NO arregla, medido porque parecía que sí:**
sacarlo del banco compartido libera **4 muestras y 565 B**, sube la tasa
mediana de 11521 a 12496 Hz y **no devuelve ni uno** de los nueve temas
recortados —siguen siendo los mismos nueve—. Y a dos de ellos los deja peor
(`vswar` 69,2→68,6%, `golden_axe` 12,2→8,3%), porque se apoyaban en programas
que ponía él. Su peso es de **stream** —156.520 B, el doble que el siguiente—
y el stream vive en el cartucho, no en la ARAM.

Lo que cuesta: 10,6 MB por minuto, o sea **unos 423 MB de PCM por cartucho**
para los 21. **Recortar por loop no ayuda**: de los 21, el único que repite
exacto a la mitad es `C3classi` —medido comparando nota por nota las dos
mitades del MIDI— y son 8,6 MB de 423. `3D-Galax`, que es el más largo con 267
s, **no** se repite.

Dos cosas que costaron al armar esas ROMs y conviene no volver a descubrir:

* **El mapa de arranque se elige con `--inicial`, no con `--map-id`.** El orden
  de la tabla de mapas es el orden en que se numeran los temas, y `--map-id`
  pone al mapa primero: el tema a escuchar quedaba primero de la lista y por
  eso entre los que sí aportan. `musica-20` armada así daba `wb3shop` al 100%.
* **Y aun así hace falta `--banco-sin-prioridad`**, porque el tema del mapa de
  arranque tiene prioridad para aportar al banco. Es la misma trampa una capa
  más abajo, y también hace sonar entero justo lo que hay que escuchar roto.
* **Y `--tema-de-arranque`**, porque la mayoría de esos mapas no tiene BGM
  propia en el LDB: la prende un `PlayBGM` de una de sus páginas, que suele
  pedir switches de la historia. Sin eso `musica-20` arrancaba muda y seguía
  muda a los 300 ticks.

Y una que conviene saber: **snes9x sí emula el MSU-1**. Una ROM con sus `.pcm`
al lado en `rom/build/` suena por pista también en la tanda; el `.msu` no está
en ningún build de las pruebas, así que no las afecta, pero al medir audio a
mano hay que mirar dónde quedaron esos archivos.

### El MSU-1 de `demo-titulo`: no se pudo reproducir, y el camino no tiene red (2026-09-14)

taro: *"la que tiene la pantalla de título no carga la música de alta calidad,
mientras que la otra sí"*. **En emulador las dos hacen exactamente lo mismo.**
Medido con bsnes y los ocho `.pcm` al lado, leyendo `MSU_HAY` y `MSU_SUENA` de
la WRAM cuadro a cuadro:

    demo-ciudad   MSU_HAY=1 desde el cuadro 1; MSU_SUENA=1 en el 208, tema 1
    demo-titulo   MSU_HAY=1 desde el cuadro 1; MSU_SUENA=1 en el 113, tema 21
                  (el del título), y en el 219 pasa al tema 1

Así que la detección anda, el número de pista del título es el 8 y está en la
tabla, y la ROM arranca las dos pistas. El defecto es **de hardware solamente**.

Lo que sí apareció mirando, y es el único candidato que produce ese síntoma:
**bsnes no pone `AUDIO_BUSY` nunca.** `io.audioBusy` arranca en falso en
`power()` y no se escribe en ningún lado —está en
`/extras/ref/bsnes-libretro/bsnes/sfc/coprocessor/msu1/msu1.cpp`—, así que el
lazo de espera de `msu_arrancar` **sale siempre en la primera vuelta en todos
los emuladores y en toda la tanda**. En el FX Pak la pista sale de la SD y
abrirla lleva tiempo de verdad: ese lazo sólo corre allá. Es un camino sin red,
de los que AGENTS.md avisa.

Y en el mismo archivo está la regla que lo vuelve sospechoso: `case 0x2007: if
(io.audioBusy) break;` — **con `AUDIO_BUSY` puesto el hardware ignora las
escrituras a los registros de audio**. `demo-titulo` pide dos pistas con 1,8 s
de diferencia —la del título y la de la apertura—; `demo-ciudad` pide una sola.
Si la segunda llega mientras la primera todavía se abre, se pierde.

Por eso `msu_arrancar` ahora **espera antes de escribir la pista, no sólo
después**, y el tope pasó de `$4000` —unos 70 ms— a `$FFFF`, unas tres décimas
de segundo. Cuesta **14 bytes del banco 0**. En emulador no cambia nada, y ése
es el punto: **esto no está verificado, lo tiene que decir la consola**.
`pruebas-manuales/audio/` lleva las dos `demo-titulo` para compararlas.

### El menú de la pelea ilegible: un índice de texto que no entraba en un byte (2026-09-14)

taro lo reportó jugando en la SNES: *"el menu de la batalla está bastante roto.
los textos se pisan entre ellos. es imposible saber qué estoy seleccionando"*.
Era una sola cosa y no tenía nada que ver con la geometría del menú:
**`ba_orden_txt` era una tabla de un byte y los índices de texto no entran en
un byte**.

El conversor guarda todos los textos de las pantallas en un solo bloque —los
ítems primero, con su nombre y sus dos renglones de descripción, después los
del equipo, la tienda y la batalla—. Con los 57 ítems de `demo-ciudad` los de
la batalla arrancan en el **273**, así que el conversor emitía `.byte 273` y
`w65` lo truncaba a 17 sin decir nada. El menú quedaba nombrando otros cuatro
textos, y como el conversor los emite **ya recortados** la ROM los dibuja con
ancho 255:

    Attack   (fila 24, col 1)   -> "detonated shell."
    Defend   (fila 24, col 22)  -> "A bandana with a circuit"
    Use Item (fila 26, col 1)   -> "Circuit Bandana-H"
    Escape   (fila 26, col 13)  -> "Prices - Sector 32\""

"Circuit Bandana-H" ocupa hasta la columna 17 y "Prices - Sector 32" arranca en
la 13: **ahí se pisan**. Y el de Defend mide 24 desde la columna 22, así que
se da la vuelta y sigue en el renglón de abajo. La única orden que se leía bien
era la segunda, porque su texto no sale de ahí sino de `actor_hab_txt`, que
**sí** es de dos bytes.

**Por qué ningún caso de la tanda lo veía**, que era la pregunta: sus cartuchos
llevan un mapa y ningún ítem, y ahí los textos de la batalla arrancan en el
**103**. El truncado no existe hasta el 256, así que los ocho casos de la
pantalla de pelea comparaban la ROM contra la referencia en el único rango
donde las dos coinciden. No es "los dos lados se equivocan igual": es que el
defecto depende de **qué cartucho se arma**, como el desborde del banco 0, y la
tanda arma cartuchos chicos. El grupo y la tropa no tenían nada que ver —con
cuatro actores y cuatro enemigos la pantalla da cero, medido—.

Tres cosas quedaron:

* **`ba_orden_txt` es de dos bytes**, como sus dos hermanas. Cuesta cinco bytes
  de RODATA y un byte **menos** de código, porque el índice ya se arma de a
  dieciséis bits.
* **`w65` rechaza un `.byte` que no entra en un byte.** El truncado callado es
  lo que dejó pasar esto, y es a propósito sólo en `.word`, donde la tabla de
  punteros de un bloque guarda los dos bytes bajos de una dirección de 24.
  Con el control puesto, `demo-ciudad` no tiene ningún otro `.byte` desbordado.
* **`--relleno-de-textos`**, el hermano de `--relleno-de-mensajes`: textos
  muertos de largo cero delante de todos, para que los índices pasen del 255 en
  un cartucho de un mapa. Lo usa el caso `batalla-textos-lejos`, verificado en
  rojo con la tabla de un byte puesta: **754 pixeles, 1,31%**, todos en los dos
  renglones del menú. Va de un solo lado a propósito: la referencia escribe
  caracteres y no modela ningún índice de texto.

Lo que **no** era, y conviene que quede escrito:

* **"no me permite seleccionar nada más que ataque" no es cierto del todo.** El
  cursor recorre las cinco con izquierda y derecha, y Attack, Defend y Escape
  hacen lo suyo. Las dos que no llevan a ningún lado con el grupo de Lashe City
  son la habilidad —**ninguno de los cuatro actores de ahí sabe ninguna**:
  Talan, Arden, Gang Member y Saldra son de nivel 1 a 4 y todas se aprenden más
  arriba— y `Use Item` con el inventario sin nada usable. Las dos van en gris o
  no pasa nada, que es lo que hace el menú de pausa; con los textos equivocados
  encima, jugando eso se lee como "sólo anda atacar".
* **Los SP siguen sin verse** en la pantalla de la pelea, que es la deuda
  declarada de las habilidades y sigue abierta.

### El cofre trampa de los Rat Tracks: el Game Over colgaba la ROM (2026-09-13)

taro no pudo pasar de Rat Tracks B1: *"hay un cofre trampa... queda la pantalla
en negro y no podés hacer nada. softlock, o un crash"*. Es el
`RatTrackChest6c`, el evento 20 del mapa 21, y su página es un `EnemyEncounter`
contra la tropa 98 —tres GiantRat— con la huida prohibida y `defeat_mode` 0, o
sea Game Over al perder.

**No era la pelea: era el reinicio.** El Game Over es `jml f:reset`, y el
arranque se quedaba clavado en `spc_upload` esperando el `$AA`/`$BB` de una ROM
de IPL que ya no corría —el botón de reset de la consola resetea al SPC700, un
`jml` de adentro del juego no—. El porqué durable está en el README, "Trampas
del hardware". El arreglo es un comando nuevo del driver que lo manda de vuelta
al IPL; lo manda `reset` antes de subir nada, así que **cualquier** Game Over
—las quince páginas del juego, el jefe del mapa 26 incluido— vuelve al juego.

Lo que hay que saber de esto:

* **La prueba que ya existía pasaba con la ROM colgada.**
  `test_perder_sin_manejador_vuelve_al_arranque` miraba `mapa_actual`, que
  `cargar_mapa` deja puesto mucho antes de la subida al SPC700. Lo único que
  dice que el arranque terminó es que el lazo vuelva a contar `vueltas`, y eso
  es lo que mira ahora `test_el_game_over_vuelve_al_juego`, **comprobado en
  rojo** sacando el comando nuevo.
* **No es el defecto del HP** que se trabajó en paralelo el mismo día. Acá
  perder sí llevaba al Game Over —`BA_RESULT` en 2 y el `jml`— y el cuelgue es
  del arranque, no de la pelea. Se tocan en un solo punto: cuanto más fácil sea
  perder, más seguido se llegaba al cuelgue.
* **La reproducción**, por si hay que volver: un cartucho del mapa 21 solo,
  `ir_al_mapa(21, 22, 36)`, mirar hacia arriba y tocarle A al cofre. Con el
  grupo por omisión —Talan solo, 40 de HP— la pelea se pierde sola en unos
  ciento cincuenta cuadros.

### Los cofres que no frenaban: era el Hover-Tram (2026-09-13)

taro reportó que en el Sector 30 y en los Rat Tracks los cofres, los bums y las
piedras no tienen colisión —los abre, las animaciones están bien, y les camina
por encima—. **No era la capa**: la capa ya estaba de los dos lados desde el
2026-09-05, y está medida: de las 5684 páginas del juego, **2953 son de la capa
del héroe** —las que frenan—, 2712 de la de abajo y 19 de la de encima; **un
solo evento de todo el juego** queda afuera de la tabla por tener una condición
que la ROM no evalúa. Preguntándole a la ROM con `pruebas/consola.py` sobre la
ROM que él jugó —`pruebas-manuales/lag-hq/demo-ciudad.sfc`, byte por byte—, los
cofres del 20, del 21 y del 26, las piedras del 21 y los dos bums del 20 **lo
frenan todos** si se entra al mapa con una partida recién arrancada.

Lo que pasaba es otra cosa: **la orden 36 de una ruta forzada, `walk_everywhere_on`,
era pegajosa y la caminata con el pad la miraba**. El Hover-Tram (mapa 13,
`EV0028`) la prende para que Talan se mueva entre los pasajeros y **nunca la
apaga**, así que desde que se toma el tram —que está en el camino principal— el
héroe le camina por encima a todos los eventos del resto de la partida. En
`demo-ciudad` son dos páginas así; en el juego entero, cuatro de las 153 que
mueven la bandera.

El porqué durable, con lo que hace RM2k y por qué acá no, está en el README:
"Atravesar paredes vale mientras dura la ruta". El titular: en RM2k la bandera
es un campo de la partida guardada y la caminata con el pad la lee, así que allá
el héroe también atravesaría **paredes**; acá sólo atravesaba eventos, porque
`can_leave` y `can_enter` ya miraban la copia por paso. La ROM quedó del lado de
la referencia, que ya lo hacía así sin decirlo.

Lo cubren dos casos nuevos, `atravesar-cofre` y `atravesar-savept`, los dos
sobre el mapa 20 y con la misma ruta de una sola orden; el primero verificado en
rojo con la ROM de antes —9,78%— y el segundo en rojo sacándole el `cmp
movil_capa` a `celda_bloqueada` —52,24%—.

**Y lo del Bum era otra cosa.** El `InnBum` del mapa 20 —el que cobra por dejarte
dormir sobre la pila de basura— **sí** frena al héroe; con lo que no se puede
interactuar es con su página, que no compila: usa `ShowInn` (código 10730) y el
port no lo tiene. El otro bum del mapa, `BumGuardingEntrance`, compila entero.
Así que "el Bum" son dos defectos distintos y sólo uno era de la colisión.

**El banco 0 quedó en 8 bytes libres** con el cartucho de `demo-ciudad`, medido
por bisección con un `.res N` en `TABLAS` sobre el árbol mergeado. El arreglo no
costó ninguno —cambia un operando por otro del mismo ancho— y los ocho ya
estaban antes.

Para probarlo a mano está **`just snes-demo-cofres`**: el 20, el 21 y el 26, con
Talan al lado del primer cofre y **con la bandera de atravesar ya prendida**, que
es el estado en el que el tram deja la partida. Sin eso el cartucho no mostraría
nada: con una partida recién arrancada los cofres frenaban también antes. La ROM
está en `pruebas-manuales/colision/`, con `demo-ciudad` al lado para el camino
de verdad.

Verificado sobre el árbol mergeado con `main` —la foto `6734dd3`—: `just
snes-hitos-foto` **166 casos, todos en verde**, `just pruebas` **142 en verde y
1 `xfail`, sin rojos** —`test_recorrido.py` incluido, con sus ocho capturas
golden sin tocar— y `just snes-demo demo-ciudad` arma.

### El lag del HQ de los Lazer Teeth: dos cosas por cuadro, no una (2026-09-13)

El mapa 11 iba a **30,00 fps** clavados y taro lo reportó como "laggea un
montón". Eran dos cosas que se recalculaban una vez **por evento paralelo y por
cuadro**, y las dos contestaban siempre lo mismo. El mapa tiene once páginas
paralelas, así que cada una se pagaba once veces:

* **`un_paralelo` llamaba a `pagina_desde_eleg`**, que resuelve cuál es la
  página activa del evento y le lee del cartucho los veinticuatro bytes de la
  cabecera, por la ventana de banco. RM2k no hace eso: `Game_Event::page` es
  una instantánea y sólo la reescribe `Game_Map::Refresh`. Ahora la página
  viaja **en la lista de paralelos**, que `aplicar_paginas` rehace entera.
* **`ranura_del_evento` recorría las doce ranuras de ruta siempre**, y en este
  mapa hay **una sola usada**. Ahora `ruta_ev_tope` dice hasta dónde vale la
  pena mirar y la búsqueda va de ahí para abajo.

Lo medido con `pruebas/consola.py` —`vueltas` contra cuadros de hardware—,
sobre `562f829`:

    main                                   30,00 fps
    main + la página en la lista           30,00 fps
    main + el tope de ranuras              30,00 fps
    las dos                                59,80 fps   (598 de 600 cuadros)

    mapa 8   60,00 -> 60,00     mapa 6   60,00 -> 60,00

**Ninguna de las dos alcanza sola, y ése es el resultado que conviene no volver
a medir**: perder el cuadro no cuesta un poco —se pierde el vblank entero y se
cae a la mitad exacta— así que quedarse cerca del borde da el mismo 30,00 que
estar lejos. El primer arreglo, solo, había dado 57,67 sobre el árbol de antes
del minijuego de las piedras; ese mismo arreglo sobre el `main` de después da
30,00, porque el presupuesto del cuadro se movió. **Un número de fps de este
mapa vale sobre el árbol donde se midió y sobre ningún otro.**

Lo demás que quedó medido:

* **No es el refresco.** En los 600 cuadros, `refresco` y `refresco_cuadro` dan
  **cero**: el filtro `VAR_REFRESCO` ya evita que las variables que escriben
  estas páginas pidan refresco.
* **Los once paralelos** son los índices de evento 1 a 8, 26, 29 y 65 —TheIdol,
  Light1 a Light6, LTSentry1, LTSentry2, LTComputer y NVSpy—. El duodécimo
  candidato, el `EV0017`, es el del minijuego de las piedras y **no entra en la
  lista con el mapa 11 solo en el cartucho**; no se investigó por qué.
* **Lo que queda son dos cuadros de cada 600.** Ya no es la caída a la mitad. Si
  alguna vez molesta, lo que sigue arriba es el cuerpo de los once intérpretes
  —la cadena de `cmp` que despacha cada opcode se paga por comando— y el paso
  de sus eventos, que RM2k también hace.

**La red que se perdió, y con qué se reemplazó.** Antes `un_paralelo` volvía a
preguntar si la página activa seguía siendo paralela, así que una lista vieja no
hacía daño. Ahora la lista es la única verdad, y lo que la cuida es
`pruebas/test_paralelos.py`: un switch que cambia qué página está activa tiene
que sacar al evento de la lista **y volver a meterlo** al apagarlo. Los dos
casos son del juego —el LTSentry1 pasa a su página de contacto con el switch 45,
el NVSpy a la de acción con el 48—. Comprobado en rojo sacándole el `stz par_n`
a `aplicar_paginas`; el de los fps, poniendo el tope en las doce ranuras.

**El banco 0 quedó en 8 bytes libres**, medidos con bisección y con el cartucho
de `demo-ciudad`, contra los 15 de antes. Las dos piezas pedían 84 y hubo que
devolverlos: `ruta_para_evento` tenía copiadas las dos búsquedas de ranura y
ahora las llama, el tope lo sube `ranura_libre`, `PAR_BYTES` y
`PAR_LISTA_BYTES` pasaron a ocho para que el índice salga con tres `asl`, y
`hdma_mascara` se fue a RODATA —el HDMA lee del banco que diga `A1B3`—.

### El recorrido largo: se juega el juego y se le pregunta a la RAM (2026-09-13)

`pruebas/test_recorrido.py`, con su arnés en `pruebas/recorrido.py`. Es lo que
pidió taro: **emular una jugada entera** y verificar el estado con lecturas de
RAM, sin referencia de por medio, sacando una captura en cada hito para que él
las bendiga a mano. Son dos jugadas:

    apertura   del reset a la cinemática del mapa 1 y de ahí, caminando, al
               Linkage Block
    talan      el cartel de "One year previously", el despertador, la puerta a
               Lashe City, la corrida al trabajo, la fábrica de Delcentric y el
               guardia que abre el auditorio

**Cuesta 3,1 s** con el cartucho armado y 23,6 s la primera vez, que es cuando
lo arma: son 6.900 ticks de emulación —menos de tres segundos a 2.900 ticks/s—
y el resto es el cartucho. Lleva **ocho mapas** (4, 1, 2, 7, 8, 16, 17, 18) y no
los veintinueve de `demo-ciudad` justamente por eso: la conversión de los 29 son
dos minutos.

Lo que hay que saber del arnés, porque es lo que lo hace no envejecer:

* **Nada se cuenta en cuadros.** Cada hito es una condición de RAM con tope, y
  cuando un tope se agota el mensaje dice en qué hito y con qué estado —mapa,
  celda, hacia dónde mira, si hay página corriendo—.
* **Por dónde se camina sale del juego original**, no de una lista: un BFS sobre
  `rm2k.passability_map`, la misma tabla que usan el conversor y la referencia.
* **Y a dónde ir, también.** `Recorrido.viajar(mapa)` planea sobre un grafo de
  **islas**: un nodo es "esta isla de este mapa" y una arista es un `Teleport`
  de un evento cuya página está activa **con los switches que la partida tiene
  puestos ahora**, que se le preguntan a la RAM. El plan se rehace después de
  cada puerta.
* **Tres cosas que costaron y conviene no volver a descubrir**: los mapas de
  ciudad son bandas de calle separadas por pared unidas por teletransportes, así
  que el mapa 8 tiene 32 islas; una puerta **no es una celda de la isla**, y
  contándola adentro el planificador creía que se cruzaba el mapa 9 caminando
  por arriba del teletransporte que devuelve a Lashe City; y la colisión
  **depende de los switches**, porque un evento de la capa de abajo con gráfico
  de tile le impone sus bits a la celda —con la página del arranque, la casa de
  Talan no tiene salida—.

Lo que queda abierto:

* **Las capturas no están bendecidas.** Están en `pruebas-manuales/recorrido/`
  con su `LEEME.txt`. Cuando taro diga que están bien, compararlas es una línea.
* **De Lashe City a la fábrica no se camina, y está medido**: el grafo de islas
  dice que desde la casa de Talan se llega a los mapas 7, 8, 9 y 10 y a ninguno
  más. La isla del mapa 9 donde están los eventos 28 y 29 —la puerta de
  Delcentric— sólo se alcanza desde el HQ de los Lazer Teeth, y el camino lo
  corta el teletransporte de (64,49), que con el switch 24 puesto devuelve a
  Lashe City. Así que la prueba entra al mapa 16 con `ir_al_mapa(16, 53, 7)`,
  que son **las coordenadas del juego**: las del `Teleport` de los eventos 65 y
  66 del mapa 8 y de los 28 y 29 del mapa 9. Si eso es un bug del port o el
  juego pide hacer antes la misión de los Neon Viper, no se investigó.
* **El grafo no entiende condiciones que no son de switch** —objeto, actor,
  cronómetro—: esas páginas las da por no activas, que es el lado seguro.

### La pantalla rota del mapa 17 es del cartucho, no de la escena (2026-09-13)

Medido con el recorrido de arriba, que es lo que lo destapó: **el mismo
recorrido, tick por tick, con dos cartuchos distintos** da la fábrica perfecta
con ocho mapas y basura con los veintinueve de `demo-ciudad`. Y la conversión
del mapa 17 es **idéntica** en los dos —217 tiles, 52 colores, 475 de sprite, el
mismo reparto de VRAM, ninguna animación de batalla—, así que lo que cambia no
es el mapa.

Con los 29 mapas se rompe en **un solo tick**, 160 después de entrar al mapa 17
desde el 16, con la página de la escena corriendo y el héroe quieto en (36,73):
el cuadro anterior está limpio y el siguiente tiene el fondo entero con rayas de
ruido. Los dos cuadros están guardados en `pruebas-manuales/recorrido/`, que es
lo que taro pidió para armar una golden artificial.

Y **no es sólo el dibujo**: con la pantalla rota el cuadro de texto del guardia
no se cierra nunca —`msg_lineas` queda en 79, que no es un número de renglones—
así que el auditorio no se abre. La pinta es la de un DMA a la VRAM de fondo
desde la dirección equivocada, y el mapa 17 es de los que no entran en la
ventana de 64x32 y la ROM va redibujando.

Lo que **no** se hizo, porque es de la otra vuelta que corre en paralelo:
bisecar qué mapa de los 29 lo enciende.

### La pantalla hecha basura: era el bloque de textos cruzando de banco (2026-09-13)

taro veía la pantalla convertirse en una ensalada de tiles al llegar a la
fábrica, y seguía rota de ahí en adelante —la captura es
`pruebas-manuales/2026-09-13-f30be91/demo-ciudad-0006.png`—. **Encontrado y
arreglado**, y no era ni el pan ni el cronómetro.

**Qué era.** `OP_MESSAGE` lleva un desplazamiento de dieciséis bits dentro del
bloque de textos, y `msg_empezar` lo sumaba al puntero **de a dieciséis bits**,
perdiendo el acarreo y dejando el banco fijo. El bloque mide 48972 bytes con
los 29 mapas de `demo-ciudad` —más que los 32 KB que mide la ventana de un
banco de LoROM— y arranca en `$46:8000`, así que **todo cuadro de texto con
desplazamiento mayor a $8000 leía de otro lado**: `msg_ptr` quedaba en
`$46:1370`, que ni siquiera es ROM. Es la misma trampa que `ptr_mas` ya sabía
para la grilla del mapa: lo que sigue a `$FFFF` no es el `$0000` del banco
siguiente sino su `$8000`.

**Por qué rompía la pantalla entera y no sólo el texto.** De esa basura salía
un largo de renglón de **70 caracteres** contra los 39 que entran, y
`componer_char` no topa la columna: escribió fuera de `texto_buf` —1920 bytes
en `$01C8`— y se llevó puesto `vq_n`, que vive justo detrás de los 544 bytes de
la imagen de OAM. Con `vq_n` en 51, `vram_drenar` empezó a subir bloques de 128
bytes a direcciones cualquiera de la VRAM —medido: `$5555`, `$5655`, `$5755`,
`$5855`, o sea encima del tilemap del mapa— durante los diez cuadros que tardó
en drenar la cola inventada.

**Cómo se reprodujo**, que es lo que costó: entrando al mapa 16 con
`pruebas/consola.py`, dejando correr la escena y pasando a la fábrica. Contra
la referencia, en un cartucho con los 29 mapas de la demo:

    cuadro 1200   0,58%     1282  34,49%     1290  66,94%
    cuadro 1250   0,58%     1283  43,12%     1300  70,93%

y con el arreglo puesto, **0,58% en los seis**. Ese 0,58% que queda es anterior
y está en los cuadros de antes del mensaje; no se investigó.

**El caso de la tanda es `texto-lejos`**, y para que fuera barato hubo que
inventar algo: reproducirlo de verdad pide un cartucho de diez mapas hablados
—minutos por caso—, así que `--relleno-de-mensajes` mete bytes muertos delante
del bloque y corre los desplazamientos más allá del banco con **un solo mapa**.
Lo usan los dos lados con el mismo número, así que los desplazamientos siguen
coincidiendo. Comprobado en rojo con el `msg_empezar` de antes: **3116 pixeles
en el cuadro 60 y 3404 en el 400**.

Lo que quedaba abierto de esto **está hecho el 2026-09-14**, y encima hizo
falta: el arreglo de arriba era la mitad del defecto. Ver "La otra mitad del
bloque de textos", abajo.

* **El tope de columna está puesto**, en `mensaje_tick` y no en `componer_char`.
* **`vq_n` sigue pegado al final de la imagen de OAM.** Ya no es lo que decide
  si la pantalla se rompe —para llegar hasta ahí hay que escribir fuera del
  buffer, y eso el tope ya no lo deja— así que separarlos pasó a ser prolijidad
  y no red. Y la RAM del banco 0 no sobra: la BSS está al tope.

### La otra mitad del bloque de textos: un cuadro **encima** del borde (2026-09-14)

taro lo reportó jugando en la SNES: *"se rompen los gráficos en la cinemática de
neon vipers ayudando a Talan, en el mapa del HQ de los Lazer Teeth"*, y que se
arregla al pasar al mapa siguiente. La foto de la tele es el mismo aspecto que
la de la fábrica: el mapa entero con los tiles pisados por basura.

**El mapa es el 14, `NV Get Talan to Work`** —la escena pasa delante del
escondite de los Lazer Teeth, que es lo que lo hacía parecer el 11—. Y el
defecto es el hermano del de arriba: **el arreglo del 2026-09-13 tocó
`msg_empezar` y no el compositor.** `msg_ptr` es un puntero largo pero
`mensaje_tick` lo avanzaba con un `inc` de dieciséis bits, así que un cuadro de
texto cuyos bytes caen **encima** del borde de banco arranca bien y sigue
leyendo el `$xx:0000` del mismo banco, que en LoROM no es ROM.

Con `demo-ciudad` hay exactamente **un** cuadro así, porque el bloque está
alineado al banco y lo cruza una sola vez: el cuarto de la escena del mapa 14
—"Not yet, man. I'm surprised the Vipers..."— que arranca dos bytes antes del
borde. Medido con `pruebas/consola.py`, entrando al 14 y dejando correr la
cinemática:

    antes    el cuadro en $47:FFFA, largo de renglón 76, vq_n 23
    después  el mismo cuadro, largo 39 como máximo, vq_n 0

Y con `vq_n` en 23, `vram_drenar` sube bloques de 128 bytes a direcciones
cualquiera de la VRAM, que es la pantalla hecha basura que taro vio.

**El tope de columna, que era la deuda declarada, está puesto de paso** —y
habría cazado esto: con él, ese largo de 76 se hubiera visto como un renglón con
la mitad del texto y nada más—. Va en `mensaje_tick`, corta el dibujo y **no la
lectura**: el byte se consume igual, porque si no el renglón que sigue
arrancaría del medio de éste. Lo cobran `pruebas/test_compositor.py` —dos casos,
comprobados en rojo: 207 bytes escritos fuera de `texto_buf` sin el tope, y el
puntero corto con un tope ingenuo— y el caso `texto-cruza` de la tanda, que es
`snes-texto` con el relleno puesto en 32766 para que el cuadro quede a caballo
del borde. Verificado en rojo con el `inc msg_ptr` de antes: **3414 pixeles en
el cuadro 60**.

**Lo que cuesta**: 29 bytes del banco 0. Con `demo-ciudad` quedan **56** libres,
medidos por bisección con un `.res` en `TABLAS`.

Lo que queda abierto:

* **La pantalla rota del mapa 17 ya no se reproduce**, y no está claro que la
  haya arreglado esto. Medido el 2026-09-14 con el mismo recorrido de
  `test_recorrido.py` corrido sobre el cartucho de 29 mapas —entrar al 16,
  dejar correr la escena y pasar al 17— y mirando los 400 ticks siguientes:
  **cero anomalías, y la captura del tick 400 sale limpia, con y sin el
  arreglo puesto**. O sea que sobre este árbol ese camino ya no pasa por
  ningún cuadro roto; lo más probable es que fuera el mismo defecto y que el
  reparto del bloque de textos se haya movido —hoy el único cuadro que cruza el
  borde es el del mapa 14—, pero eso **no está medido** y su sección se deja
  como estaba.
* **Los renglones de más no se topan, y no hace falta.** Una cabecera de basura
  puede pedir siete renglones —`CABECERA_LINEAS` son tres bits y la ventana
  tiene cuatro— y el lazo de `mensaje_tick` corta igual en
  `VENTANA_LINEAS_TEXTO`, así que no desborda nada: los de más no se dibujan ni
  se consumen, y el puntero del cuadro que viene no arrastra nada porque
  `msg_empezar` lo recalcula desde el operando. Queda anotado para no volver a
  mirarlo.

### Lo que se descartó buscando esto, para no volver a medirlo (2026-09-13)

El encargo traía dos hipótesis y las dos eran falsas. Queda escrito porque
medirlas costó la mayor parte de la vuelta:

* **El `PanScreen` con los parámetros del juego no tiene nada que ver.** La
  tanda lo probaba con distancia 2 y velocidad 2 y el juego usa 10 y 4; corrido
  tal cual —`just snes-pan 6 "2 2 10 4 1" "10 20 40 60 79 80 81" 115`— da
  **0,00% en los siete cuadros**.
* **La escena entera del mapa 16 anda**, en un cartucho de dos mapas y en otro
  con los veintinueve de la demo, entrando por la celda (53,7) que es por donde
  entra el juego: cuadros 100, 300, 700, 800, 850 y 900 en **0,00%**.
* **El cronómetro llegando a cero tampoco era.** Con una página de prueba que
  lo arranca en un segundo y hace el pan de 10/4, el cuadro 60 da **252
  pixeles (0,44%)**, todos en los dígitos —y da los mismos 252 **sin** el pan—.
  Es una divergencia de un tick en el cuadro en que el cronómetro se apaga, que
  `timer-cero` no ve porque mira los cuadros 2, 40, 59 y 61 y **se saltea justo
  el 60**. Sigue abierta y es cosmética.
* **Y el cronómetro corriendo de verdad por la escena entera tampoco**:
  inyectado con 600 segundos desde el primer cuadro del mapa 16, visible, y
  parado por el `TimerOperation` de la escena, la pantalla sigue igual.
* **No era el vblank desbordado**: con `push_strips` al principio de
  `flush_video` y con blanking forzado durante todo el vblank la pantalla sale
  byte por byte igual, y con dos contadores en la RAM `build_row` y
  `push_strips` van en lockstep.

**El rojo que apareció de paso y sigue abierto:** cuadro **500** de la escena
del mapa 16, **43,86% (25153 de 57344)**, en los dos cartuchos. Leyendo la
WRAM, en el tick 490 la ROM tiene al héroe en 368 y la cámara en 248 y la
referencia 378 y 258: **la ROM arranca el `MoveEvent` que sigue al tercer
teletransporte interno —el que va a (24,15)— cuatro ticks antes**, y la
pantalla queda corrida ocho pixeles hasta que el teletransporte siguiente las
vuelve a sincronizar. Ningún caso de la tanda corre una página con un
`Teleport` al mismo mapa, que es por donde se coló.

Y una trampa de medición que costó una hora: **el tinte de pantalla sobrevive
al cambio de mapa**, así que saltar a un mapa desde el de arranque lo deja todo
azul —tinte 0,0,100— y parece el defecto. Para mirar un mapa inyectado hay que
poner `tinte_r/g/b` en 100 primero.

### Los encuentros al azar (2026-09-13)

taro jugó y reportó que no aparecía nada ni en `Sector 30 Back Alleys` (20) ni
en los Rat Tracks (21 y 26). No estaban hechos; ahora sí. El porqué durable
—cómo se dispara, qué se simplificó y con qué número— está en el README, "Los
encuentros al azar". Lo que hay que saber para trabajar encima:

* **Los datos viven en el árbol y no en el `.lmu`.** `lcf.TreeMap` lee ahora
  `encounters`, `encounter_steps` y `area_rect`, y el comentario que decía que
  el tipo 2 era una carpeta del editor está corregido: es un **área**.
* **El alcance, medido**: 23 áreas colgando de 20 mapas, 33 mapas con tropas
  propias y ninguno con las dos cosas, o sea **53 mapas de 328** donde puede
  salir un encuentro. De los 29 de `demo-ciudad` son **cinco**: el 20, el 21,
  el 26, el 28 y el 32. Son 129 tropas distintas en todo el juego.
* **Dos simplificaciones medidas, y las cobra `pruebas/test_encuentros.py`**:
  ningún terreno que pisen esos mapas tiene `encounter_rate` distinto de 100, y
  ninguna de las 129 tropas filtra por terreno. Las dos son ciertas hoy y
  pueden dejar de serlo sin que se mueva un pixel; por eso las cobra una prueba
  de datos.
* **El azar tiene semilla propia**, `ENC_SEMILLA`, como la pelea. Caminar no le
  corre el azar al mapa, y por eso la referencia puede predecir las dos cosas.
* **Nueve bytes de RAM lejana en `$7E3900`**, `FAR_ENCUENTRO`. En el banco 0 no
  entraban: la BSS está en **7680 de 7680**, medido metiéndole un `.res 64` y
  mirando el corte de w65. Al repartir direcciones de RAM lejana, ésa está
  tomada.
* **Las tablas y las rutinas viven fuera del banco 0**, en RODATA; del otro
  lado quedan cuatro `jsl` y el puente a la pelea, que son **43 bytes**. No
  entraban: `demo-ciudad` tenía **8 libres** —medido con un `.res` en `TABLAS`,
  que es lo que AGENTS.md manda— así que bajó `item_switch` a RODATA, 124
  bytes: es la tabla más grande de las que se leen con X y no están en ningún
  lazo por cuadro. Con eso quedan **89 libres**, medidos igual.
* **`op_battle` se partió en dos**: su cuerpo es ahora `pelea_arrancar`, y lo
  llaman el opcode y el encuentro. Un encuentro pelea **sin bytecode**, así que
  no tiene cursor que guardar ni manejadores a los que saltar. **Es lo único
  que esta vuelta le toca a la pelea**; `batalla.py` no se tocó.
* **El caso de la tanda es `snes-encuentro`** y `--encuentros-de-prueba` es el
  flag que lo hace corto —los dos lados lo toman igual—. Con los pasos del
  juego el encuentro sale recién a los ~130 pasos; con 8, en el paso 8.

Lo que queda abierto, con su número al lado:

* **Se pelea sobre el color plano.** Un `EnemyEncounter` trae el nombre de su
  fondo en el string del comando; un encuentro al azar no trae ninguno —en RM2k
  sale del terreno—. Ponerlo son 32 KB de cartucho **por tropa**, y las cinco
  áreas de `demo-ciudad` tienen 22 tropas entre todas: 704 KB. Si taro lo
  quiere, lo primero a decidir es cuántas.
* **Perder no lleva a ninguna parte**, porque no hay pantalla de Game Over. Es
  la misma deuda que ya tenía `EnemyEncounter` con `defeat_mode` 0.
* **El acumulado no viaja en la partida.** Al cargar arranca en cero, como al
  entrar a un mapa; en RM2k se guarda. No cambia un pixel y evita tocar
  `partida_tabla`, que acaba de mudarse de banco.
* **`ChangeEncounterSteps` sigue sin compilar**, y ahora por una sola razón:
  aceptarlo despierta la automática `DaliaGoingToTasgarde` del mapa 66 —el
  único mapa sin ventana de las pruebas de estado— y se caen dos casos de
  `test_condicional.py`. La cuenta que le faltaba ya está hecha; lo que falta
  es mudar esa ROM de prueba a otro mapa que tampoco acepte la ventana. Son +14
  páginas y ninguna cerca de los primeros diez minutos.
* **Los encuentros no se apagan desde adentro del juego**, justamente por lo de
  arriba: las trece apariciones que ponen `encounter_steps` en cero son las que
  RM2k usa para apagarlos durante una escena. Ninguna cae en un mapa de
  `demo-ciudad`, así que hoy no se nota.
* **Un encuentro pendiente que una página nueva pisa.** En RM2k lo tira:
  `Game_Interpreter::Push` hace `SetEncounterCalling(false)` cuando arranca una
  página de primer plano, igual que con el pedido de menú. Acá se **guarda** y
  se cobra cuando la página termina. Son unos pocos bytes del banco 0 —que no
  sobran— y no lo mira nadie: para caer ahí hay que pisar un evento de contacto
  en la misma celda donde salió el encuentro. Está escrito igual de los dos
  lados, así que la comparación sigue valiendo; lo que diverge es contra RM2k.
* **Lo que ninguna prueba mira**: un encuentro que salga **con una página
  automática corriendo** o con un mensaje abierto. El modelo dice que espera
  —es el orden de `UpdateNextMovementAction`— y los dos lados lo escriben
  igual, pero ningún caso pasa por ahí: en el mapa 21 nada corre mientras se
  camina.

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

### Tres vueltas en paralelo, mergeadas (2026-09-12)

taro pidió tres cosas a la vez y se hicieron en tres worktrees. El árbol
combinado da **134 casos de la tanda en verde** y **94 pruebas de estado** más
el `xfail`, sobre la foto `25d1006`.

* **Lashe City hasta la escena del auto**: la demo pasa de 10 mapas a 29 —la
  fábrica, el auditorio, los Rat Tracks, el Sector 27 y el galpón—. El alcance
  salió del árbol de mapas, que ABL usa como carpetas y nuestro volcado a JSON
  no guarda: el subárbol del nodo 15. De paso apareció que **una página
  automática vacía se repetía para siempre** —45 páginas en 35 mapas— y hacía
  injugable Rat Tracks B1, con los dos lados equivocados igual.
* **Las animaciones de batalla se dibujan**, en una caja de 64x64 topada por los
  64 tiles libres de VRAM de sprites, con los cuadros prerenderizados y subidos
  por DMA. Achicadas: la 79 al 12% y la 82 al 11%, que **taro tiene que juzgar**.
* **Hay batalla por turnos** y las dos peleas de la intro se pelean. Las
  fórmulas están escritas de los dos lados y la prueba exige el HP exacto turno
  por turno.

**Lo que no entra: las tres cosas juntas en 2 MB.** Con 29 mapas se emiten siete
animaciones —286 KB— y el área se pasa por **218 KB**. Antes de las animaciones
quedaban 68 KB libres, así que recortarlas no alcanza. Las salidas medidas:
subir el cartucho a 4 MB —que **no es cambiar un número**: en LoROM la SRAM vive
en los bancos `$70`–`$7D`, justo donde aterrizaría la ROM, así que pide tocar el
mapeo y verificarlo en hardware—, o repartir en dos demos. **Sin decidir.**

Y dos deudas que dejaron los agentes, las dos con el número al lado:

* **El tema del título se caía del banco de muestras** con Lashe City adentro:
  arreglado el 2026-09-12, ver abajo. Y lo de "con pista de MSU-1 suena igual"
  era falso y está medido: se caía de la **lista**, no del banco, y sin número
  no hay pista que tocar.
* **De las 40 páginas del juego con batalla compilaba una sola**, y a 30 de
  las otras 39 las cortaba `ChangeEscapeAccess`. Hecho el 2026-09-12 —un bit al
  lado de los dos de `FAR_ACCESO`— son **19 de 40**, y las otras tres de esa
  cuenta las puso la orden 9. El permiso se guarda y viaja en la partida; **no
  lo lee nadie todavía**, porque la huida es de la batalla. Lo cobran dos
  pruebas de estado, no la tanda: sin nada que lo lea, el bit no cambia un
  pixel.

### Volver de una pelea dejaba el mapa hecho basura (2026-09-13)

Lo que taro reportó jugando `pruebas-manuales/2026-09-13-f30be91/demo-ciudad.sfc`:
*"las batallas rompen los gráficos consistentemente, y nunca se arreglan
después de eso"*. Arreglado, y el porqué durable está en `volver_de_batalla` en
`main.s` y en el comentario de `snes-vuelta`.

Era **VRAM que nadie reponía**. `escena_subir` sube 32 KB —las palabras $4000 a
$8000— más su tilemap en $3800 y 64 bytes en la palabra 0, y `volver_al_mapa`
reponía nada más que el banco de tiles de BG1 y el de la capa de encima. Lo que
quedaba pisado, medido con la VRAM del core: el tilemap del mapa ($5800), el de
la capa de encima ($7800), los tiles de la ventana de mensaje ($6800) y el
banco de sprites —entero en `LAYOUT_ANCHO`, que lo pone en $4000; los dos
primeros tiles del héroe en los repartos con ventana, que lo ponen en 0—.

**Alcanzaba con `volver_al_mapa` porque hasta ahora sólo volvían de ahí la
tienda, el menú y las ranuras**, que escriben nada más que `RANURA_VRAM` y
`RANURA_MAP` —elegidos justamente para caer adentro del banco de BG1 en los
cuatro repartos, ver `_controlar_ranuras`—. La pelea fue lo primero que se sale
de esa caja, y nadie lo notó porque **ningún caso de la tanda cruzaba una
batalla**: `snes-batalla` abre la pantalla de la pelea y nunca sale.

Ahora lo cubren dos casos, `vuelta` y `vuelta-ventana`, uno por reparto de
VRAM. Verificado que dan rojo con el `volver_al_mapa` de antes: **74,30% y
77,49% de los pixeles**. La referencia no cambió ni tenía que cambiar: la pelea
no cuesta ningún tick y del otro lado el mapa se dibuja como si no hubiera
habido pelea, así que que la ROM dibuje eso mismo **es** la prueba.

Dos cosas que conviene saber de cómo quedó:

* **La reparación va en `volver_de_batalla` y no adentro de `volver_al_mapa`**,
  para no cobrarle a la tienda, al menú y a las ranuras las 64 columnas de
  `fill_window` —el único momento en que se escribe tanto tilemap de una vez—,
  que ellas no necesitan y que les costaría un cuadro perdido de más.
* **`load_npcs` y `load_ruta_graficos` siguen sin ir ahí**, a propósito: copian
  tablas del cartucho a RAM y borrarían lo que los eventos hayan movido antes
  de la pelea. Lo único que se toca de `npc_buf` es el byte +12, que es la
  sombra de qué pose tiene cada ranura en la VRAM: se pone en $FF para que el
  próximo `subir_pose_npc` la vuelva a encolar, porque `load_sprite` acaba de
  dejar ahí la del cartucho.

Y una cosa que **no era de esto**, medida de paso y que conviene no volver a
medir: el *"héroe como un rectángulo beige liso"* de las capturas `0012` y
`0013` **no lo causa la batalla**. Se reproduce igual en un cartucho sin pelea:
el líder entra a Lashe City Interiors (mapa 10) con el grupo `11 12 13` y se
dibuja como una silueta de un solo color, con los NPCs de al lado bien. Dos
capturas del mismo tick, una con pelea y otra sin, dan **cero pixeles de
diferencia**. Es un defecto aparte, sin investigar, y hoy no lo cubre nada.

**Y el banco 0 tenía dos bytes libres.** Los cuarenta y seis que costó esto
dejaban `demo-ciudad` en 32748 de 32704, así que se mudó `items_banco_subir`
—131 bytes— a RODATA, con `jsl` y `rtl`. Es la más barata de mudar de todo lo
que mide más de cien: no llama a nadie, así que no pide ningún puente, y corre
al abrir una pantalla con el PPU apagado, no por cuadro. Quedan **81 bytes
libres**, medidos poniendo un relleno de 200 en TABLAS y leyendo lo que dice
`w65`. **Lo próximo que agregue código al banco 0 los va a necesitar**, y la
lista de candidatos a mudar sigue ahí: `titulo_subir` son 227 bytes y
`ranura_banco_subir` 131, las dos del mismo tipo.

Lo que **queda pisado y no se repone** después de una pelea, medido y declarado
porque no se ve: los tiles de fondo, de la capa de encima y del tilemap que
están **más allá de lo que el mapa usa** se quedan con la escena adentro. No se
dibujan nunca —ni el mapa los indexa ni el streaming los muestra— y un cambio
de mapa tampoco los limpia, exactamente igual que se quedan con los restos del
mapa anterior en un teletransporte normal.

### La persecución en auto, jugada (2026-09-13)

taro probó `just snes-demo-carrera` en mednafen y reportó tres cosas. Son tres
causas distintas y **sólo una es del intérprete**; las otras dos eran de cómo
entraba la demo. Lo medido, todo con la firma completa de `compilar_pagina`
—`mensajes`, `eventos_mapa`, `temas`, `graficos`, `imagenes`— y con los cuatro
`indexar_*` llamados antes:

    mapa 49   46 páginas disparables, 44 compilan
    mapa 52   44, compilan 43          mapa 50   2, compilan 2
    mapa 54   44, compilan 43          mapa 51   16, compilan 15
                                       mapa 53   2, compilan 1

De las seis que no compilan, **cuatro son el mismo comando**: el
`KeyInputProc` **sin espera** de `RaceController2`, que es el volante. Las
otras dos eran la intro de Talan del 49 —un `KeyInputProc` que espera cualquier
tecla, que compila desde el 2026-09-13— y el `GiveOutRewards` del 53, que se
cae en un `ConditionalBranch`. O sea que hoy son cinco.

**1. La carrera no corre sola: es el volante, y es lo único grande que queda.**
Quien mueve el auto es `RaceController2`, una página **paralela** que en cada
cuadro le fuerza al héroe la ruta `28 1 29` —acelerar, un paso a la derecha,
desacelerar— y además lee el pad para esquivar. Sin ella el héroe camina libre
y a la velocidad que le dejó `RaceController1`, que es exactamente lo que taro
describió. El comando vale **+5 páginas** del juego entero —mapas 49, 51, 52,
54 y 285— sobre una base de 5348 de 5603 disparables.

Lo importante: **los dos lados ya lo hacen**. `op_key` en `main.s` y
`OP_KEY` en `eventos.py` cubren la forma que no espera; el único que la
rechaza es el `raise` de `KEY_INPUT_PROC`, y lo rechaza por el arnés. Medido
con `TECLA_SIN_ESPERA=1`, que es el interruptor que se agregó para no tener que
volver a parchear a mano:

    la carrera corriendo sola, ROM contra referencia, --walk none
    y 900 cuadros —el auto cruza las 500 columnas del mapa—:   0,00%

    just snes-heroe 52, apretando la izquierda:
      sin nada                                                55,42%
      con la ruta forzada mandando sobre el pad                0,59%   (248 px)
      las otras cuatro direcciones, en los dos casos            0,00%

O sea que **la ROM está bien y lo que falta es la referencia**. La mitad del
arreglo entró: `hero_position` respeta la ruta forzada, como `move_hero`. La
otra mitad es que la caminata avance **cuadro a cuadro** en vez de celda a
celda: hoy vive los cuatro cuadros de una celda de un saque y la página
paralela le puede reponer la ruta en el medio, cosa que la consola sí ve. Y
hay un segundo problema que apareció midiendo y que hay que decidir antes:
**con la carrera corriendo, `snes-heroe 52` no termina**, porque el volante le
repone la ruta para siempre y "apretar hasta chocar contra la pared" deja de
tener final; el lazo corta en su tope de 10000 vueltas, 27566 cuadros de
emulador para una sola dirección. El mapa 52 está en `rom/hitos.txt`.

**2. Los obstáculos: la mitad no era un defecto y la mitad sí.** Los 40 autos
del tráfico son los eventos 4 a 43 del mapa 49 y **sus 40 páginas compilan**.
Dos números:

* **El primero está en la columna 70**, y una pantalla son 16 celdas. En las
  dos primeras pantallas no hay ninguno **tampoco en el original**.
* Pero **están todos entre las filas 23 y 28**, y la demo plantaba al héroe en
  la fila 20: sin `--inicio`, el conversor elige el tile abierto más cercano al
  centro. En la fila 20 no hay ni un obstáculo, y los cinco eventos que
  terminan el nivel —los que saltan al mapa 52— están entre la 23 y la 27. Con
  el volante puesto se ve entero: el auto cruzaba las 500 columnas sin chocar
  con nada y sin llegar a ninguna parte. La celda de entrada es (1,26) y sale
  del `Teleport [49, 1, 26]` del evento 3 del mapa 36, que es por donde el
  juego entra. La receta ahora la pasa.

**3. El auto tardaba en aparecer, y hasta entonces el héroe salía sin
gráfico.** No era el arreglo de `lideres_posibles` a medio camino: era el grupo
de la demo. Con `--grupo 10` el líder es `DummyHero`, cuyo sprite es una celda
vacía a propósito, y quien mete a `CarRED` es `RaceController1` **después** de
su `PanScreen`, que son 7 celdas a velocidad 4, o sea `7 * 256 / (2 << 4)` =
**56 cuadros**, y espera. Medido en snes9x: el auto aparece en el cuadro 60 y
antes no hay nada. La receta ahora entra con `--grupo 14`, Talan, que es con
quien el juego llega hasta acá: verificado, se lo ve desde el cuadro 1 y el
auto lo reemplaza en el 60. Los 56 cuadros de cámara corriendo siguen ahí y son
los del original.

Lo que queda abierto:

* **El volante**, con todo lo de arriba. Es lo que hace jugable la escena.
* **La intro de Talan del mapa 49** —`RaceControllerZERO`, el cartel de los
  controles— **compila desde el 2026-09-13**: su `KeyInputProc` espera
  cualquier tecla, que es la forma que entró con el minijuego de las piedras
  (ver su sección). La demo sigue entrando con `--switch 171` puesto a mano
  porque nadie volvió a mirar esa escena todavía.
* **El `GiveOutRewards` del mapa 53**, el final de la carrera: se cae en un
  `ConditionalBranch`. No se investigó cuál de las doce clases es.
* **La guarda nueva de `hero_position` no la ejercita ningún caso de la
  tanda**, y está dicho en su comentario: con el volante afuera, ninguna página
  compilada le pone una ruta al héroe mientras el jugador camina. Queda como
  código inalcanzable, igual que la guarda de la paleta vacía de
  `tenir_paleta`, no como camino a medias.

### El minijuego de las piedras del mapa 11 (2026-09-13)

taro reportó que en el `Lazer Teeth HQ` **no se podían lanzar las piedras**. El
motor del minijuego es una sola página —`EV0017` página 0 del mapa 11, la única
de las 101 disparables de ese mapa que no compilaba— y la cortaban **tres**
cosas distintas, no una:

* **La variable 5 no tenía ranura.** `variables_de` miraba `ControlVars`, las
  ramas por variable y el cronómetro, y no `KeyInputProc`, que es el único
  comando de este juego que le escribe a una variable sin ser un `ControlVars`.
  **No era circular**: ese barrido mira todos los comandos compilen o no. Son
  dos variables en todo el juego, la 5 y la 151, y el índice pasó de 81 a 83
  ranuras.
* **`KeyInputProc` sólo aceptaba esperar la tecla de acción.** Ahora espera
  también la cruceta y cancelar, con el mismo flanco —`IsTriggered`— y el mismo
  orden de `CheckInput`, de mayor valor a menor.
* **`ChangeEventLocation` con la celda en dos variables** no compilaba, y es
  con lo que la página planta la piedra donde está el jugador. Es el opcode
  nuevo `OP_PLACE_VAR = $27`.

**El corte de `KeyInputProc` era del arnés y no de la ROM**, y ésa es la parte
que conviene entender: la tanda sostenía una dirección desde el arranque con
`--walk`, así que un **flanco** de cruceta a mitad de una escena no lo podía
producir ningún caso, y escribir el camino sin nada que lo corriera es
exactamente cómo sobrevivieron los tres errores del intérprete. Ahora lo
produce `--tocar BOTON:CUADRO`, que está en las dos mitades —`snes_correr.py` y
`snes_expect.py`— y cuenta los cuadros como `--apretar-a`.

Lo que cuesta y hay que saber para usarlo: **un toque de dirección en el mapa no
lo lee sólo `KeyInputProc`**, lo lee también el héroe, que gira y da un paso, y
eso la referencia no lo modela —su caminata va por `--walk`, de a celdas
enteras—. Por eso el caso `tecla-dir` empieza en (22,8) del mapa 6, donde abajo
está cerrado y el héroe ya mira para abajo: el flanco existe y no mueve ni gira
a nadie. Con la celda de siempre el mismo caso da 30% a 41% de pixeles
distintos, que es el héroe caminando de un lado y quieto del otro.

**B queda fuera de la tanda a propósito**: abre el menú de pausa —`pedir_menu`,
que es el `Game_Player::Update` de RM2k, y sólo lo frena que haya una página
corriendo—, y el menú de pausa la referencia no lo modela. Lo cubren dos casos
de estado en `pruebas/test_tecla.py`.

Lo medido, con `eventos.compilar_pagina` sobre las páginas disparables del juego
entero y con `indexar_variables`, `indexar_comunes`, `indexar_animaciones`,
`indexar_audio_de_batalla` e `indexar_actores` llamados antes:

    base                                 5415 de 5667 disparables
    sólo la ranura de la variable        5415  (+0)
    sólo KeyInputProc entero             5415  (+0)
    las dos juntas                       5417  (+2)
    sólo OP_PLACE_VAR                    5415  (+0)
    las tres                             5418  (+3)

**Ninguna de las tres sola vale nada, y ése es el resultado.** Las dos páginas
del `(151, 1, 1, 1, 1)` —`RaceControllerZERO` del mapa 49, el cartel de los
controles de la carrera, y el `EV0011` del 285— necesitan la ranura *y* la
espera de cualquier tecla; la del mapa 11 necesita además el opcode nuevo. Con
eso el mapa 49 deja de entrar con `--switch 171` puesto a mano.

Los absolutos no son los 5198 de 5603 que este archivo trae más arriba, y no
hay que mezclarlos: aquella cuenta arma el contexto de otra manera —un
`Graficos` por mapa y no por página—. **Lo que vale es la diferencia**, que es
+3, y está medida con la misma cuenta de los dos lados.

`ChangeEventLocation` por variables aparece **129 veces en 32 páginas
disparables** y destraba una sola: las otras 31 están frenadas por otra cosa
igual. Se hizo por esa una.

**El banco 0 se pasó otra vez, por 58 bytes**, y hubo que bajar seis tablas más
a RODATA: `tabla_fila_buf`, `mascara`, `pass_salir`, `pass_entrar`, `diag_vert`,
`diag_horiz` y las dos de `fuente_pre`. **Las que quedan arriba se leen con Y**,
y ésa es la razón de que no bajen: el 65816 tiene absoluto largo indexado por X
y **no por Y**, así que `paso_por_vel`, `salto_por_vel`, `anim_parado` y
`anim_continua` pedirían además cambiar de registro en sus llamadores. Medido
con `demo-ciudad` y bisección con un `.res N` en `TABLAS`: quedaban 15 bytes
libres, y **hoy son 8** —ver el lag del HQ, más arriba—. Lo que siga pidiendo
banco 0 va a tener que pasar esos llamadores a X, o mover `paso_dx`/`paso_dy`
—16 bytes y dieciséis accesos, o sea que no rinde—.

Lo que queda abierto:

* **Nadie lo jugó a mano todavía.** Sí lo juega una prueba:
  `pruebas/test_piedras.py` le habla a la reja, aprieta A, aprieta izquierda y
  le pregunta a la RAM dónde quedó el evento `Stone`. Medido: la piedra se
  planta en la celda del héroe —(26,52)— y camina hasta (22,52) en veinte
  ticks, con el héroe quieto. Lo que eso **no** dice es si se siente bien:
  ver `pruebas-manuales/piedras/`.
* **La forma de `KeyInputProc` que no espera sigue afuera**, con su medición
  intacta: +5 páginas del juego y 3 de la persecución en auto, y lo que la traba
  no es el comando sino la ruta forzada del héroe contra el pad. Ver el `raise`
  en `KEY_INPUT_PROC`.
* **El `RaceControllerZERO` del mapa 49 ahora compila**, así que `demo-carrera`
  podría dejar de entrar con `--switch 171` a mano. No se cambió: eso es la
  carrera y no el minijuego, y cambiarlo pide volver a mirar toda esa escena.

### El sistema de batalla que taro dio por inservible: eran dos causas (2026-09-13)

taro jugó `pruebas-manuales/2026-09-13-2a75142/demo-titulo.sfc` y reportó
cuatro síntomas. Medidos, son **dos defectos y una confusión**, y conviene que
quede escrito cuál es cuál porque el reporte los ordenaba al revés.

**Uno: el número de HP del menú estaba horneado en el bloque del actor.** El
panel del grupo lo dibuja el conversor y la ROM lo sube tal cual, así que el
número no podía cambiar nunca; los 40 que taro veía son el máximo de Talan,
que es quien lidera la intro. Ahora las tres cifras las escribe
`menu_hp_escribir` desde `FAR_HP`, de a una celda cada una y con los mismos
bloques que el oro; el máximo y la barra siguen horneados. **Cuesta que las
cifras vayan a 8 pixeles y no a los 6 de la fuente**, que es el mismo precio
que el oro y la pantalla de ítems ya pagan, y que la columna del máximo se
corrió a x=192.

**Dos: perder un encuentro al azar no era Game Over**, y de ahí salían los
otros dos síntomas del reporte. `op_battle` mira `BA_RESULT` y resuelve el
destino de la derrota; el encuentro al azar arranca la pelea sin bytecode
—`pelea_arrancar` desde `move_hero`— y nadie miraba el resultado. Como
`modo_fin` guarda los HP de la pelea en `FAR_HP`, después de una derrota el
grupo quedaba en cero **para siempre** y toda pelea siguiente se perdía sola
antes de abrirse. Medido antes del arreglo, mapa 21 con
`--encuentros-de-prueba 8`: `BA_RESULT` en 2 y trescientos cuadros después la
partida seguía en el mapa; con el arreglo reinicia veintiún cuadros después.

**Y la confusión: los enemigos con HP bajo no eran un defecto.** `ba_armar`
vacía las doce ranuras y rellena los HP desde `enemigo_hp` del cartucho en
cada pelea; medido con dos y tres encuentros seguidos, cada enemigo arranca
siempre en su máximo. Lo que taro vio son los datos del juego: las tropas de
Rat Tracks B1 son GiantRat (20 HP), MutantMouse (25) y HairyVermin (40), y la
pantalla de la pelea muestra el HP de cada enemigo sin su máximo —`BA_CONMAX`
en cero—, así que un GiantRat dice "20" porque tiene 20.

Verificado el 2026-09-14 sobre la foto `151599a`: `just snes-hitos-foto 4` da
**168 casos en verde**, `just pruebas` **164 y 1 xfail**, y `just snes-demo
demo-ciudad` arma con **49 bytes libres** en el banco 0.

Lo cubren, todos comprobados en rojo antes:

    test_menu.py              el menú con los HP que deja una pelea (111 px)
    test_hp_de_batalla.py     pelear, volver al mapa, abrir el menú y mirar
                              el número; y dos encuentros seguidos mirando
                              con qué HP arrancan los enemigos
    test_game_over.py         perder un encuentro al azar reinicia, y el
                              control que gana y no reinicia

**Lo que sigue sin poder hacerse: curar.** Es la otra mitad de *"así que no
puedo curar"* y **no** es del menú: en el mapa, `objetivo_pantalla` con una
medicina ignora A a propósito —"`UseItem` sólo la gasta si sube algo, y fuera
de batalla nadie tiene los HP por debajo del máximo"—, que era cierto hasta
que las peleas empezaron a bajarlos. La cuenta ya está escrita del lado de la
pelea (`ba_item_cura`, con `item_cura_rate` e `item_cura_hp` que el conversor
emite), así que lo que falta es aplicarla sobre `FAR_HP`, gastar el ítem y
repintar la fila. **Sin eso el grupo no se recupera nunca**, porque tampoco
hay posadas ni `ChangeHP` de página que suba.

### Las habilidades: entraron las siete (2026-09-13)

Lo último que taro reportó como faltante de la batalla. Los cinco pasos que la
sección de abajo dejó medidos están hechos, y **de las siete habilidades que el
grupo de la intro sabe entraron las siete**, incluidas las dos que mueven
parámetros, que eran las que podían no entrar.

Cómo quedó, que es lo que hay que mirar jugando:

* los SP son estado —`FAR_SP`, al lado de `FAR_HP`— y viajan en la partida;
* la segunda orden del menú **dice el `skill_name` del actor**: "AgentTrain",
  "Telepathy", "Slicing", "Special". Y el menú está en el orden del original,
  Attack / <habilidad> / Defend / Use Item, con Escape quinta;
* la lista es la de la captura: descripción arriba, dos columnas leídas por
  filas, costo en SP a la derecha, y en gris la que no se puede pagar;
* el efecto es `Algo::CalcSkillEffect`, con el costo de `CalcSkillCost`.

Lo que **no** está y conviene saber antes de mirar:

* **los SP no se ven en la pantalla de la pelea.** Los renglones del grupo son
  nombre, HP y máximo, y en las 32 celdas no entra además "SP nnn" sin achicar
  la columna del nombre, que hoy la comparten con los enemigos —"GangMember LT"
  mide trece—. El original los muestra. Es lo primero que conviene arreglar de
  esto, y pide decidir la columna.
* **la descripción se corta a 31 caracteres.** El original la escribe entera
  con una fuente más chica; acá un renglón de texto ocupa dos filas del tilemap
  y la de abajo no está libre.
* **el nombre de la habilidad se corta a once.** "Healing Syringe" queda en
  "Healing Syr". Misma causa: dos columnas en 32 celdas.
* **las de alcance múltiple no están.** Ver `batalla.habilidad_usable`. En el
  grupo de la intro no hay ninguna; la primera que aparece en un cartucho más
  grande es `Gamble for Credits`, la única de Arden, que queda afuera y lo deja
  sin habilidades.
* **no hay animación de batalla al usarlas.** El `animation_id` viaja en el
  LDB y el port ya sabe dibujar animaciones en el mapa; nadie las conecta.

Y una cosa que este trabajo destapó y no era suya: **`just snes-demo
demo-ciudad` estaba roto desde antes**. El área del banco 0 se pasaba por
quince bytes en `f38b87c` —"32719 en 32704"—, y ningún caso de la tanda lo ve
porque sus cartuchos llevan uno o dos mapas. Se arregló mudando `item_actores`
a RODATA. **Conviene armar la demo después de cada vuelta que agregue código**,
que es lo que el encargo de esta vuelta pedía y por eso apareció.

### Las ramas de actor, y las dos clases que no valen nada (2026-09-13)

`ConditionalBranch` era lo que más páginas trababa de lo que quedaba libre.
Hecho: las preguntas 4 y 5 de la clase 5 —"sabe esta habilidad" y "tiene puesto
este objeto"—, **+28 páginas**, de 5170 a 5198. El porqué durable y el opcode
nuevo están en el README, "Las dos preguntas de actor de una rama". Lo cubren
cuatro casos de la tanda: `rama-equipo`, `rama-equipo-no`, `rama-hab` y
`rama-hab-no`.

Lo medido, y esto es lo que conviene no volver a medir:

* **La "clase 6" no es lo que su nombre sugería y no vale nada.** Según el
  `switch` de `CommandConditionalBranch` en easyrpg-player, la clase 6 es **la
  orientación de un personaje**. Son 124 comandos en 31 páginas, y destraba
  **cero** —medido dos veces, sola y con las dos de actor ya puestas—: esas 31
  páginas están frenadas por otra cosa igual. La clase 2 es el **cronómetro 1**:
  un comando, una página, también cero.
* **Las dos de actor van juntas.** Las 10 páginas que preguntan por una
  habilidad preguntan además por el equipo, así que "sabe la habilidad" sola da
  +0 y "tiene puesto el objeto" sola da +18. Juntas, +28.
* **Lo que queda de `ConditionalBranch` son 32 páginas**, todas de la clase 6 y
  del cronómetro, o sea todas sin valor. La clase de rama dejó de ser lo que
  traba el juego.

Lo que **no** se hizo, con su número:

* **`EnemyEncounter` con Game Over al perder: hecho el 2026-09-13**, y el
  diagnóstico de este renglón era el correcto —eran dos trabajos— pero el
  número estaba viejo: son **15 páginas**, no 3, y juntas dan **+15**. Ver "El
  Bum que trababa el juego, y el jefe de los Rat Tracks", arriba.
* **La elección con rama de cancelar: 1 página, la del mapa 348, y también
  destraba cero**: con el `raise` desactivado se cae en el `ControlSwitches`
  que invierte un switch, que tampoco compila.

Y una deuda declarada que conviene tener a mano: **`ChangeSkills` no compila**
—20 comandos en el juego— así que la respuesta de "sabe esta habilidad" es hoy
la del LDB y nada la mueve. Uno de esos 20 le enseña la habilidad 152 a Arden,
que es justo la que preguntan los mapas 47 y 48. No hay media implementación
corriendo —las páginas que enseñan tampoco compilan— pero el día que
`ChangeSkills` entre, `sabe_hab` tiene que pasar de tabla del cartucho a estado
de la RAM lejana.

### El nivel estaba mockeado en 1, y no era cosmético (2026-09-13)

Lo que se dijo primero sobre las habilidades estaba mal, **y el error era el
dato de entrada**: se midió `hp_max[NIVEL - 1]` con `titulo.NIVEL = 1` y se
concluyó que nadie sabía ninguna, porque todas se aprenden en el nivel 3 o más
arriba. El LDB dice otra cosa —`initial_level`, que el port no leía—:

    Kersh   nivel 20   HP 168  SP 168  atk 80   def 47  spi 85  agi 85
    Core    nivel 15   HP 127  SP 127  atk 117  def 37  spi 64  agi 64
    Manta   nivel 15   HP 127  SP 127  atk 37   def 37  spi 64  agi 64
    con el equipo puesto: Kersh 280/147, Core 237/112, Manta 187/77

Contra 40 HP y parámetros de 15 a 20 que salían del nivel 1. Los HP coinciden
con las capturas de EasyRPG que dejó taro en `pruebas-manuales/capturas-batalla/`,
que es lo que destapó todo esto.

**Qué más se apoyaba en el mock**, que es la parte que conviene no volver a
descubrir: el **balance entero de la pelea** —daño, acierto, orden de turnos y
chance de huir salen de atk/def/agi, y un caso de `test_batalla.py` que ponía a
todos en 1 HP **pasó a ganar**—, la pantalla de equipo, el HP del menú de pausa,
el nivel de la ranura de guardado y `actor_hpmax`.

**Lo que faltaba de las habilidades está hecho**: ver la sección de arriba. El
plan medido era, en orden, los SP como estado, la lista por actor, el menú con
el `skill_name`, la pantalla en dos columnas y el efecto; entró todo, y las dos
que mueven parámetros —Agency Badge y Mental Hack— también, que eran las que
pedían estado nuevo por combatiente.

### Los dos escapes de texto: `\|` y `\^` (2026-09-13)

Hasta ese día una página con un escape de texto no compilaba, y estaba bien que
no compilara: borrarlos calladito habría dejado a la ROM esperando un A que
RM2k nunca pide. Ahora se hacen los dos:

* **`\|` es una pausa de 61 cuadros**, no de 60 y no de un segundo. El número
  sale de `window_message.cpp` de easyrpg, que lo tiene comentado: *"Despite
  documentation saying 1 second, RPG_RT waits for 61 frames"*.
* **`\^` cierra el cuadro sin esperar a nadie**, y —como allá— no corta donde
  aparece: marca el cuadro entero.

**Dónde viajan**: en el byte de cabecera del cuadro de texto, que contaba los
renglones y le sobraban cinco bits. Los renglones quedan en los bits 0-2, el
autocierre en el 3 y cuántas pausas en el nibble de arriba. Un operando más en
`OP_MESSAGE` habría costado un byte en cada uno de los 2895 cuadros del juego
para los 2855 que no llevan ninguna cola.

Lo que hay que saber para tocarlo:

* **La cola se saca en `Mensajes.agregar`**, o sea en el único lugar por donde
  pasan todos los cuadros —los `ShowMessage`, las opciones de un `ShowChoice` y
  el `--mensaje-de-prueba` de las recetas—, y **antes** de recortar el renglón a
  lo que entra: al revés, un renglón de 39 caracteres se comería su propio
  `\|\^`. La clave de la deduplicación lleva la cola, porque dos cuadros con el
  mismo texto y distinta cola no son el mismo cuadro.
* **Sólo se acepta como cola al final de la última línea**, que es medido: los
  40 cuadros del juego con escapes son así, y ni uno tiene un escape en el
  medio. El único con espacios entre medio —`\| \| \| \^`, el
  `RunDirectorScene` del mapa 98— se los come, porque un espacio al final de un
  renglón no dibuja un pixel.
* **La pausa se cuenta desde que la página pide el mensaje**, no desde que la
  ventana termina de componerse. Es lo único que hace coincidir los dos lados
  cuadro a cuadro: la referencia dibuja la ventana de golpe y la ROM tarda entre
  nueve y diecinueve cuadros. Con 61 la composición termina mucho antes.
* **A no saltea la pausa**, igual que en `Window_Message::Update`, donde el
  `if (wait_count > 0)` va antes de `WaitForInput()`.
* **El estado vive en la RAM lejana**, `$7E30FB` y `$7E30FD`, entre el cartel
  —que termina en `$30FA`— y `FAR_ARAM_DE`. No es gusto: la BSS del banco 0
  estaba en 7679 de 7680 y hacían falta tres bytes.
* **`msg_lineas` guarda la cabecera entera** y la enmascara quien la lea, por lo
  mismo: un byte más en el banco 0 es justo lo que no hay.

**`just snes-demo demo-ciudad` no arma, y no es de esta vuelta.** El área del
banco 0 —`CODE` más `TABLAS`, 32704 bytes— se pasa. Medido el 2026-09-13 con el
mismo `mapdata.inc` de los 29 mapas:

    f38b87c, sin nada de esto      32719 B, 15 de más
    con los escapes puestos        32834 B, 130 de más

O sea que **ya no entraba antes**, y los escapes le agregan 115 bytes de código
—decodificar la cabecera, la cuenta de la pausa y el autocierre—. El conversor
no aporta ni un byte al banco 0: `f38b87c` con el `mapdata.inc` nuevo da los
mismos 32719. Las demás recetas arman, porque llevan menos mapas y `TABLAS` les
sale más chica. Lo que hay que decidir es de dónde salen esos 130 bytes; es el
mismo aviso que ya estaba escrito para la BSS —"lo que siga pidiendo RAM del
banco 0 va a tener que aflojar algo"— pero del lado del cartucho.

Lo que queda abierto:

* **`\^` sin ninguna pausa aborta la composición.** Son dos cuadros en todo el
  juego (`Map0157`, `EV0013`, la línea de puros espacios). Los dos lados lo
  resuelven en el mismo cuadro —la página sigue igual— pero la ROM no llega a
  mostrar la ventana y la referencia la dibuja un cuadro. Es la divergencia ya
  declarada de "los primeros veinte cuadros de un mensaje", y ningún caso de la
  tanda cae ahí.
* **Cualquier otro escape sigue sin compilar**, y los tres `\V` de los eventos
  comunes con él: meter el valor de una variable en el texto pide componerlo al
  abrirlo, que es otra cosa.

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

### Dos defectos de audio que ninguna prueba veía (2026-09-12)

Los dos los encontró taro escuchando, y los dos son invisibles para la tanda,
que compara pixeles: **el silencio no cambia un pixel**. Es el argumento más
fuerte que hay hasta ahora para que las pruebas de estado miren el audio.

* **La colisión de RAM lejana: arreglada.** El estado del cartel se había puesto
  en `$7E30E8`, que es donde viven `MSU_HAY`, `MSU_SUENA` y `MSU_FACTOR`: quince
  bytes encima de cuatro. La ROM dejaba de detectar el MSU-1 —`MSU_HAY=0` con
  los archivos puestos— y la música quedaba muda. Se mudó a `$30EC`, que llega
  hasta `$30FA`; `$3100` en adelante es `FAR_ARAM_DE`. **Al encargar trabajo
  sobre la RAM lejana hay que pasar el mapa**, que es lo que faltó.
* **La pantalla de título sin música: arreglada.** No era el mapa —`mapa_actual`
  vale 0 porque el mapa inicial *es* el índice 0—: era que `plx` deja N y Z del
  valor que saca de la pila, así que el `beq` que pregunta si una muestra está
  en la ARAM miraba el índice y contestaba siempre que sí. Le tocó al título
  porque su tema sale de `title_music` del LDB mientras que los paquetes se
  arman con los `PlayBGM` de los mapas: es el único tema que ningún paquete
  trae. Lo cobra `test_musica_paquete.py`, comprobado en rojo con el defecto
  puesto. **Y el mismo patrón estaba en tres lugares más**: ver la trampa de las
  banderas en `AGENTS.md`.

### Un tema no se cae de la lista por culpa de la ARAM (2026-09-12)

La segunda mitad de "la pantalla de título sin música", y es del conversor y no
de la ROM: con los 29 mapas de Lashe City la demo pide 19 temas, el banco
compartido no entró en la ARAM —89 muestras, 66353 B contra 64512— y
`build_varios` sacó ocho temas de la lista entera, desde el final. El del título
va último porque agregarlo al final es lo único que no renumera el bytecode.

Ahora **ningún tema pierde su número**: un índice y su stream cuestan cartucho,
que sobra, y lo que se recorta es quién aporta programas al banco, por
prioridad —primero el del título, después el del arranque—. El porqué durable
está en el README, "Varios temas en el cartucho".

Lo medido, 600 cuadros y pico de la salida de audio, con la ROM de antes y la de
después armadas y corridas con el mismo arnés:

    demo-titulo sin MSU-1 (snes9x)   pico 0 -> 19383, tema_actual 21845 -> 18
    demo-titulo con MSU-1 (bsnes)    MSU_SUENA 0 -> 1, pico 0 -> 12252
    demo-ciudad sin MSU-1 (snes9x)   16455 -> 16455, idéntico
    demo-ciudad con MSU-1 (bsnes)    15750 -> 15750, idéntico

Lo que queda abierto:

* **Los nueve temas que no aportan al banco suenan incompletos**, y eso es lo
  que taro terminó oyendo en la consola el 2026-09-13. Medido de nuevo el
  2026-09-14 contando notas del MIDI que sobreviven: de 12,2%
  (`golden_axe-turtlevillage2`) a 72,5% (`wb3shop`). Ver "Las voces que faltan"
  arriba, que trae la tabla por mapa y el `--banco-entero` para compararlo de
  oído.
* **El límite de verdad ya no es el banco entero**, desde que el audio sube por
  paquetes de mapa: en la ARAM viven el directorio y un paquete. Con los
  diecinueve aportando, el peor paquete son 54945 de 63831 B, o sea que entra;
  lo que se pierde es resolución para todos —12,5 a 8,4 kHz de mediana—. El
  arreglo real es presupuestar por paquete, y está en "Lo que falta" del README.

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

* **Y por eso el MSU-1 tapa lo que rompe el SPC700.** El 2026-09-12 la pantalla
  de título estuvo muda un día entero y nadie lo vio: con las pistas al lado
  sonaba. Al probar algo de audio a mano, probarlo **sin** los archivos primero.

Lo que queda abierto:

* **El punto de loop.** El MSU-1 vuelve al principio del archivo, así que un
  tema con introducción la repite en cada vuelta. Los ocho loopean enteros.
* **El clipping del Emitter Room no se pudo reproducir acá.** taro lo escuchó
  ahí; lo medido y corregido es la apertura. Todas las corridas se quedaron en
  el mapa 1, porque la apertura no avanza sola y los números de `apertura` en
  `rom/hitos.txt` son **ticks**, no cuadros de hardware. Conviene volver con
  `snes-cinematica` bien usado.
* **Los temas de la demo que no tienen pista.** Desde los 29 mapas de Lashe City
  la demo lleva 19 temas y `PISTAS_MSU` sigue teniendo ocho: los once restantes
  suenan siempre por el SPC700, y siete de ésos **incompletos**, porque no
  aportan al banco. Los siete son 908 s, unos 160 MB de PCM. Los 35 del juego
  entero que las demos no tocan serían 923 MB.

### El Bum que trababa el juego, y el jefe de los Rat Tracks (2026-09-13)

taro jugó hasta los Rat Tracks y reportó dos cosas: que al salir aparecía
**invisible y podía caminar** —la cinemática del Bum no se disparaba, o sea fin
del juego— y que el jefe *"nunca aparece"*. Eran dos causas distintas y las dos
están hechas.

Medido sobre el juego entero, con `compilar_pagina` y los cinco `indexar_*`
llamados antes, sobre las **5667** páginas disparables (3468 con comandos):

    base                              5410   (3211 con comandos)
    el destello por fila de paleta    5461   (+51)
    la pelea sin manejadores          5476   (+15)

* **El bloqueante era `FlashSprite` sobre un evento que comparte gráfico.** El
  compilador no compilaba esa página porque en la consola el destello tiñe la
  fila de CGRAM entera y la referencia lo hacía sobre la imagen del sprite. El
  comentario decía "hoy no cuesta ninguna"; costaba **51**, y una es el `EV0027`
  del mapa 20. Se resolvió **modelando la consola en la referencia** —destella
  por fila— y no aflojando el corte. El porqué durable está en el README, "El
  destello de un personaje va sobre su fila de paleta"; el precio, en
  `assets/LIMITACIONES.md`. Lo cubre `destello-compartido`, comprobado en rojo
  con 320 pixeles (0,56%) en el cuadro 2.

* **El jefe era `EnemyEncounter` con Game Over al perder**, y eran **dos**
  trabajos, no uno: la pantalla de Game Over y la pelea sin bloque de
  manejadores. Medido de nuevo: cada mitad sola da **+0** y las dos juntas
  **+15**, y las 15 páginas del juego con `defeat_mode` 0 son **todas** sin
  bloque. El número viejo de esta misma sección —"3 páginas, los mapas 21, 179
  y 255"— era de antes de los merges de esta vuelta.

  Game Over es **volver al arranque** (`jml reset`), o sea la pantalla de título
  con la partida esperando en la SRAM. **La imagen no se dibuja y el tema no
  suena**: ver `assets/LIMITACIONES.md`, "Perder una pelea es volver al
  arranque". Lo cobra `pruebas/test_game_over.py` —la tanda no puede: la
  referencia se va siempre por la victoria— comprobado en rojo desarmando el
  `bne` de `op_battle`.

**El banco 0.** El Game Over cuesta **10 bytes** de `CODE` (el `iny`/`bne`/`jml`
de `op_battle` y el `phk`/`plb` que `reset` necesitaba para que lo llamen con
el banco de datos del bytecode). Para hacerle lugar bajaron a RODATA
`pass_salir`, `pass_entrar`, `hdma_mascara`, `fuente_pre_lo` y `fuente_pre_bk`:
**24 bytes netos**, contando el `f:` que cada acceso paga. Medido con el mismo
`mapdata.inc` de `demo-ciudad`:

    main.s de d32050d                 32711 B
    con el Game Over puesto           32721 B
    con las cinco tablas abajo        32697 B de 32704, o sea 7 libres

Y un aviso que hay que leer entero: **las cuatro tablas por velocidad
—`paso_por_vel`, `salto_por_vel`, `anim_parado`, `anim_continua`— no se pueden
bajar así**. Son treinta bytes y sólo cinco accesos, o sea la candidata obvia,
pero los cinco las indexan **con Y** y el 65816 no tiene `long,Y`: bajarlas pide
mover el índice a X, y en los cinco lugares X es la ranura de ruta. Lo que queda
libre de verdad son `mascara` (8 bytes, 3 accesos, neto 5) y `tabla_fila_buf`
(32 bytes, 1 acceso, pero en el lazo del compositor de texto).

**Verificado sobre `d8e0e5d`**, que es el árbol con las dos cosas puestas:

    just pruebas                             135 en verde, 1 xfail, cero rojos
    just snes-hitos-foto 4 /extras/hitos-foto-bum   160 casos, todos en verde
    just snes-demo demo-ciudad               arma, con 7 bytes de banco 0 libres

Los cuatro casos nuevos de `just pruebas` son `test_game_over.py` (131 + 1 xfail
antes); el caso nuevo de la tanda es `destello-compartido` (159 antes).

La ROM para probar a mano está en **`pruebas-manuales/bum-y-jefe/`**, con el
`LEEME.txt` que dice cómo llegar a las dos escenas y qué mirar. Lo que taro
tiene que juzgar es **si se nota** que el `InnBum` del mapa 20 destelle junto
con el Panhandler: los dos son `Future3:1`.

Lo que quedó afuera, con su número:

* **`ShowBattleAnimation` sigue sin destellar al objetivo que comparte
  gráfico.** Ahora se podría —la referencia lo modelaría bien— pero cambia lo
  que se dibuja en los mapas donde eso pasa, así que pide medir la tanda de
  nuevo. No cuesta ninguna página: ese destello se acepta y se tira.
* **`--batalla-game-over` no está en `snes_expect.py`.** El bytecode de la
  página de prueba con esa bandera difiere en dos bytes entre los dos lados —el
  destino de la derrota, que la referencia nunca lee porque se va por la
  victoria—. Agregarlo pide un índice más en la tupla de prueba, que es de los
  números que hay que repartir de antemano: hoy está tomado hasta el 26. Ningún
  caso de pixeles usa la bandera.
* **`EnemyEncounter que corta la página al huir`** —`escape_mode` 1— sigue sin
  hacerse: **4 páginas**.
* **Huir de una pelea con `escape_mode` 0 se puede igual**, porque el permiso no
  viaja en el opcode, y sale por el destino de la victoria. Son las 24 peleas de
  esta forma.


### El Hover-Tram, el HQ de los Lazer Teeth y los Rat Tracks (2026-09-13)

taro pidió destrabar esos tres lugares, y **la mitad del encargo ya estaba
hecha**: la clase 6 de `ControlVars` con el blanco 10005 —"este evento"—
compila desde el merge de la clase 6, y `ChangeEventLocation` y `MoveEvent`
tampoco trababan nada de esos mapas. Los números del encargo eran anteriores a
`6c43aa3`. Conviene que quede escrito, porque es la segunda vez que un encargo
manda a hacer trabajo que ya existía.

Lo que **sí** quedaba, medido con esos ocho mapas adentro de la ventana de la
ROM, y lo que pasó con cada cosa:

    mapa 13  ChangePBG + la rama por objeto      hecho: 32/32 con el 16 adentro
    mapa 11  HaltAllMovement                     hecho: 100/101
    mapa 11  KeyInputProc                        hecho el 2026-09-13, 101/101
    mapa 26  ChangeSystemBGM 3                   del otro agente
    mapa  9  Teleport 7                          mapas fuera de la ventana
    mapa 18  Teleport 2                          ídem
    mapa 20  ShowInn, ChangeSystemBGM, FlashSprite, y una rama "del héroe"

Sobre el juego entero, con `eventos.compilar_pagina` sobre las **5558** páginas
disparables con comandos —el total de más arriba, 5603, cuenta además las 45
automáticas vacías, que compilan a nada—:

    base                5090
    HaltAllMovement     5091   (+1)
    la rama por objeto  5111   (+20)
    ChangePBG           5111   (+0 sola)

**`ChangePBG` se acepta y se tira**, como el panorama que el README ya declara:
el modo 3 tiene dos capas de fondo y las dos están tomadas. Aparece una sola
vez en todo el juego —siete comandos en la página del viaje en el tranvía— así
que la deuda que declara es exactamente **"el tranvía se viaja sin el paisaje
corriendo por detrás"**. Falta que taro diga si eso se nota.

**La rama por objeto era lo que más rendía de todo el encargo, y estaba
escondida**: la condición por ítem figuraba como "pide inventario, que no hay"
desde antes de que el inventario existiera (2026-09-10). Es la misma pregunta
que la condición de página por ítem, que la ROM ya contestaba.

**`KeyInputProc`: hecho el 2026-09-13.** Ver "El minijuego de las piedras del
mapa 11" más abajo.

**El banco 0 se pasó por 128 bytes** con estas dos piezas y hubo que bajar
tablas a RODATA: `partida_tabla`, los registros del PPU con su buffer de ceros,
y `dir_de_pose`. Ahora se leen con `lda f:tabla, x` —absoluto largo indexado—,
que no depende del banco de datos y cuesta un byte y un ciclo por acceso;
ninguna está en un lazo por cuadro. Lo que queda libre es del orden de la
decena de bytes, así que **lo próximo que pida banco 0 va a tener que bajar
algo más**. Las candidatas que quedan y lo que costarían: `tabla_fila_buf` (31
bytes, pero está en el lazo del compositor de texto), `mascara` (7, en
`switch_encendido`), y las de velocidad de las rutas (30 entre todas, un ciclo
por paso). **El desborde no lo ve ningún caso de la tanda**: lo cobra sólo
`just snes-demo demo-ciudad`.

### Coordenadas, teletransporte de dos bytes, y las rutas que ya no faltan (2026-09-12)

Tres piezas pedidas juntas. Las dos primeras están hechas; la tercera resultó no
existir, y ésa es la parte que hay que leer.

* **`ControlVars` clase 6**, las coordenadas de un personaje: **+119 páginas**
  sobre el juego entero, de 5016 a 5135. El porqué durable y los sub-operandos
  están en el README, "Las coordenadas de un personaje". Sobre las páginas
  **automáticas** no destraba ninguna —siguen 332—: las que la usan son de
  contacto y paralelas, que es lo que uno espera de una persecución.
* **El destino del teletransporte pasó de un byte a dos**, en `OP_TELEPORT` y en
  el registro de las puertas. No destraba ninguna página: saca un techo de 256
  mapas que estaba escrito en el formato y que el juego, con 328, ya pasaba. El
  techo que queda son 512, por `mapa_ofs`. **Cuesta que una partida guardada
  vieja no cargue**: `mapa_actual` ocupa dos bytes en la SRAM y la suma no
  cuadra.
* **Las órdenes de ruta que faltan: no falta ninguna que valga.** El encargo
  decía que la orden 10 aparecía 104 veces y valía +109 páginas; **medido sobre
  el juego entero con `just snes-destraba`, la 10 aparece una sola vez**, en una
  página del mapa 330 que ni siquiera se dispara, y aceptar las nueve órdenes
  que quedan sin hacer da **+0 páginas**. El número del encargo era de antes de
  que entrara la orden 9 (`c1a00b6`), que era la que valía —+33— y que ya está.
  Para que esto no vuelva a pasar, `snes-destraba` ahora imprime la lista.

**La persecución en auto: el número de acá abajo es de antes de
`ChangeSpriteAssociation` y ya no vale.** Decía que de las 134 páginas
disparables de los mapas 49, 52 y 54 compilaban 28, y que a las otras 106 las
cortaba `ChangeSpriteAssociation` —102— y `KeyInputProc` —4—. Ese comando está
hecho desde entonces: medido de nuevo el 2026-09-13 con la firma completa, de
esas 134 compilan **130**. Lo que queda es la sección "La persecución en auto,
jugada" de más arriba.

**Y una trampa de medición que conviene no repetir**: la tabla de "qué comando
corta" que se saca recompilando **comando por comando** miente con
`ConditionalBranch`, porque una rama suelta no compila nunca fuera de su página
—`_compilar` no la conoce; la arma `compilar_pagina`—. Medido así, parecía que
las ramas cortaban 262 páginas; preguntándoselo al compilador de verdad son 89,
y en dos motivos distintos. La lista honesta, sobre las 468 páginas del juego
que hoy no compilan:

    ChangeSpriteAssociation  103     ConditionalBranch, condición rara   53
    RecallToLocation          54     ConditionalBranch, del héroe        36
    FlashSprite               51     ChangeSystemBGM                     39
    KeyInputProc              31     ShowMessage (los escapes)           18

**El renglón de `FlashSprite` ya no vale**: desde el 2026-09-13 es **cero**, y
las 51 páginas compilan. Ver arriba.

Los 31 de `KeyInputProc` son de antes del 2026-09-13: desde ese día sólo corta
la forma que **no espera**, que son 4 páginas.

Las dos columnas de `ConditionalBranch` **ya no valen**: desde el 2026-09-13
"del héroe" es **cero** —las tres preguntas que el juego usa están hechas— y
"condición rara" son **32**, todas de la orientación de un personaje y del
cronómetro, o sea todas sin valor. Ver "Las ramas de actor" arriba.

Lo que queda abierto de la primera:

* **Las coordenadas en pantalla** —los sub-operandos 4 y 5 de la clase 6— no se
  hacen: la pantalla mide 256x224 y la de RM2k 320x240, así que el número que le
  quedaría a la variable no es el del original. Son cuatro apariciones en todo
  el juego y valen **una** página, medida.
* **Un lazo de la referencia se colgaba con una página paralela que escribe
  variables**, y quedó arreglado de paso: un paralelo pide refresco en cada
  cuadro —`SetNeedRefreshForVarChange`— así que todo lo que esperaba a que no
  quedara ninguno pendiente esperaba para siempre. Lo destapó el mapa 11, cuyas
  once páginas paralelas compilan desde la clase 6: el plan de `snes-heroe 11`
  pasó de 9 ticks a 110008, o sea cuarenta minutos de emulador por dirección.
  Ahora eso lo decide `Estado.refresco_frena`, con la misma excepción que
  `asentado` tiene para los autos. **Los cuatro lazos que lo miraban están
  cambiados**; si aparece uno nuevo, tiene que usar `refresco_frena` y no
  `refresco`.
* **La celda del héroe vive ahora en `Estado.heroe`** del lado de la referencia,
  y la escribe `cuadro_de_eventos`. El orden está elegido para copiar al de la
  ROM —el intérprete corre antes que `move_hero`— pero **la tanda no tiene
  ningún caso donde el héroe se mueva y una página lea su celda en el mismo
  cuadro**: `var-heroe-x` lo lee con el héroe quieto. Si alguna vez hay una
  página que persiga al héroe mientras camina, ese cuadro de diferencia es lo
  primero que hay que mirar.

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

### Lo próximo, si no se decide otra cosa

Al 2026-09-12, en orden.

1. **Las tres vueltas paralelas están mergeadas** (`75f0b41`), y el árbol
   combinado da **124 casos en verde** más `just pruebas` en 86 y el xfail. Era
   lo único que ninguna rama podía medir sola. La demo con todo junto está en
   `pruebas-manuales/2026-09-12-75f0b41/`.

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

3. **El `xfail` de guardar tras cambiar de mapa: confirmado como artefacto de
   la página de prueba** (2026-09-13). Ya no descansa en que taro guardara a
   mano: `pruebas/test_guardar_save_point.py` camina hasta el save point del
   juego —`SaveByTalansPad0`, el evento de índice **66** del mapa 8, en (9,56);
   el `xfail` decía "el evento 67", que es como lo numera el editor de RM2k,
   desde uno— y guarda **con pantalla
   de título y después de cambiar de mapa dos veces**, y la partida vuelve del
   reset en el mapa 8 y en la misma celda. El mismo camino sin título guarda
   igual. taro lo confirmó además en mednafen, en mesen y en la SNES. O sea que
   lo que no llega a guardar es la página de prueba —una automática con espera,
   que el doble `cargar_mapa` del menú reinicia— y eso es andamio: **el juego
   no tiene el defecto**. El `xfail` sigue puesto y `strict`, porque el andamio
   sigue roto; su `reason` tiene la medición entera.

   Lo único que costó fue el arnés, y conviene saberlo antes de escribir otra
   prueba que guarde: **mientras la pantalla de ranuras se ve, `vueltas` no
   avanza** —`OpenSaveMenu` bloquea adentro del intérprete, como `Scene_Save`—
   así que cualquier espera por ticks se planta con "la ROM no llegó al tick
   N", y **ese error es el éxito disfrazado**. Por eso no sirve
   `Recorrido.activar`, que le toca A con `Partida.correr`, y por eso hay ahora
   `Recorrido.guardar_en_el_save_point`, que corre por cuadros de hardware y
   resincroniza `Partida.cuadro` al volver. Es el primer camino de guardado de
   las pruebas que **no** pasa por la página de prueba, que era justo el
   sospechoso.

4. **El dibujo de las animaciones de batalla.** El sonido y los destellos están
   hechos; el dibujo no. Lo medido está en su sección, arriba.

5. **El tile testigo del mapa 4**, que propuso taro: que un mapa vacío no se
   confunda con una pantalla rota, porque ya pasó más de una vez que una
   captura negra fuera un PPU mal configurado. **Por el conversor y bajo un
   flag**, con la referencia sacándolo de la misma función, y no editando
   `Map0004.lmu`: el juego original es lo que hace comparable este port contra
   easyrpg, y un mapa retocado ahí contamina toda medición futura sin avisar.

6. **Lo que sigue faltando de Lashe City**: la condición por cronómetro —una
   página en todo el juego—. El `CallEvent` del Hover-Tram está hecho desde el
   2026-09-12 y el tram se toma: lo cubre el caso `tram`. **La persecución en
   auto ya la jugó taro**, con `just snes-demo-carrera`, y lo que salió de ahí
   está arriba en "La persecución en auto, jugada": de lo que reportó, dos
   cosas eran de cómo entraba la demo y están arregladas, y la tercera —que la
   carrera no corre sola— es el `KeyInputProc` sin espera, con su medición y lo
   que falta para aceptarlo.

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
* **El título del cartucho sigue diciendo `ABL SNES MUSIC POC`**, que es lo que
  muestra el menú del FX Pak y lo que lee cualquier base de datos de ROMs. Es
  una línea del header, pero se ve en hardware.

## Lo que la tanda no cubre

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
