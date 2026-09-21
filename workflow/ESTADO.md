**Todas las ramas de sub-agente están mergeadas** y sus worktrees borrados
—eran 18 y ocupaban 7,1 GB—. Lo único que no se mergeó nunca son los
translúcidos con el color math del PPU, que taro probó y rechazó el 2026-09-12:
está en el tag `color-math` y el porqué en el README.

## El objetivo, y dónde estamos

Las ROMs que taro va probando a mano quedan en `pruebas-manuales/<nombre>/`,
cada una con su `LEEME.txt` diciendo qué mirar y con qué limitaciones se chocó.

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

## Lo que la tanda no cubre

El caso más largo de la tanda es `talan`: mil doscientos cuadros de la escena
entera del Emitter Room. Lo que la tanda no mira:

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

  Y hay un pico que no es un pico sino una cuesta: **caminando**, el mapa más
  cargado pierde cuadros seguido, y lo que los produce son los eventos
  dibujados. Medido el 2026-09-20 en el mapa 11, por 1200 cuadros: del orden de
  **siete cuadros perdidos por cada evento dibujado**, y quieto ninguno. De ahí
  salió hornear los opacos —`done/eventos-opacos-al-mapa.md`—, que bajó los 450
  de ese mapa a 228; lo que queda son los eventos que el juego mueve, que no se
  pueden hornear. Ojo al medirlo: `cuadros_perdidos` **satura en 255**, así que
  hay que leerlo y ponerlo en cero cada pocas decenas de cuadros.

  **Rediseñado el 2026-09-21**: la celda donde el minijuego de las piedras se
  juega seguía en 30 fps clavados, y en vez de optimizar el motor se rediseñó
  el minijuego —ver `tareas/el-mapa-11-no-entra-en-el-cuadro.md`—. Las 52
  baldosas de luz del mapa 11 dejaron de ser eventos y son tiles del mapa, con
  el mapa forkeado en `juego/` —los eventos dibujados del mapa pasan de 69 a
  17—, y el motor aprendió `TileSubstitution` y `StoreTerrainID`. **Falta
  data**: las cinco sustituciones del mapa no compilan porque los tiles del
  estado "apagado" no están dibujados en ninguna celda, así que sus 8x8 no
  entraron en la VRAM; el conversor lo dice por línea. Está en la tarea, con
  la segunda condición que hay que mirar de paso.

  Y una divergencia del motor que sale de ahí y vale para cualquier juego:
  **una sustitución de tiles no se ve en el acto**. El tilemap de la VRAM no se
  reescribe solo, así que la ventana se rehace de a una columna por cuadro y
  tarda `WINDOW_COLS` cuadros en ponerse al día; RM2k redibuja el spriteset y
  se ve ya. Caminando se disimula, porque la cámara trae las columnas nuevas ya
  sustituidas. El techo de cuántas columnas por cuadro lo pone `push_strips`,
  que sube una sola.

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

  Lo que subiría ese techo es repartir el presupuesto por paquete:
  `wishlist/presupuesto-de-muestras-por-paquete.md`.
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

## Lo que el juego golden condiciona hoy

La idea entera —dos capas de pruebas y dos repos— está en
`wishlist/un-juego-golden-y-dos-repos.md`. **No se hace ahora.** Lo que se queda
acá es lo único que cambia una decisión de hoy: hacia dónde tiene que empujar
cada cosa que se toque para no alejarnos de ella.

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
    ditto/, voodoo/, gunter/, protocol/  los proyectos de Rust

**`port/` no está partido todavía**: tiene tres ciclos de imports adentro
—`eventos` ↔ `batalla`, `batalla` ↔ `pantallas`, `eventos` ↔ `imagen`— y
partirlo es trabajo de criterio. Ver `tools/README.md`.

