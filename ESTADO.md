# Dónde quedamos

Lo que existe **sólo mientras alguien trabaja**: qué se decidió y sigue
valiendo, qué espera respuesta de taro, qué no se probó todavía, qué no cubre
la tanda, y hacia dónde vamos.

Lo que **no** va acá: el relato de lo hecho. Eso está en `git log`, que en este
repo tiene mensajes largos justamente para eso, y lo durable está en
`README.md`. Este archivo llegó a tener dos mil líneas por append-only y se
volvió inusable; se borra sin culpa lo que ya esté en esos dos lados.

Se escribe **mientras se trabaja**, no al final.

Última vez que se tocó: 2026-09-11.


## El objetivo, y dónde estamos

**Los primeros diez minutos jugables**, que es lo que taro viene probando vuelta
a vuelta en el emulador.

Al 2026-09-10: `just snes-hitos-foto` son **99 casos, todos en verde** —los
dos últimos son el menú de guardado, `snes-guardar` y `savepoint-guarda`— y `just pruebas` son **50 en verde y 1
`xfail`**. El `xfail` no es adorno: es un defecto medido de guardar con la
pantalla de título puesta, y está abajo. Ese mismo día la ROM corrió por primera vez en la **SNES de verdad**
con el FX Pak, con el cartucho ya expandido a 1 MB, y anduvo. `demo-ciudad` se juega desde la apertura hasta la
calle de Lashe City, con los relámpagos, los autos y los NPCs andando, **el agua
moviéndose** y el save point animado y guardando.

Los seis puntos que acordamos el 2026-09-05 —`FadeOutBGM`, las órdenes de ruta
30 y 31, `PanScreen`, las diagonales, `PlayBGM` con varios temas y la orden 34—
están **los seis hechos**, entre el 2026-09-05 y el 2026-09-06. Con eso la
escena de Talan —los 233 comandos de la página de contacto del evento 5 del
mapa 3— corre y **está verificada** en mil doscientos cuadros, y
`demo-apertura` lleva los mapas 4, 1, 2, 3, 5 y 6.

Las páginas automáticas que compilan enteras son **272 de 489**, y del juego
entero compilan **2329 de 3473**.

### Lo que se hizo el 2026-09-09

taro pidió dos cosas y elegimos hacerlas **en serie y no con sub-agentes**: las
dos tocan `snes_convert.py`, `main.s` y `snes_expect.py`, que son justo los
archivos donde un merge mal hecho no se ve, y el cuello de botella es verificar
—dos tandas a la vez se pelean por CPU—.

1. **La animación de los tiles del ChipSet: hecha, verificada y jugada.** El
   porqué largo está en `README.md`, "El agua se mueve". taro la jugó el
   2026-09-09: *"esas animaciones cambian mucho esos mapas, se ven mucho más
   vivos"*.

   Lo medido antes de escribir una línea: en el **mapa 5** —el recuerdo de Core
   y Manta— cambia el **52% de la pantalla**, y ahí es donde se ve. En el
   **Emitter Room, que es lo que taro pidió, casi nada**: sus 4899 celdas de
   agua están dibujadas iguales en los tres dibujos del ChipSet y lo único que
   se mueve son 9 tiles del grupo "animados", 400 pixeles.

2. **El save point animado y guardando a disco: hecho.** El alcance de esa
   vuelta fue **una sola ranura y sin menú**; desde el 2026-09-10 a la tarde
   abre la pantalla de ranuras en modo guardar, como RM2k. El porqué largo
   está en `README.md`, "El save point".

   La animación de un evento quieto sale del reloj del juego, porque no hay
   dónde guardarle un contador; y cuesta **doce tiles de sprite por evento**,
   así que un mapa con más de cuatro no anima ninguno. Los dos límites están en
   `assets/LIMITACIONES.md`.

   Lo cubre `pruebas/test_guardar.py` —cuatro pruebas, tres dan rojo con
   `guardar_partida` cortado a propósito— y un caso nuevo de la tanda para la
   animación. **La tanda de pixeles no cubre guardar y no puede**: guardar no
   cambia un pixel.

   **Jugado el 2026-09-09**, y guardar quedó verificado del otro lado del
   emulador: mednafen escribió `demo-ciudad.<hash>.srm`, 8 KB, en
   `~/.mednafen/sav`. Falta el EverDrive, que es la única parte que no se puede
   ver acá adentro.

### La pantalla de título (2026-09-10)

taro la pidió el 2026-09-09, con su música, su imagen de fondo, las opciones de
empezar y cargar, un menú de ranuras que las muestre, y cargar de verdad. Y con
**cuatro ranuras** —"6 si hay lugar"— en vez de las quince del original. Los
datos que todavía no existen —el nivel, los HP— van mockeados.

**Hecho y verificado: la imagen con su tema.** `just snes-titulo` compara la
captura contra `tools/titulo.py` y da **cero pixeles de diferencia**; el caso
está en `rom/hitos.txt` y la tanda pasó a ser de **97 casos**.

Lo que se midió antes de escribir una línea:

* La imagen **se escala y no se recorta**. El original es de 320x240 y la
  pantalla de 256x224: el recorte centrado se come el "2.1" del título por la
  derecha y los créditos de `Additional Graphics` por abajo. Se miró la imagen
  para decidirlo.
* Escalada son **496 tiles y 369 colores**; recortada, 498 y 133. Los 369 hay
  que bajarlos a 256, y de eso se ocupa `titulo.reducir`: se queda con los más
  usados y manda el resto a su vecino más cercano. No es mediancut —no promedia,
  así que no inventa colores que haya que volver a cuantizar— y no depende de la
  versión de PIL, que es lo que permite que el conversor y la referencia lo
  llamen y saquen lo mismo.
* **Entra cómoda**: 31744 B de tiles más 2048 de tilemap, de los 65536 de VRAM.
  Va en BG1, que en modo 3 tiene ocho bits por pixel y direcciona CGRAM entera.
  Es el único lugar del port donde eso se puede: mientras se ve el título no hay
  mapa, así que no hay sprites que necesiten sus paletas.

Tres decisiones que sostienen el resto:

1. **El título corre después de `BOOT_CUADROS`,** no antes. Así una ROM sin
   `--con-titulo` llega al lazo en el cuadro de siempre y **los 96 casos viejos
   no se enteran de que esto existe**. Verificado: los 96 siguen en verde.
2. **`vueltas` no avanza en la pantalla de título.** Es el reloj del juego, y el
   título no es el juego: una ROM con título corre el mapa igual que una sin él,
   así que las dos referencias siguen siendo comparables. El precio es que el
   arnés no tiene a qué cuadro esperar, y de ahí sale `--sin-contador` en
   `snes_correr.py`, que cuenta cuadros de hardware.
3. **`title_name` y `title_music` salen del LDB**, no de la línea de comandos.
   Los dos códigos de campo —`0x11` y `0x1F`— salen de `chunks.h` de liblcf,
   igual que el resto de `lcf.py`. En el ABL son `ABL20Title` y
   `Fantasia_Of_The_Wind`; el tema entró en la ARAM y el banco compartido quedó
   en 52684 B de 64512.

**Hecho y verificado: el menú.** "Begin the Story" y "Resume the Story", que
son los términos del juego y salen del LDB —`new_game` y `load_game`, códigos
`0x72` y `0x73` de liblcf— y no de un literal nuestro: el motor de fábrica
diría "New Game" y "Load Game". Se dibujan con `ventana.dibujar_linea`, o sea
la misma fuente, el mismo degradé y la misma sombra que un mensaje del juego,
así que no hay una segunda fuente que mantener.

Van en **BG2, a cuatro bits por pixel**, y no mezclados con la imagen en BG1:
son 50 tiles y 6 colores, 1600 B. Mezclarlos habría costado un tile nuevo por
cada celda donde el texto pisa el fondo, y el texto no podría moverse.

**El cursor no se dibuja aparte: hay un tilemap por opción, y moverlo es subir
el otro** por DMA. Son 2048 B por tilemap y el DMA sólo corre cuando el jugador
aprieta arriba o abajo. La alternativa —escribir a mano las dos celdas del
tilemap que cambian— ahorra 2 KB de cartucho y pide saber en qué celda cae cada
flecha, que es justo la clase de número que se escribe bien de un lado y mal
del otro.

`just snes-titulo` compara **dos cuadros** y los dos dan cero: el menú como se
entra, y el cursor una opción más abajo. El segundo no es adorno —es lo único
que ejercita el DMA del tilemap— y de paso cobra que sostener abajo no baje un
renglón por cuadro: se corre con el botón apretado veinte cuadros y el cursor
se movió una sola vez.

Dos cosas que costaron un rojo y quedan escritas:

* **El reparto de la VRAM.** Los tiles del menú y su tilemap estaban puestos en
  `$1000` y `$0800`, que caen **adentro** de los 15872 palabras de la imagen. La
  pantalla salía de basura. El reparto que quedó está en el comentario de
  `TITULO_MENU_TILES` en el `.inc`, dibujado.
* **CGRAM se sube entera o no se sube.** El DMA llevaba las 240 de la imagen y
  no las 16 del menú, así que las últimas dieciséis entradas quedaban sin
  escribir: 145 pixeles de diferencia, todos en el degradé de los créditos, que
  es donde viven los colores menos usados.

Con `--con-titulo` el arranque **no** carga la partida sola: eso lo decide el
menú. Sin el flag —o sea toda la tanda y todas las pruebas de estado— sigue
pasando lo de siempre.

**Hecho y verificado: las cuatro ranuras en la SRAM.** Son **cuatro**, que es
lo que taro pidió; en la SRAM entrarían muchas más —son 8 KB y una partida
ocupa 159 bytes— así que el número no sale de ahí sino de cuántas se pueden
mostrar y elegir sin que la pantalla se vuelva una lista.

Cada ranura arranca en un múltiplo de **256**, que es lo que hace que su
desplazamiento sea un `xba` y no una multiplicación: multiplicar por 165
pediría el multiplicador del hardware y ocho ciclos de espera, para ahorrar 364
bytes de una SRAM que sobra. Las cuatro terminan en `$0500` de los `$2000`.

Dos cosas que costaron el rato:

* **La RAM del banco 0 está llena.** Las dos variables nuevas no entraban: 7683
  bytes en 7680. Quedó una sola, `ranura`, con **`$FF` como "ninguna partida
  cargada"**, haciendo de las dos cosas.
* **Y vive en la página directa, no por lugar sino por el banco.** Las rutinas
  que tocan la SRAM corren con el banco de datos en `$70`, así que una variable
  de la BSS leída con direccionamiento absoluto les daría la SRAM. La página
  directa apunta siempre al banco 0. Es el mismo vecindario del bug que hizo
  que la partida no cargara en hardware.

Lo cubren dos casos nuevos en `test_guardar.py`: que guardar en la ranura
elegida no toque a la otra —verificado que da rojo si el desplazamiento se
ignora— y que las cuatro entren en los 8 KB, que es una cuenta que conviene que
haga la prueba porque `PARTIDA_BYTES` crece cada vez que se agrega un campo.

**Mientras tanto el save point guarda en la ranura de la que se cargó**, o en la
primera si la partida es nueva. Así las cuatro se pueden llenar jugando desde
ahora, sin esperar a la pantalla que las muestra.

**Hecho y verificado: la pantalla de ranuras, del lado de cargar.** "Resume
the Story" abre una lista de cuatro con su cabecera —"Load which slot?", que es
`load_game_message` del LDB— y B cancela y vuelve al título. `just snes-titulo`
compara **cinco** cuadros y los cinco dan cero: el menú, el menú con el cursor
abajo, la lista de ranuras, la lista con el cursor dos abajo, y el juego
después de salir.

Tres decisiones:

* **Todo el texto viene pre-renderizado**, incluidas las dos variantes de cada
  ranura —vacía y llena—. Los datos que muestra o son fijos o están mockeados,
  así que no hay nada que componer en caliente. Son 93 tiles de 4bpp, 2976 B,
  más 3328 B de celdas.
* **De qué bloque se trata lo dice una tabla de punteros**, no una
  multiplicación: calcular el desplazamiento con corrimientos habría puesto la
  misma cuenta en el conversor y en el 65816. Lo mismo la dirección de VRAM de
  cada fila.
* **Mover el cursor reescribe dos filas**, no el tilemap entero: 96 celdas cada
  una, adentro del vblank.

Y el arnés aprendió `--toques BOTON:CUADRO`, que es lo que permite caminar un
menú en la tanda: `--teclas` sostiene, y estos menús miran flancos.

**El nivel está mockeado en 1**, como se acordó. La partida guarda posición,
mapa, switches, oro y ahora el tema; nivel no hay porque no hay actores con
nivel todavía.

**Lo que falta de esto:**

* **El menú de guardado desde el save point: hecho y verificado** el
  2026-09-10 a la tarde. `op_guardar` abre `ranuras_pantalla` en modo 1,
  bloquea adentro del intérprete sin gastar ticks —como `OpenSaveMenu` apila
  su escena en RM2k—, guarda en la ranura elegida o vuelve con B, y
  `volver_al_mapa` repone lo que la pantalla pisó. Lo cobran dos casos nuevos
  de la tanda, `snes-guardar` —seis cuadros: la pantalla, el cursor, y el mapa
  de vuelta tras cancelar y tras elegir— y `savepoint-guarda`, que es **el
  save point de verdad** del mapa 8; y `test_guardar.py`, que ahora atraviesa
  la pantalla con el cursor en vez de escribir `ranura`. Los detalles están en
  "El menú de guardado", más abajo, y en el README.

  Lo que el intento de la mañana había medido estaba **mal leído dos veces**:
  el "85" era `$55`, la basura con que snes9x llena la RAM, leída de un testigo
  que nadie inicializaba; y la "pantalla negra con basura" era que **sin
  `--con-titulo` el conversor no emitía la pantalla de ranuras** —un byte de
  relleno y `RANURA_TILES` en cero, o sea un DMA de 64 KB—. No era el contexto
  del intérprete, ni el canal 0 de DMA, ni nada de lo que se había sospechado.

* **Confirmación de pisar una ranura ocupada: no va.** `Scene_Save::Action`
  guarda y saca la escena sin preguntar; hacerlo acá sería inventar.

* **La variante "llena" la cubre `test_titulo.py` pixel por pixel** desde el
  2026-09-10 a la noche —`test_la_pantalla_de_ranuras_muestra_el_grupo_guardado`—
  porque la tanda no puede: la SRAM del emulador arranca virgen. Guarda con
  Talan y DummyHero, reinicia, abre "Resume the Story" y compara contra
  `titulo.render_ranuras` con ese grupo, con el cursor en la primera fila y
  sobre la de Talan.
* **Cada ranura con partida muestra el nombre del líder, "L  1" y las caras
  del grupo**, como `Window_SaveFile` en RM2k; taro lo pidió el 2026-09-10 al
  ver la cara de Talan en EasyRPG. Hecho esa noche y **mirado contra EasyRPG
  de verdad**, que está en `/extras/erpg` y corre con `rom/easyrpg.sh`: ahora
  con `REPLAY`, porque las teclas por xdotool se pierden —de cuatro llegaron
  dos, medido con `--record-input`—. El cómo está en el README, "El save
  point". Lo que no muestra: los puntos de vida, que este port no tiene, y la
  cuarta cara, que no entra en 256 pixeles. El nivel sigue mockeado en 1.
* **Cargar no anda todavía, y el commit anterior decía que sí.** Lo encontró
  `pruebas/test_titulo.py`, que es justo el caso que ese commit no tenía. El
  síntoma, medido el 2026-09-10: se guarda con el switch 7 prendido, la SRAM
  queda con la magia `ABLS` y el switch adentro, se resetea la consola de
  verdad, se elige "Resume the Story" —`titulo_sel` vale 1, así que la opción
  es la correcta— y el switch **no vuelve**.

  Lo que se sabe: **sin** pantalla de título el mismo cartucho carga solo en el
  arranque y el switch sí vuelve, que es lo que hace `test_guardar`. Lo único
  que cambió es **cuándo** corre `cargar_partida`: en el arranque es a los
  microsegundos del reset, y desde el menú es después de `cargar_mapa`,
  `flush_video` y la subida al SPC700. Se descartó que sea el banco de datos:
  con un `phk`/`plb` delante pasa exactamente lo mismo, así que ese código no
  quedó —agregarlo sin evidencia habría sido ruido—.

  Queda como `xfail(strict=True)` y no como comentario: el día que se arregle,
  la prueba falla y obliga a sacar la marca.

* **Y un segundo defecto del mismo vecindario**, encontrado buscando el
  primero: con pantalla de título, **irse de mapa antes de guardar deja la
  partida sin guardar**. Quedándose en el mapa de arranque la SRAM tiene la
  magia a las ~400 vueltas; con un `ir_al_mapa(6)` en el medio sigue sin
  tenerla a las 491. Sin pantalla de título ese camino guarda. El sospechoso es
  el **doble `cargar_mapa`**: con título el mapa se carga una vez en el arranque
  y otra al salir del menú, y eso no pasaba antes. También queda como
  `xfail(strict=True)`.

  Los dos son el mismo vecindario y conviene mirarlos juntos: **son lo primero
  de la próxima vuelta**, antes que las cuatro ranuras. Una pantalla de ranuras
  sobre una carga que no carga no sirve de nada.

### El menú de guardado (2026-09-10, a la tarde)

Lo que hay que saber para tocarlo, además de lo del README:

* **Bloquea adentro del intérprete y `vueltas` no avanza.** Es lo mismo que la
  pantalla de título, y por eso la referencia no cambia: `OP_GUARDAR` cuesta
  cero ticks de los dos lados. El precio lo paga el arnés: adentro de la
  pantalla no hay tick en el que caer, y de ahí `--toques-hardware` en
  `snes_correr.py` —cuadros de hardware desde el arranque, en los dos caminos,
  el de `--toques` y el de `--apretar-a`— y `menu_abierto` en la página cero,
  que es un byte para que `consola.py` sepa cuándo apretar. Como
  `cuadros_perdidos`, la ROM no lo lee.
* **Las direcciones de VRAM son de la pantalla y no del menú del título**:
  `RANURA_MAP` en `$2000` y `RANURA_VRAM` en `$3000`, dentro del banco de BG1
  de los cuatro repartos, y el conversor lo comprueba en
  `_controlar_ranuras`. Es lo que hace que `volver_al_mapa` alcance con
  `load_map` más `ppu_init` y el tinte, sin `cargar_mapa` —que reiniciaría
  eventos, rutas y poses—. Con las del menú, `$4400` pisaba los sprites del
  reparto ancho: 267 pixeles en el héroe del mapa 73, y **sólo con el grupo
  11**; el grupo 10 tiene al líder en el bloque 0 y pasaba. Medido con el
  `GRUPO` del justfile, que es 11, y no con el 10 del scratch, que es donde
  se vio primero un cero falso.
* **Cuesta dos cuadros negros al volver**, porque `load_map` son 30 KB de DMA.
  `cuadros_perdidos` cuenta uno —`cerrar` pone `nmi_visto` al día para que no
  cuente los del jugador eligiendo—.
* **El cursor arranca en la ranura en uso** en modo guardar: `latest_slot` sin
  fechas. Y `ranuras_pantalla` deja `ranura` como estaba al salir, porque
  pintar las filas la pisa; sin eso cancelar dejaba "cargada" la última fila.
* **El tema del título no se reinicia al volver de las ranuras.** taro lo
  escuchó el 2026-09-10 en la consola: se reiniciaba, y el comentario decía
  que eso hacía RM2k. No: `Scene_Title::Continue` no pasa por `Start()` al
  volver de cargar, y `BgmPlay` con el mismo tema no lo reinicia. `music_start`
  se mudó de `titulo_subir` a `pantalla_titulo`. Medido con el puntero del
  stream, que sigue de largo al volver; la tanda no escucha.
* **Un evento de la capa de abajo se dispara parado encima, no de frente.**
  Es `CheckEventTriggerHere` contra `CheckEventTriggerThere`, y el save point
  es de esa capa: `savepoint-guarda` arranca en (9,56) y no en (9,55). De
  frente el caso daba cero **en vacío**, lo dijo `menu_abierto`. Es la trampa
  de siempre y la receta lo deja escrito.
* **Lo que no cubre nada todavía**: qué queda en la SRAM después de
  `savepoint-guarda`, que es el caso del save point real y sólo mira pixeles.
  La variante "llena" de la fila sí está cubierta desde esa noche, con las
  caras: ver arriba.
* **Las caras del grupo en la fila (2026-09-10, a la noche).** Tres cosas que
  costaron: el FaceSet tiene el índice 0 transparente como un CharSet, y se
  abre con `render_map.load_image` y no con `Image.open`; el escritorio de
  `ranura_grupo_pintar` está justo —`temp` entero, `temp + 3` y
  `titulo_flancos` de índice— y el primer borrador pisaba `hero_x` para
  guardar una columna, que en el save point es el juego mismo: las direcciones
  de destino pasaron a tablas del conversor y no hizo falta más RAM; y leer
  `titulo_flancos` a dieciséis bits se lleva `menu_abierto`, que vale 1
  mientras la pantalla se ve, así que el índice de la SRAM se arma con dos
  `xba`. La VRAM de la pantalla es ahora $2000 para los tiles —170 con las
  cuatro caras de la demo, tope 448— y $3C00 para el tilemap.

### El build: dónde se va el tiempo (medido el 2026-09-10)

taro preguntó si convenía cambiar el ensamblador en Python por una toolchain
en C —pvsneslib— porque el build tarda. Medido sobre `demo-ciudad`, ocho mapas
con música, en este contenedor:

    convertir los 8 mapas con la música     76,6 s
      de eso, snes_music.build_varios       46,8 s
        de eso, brr.encode                  44,1 s   1611 llamadas, 111 distintas
      de eso, los mapas en sí               ~30 s    entre 1,3 y 9,6 s por mapa
    ensamblar main.s con w65.py              2,5 s
    convertir un mapa solo (el 73)           1,3 s

O sea que **el ensamblador no es el problema**: son 2,5 s de 80, y pasarlo a
C no cambiaría nada que se note. Lo que tarda es codificar las muestras a BRR
—un lazo en Python puro, muestra por muestra, por 4 filtros y 13 rangos— y se
codificaba **la misma muestra catorce veces**: 1611 llamadas para 111 entradas
distintas, porque cada tema arma su banco de tambores desde cero.

**Hecho el 2026-09-10: la tabla en memoria**, `_hechas` en `brr.py`. Medido
después, mismo build:

    convertir los 8 mapas con la música     39,2 s   (era 76,6)
      de eso, la música                     10,1 s   (era 46,8)
        de eso, brr.encode                   7,6 s   las 111 distintas, una vez
      de eso, los mapas en sí               ~29 s

Verificado como corresponde: el `.sfc` con la tabla y sin ella son **byte por
byte iguales** —`filecmp` sobre las dos ROMs armadas con el mismo `main.s`—.
La primera comparación dio distinto y era otra cosa: la ROM "de antes" se
había armado antes del arreglo de la música del título.

**Hecho el 2026-09-10, después: el caché en disco**, `tools/cache_disco.py`,
en `rom/build/cache/`. Dos categorías: `brr`, por muestra, y `capas`, que es
`convert_layers` —cuantizar, cortar en tiles y repartir CGRAM— con clave en
**los pixeles** de las capas y sus dibujos animados, no en el `.lmu`: así
entra todo lo que las produce sin enumerarlo. Las dos claves llevan el hash de
los fuentes de los que salen, así que tocar `brr.py`, `snes_convert.py` o
`rm2k.py` invalida solo. Medido, mismo build:

    demo-ciudad, caché frío (escribiéndolo)   41,3 s
    demo-ciudad, caché tibio                   8,7 s   (era 76,6)
    snes-espera, un mapa, tibio                1,8 s
    el caché de la demo en disco               1,5 MB, 122 archivos

Verificado: las ROMs armadas con caché frío, con caché tibio y con
`SIN_CACHE=1` son **byte por byte iguales**. Lo que queda de los 8,7 s es
renderizar las capas, los sprites y ensamblar; ninguno vale otro caché hoy.

Y **spcasm no aporta nada**, que taro preguntó: el driver del SPC700 son 20
bytes y `spc700.assemble` tarda 0,000 s. Lo caro de la música es codificar las
muestras, no ensamblar el driver.

### Los mapas 9 y 10 (2026-09-10, a la noche)

taro pidió Lashe City Interiors (10) y Lashe City 33,36 (9) para habilitar los
teletransportes del 8. Están en `snes-demos` y cuatro cruces están en la
tanda —8→10, 10→8, 8→9, 9→8, con `snes-escena` pisando la puerta con un paso de
ruta—. Con los dos en la ROM, del mapa 8 compilan 68 páginas de 71 (las tres
que faltan van al 16), del 9 32 de 40 y del 10 21 de 26.

Dos cosas que costaron:

* **El banco de poses era uno por ROM** y el mapa 9 cuantiza a `Chara2:0`
  distinto que el 8, que le presta una paleta ajena: el conversor cortaba con
  un `sys.exit`. El reparto de paletas tenía una regla para esquivarlo
  —`solo_aqui`— que el préstamo no miraba. Ahora hay **un banco por
  cuantización**: cada mapa nombra el suyo, y si dos coinciden lo comparten.
  Verificado que la demo de ocho mapas sale byte por byte igual.
* **`PanScreen` con espera y distancia cero cortaba el cuadro.** Lo delató el
  cruce 8→9: la puerta EV0009 vuelve la cámara antes del `Teleport`, y el auto
  rojo del 9 iba 4 px atrás de la referencia, constante. Medido tick por tick:
  la referencia llegaba al `Teleport` en el mismo cuadro y la ROM uno después.
  EasyRPG pone `wait_time = GetPanWait()` y sigue si es cero. Arreglado en
  `op_pan`; lo cobra `snes-pan 6 "3 0 0 4 1"`, que daba 13710 pixeles.

### EV0041, y lo que había debajo (2026-09-10, a la noche)

EV0041, EV0042 y EV0052 del mapa 8 son el mismo evento tres veces: tres
páginas por switch, y la tercera además por **ítem**. Hasta hoy una condición
de ítem tiraba el evento entero; durante un día esa página se emitió como
**nunca activa** —`switch_a = SWITCH_IMPOSIBLE`, porque `ChangeItems` se
aceptaba sin hacer nada y el grupo no tenía ítems jamás— y desde la noche
**hay inventario y la condición se evalúa**: ver "El inventario" más abajo.
Son 45 eventos que vuelven a existir en todo el juego. Lo cobra `snes-escena
... ev41`: hablarle parado encima —es de la capa de abajo—, cerrar el mensaje
y mirar la ruta.

### El inventario (2026-09-10, a la noche)

El primer paso del sistema de ítems, el (1) del plan de "Lo próximo". La ROM
lleva la cuenta de cada ítem del LDB: un byte por número de RM2k en la RAM
lejana, `FAR_ITEMS` en `$2800` —después de las variables, que son hasta
256—, topado en 99 como `Game_Party::AddItem`, en cero en el reset y en la
partida, que mide 773 bytes: `SRAM_STRIDE` pasó a 1024 y las cuatro ranuras
son la mitad de los 8 KB. `ChangeItems` compila a `OP_ITEM` —ítem y cuánto,
con signo; el juego lo usa 509 veces y siempre con constantes— y pide el
refresco de páginas, como `CommandChangeItems`. La condición de página por
ítem va en +28 de la tabla (`PAGINA_BYTES` 30) y `condiciones_ok` mira la
cuenta; `CONDICIONES_IMPOSIBLES` quedó vacía. La referencia lleva
`Estado.items`. Lo cobran `cofre-llave` en rom/hitos.txt —el KeyChest del
mapa 133 con la variable en 8 **y** la llave 151: gana la tercera página y
el cofre no se dibuja, 252 pixeles contra `cofre`— y `test_items.py`: sumar,
quitar, los dos topes, la partida, y que `ITEMS_N` sea el del LDB. Lo que
falta del sistema: mostrar el inventario, usar medicinas, el equipo y la
tienda.

Y la ruta destapó **dos errores de la ROM que no eran del evento**:

* **El salto del héroe no respetaba el atravesar paredes.** `puede_caer` mira
  `atravesando`, y `armar_salto_heroe` no lo ponía desde `ruta_atraviesa`. La
  ruta es `through`, salto sobre la reja, cuatro pasos: la referencia saltaba
  y la ROM caminaba. 40840 pixeles en el cuadro 60.
* **Una fila del mapa que se arma en un vblank lleno se pierde.** Es el bug
  "medio random" que taro vio el 2026-09-09. `push_strips` corre después de
  las poses y no descontaba nada del presupuesto: con las cinco poses del
  arranque de un salto, los cuatro DMA de la fila caían con la pantalla
  encendida y la VRAM los ignoraba, y la fila quedaba negra hasta que la
  cámara volviera. Medido: `row_addr` puesto en el tick 40 y la fila ausente
  desde el 41. Ahora una tira pendiente descuenta una pose, como el renglón de
  la ventana. 1563 pixeles, una fila de 200.

### Las variables, y el Tram Officer (2026-09-10, a la noche)

Hecho. La ROM tiene **variables de RM2k**: no las cinco mil sino **las 81
que nombra el juego entero**, con una ranura cada una que reparte el
conversor y que la referencia reparte igual —`indexar_variables`, que lee los
328 mapas en un tercio de segundo—. Hasta la noche del 2026-09-10 el índice
era de los mapas de cada ROM —seis en los mapas 1 a 10— y una partida
guardada con una ROM no valía para otra con más mapas; ahora la ranura de
una variable es la misma en cualquier ROM. Viven en la RAM lejana
(`FAR_VARIABLES`), son de dieciséis bits con signo, y **viajan en la
partida**: `PARTIDA_BYTES` son 322, así que `SRAM_STRIDE` pasó a 512 —un
`xba` y un `asl` en `ranura_en_x`, y el `asl` que faltaba en
`actor_del_miembro`, que lo cobró `test_titulo`— y las cuatro ranuras entran
en 2 KB de los 8.

**Las condiciones de página por variable** están desde esa misma noche: la
página lleva +24 la ranura o $FF, +25 la comparación y +26 el valor, y
`condiciones_ok` los lee de la tabla —la BSS está llena— y los pasa a
`comparar_var`, que es la comparación con signo de `ConditionalBranch`
compartida. `PAGINA_BYTES` pasó de 24 a 28. Escribir una variable pide el
refresco de páginas, como `SetNeedRefreshForVarChange`: sin eso el cofre
del mapa 133 no aparecía de ningún lado. Son catorce páginas del juego,
todas con `>=`; la condición por **cronómetro** la pide una sola, la 81 del
mapa 312, y sigue dejando el evento afuera. Lo cobran `cofre` y `cofre-no`
en rom/hitos.txt —el KeyChest del mapa 133 con la variable 123 en 8 y en 7:
252 pixeles entre los dos en el cuadro 30, cero contra la referencia— y
`test_paginas.py`.

Y `OpenShop` se acepta sin abrir nada: los dos vendedores de Lashe City
Interiors no contestaban por ese comando, taro lo vio jugando. Ninguna de
las 43 tiendas del juego usa las ramas de compró/no compró, así que el
diálogo de antes y el de después salen enteros; la tienda es del sistema de
ítems. Lo cobra `tienda` en rom/hitos.txt.

Lo que hay: `ControlVars` de a una —poner, sumar, restar; constante, otra
variable, azar, y "otro" oro y segundos del cronómetro—, `ConditionalBranch`
por variable con las seis comparaciones y signo, y `TimerOperation` desde una
variable. El azar es un xorshift de dieciséis bits **igual de los dos lados**,
sembrado en el reset: por eso una página con azar compara pixel por pixel.
`CallEvent` se acepta sin hacer, con la deuda declarada en
`ACEPTADOS_SIN_HACER`: en los mapas 1 a 10 sólo lo usa el Tram Officer para
subir al Hover-Tram, que taro dejó para otra vuelta.

Lo cobran `snes-vars` —el cronómetro puesto desde una variable, dígitos a la
vista— y **`tram`, la escena entera del Tram Officer**: once cuadros en cero,
con la elección, la caminata de espera, la rama "I'm late" y el "It's here!"
que sale del azar (la variable 21 da 97). Y `test_variables.py`: las
operaciones contra Python, el primer azar contra `azar_siguiente`, la rama, y
que las variables vuelven de la SRAM.

Dos cosas para saber: las órdenes 28 y 29 de la ruta del héroe —subir y bajar
la velocidad— **se hacen desde el 2026-09-10 a la noche**, así que la caminata
de espera del Tram Officer va a velocidad 5 como en RM2k; ver "La velocidad
del héroe" más abajo. Y `Wait 15` son quince **décimas**, noventa ticks, que
fue lo que explicó por qué el mensaje de "I'm late" tardaba cien ticks en
salir.

### La velocidad del héroe (2026-09-10, a la noche)

El paso del héroe dejó de ser fijo. `step_left` cuenta **medias unidades de
RM2k** —128 por celda— y baja `paso_medio_por_vel` por cuadro según la
velocidad, que vive en `FAR_HERO_VEL` (la RAM lejana: la ZP y la BSS están
llenas), arranca en 4, la suben y bajan las órdenes 28 y 29 de una ruta
forzada, **y queda así**: RM2k repone la frecuencia al terminar la ruta y la
velocidad no, o sea que el pad camina después a la que dejó la ruta. Viaja en
la partida (un byte al final de `partida_tabla`). Los pixeles se recalculan
desde la celda de destino con `step_left >> 3`, que es el `paso_resta // 16`
de `pixeles_del_paso`; `step_dx`/`step_dy` son ahora el sentido y no los
pixeles por cuadro. La animación cuenta **para arriba** contra el tope de la
velocidad de ese cuadro (`anim_por_vel`, `ANIM_PARADO`), como
`GetAnimCount() >= stationary_limit`: contando para abajo desde el tope, una
velocidad cambiada a mitad de frame recién valía un frame después. En la
referencia es `Ruta._contar_movimiento` y `columna_del_heroe`, en vez del
`cuadros_moviendose // 6` de antes, y `cuadros_por_celda(estado)` reemplaza a
la constante en la caminata con el pad.

Lo cobran `ruta-vel` (velocidad 5, cuatro pixeles por cuadro) y
`ruta-vel-lenta` (velocidad 2, medio pixel por cuadro, y después 5) en
rom/hitos.txt, cuadro por cuadro; `tram`, que ahora espera a velocidad 5; y
`test_velocidad.py`, que camina con el pad a las velocidades 1, 2, 5 y 6 —la
tanda no puede apretar una dirección después de una ruta— y guarda y carga la
velocidad. Tanda: 109 casos en verde sobre la foto `7c6e76a`; `just pruebas`:
61 pasan y una xfail de siempre.

### El menú de pausa (2026-09-11)

El paso (2) del plan de ítems. B abre `Scene_Menu`: las cinco órdenes con los
términos del LDB, el oro abajo y el grupo a la derecha —cara, nombre, "L  1",
"Normal" y los HP del nivel, llenos—, en el banco de tiles y la paleta de la
pantalla de ranuras. **Sólo guardar hace algo**: abre la pantalla de ranuras y
vuelve al menú con el cursor en Save. Las otras cuatro van en gris. La
geometría es nuestra —256x224, sin ventanas, sin título, experiencia ni SP, el
oro de a una cifra por celda— y está declarada: si se ve bien o no lo dice
taro jugando. Detalle en el README, "El menú de pausa".

Cuándo se abre es lo de RM2k, pedido y atención: B anota el pedido si el menú
está permitido, sin mensaje y sin página; el héroe lo atiende quieto, así que
B a mitad de un paso abre el menú al terminarlo. `ChangeSaveAccess` y
`ChangeMainMenuAccess` compilan a `OP_ACCESO` y viven en `FAR_ACCESO` ($25FC,
en la partida). El reloj del juego no corre con el menú abierto.

Dos defectos que aparecieron haciéndolo, los dos de flancos: el B que cancela
la pantalla de ranuras del save point le llegaba a `pedir_menu` en la misma
vuelta —si la página terminaba ahí— y abría el menú; lo cobró
`test_cancelar_no_guarda_ni_cambia_la_ranura`. Ahora la salida común de la
pantalla de ranuras consume los flancos de B y A, igual que el cierre del
menú, y la elección cancelada con B consume el suyo. Y en `op_acceso` el
permiso se leía con `ldy temp + 1`, de dieciséis bits: se llevaba el byte de
al lado y un "prohibido" con basura quedaba permitido; lo cobró
`test_los_permisos_viajan_en_la_partida`, que en otra prueba pasaba por suerte.

Lo cobran `snes-menu` en rom/hitos.txt —el menú como se abre, con el cursor
dos más abajo, y el mapa de los ticks 50 y 120 después de cerrarlo— y
`pruebas/test_menu.py`, seis pruebas.

Y un caso de la tanda que **pasaba en vacío**: `savepoint-guarda`. Con
`--toques-hardware`, `snes_correr.py` tomaba un camino que ignoraba
`--apretar-a`, así que el A que abre el save point nunca se apretó; pasaba
porque guardar no cambia un pixel. Lo destapó el menú: el B del cuadro 40 caía
en el mapa, lo abría, y el reloj se paraba. La verificación del 2026-09-10 que
decía "no es vacío" sacaba el B, y con él los toques, y eso cambiaba de
camino. Ahora los dos caminos aprietan A y el cuadro de hardware 30 del caso
es la pantalla de guardar, en cero contra `titulo.py`.

Lo que falta del menú, en orden: usar ítems —pide la lista del inventario y
los nombres de los 450 ítems en la ROM—, el equipo, las técnicas y terminar
el juego, que pide volver al título sin reiniciar el SPC700.

### La pantalla de ítems (2026-09-11)

El paso (3) del plan, recortado a lo que la demo tiene. "Use Item" abre la
lista del inventario con la descripción arriba; A usa los ítems de switch
—la Portable Console, el único ítem usable que da la demo: prende el 710 y
vuelve al mapa— y B vuelve al menú. Las medicinas van en gris: piden HP que
cambien, y en los mapas 1 a 10 ni se consiguen ni nadie baja los HP. El 710
dispara el evento común 39, el menú propio del juego hecho con imágenes, que
no corre porque los eventos comunes todavía no existen. Detalle en el README,
"La pantalla de ítems".

Lo que costó: el primer diseño llevaba el texto de cada ítem ya dibujado en el
banco de las ranuras, y con una docena de ítems no entraba —cuatro ROMs de la
tanda dejaron de armarse: `snes-puerta`, `snes-texto` y dos `snes-ventana`—.
Ahora la pantalla tiene banco propio con la fuente de a una letra por celda,
a 8 pixeles, y el texto va en ASCII. Y al mover el cursor la descripción no
entraba en el vblank: se compone en `texto_buf` y sube de un DMA por cuadro.
Dos veces más apareció el `ldx`/`ldy` de un byte con índices de 16 bits, que
se lleva el de al lado: `grep` antes de dar por bueno un camino nuevo.

Lo cobran `snes-items` y `pruebas/test_items_pantalla.py`, seis pruebas.

**Los HP y las medicinas (2026-09-11).** Fuera de batalla, en este juego nadie
baja nunca de los HP ni de los SP máximos: los 11 `ChangeHP` suman, los 16
`ChangeCondition` quitan y los 54 `FullHeal` llenan. Así que esos tres compilan
a nada —es exacto—, las medicinas van en blanco y abren la elección de actor
—el panel del grupo del menú con un cursor—, y A ahí no tiene efecto ni gasta
la medicina, como en RM2k. Los HP pasan a ser estado el día que haya batallas.

**El equipo (2026-09-11).** "Equipment" elige actor y abre sus ranuras; la
lista de cada ranura muestra lo que puede ponerse y los parámetros que
quedarían, y equipar mueve los ítems entre el inventario y `FAR_EQUIPO`, con
las armas a dos manos y el escudo como en RM2k. El equipo inicial sale del
LDB y viaja en la partida, que por eso pasó a ranuras de 2048 y la SRAM a 32
KB. Es la primera **pantalla de texto**: se compone entera en `texto_buf` y
sube de un DMA por cuadro, después de leer el control —antes perdía la mitad
de los toques—. `ChangeEquipment` no compila todavía: sólo en los mapas 30 y
151. Lo cobran `snes-equipo` y `pruebas/test_equipo.py`.

**La tienda (2026-09-11).** `OpenShop` compila a `OP_TIENDA` y abre
`Scene_Shop` como pantalla de texto: la principal, comprar con precios y el
oro, la cantidad, el "listo" de un segundo, y vender a mitad de precio. No
cuesta ticks, como guardar. El caso `tienda` de la tanda ahora entra —con el
A que antes sólo cerraba el mensaje— y sale con un B por cuadros de hardware.
Lo cobra `pruebas/test_tienda.py`, que la recorre entera en el mapa 10.

Lo que falta del sistema de ítems: los libros, los materiales y los
especiales, y `ChangeEquipment`. La consola y su evento común quedan afuera: taro
lo decidió el 2026-09-11, y la idea es un sistema propio del port en vez de
las imágenes del original.

### La lluvia (2026-09-11)

`WeatherEffects` compila a `OP_CLIMA` y la apertura llueve: la regla de RM2k
—doce cuadros de vida, cuatro pixeles abajo y uno a la izquierda, un diez
por ciento de chance de nacer— con la densidad escalada a 256x224, un
xorshift propio igual de los dos lados, y rayas de 4x16 en tres grises
opacos. Son objetos de 8x8 con prioridad 2 al final de la OAM, tapados por
los personajes y por la ventana. **Van pegadas al mapa** desde la noche del
2026-09-11 —taro vio que seguían a la pantalla al caminar—, y lo cobran
`pan-lluvia` y `sacudir-lluvia`. Un mapa sin lugar para sus colores no dibuja
lluvia —en la demo, el 2, el 8 y el 10, que no la usan—. Lo cobra `apertura`.
Detalle en el README, "La lluvia".

### Los efectos de sonido (2026-09-11)

`PlaySound` suena: `OP_SONIDO` dispara el efecto en la voz 7, robada a la
percusión y devuelta intacta al terminar. Los efectos se quedan con la ARAM
que la música deja libre; en la demo entran 5 de 38, la lluvia y el trueno de
la apertura entre ellos, y los que no entran no suenan. La tanda no mide
audio; lo medido fue una grabación A/B de la apertura (README, "Los efectos
de sonido"). **Falta que taro los escuche.**

### La música en una IRQ (2026-09-11)

taro escuchó el tema arrastrarse en la apertura con lluvia, tinte, trueno y
texto, y pidió que el audio ande siempre aunque la imagen se atrase más. La
música pasó a `irq_musica`, una IRQ vertical por cuadro de hardware; ya no
depende de cuánto tarda el lazo. README, "La música no espera al lazo".

### Los translúcidos, tramados (2026-09-11)

Los fuegos de los barriles del mapa 9 —el "Trans" de su página— van en
damero: la transparencia de la consola pide paletas que ese mapa no tiene.
README, "Los eventos translúcidos van tramados". Lo cobra `fuego`.

### Lo que le falta a la intro: medido, sin decidir (2026-09-11)

taro pidió todas las animaciones y los efectos de sonido que faltan en la
intro, en particular el Emitter Room. Lo medido:

* **Efectos de sonido: hecho**, con el paquete de audio de cada mapa —ver
  README, "El paquete de audio de cada mapa"—. Lo que había medido: el mapa 2 pide 18 distintos —contando los de sus
  animaciones de batalla— y el 3 veinte, que a la calidad de hoy (6 kHz, un
  segundo) son **43 y 55 KB**. Entran 10 KB: la música se lleva 53 de los 64
  de la ARAM, y es lo que necesitan los instrumentos de los ocho temas juntos
  —la percusión ya está en el mínimo—. Por tema, en cambio, son de 8 a 32 KB
  (evilrhys y lufsorr, los dos del Emitter Room, unos 20 KB de instrumentos).
  O sea que lo que falta es **un banco de audio por mapa** —los temas que ese
  mapa puede tocar y sus efectos— subido en el fundido de cada salto. Cuesta
  subir hasta 64 KB por salto, que al ritmo del arranque son unas siete
  décimas de segundo de negro de más, y hacer que el driver sepa escribir la
  ARAM con la música andando.
* **Animaciones de batalla** (`ShowBattleAnimation`, 3 en el mapa 2 y 8 en el
  3): **sus sonidos y sus destellos, hechos** —README, "Las animaciones de
  batalla: el sonido y la luz"—. **El dibujo falta**: celdas de 96x96 con zoom
  de hasta 200% y paleta propia; en el mapa 3 todas son de fuego (`Fire1`).

**El dibujo de las animaciones, medido (2026-09-11, sin empezar).** En todo el
juego son 388 `ShowBattleAnimation` en 81 mapas, con 42 animaciones distintas.
Las más usadas son chicas: la 141 (144x144), la 168, la 1 y la 132 (96x96).
Las de la intro son las peores: la 79 y la 82 llegan a 512x192 y 488x336 con
zoom de hasta 400%, y la 62 a 384x384. Cada cuadro se puede prerenderizar
—las celdas escaladas y compuestas— y subir como sprites, con estos límites:
VRAM de sprites libre en los mapas 2 y 3, 101 y 162 tiles (una caja de 96x96
son 144); una paleta de sprites más en mapas que ya usan las ocho; 34 tiles de
sprite por línea, que una animación ancha se come; y el DMA de un cuadro de
96x96 son 4,6 KB cada dos cuadros. Los colores —hasta 38— se reducen a 15, y
la transparencia va tramada. Las grandes no entran enteras de ninguna forma.

**Una deuda encontrada de paso, anterior a todo esto:** la página de prueba no
arranca en el Emitter Room con `--switch 13 --mapas 4` —`auto_n` queda en cero
y la bandera del evento de prueba apagada—, mientras la referencia la corre.
Es lo que impidió armar un caso con la escena grande del mapa 3. No se
investigó más.

### El giro hacia el héroe (2026-09-11)

taro lo pidió probando la ROM: los NPCs miran al héroe cuando les habla, y al
terminar su página vuelven a su pose. Es la "ranura de giro por mapa" que
`assets/LIMITACIONES.md` proponía: el quieto se muda a ella y ahí se le sube
la pose desde las doce de su gráfico, que por eso van al cartucho; el que
camina gira en la suya. Lo cobran `bum-vuelve` —el que camina, con el giro
deshaciéndose al cerrar el último mensaje— y `gemelo` —un quieto del mapa 10
con un gemelo que no se mueve—. Los que caminan solos no giran porque no está
modelada la pausa de RM2k: ver LIMITACIONES.

### El atraso de la apertura (2026-09-11)

La apertura perdía 181 cuadros en 3000; ahora 20, sueltos. FastROM —el
código corre desde el espejo del banco $80—, los glifos del compositor ya
compuestos por fase —59 KB, y el cartucho pasó a 2 MB—, la lluvia más barata
y el destello con una tabla de productos. Ni la referencia ni lo que se
dibuja cambian. README, "El costo de la apertura". **Falta que taro lo
pruebe en la consola**: FastROM y los 2 MB son justo lo que un emulador
puede perdonar y el FX Pak no.

### El MSU-1: los ocho temas de las demos (2026-09-11)

taro pidió probarlo: *"la música hoy en día está sonando bastante fea"*, y el
FX Pak lo soporta. Lo escuchó en Mesen —*"se escucha con mucha más calidad"*— y
pidió el resto de la música, así que ahora son **los ocho temas de las demos**.
Y trajo un defecto: con la pista sonando **no había efectos de sonido**.

**Arreglado: el DSP se quedaba sin inicializar.** Lo hacía el comienzo del
stream del tema —el mute con que arranca el SPC700, el volumen general, el
directorio de muestras—, y con pista el stream no corre nunca, así que los
efectos se disparaban contra un DSP mudo. El prólogo lo emite ahora el
conversor (`dsp_init_reg`/`dsp_init_val`, desde `init_writes`) y lo manda
`music_start`. De paso, dos del mismo vecindario: el fundido ya no baja el
volumen del DSP cuando hay pista —es el que oyen los efectos— y `op_fundir_bgm`
deja pasar el `FadeOutBGM` con `music_apagada` puesto, que con pista vale 1 y
hacía que la pista no se fundiera nunca.

**Y la pista suena a `$D8` y no a `$FF`** (`MSU_VOLUMEN_MAX`), desde que taro
escuchó clipping en el Emitter Room y los efectos bajos. Las dos cosas son el
mismo número: el MSU-1 se suma a la salida del SPC700, y con la música al tope
no queda margen. Medido en la apertura: 42 muestras al tope con `$FF` —todas en
cuadros con un efecto sonando— y **cero** con `$D8`, con la música bajando de
28933 a 24508, que es el nivel que tenía por el SPC700 (23867). El fundido
escala contra ese techo; el lazo del producto es uno solo para los dos caminos
y se verificó que el `FadeOutBGM` del SPC700 sigue bajando igual.

**Lo que no se pudo medir: el Emitter Room.** Es donde taro escuchó el
clipping, y todas mis corridas se quedaron en el mapa 1 —la apertura no avanza
sola, y los números de `apertura` en rom/hitos.txt son **ticks**, no cuadros de
hardware, que es con lo que estuve apretando A—. Lo medido es la apertura, y
ahí el clipping existía y desapareció; el Emitter Room tiene catorce efectos y
otro tema, así que conviene volver con `snes-cinematica` bien usado.

**Los efectos por MSU-1 no van, y no es una decisión: es el hardware.** El
MSU-1 es un único stream estéreo; mientras toca la música no hay dónde meter un
disparo. Se quedan en el SPC700, que además ahora tiene la ARAM más holgada.

**Cómo medir esto, que costó dos intentos.** La primera medición —poner
`SE_CUADROS` en cero desde el arnés para suprimir el efecto— daba cero
diferencias **también sin MSU-1**, donde los efectos se oyen: no suprimía nada.
La que sirve es la misma ROM con los volúmenes de `sonido_tabla` en cero. Y el
control por el camino conocido es obligatorio: sin él ese cero parecía una
medición. Está escrito en el README.

El detalle está en el README, "El MSU-1"; lo que hay que saber acá:

* **Sin los archivos `.msu`/`.pcm` la ROM suena exactamente como antes**, y ése
  es el camino que corren la tanda y todas las pruebas: 123 casos en verde
  sobre la foto `b188079`, y `just pruebas` 83 en verde con el `xfail` de
  siempre. Verificar el camino *con* MSU-1 pide grabar audio, y eso se hizo
  aparte: nivel, correlación de envolventes (0,927), fundido y efectos, todos
  medidos y escritos en el README.
* **Lo que no tiene evidencia propia**: el guard nuevo de `op_fundir_bgm`. El
  fundido se probó escribiendo `bgm_fundido` desde el arnés, que entra por
  debajo del comando; para ejercitarlo de verdad hay que correr una escena con
  `FadeOutBGM` y pista sonando —las hay en los mapas 3, 4 y 9— y ninguna está
  en la tanda con MSU-1, porque la tanda corre sin esos archivos.
* **Las pistas no salen de `snes-demos`**: son `just snes-msu <demo>`, aparte,
  porque pesan 10,6 MB por minuto y para jugar no hacen falta.
* **En la tarjeta los tres archivos van juntos y con el mismo nombre base.** Si
  taro renombra el `.sfc`, tiene que renombrar el `.msu` y los `.pcm` o el
  MSU-1 no se enciende y la música vuelve al SPC700 —sin romper nada—.
* **Escuchado en Mesen el 2026-09-11** y aprobado; mednafen **no tiene MSU-1**,
  así que ahí suena por el SPC700 y es el control natural de que el camino sin
  pista sigue andando. **Falta el FX Pak**, que es lo que taro iba a probar.
* **Falta el punto de loop**: el MSU-1 vuelve al principio del archivo, así que
  un tema con introducción la repite cada vuelta. Y faltan los 35 temas que las
  demos no tocan, que son 923 MB si algún día van todos.

### Lo próximo, si no se decide otra cosa

Al 2026-09-10, en orden. Los tres primeros son deuda de esta vuelta y están
acotados; del cuarto para abajo es lo de siempre.

0. **El sistema de ítems y equipamiento, y el menú de pausa.** taro lo planteó
   el 2026-09-10 a la noche como lo que sigue. Lo medido, para diseñarlo:

   * El LDB tiene 450 ítems (`data/db/items.json`); el juego da o vende **226**
     —81 armas, 48 piezas de armadura, 36 comunes, 18 medicinas, 17 únicos, 7
     libros, 1 de switch—. `ChangeItems` aparece 509 veces en 87 mapas, siempre
     de a un ítem constante y una cantidad constante (366 dan, 143 quitan);
     `ChangeGold` 48 veces; `ChangeEquipment` 34 veces en dos mapas (el 30 y
     el 151); `OpenShop` 43, ninguna con ramas. Ocho ítems distintos entran
     en condiciones de página (52 páginas).
   * Datos en la ROM: por ítem el nombre, la descripción, el tipo, el precio y
     el efecto (HP que cura; ataque y defensa del equipo). Texto en la fuente
     que ya compone la ventana. Unos 12 KB.
   * Estado: la cantidad por ítem —450 bytes, un byte cada uno, RM2k topa en
     99— y el equipo por actor —cinco ranuras de un word para los actores
     posibles—, en la RAM lejana desde `$26A2` (después de las variables) y
     en la partida, que pasaría de 322 a unos 900 bytes: sigue entrando en la
     ranura de 512 sólo si se sube `SRAM_STRIDE` a 1024; hay 8 KB.
   * Orden sugerido, cada paso con su caso en la tanda y su prueba de estado:
     (1) el inventario y `ChangeItems`/`ChangeGold` de verdad, con lo que las
     condiciones de página por ítem dejan de ser "nunca activa" y `OpenShop`
     deja de ser una deuda; la referencia lleva el mismo inventario en
     `Estado`. (2) El menú de pausa de RM2k —`Use Item`, `Tech Skill`,
     `Equipment`, `Save`, `End Game`, con el grupo a la derecha: cara, nombre,
     nivel, HP— sobre la máquina de la pantalla de ranuras (`ranuras_pantalla`
     ya bloquea el reloj y vuelve al mapa) y el compositor de la ventana; el
     oráculo es `titulo.py` extendido, como con las ranuras. (3) El inventario
     y el uso de medicinas —pide HP, o sea los parámetros de los actores y los
     niveles, que hoy no existen—. (4) El equipo y la tienda. Sin batallas,
     HP, ataque y defensa son cosméticos: se muestran, no se usan.
   * `ChangeSaveAccess` (70 usos) y `ChangeMainMenuAccess` (4) se honran
     desde el 2026-09-11, junto con el menú.
   * **Hechos**: el (1), el inventario, el 2026-09-10 a la noche; el (2), el
     menú de pausa con guardar, el 2026-09-11; el (3) a medias el mismo día:
     la pantalla de ítems y los de switch, sin medicinas.

1. **El menú de guardado desde el save point: hecho** el 2026-09-10 a la
   tarde. Queda el renglón para que nadie lo busque.

2. **El `xfail` de guardar tras cambiar de mapa.** Sigue siendo un artefacto de
   la página de prueba y sigue sin confirmar por ese camino, pero ahora hay dos
   datos más. El caso con el save point de verdad **existe** —`savepoint-guarda`
   en la tanda— y da cero, así que el juego guarda desde el mapa 8 después de
   haber cambiado de mapa; lo que no se ha mirado es la SRAM después de ese
   caso. Y se encontró un primo del mismo vecindario, también de la página y
   no del juego: la página prende `SWITCH_DE_PRUEBA` al arrancar, la partida
   se guarda con él puesto, y **al cargarla gana la página que la apaga**, así
   que después de "Resume the Story" la automática no corre nunca. Está
   resuelto desde afuera con `Partida.apagar`, y escrito en
   `test_el_cursor_de_guardar_arranca_en_la_ranura_en_uso`. Vale la pena
   mirar si el `xfail` es lo mismo con otra cara —el doble `cargar_mapa` del
   título contra el refresco de páginas— antes de tocar la ROM.

3. **El tile testigo del mapa 4**, que propuso taro: que un mapa vacío no se
   confunda con una pantalla rota. Por el conversor y bajo un flag, no editando
   `Map0004.lmu`. Ver la sección propia, más abajo.

4. **Las ROMs para probar viven en `/extras/builds/<fecha>-<commit>/`**,
   copiadas de las demos apenas se arman, porque `rom/build/` lo pisan las
   pruebas y el `snes-demos` siguiente; taro lo pidió el 2026-09-10. La de hoy
   es `/extras/builds/2026-09-10-5837301/`, con `demo-ciudad.sfc` y
   `demo-titulo.sfc` del commit 5837301 —variables y Tram Officer—.
   **Probado en mednafen el 2026-09-10 a la tarde, y anda; en la consola
   todavía no.** taro jugó las demos con el menú de guardado: guardó y cargó
   en las ranuras 1 y 4, con el cronómetro en distintos momentos, y todo
   perfecto. Lo único que trajo fue el tema del título reiniciándose al volver
   de las ranuras, que está arreglado abajo. El FX Pak sigue pendiente. Al hablarle al save point se abre "Save in which slot?",
   se elige con A o se vuelve con B.
   **Salen de `just snes-demos` y de ningún otro lado.** La primera versión de
   esa tarde estaba armada a mano con el `grupo` del justfile, que es el 11
   del banco de pruebas, y taro la vio así: Kersh sobre negro desde el primer
   cuadro, y la apertura del mapa 1 quieta y sin música. Con Kersh ya en el
   grupo la página automática de la apertura no corre, y la referencia hace lo
   mismo; `snes-cinematica` usa el 10 por eso. Verificado sobre la rearmada:
   la apertura entera hasta el tick 2910 da cero contra la referencia con los
   ocho mapas y el cronómetro.
   **La partida guardada de antes no sirve**: `PARTIDA_BYTES` cambió dos veces
   el 2026-09-10 —las ranuras y la música; el menú no lo tocó— así que hay que
   guardar de nuevo con la ROM nueva antes de probar la carga. Lo que conviene
   mirar en la consola y acá no se puede: los dos cuadros negros al volver del
   menú, y que los NPCs de Lashe City vuelvan con sus poses —es lo que se
   rompía con las direcciones viejas de VRAM, y snes9x sí lo cobró, pero sólo
   con el grupo 11—.
   **Las más nuevas son `/extras/builds/2026-09-12-af1493d/`**: la pista al 85%
   en vez de a fondo, que es lo que saca el clipping y devuelve el balance con
   los efectos. Mismas pistas que el build anterior —no hizo falta rehacerlas—.
   Lo que falta escuchar ahí es el Emitter Room, que acá no se pudo reproducir.
   Antes, `2026-09-11-ddc82ea/`: los ocho temas
   por MSU-1 y los efectos de sonido de vuelta. Son las dos ROMs con su `.msu`
   vacío y ocho `.pcm` cada una, 195 MB por ROM —las pistas están duplicadas
   con los dos nombres base porque el MSU-1 empareja por nombre—. Borrando esos
   archivos las ROMs suenan por el SPC700 como siempre; el `LEEME.txt` del
   directorio lo explica, con la lista de qué tema es cada número.
   Antes, `2026-09-11-e6bb4bc/`, con el MSU-1 en `escape_newyork` solo —la que
   taro escuchó en Mesen—. Antes, `2026-09-11-d150491/`: el paquete
   de audio por mapa, las animaciones con sonido y destellos, y los
   translúcidos tramados, sin probar a mano. Antes, `2026-09-11-9fe396b/`, con
   el giro hacia el héroe. La anterior, `2026-09-11-7d992b6/` —el menú, la tienda, la
   lluvia pegada al mapa, los efectos, la música en una IRQ y FastROM—, taro
   la probó en mednafen y anda sin lag. Son de
   2 MB. La anterior, `2026-09-11-19e7dcc/`, es la que taro probó y le trajo
   el lag y la lluvia pegada a la pantalla. La SRAM pasó a 32 KB y la partida creció con el
   equipo, así que las partidas de las ROMs anteriores no cargan.

5. **Lo que sigue faltando de Lashe City**: la condición de **ítem** —45
   eventos— quedó resuelta como "nunca activa", las **variables** están desde
   el 2026-09-10 a la noche, y **Lashe City Interiors (10) y Lashe City 33,36
   (9) están en la demo** con sus puertas. Las condiciones de página por
   variable y la velocidad del héroe en las rutas están hechas (2026-09-10 a
   la noche). Lo que queda: la condición por cronómetro —una página en todo
   el juego— y el `CallEvent` del Hover-Tram.

6. **La animación del save point** (`animation_type` 3, "Fixed Dir/Continuous")
   está **hecha** desde el 2026-09-09; queda el renglón para que nadie la
   busque como pendiente.

7. **El giro de los eventos al hablarles.** Hoy contestan mirando para donde
   estaban; es una deuda declarada en `assets/LIMITACIONES.md`, con el diseño de
   la ranura de VRAM que haría falta ya escrito.

8. **La ráfaga de entrada del mapa 8**, ahora que la tanda no la cobra: son dos
   cuadros perdidos al entrar, invisibles jugando porque el fundido los absorbe.
   Está perfilada más abajo. Es optimización, no corrección.

9. **Los gráficos: está todo medido y vive en `assets/`.** El titular, para no
   tener que abrirlo: **el juego entra en 4 MB**. Son unos 2,9 MB entre mapas,
   sprites, tiles y música, más 2,7 de arte que todavía no dibuja nadie.

10. **Los líderes posibles son una aproximación.** El conversor simula los
   `ChangePartyMembers` de las páginas que compilan para saber qué actores
   pueden ir primeros. Si alguna vez un personaje se dibuja sin gráfico, es el
   primer lugar donde mirar; `pruebas/test_lideres.py` cuida la parte que ya
   falló.

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
  soltar la mirada. Decidido con taro el 2026-09-06: son un extra, como los
  efectos climáticos, y el juego se puede jugar sin ellas. Se tiran **al
  compilar**, como el sonido y la transparencia, así que la referencia tampoco
  las camina y los dos lados quedan iguales por construcción. **Las 28 y 29
  —la velocidad— se hacen desde el 2026-09-10 a la noche**: lo que sigue es
  la historia de por qué se tiraban.

  El primer intento fue **rechazar la página entera**, y costaba demasiado: la
  escena de Talan tiene una ruta del héroe que empieza con la 28, así que la
  escena que motivó los seis puntos no compilaba y el jugador se quedaba
  encerrado en el pasillo del Emitter Room —taro lo encontró jugando—. Son 4
  páginas automáticas más ésa.

  Lo que se perdía era el cambio de ritmo: donde RM2k acelera al héroe, acá
  caminaba a la suya. Arreglarlo fue que su paso dejara de ser fijo —era
  `WALK_SPEED`, ocho cuadros por celda, escrito a mano en `try_up` y sus tres
  hermanas— y pasara al acumulador de 256 por celda que ya tenían los eventos,
  a medias unidades para que entre en el byte de `step_left`. Ver "La
  velocidad del héroe" arriba. En todo el juego son 178 rutas.

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

* **Los builds numerados de `rom/build/` no se arman a mano.** No están en git
  y no los produce ninguna receta salvo el 12. Armar uno a mano es cómo se
  terminó mirando el mapa 6 creyendo que era la demo del hito 12.


## Decisiones tomadas el 2026-09-07

**El presupuesto de teletransportes se repone cuando el jugador tiene el
control, y agotarlo es un error, no un caso.** `saltos_restantes` existe para
que dos mapas que se apunten entre sí no cuelguen a la consola. Estaba mal de
las dos maneras posibles: sólo lo reponía `cargar_mapa`, que a esa altura
llamaba únicamente una **puerta** —un comando `Teleport` carga el mapa por
`cargar_mapa_sin_eventos`—, así que los ocho se gastaban para toda la partida; y
al agotarse, el salto se **descartaba en silencio**. Ahora se repone en
`eventos_tick` cada cuadro en que no hay nada corriendo ni esperando, que es el
mismo alcance que tiene en la referencia —`saltos` es local a `entrar_al_mapa`—,
y al agotarse la ROM llama a `entrar_en_panico`: deja el código en `panico` y
parpadea la pantalla para siempre. La referencia levanta `DemasiadosSaltos`.

Lo pidió taro y tiene razón por encima del caso: un salto descartado sin avisar
es la forma de falla que el CLAUDE.md nombra, y ésta sobrevivió semanas porque
la partida seguía andando, sólo que en el mapa equivocado.


**`ShowChoice`, y el cursor sin un solo tile nuevo.** La ventana con opciones es
la ventana de mensaje de siempre, y el cursor no se dibuja: el conversor emite
**un cuadro de texto por opción** —los mismos renglones, el `>` en otro lado— y
moverlo es recomponer la ventana con otro desplazamiento. Cuesta unas decenas de
bytes por elección y ahorra un tile de sprite, una paleta y el código de
dibujarlo; en la consola un cursor tiene que ser un sprite, y los del mapa ya
están repartidos entre los personajes. Recomponer un renglón de cinco
caracteres son dos cuadros, así que se ve como un cursor que se mueve.

El bytecode es `OP_ELEGIR`, con la misma forma que `OP_SI`: destinos absolutos
dentro de la página, resueltos por el conversor, que es el único que ve la
página entera. El cuerpo de cada opción termina en un `OP_IR` al final de la
elección, emitido en la opción **siguiente** —ahí se sabe que la anterior
terminó— y no en el `END` del cuerpo, para no depender de la indentación.

**El movimiento del cursor no lo cubre la tanda de pixeles y no se modela en la
referencia.** La tanda sólo sabe apretar A, así que arriba, abajo y B son
caminos que no puede ejercitar; escribir del otro lado código que ninguna prueba
corre es exactamente cómo sobrevivieron los tres errores del intérprete. Lo
cubre `pruebas/test_elegir.py`, que aprieta cualquier botón. La tanda cubre la
otra mitad, que es cómo se ve.


**El spike de desacoplar los gráficos: hecho, y lo que midió vale más que lo que
ahorró.** Los bloques de datos pasan por `Materiales`, tienen nombre propio en
vez del número del mapa que los pidió, y los idénticos se emiten una sola vez.
El primer paso salió **byte por byte igual** en seis configuraciones del
conversor, que es una red más fina que la tanda para un refactor.

Encender la deduplicación ahorra **0,1 KB**, y todo son bloques vacíos. Ése es
el resultado: separar el material de los mapas no ahorra nada por sí solo. Lo
que lo explica está medido en `assets/README.md` —seis mapas del mismo chipset
comparten hasta 122 tiles de 150 **como dibujo** y 2 como bytes—, así que todo
el ahorro está del otro lado, en las paletas.

Vale igual porque es la infraestructura que la estrategia de paletas necesita:
sin bloques con identidad propia no hay dónde poner un tile que sea de dos
mapas. Y porque convirtió la frase "es un problema de paletas disfrazado" en un
número.

Y dejó una lección sobre las dos redes. El primer paso se verificó comparando
bytes y las seis configuraciones dieron idéntico; el segundo **rompió**
`snes-varios`, porque `tabla_de_paginas` seguía rearmando `evcodigo_<mapa>` con
el número del mapa y dos mapas pasaron a compartir el bloque. Comparar bytes no
podía verlo —esas seis configuraciones no tenían dos mapas con el mismo código
de eventos— y la tanda lo cobró en el primer intento. Ninguna de las dos redes
sobra.


**La ventana de mensaje se muda a la paleta 0, y el fondo recupera media
CGRAM.** Iba en la paleta más baja de las capas de encima de toda la ROM, y al
fondo se le daba sólo el bloque que quedaba debajo: 47 colores, mientras las
paletas 4, 5 y 6 no las usaba nadie. BG1 va a 8 bits y direcciona CGRAM en
directo, así que no le hacía falta ninguna alineación; le hacía falta que la
ventana no le partiera el espacio al medio.

Con la ventana abajo de todo —nueve entradas, el color de fondo más sus ocho
colores— el fondo queda contiguo desde la 9 hasta su propia capa de encima. En
`demo-apertura` el presupuesto pasa de 47 a 55, 71, 87 o 103 según el mapa, y
los colores fusionados de **97 a cero**. Ningún mapa pierde un color.

Se cayeron dos cosas que existían sólo por la paleta flotante: la reconversión
de mapas en `main()` y el rastreo de la paleta en la referencia, que obligaba a
convertir todos los mapas de la tabla para dibujar uno.

Detalles del arreglo, por si alguno vuelve a morder:

* `subir_paletas` subía la paleta del mapa desde la entrada 0 y le pisaba la
  ventana. Ahora arranca en `CGRAM_BASE`.
* Los colores de la ventana se contaban con `sum(1 for w in cram if w)` y son
  **ocho, no siete**: uno es negro puro y su palabra es cero. Con siete
  reservadas el texto salía con un color que nadie había subido —79 pixeles—.
  `convert_ventana` ahora mira el índice más alto que usa y corta si no entra.
* El tinte no toca la ventana **por dónde arranca el rango** y no por acordarse.


**El cronómetro comparte paleta, y el cartucho pasa a 1 MB.** Los dígitos usan
dos colores —negro y rojo puro— y se llevaban una de las ocho paletas de sprite
para ellos solos. Ese número no es contabilidad: `npcs_dibujables` decide con él
**qué eventos se dibujan**, y un evento que no se dibuja igual ocupa. Con siete,
el mapa 2 perdía el evento 30, que es la celda del medio de la puerta que Core
rompe: taro llegó a la cinemática, la puerta no cambió de tile y no pudo pasar.

Ahora entran en la paleta de cualquier personaje que tenga trece o menos, con el
mismo primer-ajuste que ya se usaba para los eventos dibujados con un tile del
chipset. Y al recuperar esos eventos la ROM se pasaba por 8 KB, así que
`ROM_BANKS` pasó a 32: el área de datos ahora se deriva de ahí en vez de estar
escrita a mano, y la cabecera dice `$0A`.

**Y descartar un evento dejó de ser silencioso.** Era un `print` entre otros
cincuenta y por eso costó una tarde.

El ruido va en el conversor y no en la ROM a propósito, aunque taro pidió que
"crasheara el juego": un descarte se decide **al convertir**, y para cuando la
consola corre el evento ya no está en ninguna tabla. Hacerla explotar al cargar
el mapa sería lo mismo que no armar la ROM, pero más tarde y sin poder decir
cuál evento.

Y no corta con **todos** los descartes, porque eso tampoco protegería: hoy hay
decorativos que no entran en varios mapas, así que todas las recetas tendrían
que pedir seguir y el corte quedaría apagado en todas partes. El tope es
`cambia_de_grafico`: un evento con una sola página que no se dibuja se pierde y
ya —el `CoreBlood` del mapa 3, los cuatro `Link`—, pero uno que **cambia de
gráfico entre páginas** es un mecanismo, y sin dibujarse deja una pared
invisible donde el juego esperaba una puerta. El evento 30 del mapa 2 era de
esa clase, así que el corte lo habría agarrado.

Dos builds lo declaran con `--descartar-eventos`, y los dos tienen un mecanismo
roto de verdad que arregla el trabajo de paletas y no un flag:

* **`demo-apertura`**: los eventos 31 y 32 del mapa 2, los costados de la misma
  puerta que Core rompe. Hoy la puerta funciona porque el 30, el del medio, es
  el que abre el paso.
* **`snes-convert`**, que usa `snes-heroe 8`: `PawnDoorTop` del mapa 8.


**Una puerta al mismo mapa ya no recarga el mapa.** Un `Teleport` al mismo mapa
lo distinguía desde antes —`hubo_salto` compara con `mapa_actual`— pero una
**puerta** —una página de contacto cuyo único comando es un teletransporte, que
el conversor compila a una tabla aparte— recargaba siempre. Recargar vuelve a
leer del cartucho las posiciones de los eventos, y con eso se pierde lo que los
haya movido aunque el jugador nunca haya salido del mapa.

taro lo vio en la puerta de arriba a la izquierda del mapa 2: abrirla manda el
`LBDoorTop` a (94,97) y truequea el `LBDoorBottom` con el `MovinDoor`, así que
el hueco queda negro; al volver reaparecían las franjas amarillas. Los dos
cuartos que jugando parecen dos mapas son el mismo mapa 2.

**La referencia lo tenía peor: recargaba en los dos caminos.** Su lazo llamaba a
`entrar_a_un_mapa` en cada vuelta, también sin cambio de mapa, así que ni el
`Teleport` de ida estaba bien modelado. No se veía porque ningún caso de la
tanda mueve un evento y después salta adentro del mismo mapa. Ahora los dos
lados comparan contra el mapa anterior, que es el `map_changed` de
`Game_Player::PerformTeleport`.

Lo cubre `pruebas/test_puerta_misma.py`, con una tercera ROM compartida que
lleva el mapa 2 solo —alcanza, porque los teletransportes son internos—.


**Los líderes posibles comparten una ranura de CGRAM.** Lidera uno a la vez, así
que reservarle una paleta de sprite a cada uno es tenerla ocupada por alguien
que no está en pantalla. Ahora la tabla de actores lleva los quince colores de
cada líder y la ROM los sube a la ranura al cargar el mapa y al cambiar el
grupo, **por el camino del tinte** para que se tiñan con todo lo demás.

La excepción es el líder que además está como NPC en ese mapa: ése se lleva
paleta propia, porque su fila la usa al mismo tiempo que el héroe. Pasa con
Kersh en los mapas 1 y 6 y con Talan en el 3; ahí no se gana nada, pero tampoco
se rompe. En los otros seis del PoC se gana una paleta.

Dos cosas que destraba:

* **El mapa 2 deja de descartar los eventos 31 y 32**, que son los costados de
  la puerta doble que taro veía con "cachos". Era su tercer bug cosmético.
* **El mapa 8 entra en las ocho paletas**, que era el bloqueo para salir del
  pad de Talan. Falta una sola cosa: los dos colores del cronómetro. El negro ya
  está en siete de las ocho paletas y falta el rojo puro, con las ocho llenas a
  quince. Lo más barato medido es bajar a `BLVehicles:5` de 15 a 14 colores:
  **105 pixeles de 4648, 2,26%**, con un salto de 4 sobre 31; los otros
  candidatos cuestan 11% o más.


**La tecla de acción mira las dos celdas.** `Game_Player::CheckActionEvent`
prueba la del héroe y la de adelante, y **cada una pide la capa contraria**:
`CheckEventTriggerHere` quiere `GetLayer() != Layers_same` y
`CheckEventTriggerThere` quiere `== Layers_same`. No es simetría de adorno: un
evento de la capa del héroe le cierra el paso, así que nunca se podría parar
encima; uno de otra capa no lo frena y se le camina por arriba.

Sólo estaba la de adelante, y estaba escrito como hueco conocido en
`puede_dispararse`. taro lo encontró jugando el 2026-09-07: la puerta que sale
del pad de Talan es `TalDoorTop`, evento 3 del mapa 7, **de acción y capa 2**, y
se abre parándose encima. Debajo está `TalDoorBottom`, de la capa del héroe, que
bloquea; por eso hay que llegar desde arriba.

El filtro de capa pasó a la ROM y ya no lo resuelve el conversor: la misma
página vale o no según qué celda la esté mirando, así que rechazarla al compilar
no alcanzaba.


**El oro, y dos clases más de `ConditionalBranch`.** `OP_SI` ganó adelante un
byte con **la clase de condición, con el número de RM2k tal cual**, y con eso
entran dos que no piden estado nuevo o casi:

* **"el actor está en el grupo"** —el `grupo` ya estaba—, +9 páginas. Sólo el
  sub-tipo 0: de los 155 comandos del juego que preguntan por un héroe, 57 son
  de ése; 78 preguntan por el equipo y 20 por una habilidad, y eso pide
  estadísticas de actor que no llevamos.
* **el oro**, +7 páginas, junto con `ChangeGold`, que hasta ahora se aceptaba y
  no se hacía.

En total **2313 → 2329 páginas**. Dos que se midieron y se descartaron: la
orientación del héroe y el cronómetro destraban **cero** —esas páginas están
frenadas por otra cosa igual—.

El oro son tres bytes: el tope de RM2k son 999999 y este juego usa el valor
entero. Se recorta a [0, 999999] como `Game_Party::GainGold`.

Y un detalle que casi se escapa: **`>=` y `<=` no son una la negación de la
otra**, porque en la igualdad se cumplen las dos. El primer intento calculaba
`oro >= x` y le daba vuelta el bit según la polaridad, que está mal exactamente
en el borde. La ROM las calcula por separado, y el banco de prueba pasa por ahí:
el `DetourOfficer` del mapa 8 es un peaje que pregunta `oro >= 500` y cobra 500,
así que con 500 justos tiene que cobrar.


**El que atraviesa paredes cae donde sea, también saltando.**
`Game_Map::CheckOrMakeWayEx` corta con `if (self.GetThrough()) return true;`
apenas pasa el chequeo de límites, **antes** de mirar la pasabilidad, y el salto
de una ruta pasa por ahí: `BeginMoveRouteJump` llama a `MakeWay`. Nuestro
`puede_caer` miraba sólo la pasabilidad.

Lo encontró taro el 2026-09-07 en el recuerdo de Core y Manta: Core se movía
arriba de su piedra y no saltaba nunca. Las celdas de las piedras están cerradas
de verdad —(31,18) tiene los cuatro bits en cero—, que es el punto: son piedras
en el agua. Su ruta arranca con `atravesar_on`, así que tenía permiso.

Lo incómodo del caso: **la caminata sí lo respetaba** y el salto no. La misma
regla implementada en un camino y olvidada en el otro, y por eso costaba verlo.


## Decisiones tomadas el 2026-09-08

**Se dibujan todos los eventos, aunque sea con una paleta ajena.** Es de taro:
*"si no podemos incluir todos los eventos, el proyecto entero se cae"*. El
gráfico que no consigue paleta propia se cuelga de la que menos colores le
falte y cada color ausente va al más cercano por luma. Los números y el caso
que los justifica están en `assets/LIMITACIONES.md`; lo que destraba es el mapa
8 —que pedía trece paletas de ocho— y el Hover-Tram.

La referencia hace la **misma** aproximación: `pose_image` recibe la paleta
prestada y elige el color más cercano con la misma cuenta. Sin eso la
comparación medía dos programas distintos, y lo cobró el caso `talan` con 332
pixeles.

**El reparto de VRAM se rebalanceó**, porque dibujar todo llevó al mapa 8 de 192
a 347 tiles de sprite y ningún reparto le daba 400 de fondo y 347 de sprite a la
vez. La capa de encima bajó de 256 tiles a 128 —la mediana de los 328 mapas es
**1 tile** y 326 entran en 128—, los tilemaps se mudaron a `VRAM_MAP = $5800` y
`VRAM_ABOVE_MAP = $7800`, y `VENTANA_TILE_BASE` sale del reparto en vez de estar
escrito a mano.

### El cuadro del tinte estaba a una línea de barrido de perderse

Y el primer evento de más se lo llevó puesto. Medido con una sonda que engancha
`OPVCT` al final del lazo principal: una vuelta normal termina en la línea 61 de
262, y la vuelta en que corre `aplicar_tinte` terminaba en la **224**, con
vblank arrancando en la 225. Un cuadro perdido, y la pantalla queda sin teñir un
cuadro contra la referencia.

El gasto era `armar_paleta`: 151 colores por vez —el mapa, la capa de encima,
las ocho paletas de sprite y el líder— a 205 ciclos cada uno. Con la saturación
neutra, que es casi siempre, el color no necesita los tres canales juntos ni
salir de los dieciséis bits: el lazo corto lo baja a ~123 y la vuelta termina en
la 188. Quedan 37 líneas de margen donde había una.

### El cronómetro iba un cuadro adelante, y un cuadro perdido lo tapaba

`timer_tick` corría **después** de `eventos_tick`, y en `Game_Map::Update`
—easyrpg, `game_map.cpp:1304`— `UpdateTimers()` corre **antes** de
`UpdateForegroundEvents`. O sea que la página que arranca el cronómetro no
debería llevarse un cuadro en el mismo cuadro en que lo arranca, y acá se lo
llevaba. La ROM quedaba un cuadro adelante para siempre; se ve sólo en los
cuadros en que parpadean los dos puntos o cambia un dígito.

Nadie lo cobraba porque `snes-timer` tiñe la pantalla, el tinte costaba el
cuadro perdido de acá arriba, y ese cuadro tapaba justo este uno de más. **Los
dos errores juntos daban cero**, que es exactamente el modo en que la
comparación falla en silencio. Se destapó al arreglar el presupuesto, no al
buscarlo.

## Decisiones tomadas el 2026-09-08, tarde

taro jugó `demo-ciudad` y trajo nueve síntomas de Lashe City. Medidos, son
**cuatro causas**, y la más grande no estaba en su lista:

| causa | tamaño en el juego entero |
|---|---|
| páginas de acción frenadas porque el evento tendría que **girar** | 1572 páginas, 1224 eventos, 220 mapas |
| trigger **Parallel Process** | 353 páginas, 86 mapas |
| eventos afuera por **condición de ítem** | 45 eventos (14 más por variable, 1 por cronómetro) |
| un evento que **camina y además aparece** con la página | el `Bum` y el `Mechanic` |

**El giro se declara como deuda y la página corre igual.** De las 1572,
compilan enteras **1535 en 214 mapas**: es, de lejos, lo más grande que se
destrabó de una vez. El evento contesta mirando para donde estaba. Lo que falta
para hacerlo bien —una ranura de VRAM por mapa— está en
`assets/LIMITACIONES.md`.

**Caminar y aparecer dejaron de ser el mismo bit.** No hacía falta uno nuevo: la
fila ya dice si camina (`+9`), así que la ROM copia de la página todo menos el
tile y la paleta. El bit 4 de `+13`, que fue el primer intento, **está ocupado**
—con ruta propia esos cinco bits son las banderas de la ruta— y usarlo escondió
al droide del mapa 2 en seis casos de la tanda.

### Lo que sigue faltando en Lashe City

* **Parallel Process**: `Car1`, `Car2`, `Car4`, `EV0004` y `EV0005` no se
  mueven. El intérprete ya existe; falta la clase de disparo.
* **Condición de ítem**: `PawnDoorBottom`, `GangMember1`, `EV0039`, `EV0040` y
  `EV0041` se caían enteros —no se dibujaban, no frenaban y no disparaban—.
  Resuelto el 2026-09-10: hay inventario y la condición se evalúa. `EV0041`
  **no** es el caso de la puerta del pad, como parecía: era esto.
* **Lashe City Interiors** no está en la ROM, así que `EV0055`, `EV0033` y
  `EV0057` no compilan. taro lo pidió para la próxima vuelta.

## Parallel Process, y la ráfaga de entrada que dejó a la vista

Hecho el 2026-09-08. Cada evento con página paralela tiene **su propio
intérprete**: corre todos los cuadros, aparte del de primer plano, con un
mensaje abierto y con otra página en curso, y cuando su página termina el cuadro
siguiente la vuelve a empezar —el `Push` que RPG_RT hace antes de cada
`Update`—. De las 353 páginas paralelas del juego **compilan 36**, en 25 mapas;
el resto pide variables. El tope simultáneo es el mapa 8, con nueve.

**El paso de cada evento va pegado a su intérprete**, no al final de la vuelta:
`Game_Event::Update` corre el intérprete paralelo y a continuación llama a
`Game_Character::Update()` (easyrpg, `game_event.cpp:580`), evento por evento.
La diferencia se ve cuando una página paralela le fuerza una ruta a **otro**
evento: en Lashe City el `Car4` le pisa la suya al `Car2` en cada cuadro —los
dos apuntan al id 3 de RM2k, que ahí es el `Car2`—, y corriendo todos los
intérpretes antes que todos los pasos el pisotón gana y el `Car2` no camina
nunca. taro lo vio jugando y lo confirmó contra EasyRPG y contra el RPG Maker
original: los cuatro autos andan siempre.

**La RAM del banco 1.** El estado de los intérpretes no entraba: la BSS del
banco 0 estaba en 7680 de 7680 y el ZEROPAGE tenía doce bytes libres. Va a
`$7E:2000` por la ventana que la WRAM tiene en el bus B —WMADD más `$2180`, la
misma que ya usaba la fuente—. No se puede indexar, así que sirve para lo que se
guarda y se recorre de a poco; es lo que van a necesitar las variables de RM2k,
que son cinco mil.

### Tres casos de la tanda en rojo, y es un solo defecto de antes

`just snes-hitos` queda en **3 rojos de 93**, y los tres son la misma cosa:
**cuadros que la ROM pierde al entrar a un mapa**. Medido en HEAD, sin nada de
esto:

* el mapa 8 pierde **1** cuadro al entrar —2 con los paralelos—,
* el salto del mapa 4 al 1 pierde **7**.

Estaban desde antes y no molestaban porque durante esos cuadros no se movía
nada. Los eventos paralelos sí se mueven, así que ahora la comparación arranca
corrida. Los tres casos:

* `snes-heroe 8` y `snes-hablar 8 ... bum`: los dos cuadros del mapa 8.
* `snes-mednafen`: bajo snes9x el mismo caso (`snes-evento`) da **cero**; con
  siete cuadros perdidos los dos emuladores caen en distinto punto del ciclo del
  relámpago del mapa 1, y un destello a pantalla completa convierte un cuadro de
  diferencia en la pantalla entera.

### La ráfaga de entrada, perfilada

**Lo primero: el fundido ya la absorbe.** Su reloj es `boot_cuadros`, o sea
cuadros de hardware y no vueltas del lazo —ver `empezar_fundido`—, así que la
carga del mapa puede tardar seis o siete cuadros adentro del negro sin correr
nada. Verificado: el salto del mapa 4 al 1 pierde **7 cuadros** y `snes-evento`
da **cero** igual. O sea que en el juego esto no se ve nunca: a un mapa siempre
se entra por una puerta o un teletransporte, y eso es un fundido.

**Sólo molesta al arrancar derecho en un mapa pesado**, que es lo que hacen las
ROMs de un solo mapa de la tanda. Ahí el que tendría que absorber es el arranque
—`BOOT_CUADROS` más tres— y es fijo.

Medido con una sonda que anota `boot_cuadros` y el contador de barrido al final
de cada vuelta, arrancando en el mapa 8 (el presupuesto son **262 líneas**):

    vuelta 0    370 líneas
    vuelta 1    386
    vuelta 2+   147 a 170       ← el régimen entra cómodo

O sea que las dos primeras se pasan por **1,45x**, y de la tercera en adelante
sobra la mitad del cuadro. En líneas, quién se las lleva:

                          vuelta 0   régimen
    paralelos_tick           218        80
      de eso, correr_codigo  164        30    ← crear las ranuras de ruta
    build_oam                 46        54
    el paso interleaveado      3         0    ← el arreglo de los autos es gratis

Lo que **no** es: un refresco por cuadro no pierde ni un cuadro, y encadenar 1,
2, 4 u 8 páginas automáticas da lo mismo. `capa_activa` y `npc_de_evento`
tampoco aparecen.

Para bajar de 262 hay que sacar ~110 líneas de la vuelta 0 y ~124 de la 1. La
mayor parte de la 1 es el primer plano: sin los paralelos igual mide 306.

**Intentado y descartado:** resolver `capa_activa` en O(1) leyendo `eleg_por_ev`
en vez de recorrer las 73 páginas. Cambia el comportamiento —la vuelta 0 sube a
541— así que hay algo del camino rápido que no es equivalente, y hay que
entender qué antes de volver a intentarlo.

## La tanda dejó de ser sensible al rendimiento

Hecho el 2026-09-08, y es la respuesta a una pregunta de taro: *¿tenemos un bug
que depende de que algo esté optimizado?* No. La ROM computa la misma secuencia
de estados vaya rápido o lento; lo que cambia con una vuelta que se pasa del
cuadro es **cuándo** se ve cada uno, que es lag y es lo que le pasa a RPG_RT en
una máquina lenta. Lo que estaba mal era **el instrumento**: la comparación
suponía "cuadro N de la captura = tick N de la referencia".

**Qué es un tick.** El paso lógico de RM2k. En easyrpg el lazo es
`while (Game_Clock::NextGameTimeStep())` (`player.cpp:245`): corre N pasos de
lógica y después **un** `Player::Draw()`, en un solo hilo. La lógica va a
DEFAULT_FPS y el dibujo a lo que la máquina aguante. Acá un tick es una vuelta
del lazo principal, y un cuadro de hardware avanza **cero o un tick, nunca dos**:
el lazo empieza con `wait_vblank`. EasyRPG se pone al día corriendo más lógica;
nosotros no podemos, así que nos atrasamos. Las dos computan lo mismo.

**Cómo se cuenta.** La ROM lleva `vueltas`, y `snes_correr.py` avanza de a un
cuadro leyéndolo hasta llegar al tick que quiere: `retro_run()` no sabe de
ticks. El cuadro N de la referencia es el tick **N+1**, medido en los mapas 6 y
7 —que no pierden ningún cuadro— y **fijo, no muestreado**: muestrearlo fue el
primer intento y falla justo donde importa, porque en el mapa 8 los cuadros que
se pierden caen adentro de la ventana del arranque.

**El fundido pasó a contar ticks.** Va junto y no es opcional: la referencia lo
cuenta así (`estado.fundido` sube una vez por `cuadro()`), y si la ROM lo
contara en cuadros de hardware los dos relojes se irían. Cuesta que un fundido
dure unos cuadros más de reloj de pared cuando la carga del mapa se pasa, que es
justo lo que da lo mismo.

**Lo que destapó**, todo pre-existente:

* `snes-espera` corría con `--arranque 0` y comparaba el cuadro 60 **de reset**
  contra el tick 60 de la referencia. Daba verde porque en los dos lados no
  pasaba nada todavía. Con el arranque normal da cero de verdad.
* **bsnes no expone la WRAM**: `retro_get_memory_data` devuelve nulo, y el
  comentario de `retro.py` decía que los tres cores la implementaban. Ahí el
  reloj cae al camino viejo —contar cuadros—, que sirve porque esos casos corren
  mapas livianos.
* `snes-mednafen` captura por **reloj de pared** —mednafen de verdad, no un
  core— así que no se puede alinear por tick. Pasó a los 6 segundos: a los 5 el
  fundido todavía no había terminado, y a los 7 se le viene encima el relámpago
  del mapa 1, que cae a los 7,1.

### Los 3 rojos del mapa 8: cerrados

* `mecanico` y `bum`: **arreglado**. No era la ventana dejando basura sino el
  vblank: `subir_linea` son 1920 bytes de un solo DMA —casi cuatro poses— y con
  las cinco de siempre no entra, así que la cola del renglón se escribía con la
  pantalla ya encendida y no se escribía. Se ve como una franja fija, y sólo en
  un mapa con muchos eventos moviéndose. Apareció con los paralelos, que sumaron
  nueve personajes que se mueven. El arreglo es el mismo recorte que ya hacían
  el tinte y el destello: con un renglón esperando, `vq_tope` baja a 1.
* `snes-heroe 8`, caminando a la izquierda: **cerrado el 2026-09-09**, y eran
  dos defectos encadenados, los dos de la referencia.

  El de fondo: **los intérpretes paralelos no corrían en el camino colapsado**,
  así que un evento que camina desde su propia página paralela se quedaba
  clavado donde arrancó. Los paralelos pasaron a ser del mapa y no del
  `Interprete` de turno —viven en `Estado`, como `FAR_PAR_ESTADO` en la
  consola—, la entrada les da su paso y la caminata vive sus ocho cuadros por
  celda. De ahí salió además que el plan ya no diga "cuánto dura la caminata"
  sino **cuántos ticks vivió la referencia**, margen incluido.

  Y el que quedaba, 175 pixeles: **atravesar paredes no es salirse del mapa**.
  El `Car3` camina a la derecha con `walk_everywhere` puesto, llega a la última
  columna —la 74 de 75— y ahí la consola lo deja clavado hasta que otro evento
  lo reubica; la referencia lo sacaba del mapa. En
  `Game_Map::CheckOrMakeWayEx` el `IsValid` va **antes** que el
  `if (self.GetThrough()) return true;`, y la ROM ya lo modelaba así en
  `puede_celda`: era la referencia la que estaba de más.

  Cómo se llegó, que es lo que no conviene volver a caminar: la entrada de la
  referencia son 4 ticks y la de la ROM 0, y **eso no era la causa** —darle
  entre 0 y 6 ticks mueve el número de 475 a 518, nunca cerca de cero—; barrer
  la captura entre los ticks 292 y 320 no baja de 257, así que tampoco era un
  desfasaje de tiempo; y el patrón final de dos ticks rojos de cada cinco
  apuntaba a `ANIM_PARADO[4]` pero la animación no tenía nada que ver: el
  contador subía hasta `ANIM_CONTINUA` porque el evento estaba **quieto**.
  Leyendo `ruta_ev` y `ev_pos_buf` en la WRAM se vio quieto en la columna 74, y
  con una sonda de una línea en `poner_ruta` —revertida— se descartó al
  intérprete paralelo: repone la ruta todos los cuadros.

  Verificado: `just pruebas` en 35 verdes y `just snes-hitos-foto` en **93
  casos, todos en verde**.

## bsnes: la WRAM, arreglada y compilada acá

bsnes upstream devuelve nulo en `retro_get_memory_data` para **todos** los ids
—`bsnes/target-libretro/libretro.cpp:1039`— así que el reloj de ticks no lo
podía usar. El comentario del propio archivo dice por qué: *"there is no
safe/sensible way to use the memory interface without severe hackery. Rely on
higan to load and save SRAM"*. O sea que la razón es la **SRAM**, que es lo que
un frontend guarda y carga.

`RETRO_MEMORY_SYSTEM_RAM` es otra cosa: es la RAM de trabajo, la que los
frontends leen para cheats, RetroAchievements y depuración, y no participa de
cómo se guarda la SRAM. Así que exponerla **sólo a ella** respeta el motivo que
ellos dan, y ése es el argumento del PR.

El parche son dos hunks —incluir `sfc/sfc.hpp` en vez de sólo
`sfc/interface/interface.hpp`, que igual lo incluye al final, y devolver
`SuperFamicom::cpu.wram` con su `sizeof`— y está en `/extras/bsnes-wram/`:

    wram.patch                    el diff
    bsnes_libretro.parcheado.so   el build con el arreglo
    bsnes_libretro.original.so    el de pacman, por si hay que volver

**El core instalado en `/usr/lib/libretro/` es el parcheado.** Con él, `bsnes`
declara 131072 bytes de WRAM y el reloj de ticks lee `vueltas` igual que en
snes9x: mismos números, `vueltas = tick + 1`. `just snes-bsnes` pasa sus cuatro
comparaciones en cero.

Para compilarlo hicieron falta `gcc` y `make` de pacman, que el contenedor no
tenía porque el port es Python puro. El clon está en
`/extras/ref/bsnes-libretro`, **con el parche aplicado**: ya no es una copia
limpia del upstream.

## Lo que taro trajo de jugar el 2026-09-09

* **El peaje del `DetourOfficer` anda, y la mitad que él no pudo probar no se
  puede probar jugando.** Preguntó si con 500 creds o más lo dejaría pasar.
  Medido sobre los ocho mapas de `demo-ciudad`: el único `ChangeGold` que
  **suma** es el +100 de la escena del despertar en el pad —evento 4 del mapa
  7— así que por el camino jugable no se llega nunca a 500, y el peaje siempre
  rechaza. La rama que sí se cumple la cubre
  `pruebas/test_oro.py::test_el_peaje_cobra_si_alcanza_y_no_da_la_vuelta_si_no`,
  con 500 justos, 700, 499 y 0. No hay nada que arreglar; lo que hay es un
  camino del juego que no se puede caminar todavía.

* **Apretar A sobre el save point abre la pantalla de ranuras** desde el
  2026-09-10 a la tarde. Antes no mostraba nada por diseño: una sola ranura y
  sin menú.


## Cargar la partida: era un modo de direccionamiento, y está arreglado

**Un solo bug explicaba los tres reportes de taro** —mednafen, Mesen y la
consola de verdad no cargaban la partida— **y el `xfail` del menú del título.**
Estaba en `partida_suma`, en `main.s`:

    ldx #SRAM_DATOS
    lda $0000, x        ; "X ya trae la dirección; el banco es la SRAM"

El operando `$0000` **entra en un byte**, así que `w65.py` elige página directa
igual que ca65, y el bucle sumaba **la WRAM baja** en vez de la SRAM. Es
exactamente la trampa que el comentario de `SRAM_MAGIA` advierte veinte líneas
más arriba —"con la partida en `$0000` un `lda SRAM_MAGIA, x` leería la página
directa"— cometida en la línea de al lado.

**Por qué sobrevivió tanto.** El error es *simétrico*: guardar y cargar suman
los dos la misma basura, así que **mientras la WRAM no cambie entre una cosa y
la otra, los números coinciden y la partida carga igual**. Eso es justo lo que
pasa en snes9x, que llena la RAM siempre con lo mismo y llama a
`cargar_partida` a los microsegundos del reset. Con la WRAM de mednafen, de
Mesen o de la consola, no coinciden y no carga nunca; y desde el menú del
título tampoco, porque para entonces la WRAM ya se movió.

O sea que `test_guardar` daba verde **cobrando la coincidencia de dos errores**,
que es el modo de fallar en silencio que este repo tiene escrito en CLAUDE.md
como la regla que sostiene todo.

El arreglo es indexar desde cero y poner la dirección en la base —`ldx #$0000`
y `lda SRAM_DATOS, x`—, que no entra en un byte y sale absoluto.

**Lo que lo cobra ahora**: `pruebas/test_titulo.py::test_seguir_la_historia_
carga_la_partida`. Verificado que da rojo con el bug puesto y verde sin él, que
es la única forma de que un caso nuevo pruebe algo. `test_guardar` **no** lo
cobra ni lo cobraría: en snes9x pasa de las dos maneras.

Medido antes y después, sobre la misma partida guardada:

    con el bug     SRAM_SUMA guardada $052d, recalculada al cargar $0729,
                   suma real de los 156 bytes $0479 — las tres distintas
    arreglado      guardada $0479, recalculada $0479, real $0479

**Falta que taro lo pruebe en hardware**, que es lo único que cierra esto:
`rom/build/demo-ciudad/` quedó rearmada con el arreglo. La partida que ya tiene
guardada en la SD **no va a cargar** —su `SRAM_SUMA` es la vieja, calculada
sobre la WRAM— así que hay que guardar de nuevo con la ROM nueva y recién ahí
apagar y encender.

### Lo que sigue abierto del mismo vecindario

Con pantalla de título, **irse de mapa antes de guardar deja la partida sin
guardar**. Quedándose en el mapa de arranque la SRAM tiene la magia a las ~400
vueltas; con un `ir_al_mapa(6)` en el medio sigue sin tenerla a las 491. Sin
pantalla de título ese camino guarda, que es `test_guardar`.

**No es el bug de arriba** —sigue pasando con ése arreglado— y **tampoco
parece afectar al juego**, que es lo que importa saber antes de asustarse:

* No es cuestión de esperar más: a las 891 vueltas sigue sin guardar, y sin
  título guarda a las 351.
* Con título y sin título, **los 128 bytes de switches quedan idénticos**
  después de cambiar de mapa. Y la pantalla también, que es lo que compara el
  caso nuevo de `snes-titulo`. O sea que las páginas del juego no se rompen.
* taro **guardó y cargó en `demo-titulo`** el 2026-09-10 después de caminar
  hasta el save point, que es cambiar de mapa.

Con lo cual el sospechoso es **la página de prueba misma** —una automática con
espera, que el doble `cargar_mapa` del menú reinicia— y no el save point.
Confirmarlo pide un caso que use el save point de verdad, que hoy no existe:
las pruebas de guardado usan la página falsa justamente para no tener que
llegar caminando hasta Lashe City.

Queda como `xfail(strict=True)` en `test_irse_de_mapa_antes_de_guardar_no_guarda`.

## La música del título se quedaba sonando adentro del juego

taro lo vio el 2026-09-10: se elige una opción, entra la partida, y sigue
sonando `Fantasia_Of_The_Wind`. Faltaba que al salir del menú pasara lo mismo
que en el arranque de una ROM sin título, o sea `music_boot`.

Con una vuelta de tuerca que no es obvia: `music_boot` con `TEMA_ARRANQUE` en
`$FF` —el caso normal en este juego, donde el tema lo prende un `PlayBGM`— sólo
marca `music_apagada` y **no le escribe nada al DSP**, porque en el arranque no
hay nada sonando. Viniendo del título sí lo hay, así que el volumen general se
baja a mano; el `PlayBGM` que venga lo vuelve a subir, porque su stream escribe
los dos registros al arrancar.

Verificado comparando el estado contra la ROM sin título: las dos llegan al
juego con `music_apagada` en 1.

**Y el tema pasó a guardarse en la partida**, que lo pidió taro en el mismo
mensaje y tiene razón: lo prende un `PlayBGM` de un evento, así que es estado
del mundo igual que un switch. Son dos entradas nuevas en `partida_tabla`
—`music_apagada` y `tema_actual`— y `PARTIDA_BYTES` pasó de 156 a 159.

**Esto invalida las partidas guardadas con la ROM anterior**: la suma se
calcula sobre otro largo. Hay que guardar de nuevo.

Los dos casos que lo cubren costaron tres intentos, y los dos descartes valen
más que el resultado:

* **Mirar `tema_actual` después de cargar no prueba nada.** Al cargar, las
  páginas del mapa corren sus propios `PlayBGM` y reponen la música en un par
  de cuadros, así que el caso pasa igual con el campo sacado de
  `partida_tabla`. Comprobado. Lo que sí prueba es mirar **los bytes de la
  SRAM**: si el campo no se guarda, no están.
* **El reset de snes9x no borra la WRAM.** El caso que sí mira el estado
  después de cargar tiene que **ensuciarla a mano** primero, porque si no el
  valor viejo sobrevive solo y la comparación mide cero. Una consola de verdad
  enciende con basura ahí. Es la misma trampa que escondió el bug de página
  directa de `partida_suma` durante semanas, y conviene tenerla presente en
  cualquier prueba futura que dependa de que algo se borre al reiniciar.

Los dos están verificados en las dos direcciones: dan rojo con el campo sacado
de la tabla y verde con él puesto.

## El arnés se comía la máquina en vez de fallar

`correr_con_a`, en `snes_correr.py`, tenía un `while reloj.cuadro() < ticks`
**sin tope**, a diferencia de `Reloj.avanzar`, que sí lo tiene. El 2026-09-10
costó caro: una captura de la pantalla de título —donde `vueltas` no avanza y
el tick pedido no llega jamás— se quedó **una hora** comiéndose un núcleo y 42
GiB de la máquina de taro, hasta que él la vio en `ps`. Ahora lleva el mismo
tope y corta en dos minutos diciendo qué pasa y que para eso está
`--sin-contador`.

## El PPU se queda con los registros del título, y snes9x no lo ve

taro lo encontró en Mesen el 2026-09-10, y el síntoma se leía en dos formas
distintas según el build:

* **`titulo.sfc`**: la pantalla de título se ve bien, se elige cualquier opción
  y la pantalla queda **negra** —con la música corriendo detrás y hasta
  cambiando de tema—, que es `TM` en cero con toda la lógica andando.
* **`demo-titulo.sfc`**: el juego se ve, los `PanScreen` y los relámpagos
  aplican bien, pero **todos los tiles apuntan al gráfico equivocado**, "como
  movido X bytes". Ése es `BG1SC` apuntando al tilemap del título, en `$4000`,
  en vez de al del mapa.

La causa es una sola: **`BG1SC` y `TM` se escriben en `ppu_init` y en la
pantalla de título, y en ningún otro lado**. `ppu_init` corría una única vez en
el arranque porque hasta ahora nadie los tocaba después. El arreglo es volver a
llamarlo al salir del menú, antes de `cargar_mapa`.

**Lo que hay que saber de esto es que la red no lo ve.** Verificado sacando el
`jsr ppu_init` y volviendo a correr: snes9x sigue dando **cero pixeles de
diferencia**. O sea que es el cuarto defecto de la clase "snes9x perdona", y el
tercero seguido que encuentra taro jugando.

El caso nuevo de `snes-titulo` —salir del título tiene que dejar el juego
idéntico a la misma ROM sin pantalla de título, comparando ROM contra ROM y
pasando el título con START, que el juego no mira— **queda igual**, pero con la
advertencia escrita en la receta: cubre el reparto de la VRAM y **no** cubre
esto. Un caso verde que no da rojo con el bug puesto no prueba lo que parece.

`demo-titulo/` estaba armada con el código de media tarde —la etapa sin menú— y
por eso taro no veía el cuadro para elegir. Las dos ROMs con título quedaron
rearmadas.

## El mapa 4 vacío se confunde con una pantalla rota

taro lo propuso el 2026-09-10, y tiene razón en que ya pasó más de una vez: el
mapa 4 es "Blank (Leave START here)" y es negro a propósito, así que una
captura negra puede ser el mapa o puede ser el PPU mal configurado. Ese mismo
día me pasó a mí: miré la captura de después de salir del título, la di por
buena, y era el defecto de arriba.

**Cómo hacerlo sin ensuciar la vara**: no editando `Map0004.lmu`. El juego
original en `/extras/abl-rm` es lo que hace que este port sea comparable contra
easyrpg, y un mapa retocado ahí contamina toda esa comparación y además viaja a
cualquier medición futura sin avisar. La forma que no cuesta nada es un **tile
testigo emitido por el conversor bajo un flag**, con la referencia sacándolo de
la misma función: así los dos lados siguen coincidiendo, la comparación pixel a
pixel sigue valiendo, y **ninguna ROM de la tanda cambia** porque el flag no se
usa en ninguna.

Sin hacer. Va después de los dos defectos abiertos.

## Guardar y cargar: probado de punta a punta

taro lo jugó el 2026-09-10 sobre `demo-titulo`: caminó hasta el save point,
guardó, reinició, eligió "Resume the Story", cargó, y **el cronómetro y la
música volvieron bien**. Eso cierra el camino entero, que hasta ayer estaba
roto en tres lugares distintos —la suma que leía la WRAM, la música que no se
guardaba, el PPU que quedaba con los registros del título—.

Lo que eso confirma y no lo hacía ninguna prueba de acá adentro:

* La partida cargada **sigue jugándose**, no sólo arranca. Las pruebas de
  estado miran el primer cuadro después de cargar; taro siguió jugando.
* **El cronómetro** vuelve donde estaba. Está en `partida_tabla` desde el
  principio y nadie lo había mirado después de un ciclo completo.
* **La música** vuelve, que es lo que se agregó ese mismo día.

Falta lo mismo de siempre y sólo eso: **el hardware**. `demo-ciudad` y
`demo-titulo` quedaron rearmadas con todo esto.

## Lo que sólo sabía la sesión, y por eso queda escrito

Anotado el 2026-09-10 antes de un `/clear`. Son las cosas que no están en
ningún commit ni en ningún caso, y que sin esto habría que volver a descubrir.

* **Las dos ROMs para probar son `rom/build/demo-ciudad/` y
  `rom/build/demo-titulo/`**, las dos rearmadas ese día. La primera no lleva
  pantalla de título y la segunda sí; el resto es idéntico.
* **Ninguna partida guardada de antes del 2026-09-10 sirve.**
  `PARTIDA_BYTES` cambió dos veces ese día —las cuatro ranuras y la música— y
  la suma se calcula sobre el largo, así que una ranura vieja da inválida y la
  carga arranca de cero. No es un bug: hay que guardar de nuevo.
* **`snes9x` perdona cosas que el hardware no.** Van cuatro defectos de esa
  clase y tres los encontró taro jugando: la carga de la SRAM, el PPU al salir
  del título, y los dos que están más arriba. Antes de escribir un caso que
  dependa de que algo *no* sobreviva a un reinicio, acordarse de que **el reset
  de snes9x no borra la WRAM**: hay que ensuciarla a mano o la prueba mide
  cero. Está en `test_titulo.py`, con el comentario al lado.
* **Un caso nuevo se verifica en las dos direcciones.** Esta vuelta, tres casos
  que parecían correctos no probaban nada hasta que se les puso el bug adelante
  y se comprobó que daban rojo. Uno de ellos —el de la música— pasó dos veces
  con el campo sacado antes de que el tercer intento midiera algo.
* **El scratchpad de esa sesión ya no existe**, así que las capturas que se
  nombran en los commits no se pueden mirar: si hace falta ver algo, se vuelve
  a correr la receta, que es de donde salían.

## Esperando respuesta de taro

* **Si el save point tiene que avisar que guardó.** Resuelto por el lado de
  RM2k: ahora abre la pantalla de ranuras, que es lo que allá se ve, y al
  elegir vuelve al mapa sin decir nada más, igual que `Scene_Save::Action`.
  Un *"Partida guardada"* sería un texto que el juego no tiene. taro lo
  preguntó el 2026-09-09; si quiere el aviso igual, es un `OP_MENSAJE` y sale
  barato.

* **Si las ocho décimas de arranque molestan.** Ver la decisión de arriba.


## Salir del pad de Talan: hecho

El 2026-09-07 taro llegó al pad, y el 2026-09-08 pudo salir. Los tres puntos que
faltaban están: el mapa 8 entra en la ROM —ver la decisión de las paletas
prestadas—, `ShowChoice` anda con cursor, vuelta y cancelar con B, y el
cronómetro también.

## `rom/build/demo-ciudad/`: jugada el 2026-09-09, y en hardware

Rearmada el 2026-09-08 y **jugada** el 2026-09-09 —el agua, el save point y
el peaje del `DetourOfficer`, más arriba— y corrida en la SNES de verdad con
el FX Pak. Es la ROM viva del proyecto: cualquier cosa que se quiera ver
jugando sale de acá. Es `demo-apertura` **más el mapa 8** —Lashe City, la
calle a la que da el pad de Talan— y por lo tanto la primera ROM en la que se
puede salir del pad: con el 8 adentro, la puerta `TalDoorTop` compila.

Desde el 2026-09-08 el mapa 8 **dibuja sus 68 eventos**, seis de ellos con una
paleta ajena: `@tile:BLchp1:111`, `@tile:BLchp1:117` —la puerta del pad—,
`@tile:BLchp1:53`, `Chara2:0`, `People4:0` y `savept:0`, o sea el save point.
Se ven con los colores cambiados y se ven; ver `assets/LIMITACIONES.md`.

Va **con cronómetro**: para hacerle lugar al rojo de los dígitos, `Future1:7`
baja de 15 a 14 colores (14,07% de sus pixeles). Se arma así:

    python3 tools/snes_convert.py --grupo 10 --map-id 4 --mapas 1 2 3 5 6 7 8 \
        --con-ventana --con-timer \
        -o rom/build/demo-ciudad/mapdata.inc
    python3 tools/w65.py rom/src/main.s -I rom/build/demo-ciudad \
        -o rom/build/demo-ciudad/demo-ciudad.sfc \
        --simbolos rom/build/demo-ciudad/demo-ciudad.sfc.sym

A quién bajarle un color lo elige el conversor, y sólo cuando de verdad no
tiene dónde: ni una paleta con lugar **ni una ranura libre**. Mirar sólo lo
primero le bajaba dos colores a `People4:5` en el mapa 5 —16,85% de sus
pixeles— cuando ese mapa usa cuatro paletas de las ocho.

Y el candidato tiene que estar **sólo en este mapa**: el banco de poses es de la
ROM entera, así que cuantizar a alguien distinto en dos mapas no da una imagen
fea sino un corte al emitir. Pasó con `Future1:4` la primera vez que se escribió.

El resto de los mapas donde el cronómetro puede aparecer no paga nada: de los
diez, en ocho entra en una paleta que ya tiene lugar.

### El Hover-Tram (mapa 13): entra

Pedía **once paletas de sprite de las ocho** —27 pasajeros de una sola página
cada uno, dibujados con diez sprites distintos, todos a la vez—. Desde que el
que no consigue paleta propia se cuelga de una ajena, el mapa convierte con
**dos** gráficos prestados: `BLPeople:0` y `Future1:2`. No hace falta ni
descartar pasajeros ni fusionar paletas, que eran las dos salidas caras.

Sin probar todavía: la ROM con el mapa adentro.

## Lo que taro probó y anda

El 2026-09-07, sobre `demo-apertura` en mednafen:

* **La apertura entera hasta el ascensor**, incluida la cinemática en la que
  Core rompe la puerta, que era la que estaba rota.
* **El Insta-Shave**, o sea `ShowChoice` con su cursor.
* **El cronómetro**, contando bien. Llegar a cero todavía no hace nada: en RM2k
  eso dispara un evento común con la condición "cronómetro en 0", y los eventos
  comunes no están.
* **Los mapas se ven mejor**, y hay un caso concreto: la sangre de Core en el
  piso era marrón y ahora es roja. Es el efecto de que el mapa 2 pasara de
  fusionar 13 colores a fusionar ninguno —ver la ventana de mensaje en la
  paleta 0—. `merge_least_used` fusiona el menos usado con su vecino más
  cercano por luma, y un rojo de unos pocos pixeles era justo el candidato a
  que lo absorbiera un marrón. No se buscó ni se predijo: es lo que el número
  anunciaba.


## Lo que taro todavía no probó

* **~~La salida del pad de Talan~~: probada y anda** —ver "Salir del pad de
  Talan: hecho", arriba—. Se deja el diagnóstico porque el mecanismo se repite:
  el 2026-09-07 taro quedó encerrado en un mapa vacío del que no se podía salir,
  sin control y con `hzstream` fundiéndose y empezando de nuevo en ciclo. El
  volcado de la WRAM que pasó —`/extras/demo-apertura - SnesWorkRam.dmp`— dijo
  que no estaba en el pad sino en el **mapa 4**, "Blank (Leave START here)", que
  es vacío a propósito: por eso "no renderizaba" nada más que el héroe, con
  `brillo` en 15. El mapa 4 es un **despachante** —cinco páginas automáticas,
  una por switch, cada una teletransportando a otro lado— y la escena del escape
  del mapa 3 devuelve ahí. Su salto al pad se estaba perdiendo por el
  presupuesto agotado, y como la página es automática y el switch 21 sigue
  prendido volvía a arrancar sola para siempre. Hay que rearmar
  `demo-apertura` y volver a jugar la secuencia entera.

* **`rom/build/demo-apertura/`, rearmada el 2026-09-06** con el disparo de
  páginas rehecho —ver la decisión de abajo— y con el **mapa 6 adentro**, que
  antes no estaba: la línea de este archivo
  que decía "los mapas 4, 1, 2, 3, 5 y 6" era falsa y el `--mapas` nunca lo
  llevó. Sin el 6, las cuatro páginas automáticas del mapa 5 daban **cero
  ejecutables** —tres de ellas teletransportan al 6— y el recuerdo de CORE y
  MANTA no arrancaba: el héroe quedaba caminando invisible por la casa. taro
  lo encontró jugando el 2026-09-06. Ahora el 5 y el 6 tienen una ejecutable
  cada uno. Se arma así:

      python3 tools/snes_convert.py --grupo 10 --map-id 4 --mapas 1 2 3 5 6 7 \
          --con-ventana --con-timer --descartar-eventos \
          -o rom/build/demo-apertura/mapdata.inc
      python3 tools/w65.py rom/src/main.s -I rom/build/demo-apertura \
          -o rom/build/demo-apertura/demo-apertura.sfc \
          --simbolos rom/build/demo-apertura/demo-apertura.sfc.sym

  El `--con-timer` no estaba y por eso el 2026-09-07 taro no veía el
  cronómetro: la cuenta corría —`timer_activo` en 1— pero `TIMER_BASE` era 0 en
  los siete mapas, o sea que los dígitos no estaban en VRAM y el dibujo se
  salteaba entero. El flag cuesta una paleta de sprite, de 8 a 7. Y el
  `--simbolos` tampoco estaba: sin él las pruebas de estado no pueden mirar
  esta ROM.

  Lleva además la escena de Talan entera, la puerta del Emitter Room, y cuatro
  temas —`escape_newyork`, `TF3_1_awe`, `evilrhys`, `lufsorr`—. El banco de
  muestras quedó en 61569 B de los 64512 de ARAM: agregar un mapa más con tema
  propio ya no entra sin sacar algo.

  Las otras ROMs con nombre —`demo-musica`, `demo-cinematica` y el resto— son
  viejas y no se rearmaron.

* **La SNES de verdad, con el FX Pak: corrió, y anda.** taro lo probó el
  2026-09-09 y su veredicto fue *"anda todo bien, igual que en el emulador, al
  menos"*. Es la primera vez que se corre en hardware desde que el CRT volvió, y
  cae después de los cambios fuertes —entre ellos que el cartucho pasó de 512 KB
  a 1 MB—, así que lo que queda cerrado es lo que más pesaba: **el mapeo del
  cartucho expandido**. El header lo respalda, verificado sobre
  `rom/build/demo-ciudad/demo-ciudad.sfc`: mapmode `$20` (LoROM), tipo `$02`
  —ROM + RAM + batería—, tamaño declarado `$0A` = 1024 KB, que es exactamente lo
  que mide el archivo, SRAM `$03` = 8 KB, y el checksum del header coincide al
  byte con la suma real de la ROM (`$03DB`). Nada de eso quedó a medias tirando
  del tamaño para arriba.

  **Lo que el hardware todavía no desempató**, porque taro miró y no midió:

  - **Guardar en el FX Pak.** En mednafen la partida llegó al disco —8 KB de
    `.srm`—, y en el flashcart es justo lo que puede portarse distinto: el
    cartucho tiene que escribir la SRAM a su tarjeta al apagar. La prueba es
    guardar, **apagar la consola**, y volver a encender esperando que arranque
    donde se guardó. No consta que se haya hecho.

* **El título del cartucho sigue diciendo `ABL SNES MUSIC POC`.** Es lo que el
  menú del FX Pak muestra y lo que lee cualquier base de datos de ROMs; quedó de
  la etapa en que la ROM era una prueba de audio. Es cosmético y de una línea del
  header, pero se ve en hardware, que es donde ahora estamos mirando.

* **El brillo de `INIDISP`: cerrado el 2026-09-09.** taro lo miró en la SNES de
  verdad y dijo *"está todo OK a simple vista"*, así que damos por bueno el
  redondeo de snes9x y bsnes, que es con los que corre la tanda. **No se midió
  contra una captura del hardware**: lo que se cierra es la decisión, no el
  número. Si algún día un fundido se ve mal en fierro, acá está lo que se sabe.

  El
  2026-09-06 se compararon los tres cores cuadro por cuadro sobre el fundido de
  entrada al mapa 1 de `demo-apertura`, que recorre los dieciséis niveles:

      brillo 0 y 15           los tres coinciden, cero pixeles de diferencia
      brillo 1 a 14           snes9x y bsnes coinciden exactamente;
                              mesen-s difiere en 30% a 48% de los pixeles

  O sea que difiere **exactamente mientras dura un fundido** y en ningún otro
  momento, que es lo que confirma que el asunto es el escalado y nada más. Y
  difiere para abajo: da un paso menos —3 contra 2, 11 contra 10, a 15 bits— y
  nunca más. Es "trunca donde los otros redondean"; la fórmula exacta no sale
  de esta medición porque la escena lleva además un tinte en CGRAM, así que el
  pixel no es color puro por brillo.

  **La trampa práctica:** el justfile toma el core de la variable `CORE`, así
  que correr la tanda con `CORE=mesen-s` es un comando —y pondría en rojo todos
  los cuadros que caigan en un fundido, sin que haya ningún bug. La tanda usa
  snes9x, y `snes-bsnes` y `snes-mednafen` la respaldan.

  Dos de tres no desempata: el hardware es el que decide, y para eso hay que
  esperar al CRT. A ojo, taro no distingue mednafen de mesen y los dos le
  parecen bien.


* **Las pruebas de estado son la otra mitad de la red, no un reemplazo.**
  `just pruebas` corre pytest sobre `pruebas/`: se le pregunta a la ROM en qué
  mapa está, qué switch tiene prendido, qué evento corre. No miran la pantalla.

  El reparto es por dónde se queda ciega cada una. La tanda de pixeles cobra
  los errores de PPU —una paleta mal repartida, una prioridad de OAM— y no
  puede cobrar nada donde la referencia se equivoca igual que la ROM. Las de
  estado no ven un pixel, pero no dependen de que la referencia esté bien: el
  recuerdo de CORE y MANTA que no arrancaba daba **verde en los 87 casos** y da
  rojo en una línea acá. Medido: con la ROM de antes del arreglo,
  `test_el_recuerdo_cruza_a_la_ciudad` dice mapa 5 en vez de 6.

  Ninguna dirección de RAM está escrita a mano: salen de la tabla que deja
  `w65.py --simbolos`, que además exporta las constantes del ensamblador
  —`BOOT_CUADROS`, `FLAG_AUTO`, `EV_MAX`—. Renombrar una variable en `main.s`
  hace fallar la prueba diciendo qué símbolo falta, en vez de leer en silencio
  la dirección de al lado.

  Decidido con taro el 2026-09-06: **los casos nuevos se escriben acá**, y la
  tanda de pixeles se mantiene pero deja de crecer.


## Lo que la tanda no cubre

* **El destello de un evento sobre la paleta de otro.** En la consola
  `FlashSprite` es un tinte de CGRAM: `pintar_flash` sube la paleta entera del
  personaje, así que tiñe todo lo que la comparta. La referencia lo aplica sobre
  la **imagen** del sprite, que es lo que hace RM2k. Son dos cosas distintas y
  ninguno de los 89 casos lo ve, porque ninguno tiene un segundo sprite visible
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

`just snes-hitos-foto` son **96 casos, todos en verde**, y el más largo es
`talan`: mil doscientos cuadros de la escena entera del Emitter Room. Lo que la
tanda no mira:

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

* **La guarda de la paleta vacía** en `tenir_paleta` protege una condición que
  el conversor no puede producir hoy: siempre emite al menos una paleta de
  sprites y una de la capa de encima. Se deja —el error que arregló fue real y
  un DMA de cero bytes transfiere 64 KB— pero como código inalcanzable, no como
  camino sin probar. Si el conversor deja de forzar esa paleta mínima, vuelve a
  la lista.


## Lo que se dejó afuera a propósito

* **El panorama del mapa 2** —los puntitos sobre azul cuando se enciende la
  pantalla grande— pide una tercera capa de fondo y el modo 3 tiene dos.
* **Los otros tipos de movimiento de las rutas propias**: al azar, vertical,
  horizontal y hacia el héroe. Son 106 páginas. Y el giro en el lugar.
* **El fundido de la transparencia de una ruta**: se acepta y se tira, porque
  la SNES no atenúa un sprite por partes sin color math.
* **Los cuadros que el lazo pierde de vez en cuando** —la primera vuelta de una
  ROM con muchas páginas, y la vuelta en que termina un fundido—. No cambian
  ningún pixel comparado, y son lo único que le falta a la escena del ascensor
  para tener caso propio en la tanda.
