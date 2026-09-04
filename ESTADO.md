# Dónde quedamos

Lo que existe sólo mientras alguien trabaja: qué está a medias, qué se cree sin
haberlo corrido, y qué se dejó afuera a propósito. Todo lo durable va al
`LEEME.md` de cada port y a los mensajes de commit, que en este repo son largos
justamente para eso.

Se escribe **mientras se trabaja**, no al final. Un resumen escrito al cerrar
es la misma operación con pérdida que compactar, sólo que a un archivo.

Última vez que se tocó: 2026-09-04.

## En vuelo

Se está tapando la lista de más abajo: supuestos escritos de los dos lados y
corridos de ninguno. Cerrado el primero, **la prioridad de objeto contra la capa
de encima**, con tres casos nuevos en `snes-hitos` y una receta `snes-encima`.
Cerrada la mitad corrible del segundo, **el orden de la tabla de mapas**, con un
cuarto caso. Y relevados los tres que quedaban —el tope de ocho saltos, la
guarda de la paleta vacía y las 29 páginas a puro `FIN`—, que no pedían pruebas
nuevas sino medir: dos de los tres tenían la premisa mal escrita.

La lista queda entonces sin nada "sin correr por falta de ganas": lo que sobra
es de dos clases, o inalcanzable con los datos del juego, o compartido entre la
ROM y la referencia y por lo tanto no comprobable comparando. Las dos clases
están dichas con todas las letras abajo.

El hito 12 —el intérprete de eventos— quedó cerrado de los dos lados el
2026-09-02, en `f337a02` y `fe2767d`.

    just snes-hitos    50 comparaciones, todas en 0 pixeles de 57344

**Terminada la migración del harness a libretro in-process**, el 2026-09-03.
La tanda corría 19m30s y el 100% era el emulador en tiempo real mientras la
prueba lo esperaba durmiendo. Ahora:

    just snes-hitos              2m23s    19 casos, 56 comparaciones en 0
    just snes-hitos-paralelo 6   0m32s    lo mismo, repartido en procesos

Hoy, con `snes-mednafen`, `snes-bsnes` y `snes-ruta` adentro, son 25 casos y 68
comparaciones: 3m34s en serie y 1m04s repartida en seis. Lo que se sumó es casi
todo mednafen, que corre en tiempo real con ventana; bsnes cuesta veinte
segundos y `snes-ruta` unos pocos.

Lo que se ganó además del tiempo, que era el punto: los cuadros salen de la
referencia y no de un número elegido a ojo, la prueba dejó de depender de la
carga de la máquina, y `snes-caminando` compara al héroe **a mitad de camino**
—cosa que antes no se hacía nunca, porque en el cuadro final está chocando
contra la pared y la única pose que se comparaba era la parada—.

Quedó una deuda acotada, **completar el frontend de libretro**, que se pagó el
mismo día: ver más abajo.

**En curso: el intérprete corre cuadro a cuadro.** Hecho el 2026-09-03 de los
dos lados. Antes `cargar_mapa` ejecutaba todas las páginas de una sola pasada,
con la pantalla apagada, y las esperas se salteaban: el tiempo quedaba
colapsado y nada de lo que en RM2k pasa *durante* una página existía. Como el
46% de las páginas automáticas del juego terminan en un teletransporte, eso
además volvía imposible de verificar todo lo anterior al salto.

Ahora las páginas elegidas se encolan al cargar el mapa y el lazo principal las
va comiendo; las esperas esperan y el teletransporte corta el cuadro, como el
`return false` de easyrpg-player.

Y ya está verificado. Ninguna página del juego que compile tiene una espera, así
que `snes-espera` corre una **página inventada** —esperar N cuadros y después
teñir—, del mismo modo que `snes-encima` existe porque ningún evento del juego
llega a la prioridad 2: lo sintético es la entrada, no la comparación. Se mira
antes y después con margen y no el cuadro exacto del borde, porque el arranque
de la ROM incluye la subida al SPC700 —unos 42 cuadros cuando el mapa tiene
música— y la referencia no modela eso. Entre las dos capturas hay 57247 pixeles
de diferencia, así que si la espera no esperara se vería.

Falta lo que esto habilita: las rutas forzadas caminando y el clima.

**Cerrado el 2026-09-03: andan los tres cores.** Era el corte en curso, y la
causa no era ni la ROM ni el core sino `tools/retro.py`, que implementaba el
mínimo del contrato de libretro. Tres errores, uno por core y todos en silencio:

* **bsnes declara `need_fullpath` y su `retro_load_game` ignora `game->data`**:
  hace `superFamicom.location = string(game->path)` y abre el archivo él mismo.
  Le pasábamos el path en NULL, así que cargaba "" —y devolvía true igual—: la
  ROM nunca entraba. De ahí la pantalla negra con el audio sonando, que era el
  APU corriendo sin ROM.
* **mesen-s guarda los callbacks adentro de un objeto que crea `retro_init`**,
  así que ponerlos antes escribía en la nada. Ése era el segfault. El orden
  bueno —entorno, `retro_init`, y recién ahí video, audio e input— es el de
  RetroArch.
* **mesen-s además corta `retro_load_game` en la primera línea** si
  `GET_SYSTEM_DIRECTORY` contesta que no.

Verificado corriendo: los tres cores dibujan **el mismo cuadro a 15 bits** —0
pixeles de 57344, mapa 7 a los 180 cuadros—, y `just snes-hitos` quedó en 24
casos y 64 comparaciones, todas en 0.

La tanda sigue en snes9x por una razón medida y no por costumbre: bsnes emula
121 cuadros por segundo contra 2747, o sea 23 veces más lento, y correrla entera
con él la mandaría de vuelta a la media hora. Entra por **`snes-bsnes`**, que
corre los mismos dos casos que `snes-mednafen` —uno que tiñe desde un evento y
uno que camina— y cuesta veinte segundos. Cualquier otro caso se puede mirar con
`CORE=bsnes just snes-heroe 7`.

Y lo que se buscaba de bsnes se consiguió: corre con **`bsnes_entropy=High`**,
o sea con la WRAM llena de basura al encender, como la consola. Medido contra el
error de verdad: comentando las dos líneas que inicializan `ruta_n`/`ruta_i` en
`main.s` y corriendo veinte veces el mapa 7, el cuadro sale mal 11 veces de 20
con `High`, 3 con `Low` y 0 con `None`. Con la ROM sana, 20 de 20 dan el mismo
cuadro. O sea: la tanda ahora ve esa clase de error sola la mitad de las veces,
y no se vuelve inestable a cambio.

De paso salió un error viejo que nadie había pisado: `snes-caminando` con un
solo avance escribía la referencia como `-right` y después la buscaba como
`-60`, así que la receta no andaba con menos de dos avances. La etiqueta ahora
es el avance siempre que se pida uno.

`snes-mednafen` se queda. No es redundante: mednafen no es un core de libretro,
así que es lo único que probaría que `tools/retro.py` no se está equivocando
parejo con los tres cores a la vez —el error de siempre en este repo, ahora
aplicado al frontend—.

**Cerrado el 2026-09-03: las rutas forzadas caminan y coinciden.** `MoveEvent`
con `move_*` ya se acepta en `_compilar`. Lo que estaba escrito acá —"a 410
pixeles de coincidir", "la ROM no vuelve a la pose parada"— **era falso**, y vale
la pena decir por qué, porque la manera en que se equivocó se va a repetir.

La ROM nunca estuvo mal: reconstruida la de `483c043` —el commit que reportó los
410— y comparada contra la referencia de hoy, da 0. Los 410 salieron de comparar
contra una referencia puesta a mano, y de un log que mentía: `snes_expect.py`
imprimía "mirando abajo" **siempre** que se corriera con `--walk none`, aunque una
ruta forzada hubiera girado al héroe. Era una cadena fija, no la dirección. Ya no.

Los dos errores de verdad estaban en la referencia, y los dos en el contador de
cuadros caminando:

* `columna_de_caminata(cuadros_moviendose - 1)` para la ruta, contra
  `columna_de_caminata(cuadros_moviendose)` para la caminata con el pad. En la
  ROM `advance_step` prende `moving` y `animate_hero` corre en la misma vuelta,
  así que el `-1` sobra. Se veía **sólo en los múltiplos de ANIM_FRAMES = 6**.
* El contador no volvía a cero ni al terminar la ruta ni durante una espera,
  porque el lazo de `entrar_al_mapa` cortaba antes de simular el cuadro en que
  la ROM apaga `moving`. Se veía sólo si la columna en la que quedaba el ciclo
  no era casualmente la parada.

Los dos son de la misma familia y ninguno se veía comparando el cuadro final:
sólo aparecen **durante** la caminata. La prueba que faltaba es `snes-ruta`, que
compara cuatro cuadros de una ruta de doce celdas con esperas en el medio. Está
en la tanda.

Cómo se eligió qué comparar, porque a ojo no alcanzaba: los tres errores se
volvieron a meter de a uno y se verificó que cada uno da rojo. La primera ruta
que probé —doce celdas de corrido— los dejaba pasar dos de tres, porque 96
cuadros moviéndose caen justo en la pose parada. De ahí las tres patas de cuatro
celdas y las esperas.

Y hay una medición que hacía falta: barrida cuadro por cuadro, la ROM y la
referencia coinciden en **115 de 115 cuadros** de esa ruta, y en 104 de 104 de
otra de doce celdas sin esperas. Eso pide un desfasaje de arranque, que es real
y está medido: la ROM tarda 10 cuadros en el mapa 6 —que es mudo— y 44 en el 73,
que tiene música y sube el banco al SPC700. `snes-ruta` corre en el 6 por eso.

Lo que esto **no** desbloquea, dicho con todas las letras: **cero páginas del
juego**. Siguen compilando las mismas 35. De las 60 páginas automáticas que
corta `MoveEvent`, 46 mueven otro evento y no al héroe, y las demás usan órdenes
de ruta que seguimos sin aceptar. Así que lo único que ejercita esto es
`snes-ruta`, que es sintético, igual que `snes-encima` y `snes-espera`. Y por lo
mismo, el tope de ocho saltos no hace falta volver a medirlo: no compila ninguna
página nueva, así que ninguna cadena de teletransportes cambió.

**Cerrado el 2026-09-04: `ShowMessage`.** Decidido ese mismo día, y antes que
la cinemática,
porque es lo que más destraba: de las 473 páginas automáticas que no compilan,
**144 las corta un cuadro de texto**, contra 60 de `MoveEvent` y 47 de
`ConditionalBranch`. La cinemática además tiene texto igual.

Va en fases, y la primera la eligió taro: **ancho fijo de 6 px, sin envolver, y
lo que no entra se trunca.** Feo a propósito. La razón es que deja la fase 1 sin
la parte con más superficie para errores —el reacomodo de líneas— y permite
comparar contra capturas del ABL original o contra la referencia con menos
cosas moviéndose. Después se pasa a otra feature y el texto queda visualmente
roto un tiempo: deja de ser un problema técnico y pasa a ser cosmético.

Por qué hace falta decidirlo: **el texto del juego no entra en la pantalla de
la SNES**. RM2k dibuja en 320 px y le da 304 al texto; nosotros tenemos 256 y le
damos 240. El autor escribió pegado al límite de RM2k —la línea más larga son 51
caracteres, 306 px—. Medido sobre las 18.614 líneas de mensaje:

    ttyp0 fijo de 6 px, en 240 px      entra el 92,26%   1440 líneas se truncan
    ancho variable, en 240 px          entra el 98,02%    369
    fijo de 6 px, en 256 px sin borde  entra el 96,25%    698

El ancho variable queda anotado como fase posterior, y puede que nunca haga
falta.

**Y ya hay un oráculo externo, que es la novedad grande.** EasyRPG corre acá
adentro sin pantalla —`rom/easyrpg.sh`, Xvfb más las capturas automáticas del
propio player— así que se puede comparar nuestra ventana contra **el juego de
verdad** y no sólo contra nuestra propia referencia. Es la primera vez que este
repo tiene con qué romper el empate de "si los dos lados se equivocan igual, la
comparación da cero".

Lo cobró enseguida, con dos errores que **se veían perfectamente bien**:

* **El índice 0 de la paleta de los PNG de RM2k es transparente**, y en
  `ablskin` ese índice es un naranja fuerte que el marco de la ventana usa para
  todo su interior. Dibujado opaco daba un marco naranja de 8 px donde el juego
  tiene uno de 2 y el resto deja ver el fondo. La regla ya estaba escrita en
  `render_map.load_image`; `ventana.py` no la usaba.
* **La fuente del juego es `rmg2000`, no `ttyp0`.** `Font::Default()` de easyrpg
  elige una u otra según `font_id` del System, y este juego tiene `font_id = 1`
  —Mincho—, que le toca rmg2000. Yo había elegido ttyp0 leyendo el camino del
  código y sin mirar el dato. Los colores daban exactos y las letras no: 4,57%
  de los pixeles.

Con las dos arregladas, `just snes-oraculo` da **0 pixeles de diferencia de
25600** en el mapa 145 y 18 en el 167, y esos 18 son la flecha roja de "seguir"
que EasyRPG anima mientras espera al jugador y que nosotros todavía no
dibujamos. La receta la deja pasar por dónde cae, no por cuántos son.

No entra en `snes-hitos` y es a propósito: levanta un Xvfb, corre el juego medio
minuto y depende de que EasyRPG esté bajado en `/extras`. Se corre a mano cuando
se toca la ventana o la fuente.

Trampa del entorno que costó un rato: el binario oficial de EasyRPG para Linux
**trae su propio SDL2 compilado sin el backend de wayland**. Con
`SDL_VIDEODRIVER=wayland` en el entorno —común en Arch— falla con
`wayland not available`, y el mensaje no dice que la culpa es de la variable.
Desde el host se arregla con `SDL_VIDEODRIVER=x11`; acá adentro corre sobre
Xvfb y no aplica.

Lo que ya está hecho, y es **sólo el lado de la referencia**:

* `tools/fuente.py`, generada desde easyrpg-player igual que `event_codes.py` se
  genera desde liblcf y por la misma razón. Trae **las dos** fuentes de 6x12
  —ttyp0 y rmg2000— y cuál se usa lo dice `font_id` del juego, no una constante
  nuestra. Los 95 caracteres ASCII imprimibles; el texto del juego es ASCII
  puro, 93 distintos y sin acentos.
* `tools/ventana.py`, la ventana de mensaje armada desde el System del juego,
  que es `ablskin`. Las reglas salen de `Window::RefreshBackground`,
  `Window::RefreshFrame` y `Font::Render` de easyrpg-player, con los números que
  no se adivinan: el fondo se **estira** y no se repite, el marco son cuatro
  esquinas de 8x8 más bordes repetidos, el color del texto es un **bloque de
  16x16** que se usa como máscara —por eso las letras salen con degradé— y la
  sombra sale de (16,32) dibujada primero y corrida un pixel.

Y una medición que sale bien: la página entera —ventana, marco, texto y sombra—
usa **9 colores a 15 bits**. Entra en una sola paleta de 4bpp, así que la
ventana puede vivir en BG2 sin pelear por CGRAM.

**Cómo lo resuelve un juego de SNES de verdad**, que era la duda razonable —lo
normal es suponer que usaban glifos de 8 px y listo—. Se miró **Final Fantasy
VI**, en `/extras/ref/ff6`, que es el caso más parecido: un RPG en inglés con
mucho texto. No usa 8 px fijos:

* tiene una **tabla de anchos por caracter**, `FontWidth`, con valores de 4 a
  12, que copia a la WRAM en `$7E9E00` al arrancar (`InitDlgVWF`);
* **compone el texto en un buffer de WRAM** —`$9183-$9DFF`, "Dialog Text
  Buffer"— y lo sube, en vez de armarlo con índices del tilemap;
* y pone **la sombra en los bitplanes 3 y 4**, separada del glifo.

O sea, exactamente la arquitectura que hace falta acá, y por la misma razón: con
glifos de 8 px el texto en inglés no entra. Medido sobre este juego: a 32
columnas truncar pierde el **9,23% de los caracteres** —6,1 por línea cortada— y
envolver manda el 27,4% de las páginas a más de cuatro líneas. A 40 columnas es
1,06% y 8,6%.

Lo que eso cambia del plan: nada, y ahora se sabe por qué. Componer pixel por
pixel hace falta para cualquier ancho menor a 8, así que **el ancho fijo no
ahorra la parte cara**: contra el variable es una tabla de anchos y dos líneas
más. El ancho fijo de la fase 1 se queda igual, pero por otro motivo del que se
creía: no es que sea más simple de implementar, es que es **idéntico a
easyrpg-player pixel por pixel**, y eso convierte una captura de EasyRPG en un
tercero contra el que comparar. Es lo que este repo nunca tiene. Para eso está
`just snes-mensaje`, que dibuja una página de mensaje de verdad del juego.

**Lo que falta, que es todo el lado de la ROM.** El problema real es la VRAM:
estamos en modo 3, que no tiene BG3, y los 64 KB están reeprtidos al 100%. La
ventana necesita 8 KB —el texto son 240 tiles de 4bpp y no hay forma de bajarlo,
porque un glifo de 6 px no se alinea a celdas de 8 y hay que componerlo pixel
por pixel—. El reparto que cierra, ya calculado:

    sprites   0..16383      16 KB, 512 tiles, base de OBJ en 0
    fondo     16384..40959  24 KB, 384 tiles de 8bpp
    encima    40960..49151   8 KB, y acá va la base de BG2
    ventana   49152..57343   8 KB, o sea los índices 256..511 de BG2
    tilemaps  57344..65535

BG2 llega a los dos bancos con una sola base porque quedaron pegados, que es lo
que obliga a poner los sprites primero. Para los mapas que necesitan más de 384
tiles de fondo hay un segundo reparto con el fondo en 32 KB y los sprites en 8.
Medido sobre 299 mapas: 290 entran en el primero, 7 en el segundo, y **sólo 2 se
quedan sin ventana** —el 8, Lashe City, y el 250—, que piden a la vez más de 384
de fondo y más de 256 de sprites.

**Hecho el 2026-09-04: el reparto de VRAM.** `vram_layout()` ahora toma también
cuántos tiles de sprite gasta el mapa y si la ROM lleva ventana, y devuelve uno
de cuatro repartos. Los dos de siempre quedaron intactos y se siguen usando
cuando no hay ventana, así que **la tanda no cambia**: `snes-heroe 7` da los
cinco en cero después del cambio. Las direcciones y el porqué de que `encima` y
`ventana` tengan que quedar pegados están en el comentario de `LAYOUT_VENTANA`.

Y con eso quedó medido lo que faltaba para saber si el plan cierra:

    ventana vacía            4 colores,  15 tiles distintos de 320 celdas
    con las 4 líneas llenas  8 colores, 224 tiles distintos (entran 256)

O sea que el banco de 8 KB alcanza **en el peor caso**, no en el promedio, y los
8 colores entran en una sola paleta de 4bpp con el índice 0 libre para la
transparencia. El texto denso con el que se midió son 39 caracteres por línea de
letras, números y símbolos, que es más de lo que tiene ninguna página del juego.

Falta entonces: emitir los tiles de la ventana y de la fuente, elegirle una
paleta de CGRAM, componer el texto en tiles desde el 65816, el opcode del
intérprete y que la página espere a que el jugador apriete A.

Y hay un problema abierto que hay que resolver **antes** de escribir el
assembly, porque decide la forma de todo lo demás. **El tilemap de BG2 es el de
la capa de encima y se scrollea con la cámara**, así que escribir la ventana ahí
la hace moverse con el mapa.

Yo había escrito acá que no importaba, porque durante un mensaje de RM2k no se
mueve nada. **Es falso**, lo preguntó taro y al medirlo salió que ni siquiera es
un caso raro:

* En `game_player.cpp` de easyrpg, `UpdateMoveRoute` se llama **antes** del
  guard de `IsMessageActive()`. O sea que **una ruta forzada del héroe sigue
  caminando mientras hay un mensaje en pantalla**, y la cámara lo sigue. En este
  juego hay **186 páginas** donde el héroe arranca una ruta que camina y a los
  pocos comandos aparece un mensaje. La primera está en el mapa 1.
* `Game_Map::Update` sigue corriendo durante un mensaje, así que los eventos de
  **proceso paralelo** también. Hay **25 páginas paralelas con `PanScreen`**, de
  72 que lo usan en total.

Así que la ventana tiene que quedar clavada a la pantalla aunque BG2 se
scrollee, y las salidas que se vieron son todas caras de distinta manera:

* **HDMA sobre `BG2HOFS`/`BG2VOFS`** en las líneas de la ventana. Es la técnica
  clásica de barra de estado, pero muestra una región *fija* del tilemap de
  encima, y con un tilemap de 64x32 y una cámara que se mueve libre no hay
  ninguna región que no se use.
* **HDMA sobre `BG2SC`**, apuntando a un tilemap propio para esas líneas. Es lo
  más limpio, y cuesta 2 KB de VRAM que hoy no están: los dos tilemaps ya se
  comen los 8 KB de $7000 a $8000.
* **Achicar el tilemap de encima a 32x32** para liberar esos 2 KB. Entra justo
  —la pantalla son 32x28 celdas— pero deja sin margen al scroll.
* **La ventana por OBJ**, que no se scrollea con el fondo. El marco entraría en
  pocos objetos grandes; el texto no, por el límite de 32 objetos por línea.

**Elegida el 2026-09-04: ninguna de las cuatro, sino seguir el scroll.** En vez
de pelear con que BG2 se mueva, se escriben las celdas de la ventana en las
posiciones que en *ese* cuadro corresponden a la franja de abajo. Si la cámara se
movió, se estampan en otro lado y se ven igual de quietas. No usa HDMA ni un byte
más de VRAM, son escrituras de VRAM y nada más —el camino que los tres cores
emulan igual— y no inventa un mecanismo: el scroll ya escribe celdas del tilemap
cuando la cámara se mueve.

Y hay una corrección importante al plan, que salió de medir y no de pensar. Yo
había dicho "320 celdas por cuadro, 640 bytes, un 10% del vblank". **Está mal por
un factor de cuatro**: el tilemap es de 64x32, o sea dos pantallas, y hay dos
capas, así que una franja de diez filas son **2560 bytes**. Y eso no entra:
llamando a `redibujar_franja` de más a propósito sobre `snes-heroe 7`, cada
cuadro da 532 pixeles de basura, cada 8 cuadros 262, cada 64 cuadros 0 y una sola
vez 0. Que la basura escale con la frecuencia y no con el contenido es lo que
dice que el problema es el vblank y no las direcciones.

Así que la ventana **no se estampa entera cada cuadro**. Se estampa una vez al
abrir el mensaje, y después alcanza con **enganchar el estampado en
`stream_map`**: la cámara se mueve dos pixeles por cuadro y cruza un borde de
celda cada cuatro, así que cuando entra una fila o una columna que pisa la
franja, se le sobreescriben esas celdas con las de la ventana antes de subirla.
Es el mismo puñado de celdas que el scroll ya sube, o sea gratis.

**Hecho, y es lo primero del assembly: `redibujar_franja`.** Redibuja las diez
filas que tapa la ventana, en las dos capas, desde los datos del mapa; es lo que
hay que correr al cerrar un mensaje. No arma nada nuevo: usa `build_row` y
`push_strips`, los mismos del scroll. Verificada llamándola una vez justo
después de `fill_window` —que acaba de escribir esas mismas celdas— y corriendo
`snes-heroe 7` y `snes-heroe 6`, los diez en cero. Y la tanda entera sigue en 25
casos verdes.

Hoy no la llama nadie, porque todavía no hay forma de **cerrar** un mensaje. Es
el único pedazo de código del repo que no ejercita ninguna prueba, y se sabe.

**Y la ventana ya se dibuja en la consola**, el 2026-09-04. `just snes-ventana`
arma una ROM con un mensaje sintético y compara la pantalla entera contra la
referencia: **0 pixeles de 57344**, en el mapa 7, el 6 y el 18. Con eso la cadena
queda atada de punta a punta —la referencia contra una captura de EasyRPG por
`snes-oraculo`, y la consola contra la referencia— y los dos casos están en
`snes-hitos`, que quedó en 27 casos verdes.

Lo que entró para eso: `convert_ventana()` en el conversor, que corta la ventana
en celdas de 8x8 y la deduplica; el bloque global en el `.inc` —la ventana es
una sola para toda la ROM, así que no va en la tabla de mapas—; y del lado de la
ROM `load_ventana`, que sube tiles y paleta con la pantalla apagada, y
`estampar_ventana`, que escribe las celdas en el tilemap de encima siguiendo a
la cámara.

Dos cosas que costaron y conviene no volver a descubrir. **Las celdas de BG2 sí
usan los tres bits de paleta**, a diferencia de las del fondo, que va en 8 bits
y los ignora: `entry()` no los ponía y la ventana salía con la paleta 0. Y **un
tramo del tilemap no puede cruzar la columna 32**: las dos pantallas del mapa de
64x32 no son contiguas en la VRAM, la de la derecha vive 1024 palabras más
adelante. Cortando sólo en 64 quedaban cuatro columnas sin escribir y el mapa
asomaba por el borde derecho de la ventana.

**Hecho el 2026-09-04: la ventana entra en `snes-bsnes`.** Era el caso más nuevo
y el que más CGRAM y VRAM toca con la pantalla apagada, o sea justo la clase de
escritura que snes9x perdona y que ya nos mordió dos veces. La receta pasó de 16
a 18 segundos. Doce corridas seguidas con `bsnes_entropy=High` dan el mismo
cuadro, así que la ventana no depende de nada sin inicializar. De paso quedó
medido lo que el `LEEME` afirmaba: los tres cores dibujan este cuadro igual a 15
bits —los PNG difieren en los bits bajos, que es por lo que la comparación es a
15 y no por md5—.

**Hecho el 2026-09-04: la paleta de la ventana la paga el fondo.** El conversor
cortaba en el mapa 1. Ahora, con ventana, el fondo se aprieta en las paletas que
quedan debajo de la de la ventana y fusiona el excedente.

A quién cobrarle no era obvio y se midió. El fondo va en 8 bits, así que sus
paletas son un pozo común y una menos le saca 16 entradas: fusiona sólo lo que
se pase. La capa de encima va en 4 y empaqueta por tile, así que perder una le
cuesta mucho más. En el mapa 1, quitándosela al fondo se fusionan 2 colores;
quitándosela a la capa de encima, 16.

Relevados los 328 mapas, la reserva le cuesta al fondo **a lo sumo una paleta**,
que es lo máximo que puede costar: **290 no fusionan nada** y los 38 que sí van
de 1 a 16 colores. Los 16 son el techo y los toca el mapa 348.

Y faltaba una pata: `snes_expect.py` llamaba a `convert_layers` **sin**
`con_ventana`, así que la referencia repartía CGRAM de otra manera. No se veía
porque en los mapas 7 y 6 el fondo no llega a fusionar y las paletas quedan
idénticas igual. Arreglado, y ahora lo ejercita `snes-ventana 348`: con la
referencia vieja difiere en 45 pixeles.

`snes-hitos` quedó en **29 casos**, todos en verde, 69 segundos repartida en
seis. Los dos casos nuevos de ventana son el mapa 1 —el que descubrió esto, y el
único de los cuatro que no entra en el tilemap de 64x32, o sea el único que
estampa la ventana sobre un mapa que la ROM va redibujando— y el 348, que es
donde la fusión se ve.

**Hecho el 2026-09-04: el opcode, el bloqueo y la espera de A.** `OP_MENSAJE`
abre la ventana y corta el cuadro; la página queda frenada hasta el **flanco** de
A —`pad_a` contra `pad_a_ant`, que es el `IsTriggered` de RM2k— y sigue en ese
mismo cuadro. El estampado y el redibujado los hace `mensaje_de_evento` al final
del cuadro, con la pantalla apagada, por lo mismo que el tinte: son 640 y 2560
bytes de tilemap y no entran en un vblank.

Lo prueba `snes-cerrar`, con la misma forma que `snes-espera`: dos cuadros con
margen, a los 60 la ventana abierta y la página frenada —el tinte que viene
detrás todavía no se aplicó— y a los 400 la ventana borrada y el tinte puesto.
Los dos cuadros difieren en 52637 pixeles de 57344. Cada mitad se verificó
rompiéndola: sin `redibujar_franja` el cuadro 400 da 15789, y sin bloquear el
cuadro 60 da 36848. Es la primera prueba que ejercita `redibujar_franja`, que
hasta hoy no la llamaba nadie.

**El `ShowMessage` de RM2k todavía no compilaba, y el opcode no llevaba
operandos.** Una página de mensaje ya compuesta son ~240 tiles de 4bpp, o sea
7,5 KB: emitir una por mensaje no entra ni cerca en 256 KB. Hasta que el texto
se armara en caliente desde el 65816, como FF6, la ROM llevaba una sola ventana
compuesta por el conversor. O sea que esto no desbloqueaba ninguna de las 144
páginas: lo que desbloqueaba era el intérprete, que ya sabía abrir, bloquear y
cerrar. Las dos cosas que faltaban se hicieron el mismo día —el compositor
primero y el operando después—; está más abajo.

`snes-cerrar` entró además en `snes-bsnes`, en el lugar de `snes-ventana`:
cubre lo mismo —su primer cuadro es la ventana dibujada— y algo más.

Y de paso salió una **corrección a algo que este repo daba por sabido**. Decía,
en el LEEME y en tres comentarios, que "snes9x arranca la RAM en cero". Es
falso: `msg_abierto` sin inicializar rompe el cuadro 400 en las doce corridas de
snes9x, y da igual en qué dirección de BSS caiga —se probó pegada a `port0` y al
final del segmento—. Lo que sí se sostiene, y es más útil, es que lo que snes9x
deja es siempre lo mismo, así que esconde los errores que un patrón fijo
esconde: con el error de `ruta_n`/`ruta_i` puesto de vuelta a mano, snes9x da 0
de 10 en rojo y bsnes 2 de 10. Sea cual sea el valor que deja, hace que
`ruta_i < ruta_n` dé falso las diez veces. `msg_abierto` no tiene con quién
empatar y se ve siempre.

**Hecho el 2026-09-04, y lo encontró taro jugando: el pad movía al héroe con el
mensaje abierto.** No era una decisión, era un agujero, y del peor tipo: la
referencia hacía lo mismo, así que `snes-cerrar` daba cero. En easyrpg,
`Game_Player::UpdateNextMovementAction` llama primero a `UpdateMoveRoute` y
recién después vuelve si `IsMessageActive()`, o sea que la ruta forzada camina y
el input no. Arreglado de los dos lados, y lo prueba `snes-cerrar 7 200
cerrar-right right`, que mantiene la cruceta apretada: sin el guard, el cuadro
60 se va a 22658 pixeles.

De paso, el log de `snes_expect.py` mentía otra vez, y en el mismo lugar que la
vez pasada: imprimía la dirección **pedida** y no la dibujada, así que decía
"mirando right" mientras dibujaba al héroe mirando abajo. Ahora imprime la que
se dibuja siempre.

**Cerrado el 2026-09-04: la ventana queda quieta, y por HDMA.** El camino que se
había elegido —seguir el scroll estampando celdas— se implementó, se midió y
**no funciona**, y la razón no es de implementación: el tilemap se dibuja en
celdas de 8 pixeles y la cámara se mueve de a 2, así que la ventana cae a
`camara_x mod 8` pixeles de donde va. Medido con la cámara moviéndose sólo en
horizontal, y comprobado corriendo la referencia esos mismos pixeles:

    camara_x 720, resto 0    238 pixeles
    camara_x 722, resto 2   2627
    camara_x 724, resto 4   2717
    camara_x 726, resto 6   3198

O sea un cuadro de cada cuatro por eje. Y por el camino aparecieron dos cosas
más: la franja hay que reestamparla **entera** en cada cruce y no la columna que
entra —lo que decía acá era falso—, y la fila que sale de la franja no la
redibujaba nadie, así que bajando doce celdas quedaban doce filas de basura
arriba del texto.

**Lo que anda es HDMA**, que estaba descartado por 2 KB de VRAM que no había. De
la línea 0 a la 143 BG2 sigue siendo la capa de encima con la cámara; de la 144
a la 223 es un tilemap propio de la ventana, de 32x32, con el scroll clavado.
Dos canales: uno para `BG2SC` y otro para `BG2HOFS`/`BG2VOFS`.

Lo que compra además de ser exacto: el tilemap de la ventana no lo toca nadie
más, así que se escribe **una sola vez al cargar el mapa** —320 celdas seguidas,
un solo DMA— y abrir un mensaje es prender el HDMA y cerrarlo es apagarlo. Ni
una escritura de VRAM en el medio, ni un cuadro en negro, y `redibujar_franja`,
`estampar_fila` y `mensaje_de_evento` se borraron.

**Los 2 KB salen de los sprites**, y está relevado sobre los 318 mapas que
convierten: el que más gasta usa 380 tiles de sprite de los 512 que el reparto
le da, así que con 448 no se queda corto ninguno y la palabra $1C00 queda libre.
En el reparto para mapas con mucho fondo no pueden salir de ahí —esos usan hasta
320— y salen del fondo: 480 tiles en vez de 512.

Lo prueba `snes-anclada`, con los cuadros elegidos por el resto de la cámara
contra 8, que es justo lo que hundía al intento anterior:

    cuadro  21   camara_x 722, resto 2   antes 2627 pixeles, ahora 0
    cuadro  23   camara_x 726, resto 6   antes 3198, ahora 0
    cuadro  50   camara_y 700, resto 4   antes 5964, ahora 0
    cuadro 130   la ruta ya bajó doce celdas   antes 11705, ahora 0

Y los tres cores dibujan el mismo cuadro con HDMA adentro, medido sobre el 23.

**Dos errores que salieron de rebote, y los dos eran invisibles.**

* **La tabla de mapas se pisaba a sí misma.** `MAPA_PTR_BASE` estaba escrito a
  mano en 48, y agregar un escalar más dejó `ABOVE_FIRST` y el primer puntero en
  el mismo desplazamiento: la ROM leyó el byte de la paleta como puntero a los
  tiles del mapa y la pantalla salió de un color plano. Ninguna de las dos
  puntas lo puede ver —para el ensamblador son dos nombres distintos con el
  mismo valor, y la comparación dice "todo mal" sin decir dónde—. Ahora el
  número sale de los datos y hay un `assert` de que el registro entra.
* **`vram_layout` no comprobaba que el fondo entrara en el banco.** `MAX_TILES`
  es 1024, que es el tope del índice del tilemap y no el del banco, así que los
  mapas 66 y 250 —518 y 620 tiles— se llevaban el reparto de 512 y se pasaban
  por arriba de la capa de encima. Nunca se vio porque ninguna receta les pide
  una ventana. Por eso el número de mapas sin ventana pasó de 2 a 3: el 2 estaba
  mal contado.

`snes-hitos` quedó en **34 casos**, todos en verde, 72 segundos repartida en
seis.

**Hecho el 2026-09-04: la ROM compone el texto.** La fuente está en el
cartucho y los 240 tiles del área de texto los arma el 65816, renglón por
renglón, de a 5 caracteres por vuelta del lazo. `snes-ventana` da 0 pixeles de
57344 contra la referencia, y `snes-oraculo` sigue dando 0 de 25600 contra la
captura de EasyRPG: la cadena queda atada de punta a punta con el texto armado
en la consola.

Lo que lo volvió barato es una medición: RM2k usa el glifo como máscara sobre un
bloque de 16x16 del System, y eso pide muestrear pixel por pixel. Pero **cada
fila del glifo toma un solo color** y la sombra es plana, así que todo el color
son doce bytes más uno. El detalle está en "El texto se compone en caliente" del
`LEEME.md`, junto con lo de los planos vecinos, que baja de dieciséis
escrituras por fila de glifo a cuatro.

Dos números que quedan fijados: **39 caracteres por línea** —lo impone el banco
de 256 tiles, y truncar ahí pierde el 1,58% de los caracteres del juego contra
el 1,09% de truncar a 40— y **5 caracteres por cuadro**, medido: con 5 y con 6
`snes-anclada` no pierde un cuadro y con 8 pierde uno. Perder cuadros no se ve
mirando; lo que pasa es que el héroe camina más lento que en la referencia.

**Y salieron tres errores del ensamblador, los tres en silencio**, que es lo que
hizo largo esto:

* **`.res` en el segmento equivocado.** Las variables del compositor se
  declararon donde estaba el comentario que buscaba, que era código y no
  `ZEROPAGE`: quedaron en la ROM, en $8B40, y el compositor escribía en el
  cartucho. Nada lo dijo.
* **`[dp],y` con una variable que no está en la página directa.** `msg_ptr` vivía
  en BSS, el modo indirecto largo direcciona sólo la página directa, y el
  ensamblador emitía el byte bajo de $0129: la ROM leía el puntero de $0029.
  **Ahora es un error**: un operando que no entra en su modo se rechaza.
* **`emit_item` duplicaba `Instruction.emit`.** Eran dos copias de la misma
  cuenta, y se notó de la peor manera posible: el control del punto anterior,
  agregado en una, no corría nunca. Quedó en un solo lugar.

De paso quedó confirmado con qué llena snes9x la WRAM: **$55**. Se vio leyéndola
en el primer cuadro, `msg_estado = 85`. Es lo que explica que `ruta_n` y
`ruta_i` sin inicializar quedaran iguales y el error desapareciera.

**Hecho el 2026-09-04, y con esto la ventana queda cerrada: el operando de
`OP_MENSAJE`.** Ahora lleva un desplazamiento de 16 bits dentro del bloque
`mensajes`, y el conversor compila los `ShowMessage` del juego. Las páginas que
compilan enteras pasaron de **16 a 71**, medido con `just snes-destraba`, que es
exactamente el número que se había prometido.

El bloque de textos es de la ROM entera y no del mapa, y lo arma
`eventos.Mensajes` mientras se compilan las páginas: cada cuadro de texto deja
su texto ahí y se lleva un desplazamiento. Tres decisiones que no se deducen
leyendo el código:

* **Los dos lados lo arman en el mismo orden**, porque el desplazamiento sale de
  ese orden y de nada más. El conversor recorre los mapas de la tabla; la
  referencia, que hasta ahora compilaba cada mapa cuando el héroe lo pisaba, los
  compila **todos al construir el `Mundo`**. Si no, una puerta que llevara al
  mapa 3 antes que al 1 le daría al mismo texto otro número que el que emitió el
  conversor, y los dos lados dibujarían mensajes distintos con el mismo
  bytecode. El mensaje de `--mensaje-de-prueba` va primero de todo, así que su
  desplazamiento es 0 y no depende de nada.
* **Una página que no compila no deja su texto en el cartucho.** La página se
  compila comando por comando y puede cortarse en el último; sin deshacer lo
  agregado, el texto de las 418 páginas que **no** compilan viajaría igual. Son
  los 161 KB del juego entero contra los pocos que hacen falta.
* **Llevar ventana es ahora una decisión explícita, `--con-ventana`**, y
  `--mensaje-de-prueba` la implica. No es de gusto: la ventana cuesta 8 KB de
  VRAM y una paleta, así que una ROM que no la lleve no tiene dónde dibujar un
  mensaje y sus `ShowMessage` no compilan. Antes esa cuenta estaba escrita
  cuatro veces como `getattr(args, "mensaje_de_prueba", None)`, y con eso el
  reparto de CGRAM y el de VRAM podían contestar cosas distintas.

* **Los otros dos lugares que filtran páginas tuvieron que aprender la misma
  regla.** El aviso de deudas —el que dice "esta página usa `PlayBGM` y la ROM
  no lo hace"— y `lideres_posibles`, que decide qué actores pueden llegar a
  dibujarse como héroe y por lo tanto qué sprites van a la VRAM. Los dos
  recompilaban las páginas con su propio criterio, y sin el bloque de textos una
  página que agregue a alguien al grupo después de un cuadro de texto les
  parecía no compilar: el actor se quedaba sin sus tiles y la ROM lo iba a
  dibujar con los del anterior. Es la trampa de siempre —dos filtros que dicen
  cosas distintas sobre el mismo dato— y no la habría visto ninguna comparación
  de las que hay.

**Lo prueba `snes-texto`, que es lo que ninguna receta anterior probaba.** Todas
las de la ventana usan `--mensaje-de-prueba`: tres líneas inventadas en una
página inventada. Eso probaba el dibujo, el bloqueo y el cierre, pero el camino
nuevo —que un `ShowMessage` compile, que su texto entre al bloque y que el
operando lo vuelva a encontrar— no lo corría **nada**, que es exactamente cómo
sobrevivieron los tres errores del intérprete de eventos.

El mapa 255 se eligió midiendo: tiene una página automática sin condición de
switch cuyo código entero son dos cuadros de texto seguidos y un switch. De ahí
salen las tres cosas que faltaba mirar —que el segundo mensaje está en el
desplazamiento 124 y no en el 0, que tiene cuatro renglones y el de prueba tenía
tres, y que al apretar A el primero se cierra y el segundo se abre en el mismo
cuadro—. Los cuadros 60 y 400 dan 0 de 57344 contra la referencia, y **entre
ellos difieren en 2869 pixeles**, todos en las filas de la ventana: si el A no
avanzara al segundo mensaje serían cero y la receta daría verde sin probar nada.

Lo que **no** compila, dicho con todas las letras: **las páginas con códigos de
escape**. Este juego usa dos, `\|` —una pausa de un segundo— y `\^` —cerrar el
cuadro sin esperar al jugador—, en 35 líneas y 17 páginas. Dibujarlos como dos
letras se vería; borrarlos calladito sería peor, porque con `\^` la ROM quedaría
esperando un A que RM2k nunca pidió y la página pasaría a durar lo que tarde el
jugador. Son 11 de las 305 que quedarían si se hiciera todo lo demás.

**Y el despacho del intérprete dejó de tener un límite de alcance.** Era una
cadena de `beq` al cuerpo de cada opcode, y un `beq` llega a 127 bytes: el
cuerpo del último opcode está detrás de todos los demás, así que el límite lo
marca la suma de los otros. Cortó dos veces —OP_MENSAJE dejó a OP_TELEPORT a 140
bytes, se arregló ordenando las comparaciones como los cuerpos, y darle su
operando a OP_MENSAJE lo mandó a 129, o sea que aquel arreglo duraba exactamente
un opcode—. Ahora cada opcode se despacha con `bne :+` y `jmp`, que llega a
cualquier parte del banco. Sale tres bytes y cuatro ciclos por opcode que no
matchea, en un despacho que corre unas pocas veces por cuadro, y saca del medio
un corte que iban a volver a pagar los cuatro comandos que siguen.

Y falta el reacomodo del texto, que taro pidió dejar **para otro hito**: la fase
1 trunca y queda medio ilegible a propósito. A 40 columnas eso es el 1,06% de
los caracteres.

**Después: la cinemática de apertura.**
El mapa 4 ya prende el switch 20, que es la condición de la página que abre el
mapa 1, así que el enganche funciona. De los cuatro comandos que le faltaban ya
están dos —`PlayBGM` aceptado sin hacerlo, `MoveEvent` caminando de verdad—;
quedan `ChangePartyMembers` y `WeatherEffects`, más que exista un grupo, porque
la condición pide `actor`. Mientras tanto el héroe queda parado adentro del
caño, que es donde RM2k también lo deja.

**`WeatherEffects` va último**, decidido por taro el 2026-09-03. No bloquea
nada, es atómico, y es de los caros. La idea que dejó anotada y que conviene no
perder: que se pueda **apagar**, porque si el clima dibuja encima cambian todas
las referencias PNG de los mapas que lo usen. Son 5 páginas del juego.

**Y el orden de lo que sigue se volvió a medir el 2026-09-04, porque el número
que se venía usando medía otra cosa.** La tabla vieja contaba qué comando corta
**primero** cada página —ShowMessage 144, CallEvent 98, MoveEvent 60— y eso no
es lo que se destraba: una página cortada por un cuadro de texto puede estar
cortada además por otras cuatro cosas. Lo que hay que contar es cuántas páginas
pasan a compilar **enteras**, y eso ahora lo dice `just snes-destraba`:

    489 páginas automáticas con comandos, 16 compilan enteras hoy

    ShowMessage               +55      ConditionalBranch      +0
    FlashSprite               +23      WeatherEffects         +0
    PlaySound                  +5      FullHeal               +0
    ControlVars                +4      PanScreen              +0
    MoveEvent de otro evento   +3      ChangeItems            +0
    TintScreen con saturación  +2      FadeOutBGM             +0
    ChangeEventLocation        +1      CallEvent              +0

La conclusión sobre los cuadros de texto se sostiene —siguen siendo de lejos lo
que más rinde, y ahora se sabe cuánto: de 16 páginas a 71— pero las de abajo
cambian de lugar, y dos números estaban directamente mal:

* **`CallEvent` no destraba 98 sino cero.** Aceptarlo sin hacerlo daba +97, y es
  falso: el evento común llamado tiene que compilar él también, y los 45 eventos
  comunes con comandos de este juego se cortan casi todos en `FullHeal` y en
  `ControlVars`.
* **`ShowMessage` parecía destrabar 3.** RM2k emite un `ShowMessage` y después
  un `ShowMessage_2` por cada línea de más del mismo cuadro; contándolos aparte
  el número salía mal. Ésa es la trampa que más fácil se repite y por eso está
  anotada en `tools/destraba.py`.

Puestas las catorce juntas se llega a 314 de 489. La tabla entera y la cola de
lo que quedaría después están en "Lo que falta" de `rom/LEEME.md`.

Después del hito, el mismo día, se armó la documentación de proceso: este
archivo y `AGENTS.md` en `92509fc`, y el contenedor y `snes-tinte` en `d7597cc`
y `2cc8078`. Nada de eso toca la ROM.

Dos cosas cambiaron del lado de taro, en su `box`, y no se ven desde el repo:
sacó el montaje de sólo lectura de `/home/taro/git/gaming/abl-rm`, que no usaba
nadie, y pasó a `--rm --replace --name` para que los contenedores dejen de
acumularse. Si algo del entorno se ve distinto a lo que dice `AGENTS.md`, es
por ahí.

## Lo que se cree y no se corrió

Esta sección existe porque el commit `c64e4d9` decía "Verificado" sobre un
camino que ninguna prueba ejecutaba, y eso costó tres errores encadenados. Un
commit narra lo hecho; los supuestos no tienen dónde vivir. Acá.

* ~~**`OBJ_PRIORITY_ABOVE = $20`.**~~ Cerrado el 2026-09-03. La respuesta
  resultó ser que con los datos del juego **no se puede** ejercitar: se
  relevaron los 335 mapas y hay un solo evento con gráfico en esa capa —el
  Package del mapa 261— y la capa de encima de ese mapa no llega a pisarlo por
  dos pixeles. Donde no hay capa de encima, las prioridades 1 y 2 dibujan lo
  mismo. Así que la prueba pasa por el héroe: `snes-encima` lo sube a prioridad
  2 en una celda donde la capa lo tapa a medias, que es el mismo byte de
  atributos y el mismo `emit_object` que usaría un evento "above". Los dos
  lados coinciden en 0, y las dos referencias —prioridad 1 y prioridad 2—
  difieren en 284 pixeles, o sea que el par no da cero por casualidad. El
  Package igual entró en la tanda, por el orden capa-antes-que-Y. Ver "Cómo se
  verifica" en `rom/LEEME.md`.
* ~~**Moverse por una ruta forzada.**~~ Cerrado el 2026-09-03, y la premisa que
  estaba escrita acá era falsa de punta a punta: la ROM ya coincidía, los 410
  pixeles salieron de una referencia puesta a mano y de un log que mentía, y los
  dos errores de verdad estaban en la referencia. Está contado arriba, en "En
  vuelo". Lo ejercita `snes-ruta`, que es sintético porque ninguna página del
  juego lo pide todavía.
* **Que la página siga después de un teletransporte.** Anotado el 2026-09-03.
  El intérprete cortaba la página en el primer `Teleport`, con un comentario
  que decía "RM2k tampoco". Es falso: en
  `Game_Interpreter_Map::CommandTeleport` de easyrpg-player el motor reserva el
  salto, hace `index++` y devuelve false, o sea que corta el cuadro pero retoma
  en el comando siguiente después del cambio de mapa. Ya está arreglado de los
  dos lados, pero **no lo ejercita ninguna prueba**: de las 335 páginas
  automáticas del juego, las que hoy compilan y tienen comandos después de un
  teletransporte son **cero**. Lo va a ejercitar la cinemática de apertura, que
  tiene once comandos después del primero.
  Y queda una aproximación adentro: no se corren los eventos automáticos del
  mapa intermedio, que RM2k sí correría entre un salto y el siguiente. En la
  cinemática los dos van al mismo mapa; si aparece una que salte entre mapas
  distintos, hay que volver acá.
* **La tanda no puede ver la RAM sin inicializar.** Descubierto el 2026-09-03,
  jugando. `snes9x` —el core con el que corre toda la tanda— **deja siempre la
  misma basura**, y mednafen no. (Acá decía "arranca la RAM en cero", y el
  2026-09-04 se midió que no: ver arriba.) Una variable nueva que nadie inicializa da verde en las
  60 comparaciones y falla en mednafen y en hardware real. Ya pasó: `ruta_n` y
  `ruta_i` sin inicializar hacían que `move_hero` creyera que había una ruta
  forzada pendiente y no leyera el pad nunca; el héroe no se movía y la tanda no
  se enteraba.
  Y no fue la única: el tinte pedido por un evento se aplicaba con la pantalla
  encendida, así que entraba a medias —CGRAM no acepta escrituras mientras el
  PPU dibuja—. snes9x las acepta igual; mednafen no. Las dos las encontró taro
  jugando, con la tanda en verde.
  Mitigado el mismo día con `snes-mednafen`, y **cerrado a la tarde con
  `snes-bsnes`**, que corre los mismos dos casos —uno que tiñe desde un evento y
  uno que camina— con `bsnes_entropy=High`, o sea con la WRAM llena de basura al
  encender. Los dos están en la tanda.
  Lo que queda sin cerrar es que la detección es probabilística: con el error de
  `ruta_n`/`ruta_i` puesto de vuelta a mano, el cuadro sale mal 11 corridas de
  20. Es mucho mejor que las 0 de 20 de snes9x, pero no es una garantía: un
  error de esta clase puede pasar una tanda y caerse en la siguiente. Si eso
  molesta, la salida sería correr el caso de bsnes varias veces, que a veinte
  segundos por vez es barato.
* ~~**Por qué bsnes devuelve una pantalla negra.**~~ Cerrado el 2026-09-03. Era
  `tools/retro.py` pasándole `game->path` en NULL a un core que declara
  `need_fullpath` y no mira `game->data`. El detalle está arriba, en "En vuelo".
* **El orden de la tabla de mapas.** Cerrado a medias el 2026-09-03, y la
  mitad que queda no se puede cerrar comparando. Lo que sí se corre ahora es
  que la ROM resuelva un índice compilado que no sea 0 ni 1: `snes-hitos` corre
  el mismo evento del mapa 4 dos veces, con la tabla de dos y con `[4,7,19,1]`,
  donde el salto compila a 3. Bajarlo a mano a 2 manda la ROM al mapa 19 y
  mueve 55336 de los 57344 pixeles.
  Lo que no se puede probar así es **la convención**: cómo se arma la tabla
  —el de `--map-id` primero, después los de `--mapas` sin repetir— está escrito
  igual en el conversor y en la referencia, a propósito, porque si no
  compararían dos mundos distintos. Justamente por eso, equivocarla los
  equivoca a los dos juntos y la comparación sigue dando cero. Es el mismo
  agujero de siempre y no tiene salida por este lado: se revisa leyendo los dos
  lados, no corriéndolos.
* **El tope de ocho saltos.** Medido el 2026-09-03, y sigue sin correrse pero
  ahora se sabe por qué. Con los 328 mapas en la tabla —lo más largo que puede
  dar— hay **un solo** mapa cuya página automática teletransporta al entrar: el
  4 al 1. La cadena más larga es de un salto sobre ocho, y no hay ningún ciclo.
  Ojo con esto: no es estable. En cuanto entren los comandos que hoy hacen que
  una página no compile —los de la cinemática—, van a compilar más páginas
  automáticas y las cadenas pueden crecer. Vale la pena volver a correr la
  medición después de ese corte: está en el historial de la sesión como
  `saltos.py`, son veinte líneas.
* **La guarda de la paleta vacía** en `tenir_paleta`. Relevado el 2026-09-03,
  y la premisa que estaba escrita acá era falsa. El conversor **no** emite cero
  cuando un mapa no declara sprites: `poses` arranca siempre con el CharSet del
  héroe, así que siempre hay al menos una paleta de sprites, y la capa de
  encima también recibe una aunque esté vacía. Medido en los mapas 4, 18, 19,
  261 y 1, los tres contadores —fondo, encima, sprites— dan como mínimo 2, 16 y
  16; ninguno da cero. El mapa 7 tiene la capa de encima **completamente
  vacía** y aun así emite `ABOVE_CGRAM = 16`.
  O sea que hoy la guarda protege una condición que el conversor no puede
  producir: sacarla y capturar el mapa 7 da 0 pixeles de diferencia. Se deja
  igual —el error que arregló fue real, está en "Trampas del hardware" del
  `LEEME.md`, y un DMA de cero bytes transfiere 64 KB—, pero como código
  inalcanzable, no como camino sin probar. Si alguna vez el conversor deja de
  forzar esa paleta mínima, esto vuelve a la lista.
* ~~**Las 29 páginas que compilan a puro `FIN`.**~~ Medido el 2026-09-03, y la
  respuesta es más simple que el supuesto: **las 29 tienen cero comandos**. No
  es que todos sus comandos sean de los "ignorables" —no hay comandos—. Están
  en 25 mapas, y dos de ellos, el 18 y el 52, ya están en `snes-hitos`: el
  intérprete corre esas páginas en cada tanda, no es un camino muerto.

## Lo que se dejó afuera a propósito

* **Que un NPC frene al héroe.** La referencia tampoco lo modela, y es a
  propósito: modelar de este lado algo que la consola no hace inventa una
  diferencia. Los dos lados se mueven juntos o ninguno.
* **`PlayBGM`, aceptado sin hacerlo.** Decidido el 2026-09-03. Una página que
  cambie la música compila igual y la ROM sigue con el tema que venía sonando.
  Es distinto de los comandos "ignorables", que no hacen nada porque no hay nada
  que hacer: esto sí hace algo y nosotros no lo hacemos. Se acepta porque lo que
  deja sin hacer no aparece en la pantalla que se compara, y a cambio deja
  correr páginas que si no quedarían afuera enteras —la cinemática de apertura,
  entre ellas—.
  Vive en `ACEPTADOS_SIN_HACER` de `tools/eventos.py`, en una lista aparte de
  los ignorables justamente para que la diferencia no se pierda, y el conversor
  avisa por pantalla cuando emite una página con deuda. Hoy no avisa nunca:
  aceptarlo no desbloquea ninguna página, se midió. Detalle a no olvidar:
  `snes-check` compara el audio contra el MIDI del mapa, así que el día que una
  página cambie el tema esa prueba va a estar midiendo contra el equivocado.

* **La saturación del tinte.** El conversor sólo deja pasar la neutra, así que
  una página que la use no se emite. Aceptarla sin aplicarla sería el error de
  siempre: la referencia haría lo mismo mal.
* **Los builds numerados de `rom/build/`.** No están en git y no los produce
  ninguna receta salvo el 12. Armar uno a mano es cómo se terminó mirando el
  mapa 6 creyendo que era la demo del hito 12 —ver `AGENTS.md`—.
