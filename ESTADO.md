# Dónde quedamos

Lo que existe **sólo mientras alguien trabaja**: qué se decidió y sigue
valiendo, qué espera respuesta de taro, qué no se probó todavía, qué no cubre
la tanda, y hacia dónde vamos.

Lo que **no** va acá: el relato de lo hecho. Eso está en `git log`, que en este
repo tiene mensajes largos justamente para eso, y lo durable está en
`README.md`. Este archivo llegó a tener dos mil líneas por append-only y se
volvió inusable; se borra sin culpa lo que ya esté en esos dos lados.

Se escribe **mientras se trabaja**, no al final.

Última vez que se tocó: 2026-09-13.


## El objetivo, y dónde estamos

**Los primeros diez minutos jugables**, que es lo que taro viene probando vuelta
a vuelta.

Al 2026-09-13: `just snes-hitos-foto` son **161 casos, todos en verde** —sobre
la foto `254461b`, con los dos casos de la vuelta de la pelea adentro— y `just
pruebas` son **131 en verde y 1 `xfail`, sin rojos**. Los dos de audio de la
pelea que venían en rojo desde el 2026-09-12 no eran preexistentes de nadie:
los rompió el merge `6c43aa3`, que dejó a la pelea cargando el paquete de audio
del mapa. Está arreglado y contado abajo. El
`xfail` no es adorno: es un defecto medido de guardar con la pantalla de título
puesta, y está abajo.

**La ROM para probar a mano** está en `pruebas-manuales/2026-09-13-f30be91/`,
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

### Lashe City iba a la mitad de velocidad, y era el refresco (2026-09-13)

taro lo reportó jugando `pruebas-manuales/2026-09-13-f30be91/demo-ciudad.sfc` en
mednafen: *"hay lag EXTREMO en Lashe City. varía de zona a zona, pero apenas
salís del pad de Talan, es insufrible. Parece que vas en slow motion."*

**El número, medido con un cartucho de un solo mapa y el héroe quieto en el 8**
—`Lashe City - 34,35`, que es a donde sale la puerta del pad de Talan—:

    antes    30,00 cuadros por segundo, 1 cuadro perdido por vuelta
    después  60,00
    caminando a la derecha, 300 cuadros: 33,40 -> 54,20

No era "slow motion" como manera de decir: eran **exactamente la mitad**. Cada
vuelta del lazo medía unas 388 líneas de las 262 que tiene un cuadro, así que
`wait_vblank` esperaba siempre al vblank siguiente y el juego entero corría a
mitad de reloj —la lógica de RM2k va por vueltas, no por cuadros: ver
`vueltas`—.

**La causa**: el mapa 8 tiene una página **paralela** que escribe cuatro
variables por cuadro —las coordenadas del héroe contra las de otro evento, la
clase 6 de `ControlVars`— y cada escritura marcaba `refresco`. Con el refresco
pedido todos los cuadros, `rutas_de_pagina` recorría los 68 eventos y las 106
páginas del mapa **una vez por cuadro**, que es lo que no entra. **Ninguna de
esas cuatro variables la mira ninguna condición de página**, ni en ese mapa ni
en ningún otro del juego.

RM2k no hace eso, y el port lo estaba copiando de más: `SetNeedRefreshForVarChange`
le pregunta antes al `map_cache`, que tiene las variables que alguna condición
de página **del mapa cargado** mira. Acá esa pregunta no hace falta correrla:
quién mira qué es estático por mapa y el bytecode de una página se compila para
su mapa, así que la contesta el conversor y en la consola queda un `and`. Es el
bit `VAR_REFRESCO`, el de arriba de la ranura de `OP_VAR` y de `OP_TECLA`;
`var_apuntar` lo enmascara y `var_escribir` lo mira. **Cuesta cuatro bytes
menos de banco 0 que antes**, porque el `lda #1 / sta refresco` estaba repetido
en los tres lugares que escriben una variable y ahora está una sola vez.

Cómo se midió, porque conviene no volver a inventarlo: un script descartable que
corre la ROM en snes9x por `tools/retro.py` y muestrea `vueltas` y
`cuadros_perdidos` de la WRAM cada N cuadros de hardware —fps efectivos =
ticks / cuadros x 60—, y una bisección que saca un `jsr` del lazo principal por
vez, arma y vuelve a medir. La bisección fue lo que señaló a `eventos_tick` y
adentro de él a `rutas_de_pagina`; **el medidor de líneas por V-counter mintió**
y conviene saber por qué: entre dos marcas puede pasar más de un cuadro entero,
y ahí la cuenta se come 262 líneas sin avisar.

**Verificado**: `just pruebas` 131 en verde y 1 `xfail`, `just snes-hitos-foto
4 /extras/hitos-foto-lag` **159 casos todos en verde** sobre la foto `12616e2`,
y `just snes-demo demo-ciudad` arma —es lo único que ve el desborde del banco
0—. Y el `mapdata.inc` del mapa 7 sale idéntico con y sin `SIN_CACHE=1`. La ROM
para probar a mano está en `pruebas-manuales/lag-lashe/`.

Lo que queda abierto, con su número:

* **Ningún caso de la tanda mira una página con condición por variable**, que es
  justo lo que este cambio decide. Son 14 mapas en todo el juego —el 11, el 20,
  el 21, el 26, el 28, el 32 y los siete del 133 al 140— y ninguno tiene caso
  propio. O sea que lo que la tanda verificó es que **nada más se rompió**, no
  que el filtro deje pasar lo que tiene que dejar pasar; eso hoy es lectura de
  `Game_Map::SetNeedRefreshForVarChange` y del `map_cache`, no medición.
* **El mapa 11, `Lazer Teeth HQ`, sigue a 30,00 fps y no es esto.** Medido con
  la misma bisección: sacarle `rutas_de_pagina` no cambia nada y sacarle
  `paralelos_tick` lo lleva a 60. O sea que ahí el costo son **los paralelos
  mismos**: doce páginas paralelas que corren unos 48 `ControlVars` por cuadro,
  que es lo que RPG_RT también hace. No se tocó.
* **Caminando quedan cuadros perdidos** —30 en 300 en el mapa 8— y no se
  investigó cuáles: el sospechoso es `stream_map`, que arma la columna o la
  fila que la cámara destapa.
* **`ControlSwitches` no está filtrado.** EasyRPG filtra los switches con el
  mismo cache. Acá no hace falta todavía: medido sobre las páginas paralelas de
  los 29 mapas de la demo, ninguna escribe switches cuadro a cuadro; las cinco
  del mapa 11 van adentro de ramas. Si algún día un paralelo los escriba
  seguido, el arreglo es el mismo bit en `OP_SWITCH`.
* **La ranura de variable entra en siete bits**, y ahora eso es un requisito:
  `ranura_de_variable` se rompe si alguna pasa de 127. El juego usa 81.

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
otras dos son la intro de Talan del 49 —un `KeyInputProc` que espera cualquier
tecla— y el `GiveOutRewards` del 53, que se cae en un `ConditionalBranch`.

**1. La carrera no corre sola: es el volante, y es lo único grande que queda.**
Quien mueve el auto es `RaceController2`, una página **paralela** que en cada
cuadro le fuerza al héroe la ruta `28 1 29` —acelerar, un paso a la derecha,
desacelerar— y además lee el pad para esquivar. Sin ella el héroe camina libre
y a la velocidad que le dejó `RaceController1`, que es exactamente lo que taro
describió. El comando vale **+5 páginas** del juego entero —mapas 49, 51, 52,
54 y 285— sobre una base de 5348 de 5603 disparables.

Lo importante: **los dos lados ya lo hacen**. `op_tecla` en `main.s` y
`OP_TECLA` en `eventos.py` cubren la forma que no espera; el único que la
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
  controles— sigue sin compilar: su `KeyInputProc` espera cualquier tecla, y de
  las tres formas del comando ésa es la que el arnés no sabe producir. Mientras
  no esté, la demo entra con `--switch 171` puesto a mano.
* **El `GiveOutRewards` del mapa 53**, el final de la carrera: se cae en un
  `ConditionalBranch`. No se investigó cuál de las doce clases es.
* **La guarda nueva de `hero_position` no la ejercita ningún caso de la
  tanda**, y está dicho en su comentario: con el volante afuera, ninguna página
  compilada le pone una ruta al héroe mientras el jugador camina. Queda como
  código inalcanzable, igual que la guarda de la paleta vacía de
  `tenir_paleta`, no como camino a medias.

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

* **`EnemyEncounter` con Game Over al perder: 3 páginas cortadas —los mapas 21,
  179 y 255— y destraba cero.** El 21 son los Rat Tracks B1, que es lo próximo
  que taro quiere jugar, así que el número importa: **hacerlo no los destraba**.
  Medido desactivando el `raise`: la página del 21 se cae enseguida en "una
  batalla sin cerrar", porque con `defeat_mode` 0 RM2k no emite bloque de
  manejadores y la pelea no tiene `EndBattle`. O sea que además de la pantalla
  de Game Over —que este port no tiene— hay que modelar la pelea sin
  manejadores. Dos trabajos para +0 páginas hoy.
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
`OP_MENSAJE` habría costado un byte en cada uno de los 2895 cuadros del juego
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

* **Los siete temas que no aportan al banco suenan incompletos.** Son los de los
  mapas del final de Lashe City, ninguno con pista de MSU-1, y sus notas con
  muestra van del 8% (`golden_axe-turtlevillage2`) al 70% (`Lunar_Pyramid`);
  antes no sonaban ni existían. **Si incompleto suena peor que mudo, lo dice el
  oído de taro** y es cortarles el stream.
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
    mapa 11  KeyInputProc                        medido, sin hacer (ver abajo)
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

**`KeyInputProc`: medido y sin hacer.** Son 31 páginas disparables y **+30** si
se acepta entero; de sus 32 apariciones, 23 son la misma forma —esperar la
tecla de acción y guardar cuál fue—, y sólo ésa vale **+23**. La página del
mapa 11 no entra en ese subconjunto: usa las dos formas, la que espera A y la
que lee la cruceta. Las dos razones para no hacerlo ahora, las dos con número:
es del otro agente que corría en paralelo, y **en el banco 0 quedan unos pocos
bytes** (ver abajo).

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
