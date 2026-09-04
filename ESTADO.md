# Dónde quedamos

Lo que existe sólo mientras alguien trabaja: qué está a medias, qué se cree sin
haberlo corrido, y qué se dejó afuera a propósito. Todo lo durable va al
`LEEME.md` de cada port y a los mensajes de commit, que en este repo son largos
justamente para eso.

Se escribe **mientras se trabaja**, no al final. Un resumen escrito al cerrar
es la misma operación con pérdida que compactar, sólo que a un archivo.

Última vez que se tocó: 2026-09-03.

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

**En curso: `ShowMessage`.** Decidido el 2026-09-04, y antes que la cinemática,
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

Dos cosas a tener presentes para eso, que ya se pensaron y conviene no
rederivar. **El tilemap de BG2 es el de la capa de encima y se scrollea con la
cámara**, así que la ventana no puede escribirse ahí y quedarse quieta... salvo
que nada se mueva, y durante un mensaje de RM2k efectivamente nada se mueve: el
jugador no camina. Así que alcanza con escribir las celdas al abrir el mensaje y
restaurarlas al cerrarlo, sin HDMA. Y **restaurarlas es el trabajo que falta
pensar**: hoy no hay una rutina que redibuje una franja del tilemap de encima
sin recargar el mapa entero. Nada de eso está
escrito todavía, y por lo tanto nada de esto lo corre ninguna prueba: `fuente.py`
y `ventana.py` están verificados sólo a ojo, mirando el PNG que saca
`just snes-mensaje`.

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

Y el orden de lo que sigue después no es opinión: de las 519 páginas automáticas
del juego se cortan 473, y el comando que más corta es `ShowMessage`, con 144.
La tabla entera está en "Lo que falta" de `rom/LEEME.md`.

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
  jugando. `snes9x` —el core con el que corre toda la tanda— **arranca la RAM en
  cero**, y mednafen no. Una variable nueva que nadie inicializa da verde en las
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
