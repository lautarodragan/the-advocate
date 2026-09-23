# ESTADO

> **Congelado el 2026-09-23, y de sólo lectura.** Nadie lo actualiza más: lo que
> está a medias vive en `tasks/wip/` y `tasks/testing/`, lo decidido en
> `decisiones/`, lo que diverge de RM2k en `divergencias/`, y lo que nos gustaría
> en `tasks/wishlist/`. **Ningún archivo del repo lo nombra ya.** Queda mientras
> tenga algo que todavía no se mudó; el día que no quede nada, se borra.


!!ESTE DOCUMENTO ESTÁ DEPRECADO!!

Taro lo está trabajando manualmente. Está en proceso de ser revisado manualmente,
eliminar todo lo que ya no aplica, y extraer a tareas o documentación lo que sí.

---------------------------------------

## El objetivo, y dónde estamos

Las ROMs que taro va probando a mano quedan en `pruebas-manuales/<nombre>/`,
cada una con su `LEEME.txt` diciendo qué mirar y con qué limitaciones se chocó.

Cada uno de los cuatro tiene su prueba de que no cambió nada: las ROMs salen
byte por byte iguales a las de antes de cada corte. `tools/voodoo/` está
enchufado desde el paso 8c, el 2026-09-17: convierte la capa de encima desde la
imagen del asignador (`tools/port/tiles_bin.py`).

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

**Esperando que taro las mire:** las **cinco goldens `18-*`** —`test_heroe` en
el Auditorio— se movieron al hornear el público y **quedaron sin regenerar a
propósito**, así que la tanda está en rojo en esos cinco. Lo que cambió está
mirado pixel por pixel y va hacia el lado bueno: aparece gente que el port
venía **descartando** por falta de paletas de sprite, y el resto son cambios de
tono de un paso de los 15 bits, porque el público dejó de pasar por la fusión
de las paletas de sprite y va al fondo, donde entra sin fusionar. Contra el
render de RM2k del mismo cuadro, el nuevo tiene **152 pixeles de delta grande y
la golden 552**. Las capturas están en `/extras/capturas/auditorio/`.

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

* **La guarda de la paleta vacía** en `tenir_paleta` protege una condición que
  el conversor no puede producir hoy: siempre emite al menos una paleta de
  sprites y una de la capa de encima. Se deja —el error que arregló fue real y
  un DMA de cero bytes transfiere 64 KB— pero como código inalcanzable, no como
  camino sin probar. Si el conversor deja de forzar esa paleta mínima, vuelve a
  la lista.


**Lo que no cubre nada**: el cartel sobre una pantalla que destelle. En RM2k las
imágenes sí reciben el `FlashScreen` —`affected_by_flash` viene prendido— y acá
no, porque su paleta queda fuera del rango que el destello recorre. Ninguna
página del juego destella con un cartel puesto, así que es deuda declarada y no
un camino a medias.

## Lo que falta del port

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

    Y una divergencia del motor que sale de ahí y vale para cualquier juego:
  **una sustitución de tiles no se ve en el acto**. El tilemap de la VRAM no se
  reescribe solo, así que la ventana se rehace de a una columna por cuadro y
  tarda `WINDOW_COLS` cuadros en ponerse al día; RM2k redibuja el spriteset y
  se ve ya. Caminando se disimula, porque la cámara trae las columnas nuevas ya
  sustituidas. El techo de cuántas columnas por cuadro lo pone `push_strips`,
  que sube una sola.

## Lo que el juego golden condiciona hoy

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

