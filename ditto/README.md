# Ditto

Lee los archivos de RPG Maker 2000 —`.ldb`, `.lmu`, `.lmt`— y los vuelca a
JSON, **y los vuelve a escribir desde el JSON**. Se llama así porque hace una
sola cosa: copiar la forma de otro.

    cargo run --release -- leer   /extras/abl-rm/Map0001.lmu mapa1.json
    cargo run --release -- volver mapa1.json                 Map0001.lmu

## Lo único que lo hace valioso: la vuelta es byte por byte

Sobre el juego entero —los **328 `.lmu`**, el `RPG_RT.ldb` y el `RPG_RT.lmt`—
leer, volcar a JSON, volver a escribir desde el JSON y comparar contra el
original da **330 de 330 idénticos**. Eso es lo que permite lo que taro pidió:
tener el juego como JSON en el repositorio, abrirlo con el RPG Maker de verdad
—o con el de EasyRPG—, guardarlo y volver, usando el formato propio nada más
que como medio de transporte. Un "casi" no sirve: un byte de más rompe el juego
de otro.

Lo mide `cargo test`:

    just ditto-pruebas          # una muestra de mapas, un segundo
    just ditto-vuelta-entera    # los 330, con el número impreso

La tanda corta va por omisión para que `cargo test` siga siendo algo que uno
corre sin pensarlo. `GAME_DIR` dice de dónde sale el juego; por omisión
`/extras/abl-rm`.

Y hay una segunda prueba, porque la vuelta sola no alcanza: un lector que no
entendiera **nada** y guardara cada chunk crudo también daría byte por byte, y
el JSON no serviría. Así que `ningun_chunk_queda_sin_nombre` exige que no
sobreviva un solo chunk sin nombre en el volcado. Hoy no sobrevive ninguno.

## Por qué existe

Hasta el 2026-09-14 el conversor a SNES leía los binarios de RM2k **cada vez**,
con un lector propio en Python (`tools/lcf.py`), y el volcado a `data/*.json`
era un camino paralelo con su propio decodificador. Dos caminos para el mismo
formato, y los dos con los defaults escritos a mano.

Eso se pagó: el `max_hp` de un enemigo llegaba con 1 donde el formato dice 10,
porque **el binario no guarda un campo cuando vale el default** y el default
nuestro estaba mal. Un enemigo del juego moría de un golpe y nadie lo notó
hasta que taro lo jugó. En el volcado de Ditto son **24 los enemigos de ABL con
`max_hp` en 10, y ninguno con 1**.

La decisión que Ditto implementa: **los JSON son la fuente de verdad de las
ROMs**, y el formato de RM2k se lee **una sola vez**, acá.

## Los nombres no son nuestros

En el binario no hay nombres: el formato es *chunk-based* y cada campo es un
índice numérico —el HP máximo de un enemigo es el campo `0x04` de `Enemy`—. Los
nombres, los tipos y los defaults salen de **liblcf**, que los define en unas
tablas CSV (`generator/csv/`), y de ahí generamos nuestros structs.

Eso no es fidelidad —liblcf también es ingeniería inversa, hecha por EasyRPG—,
es **compatibilidad y cultura**: usar el vocabulario que el ecosistema ya usa
nos ahorra decisiones y hace nuestro volcado comparable con el de cualquier
otra herramienta.

## El código generado se versiona

`src/esquema/` sale de las tablas de liblcf, **pero está en git y es la fuente
de verdad de este proyecto**. Regenerar es una acción explícita:

    cargo xtask generar --liblcf /extras/ref/liblcf

Lo que eso produce es un diff que se lee y se revisa, no un paso oculto del
build. Si liblcf renombra un campo, el commit dice exactamente eso: un nombre
que cambia en el struct que corresponde.

Conceptualmente el CSV es una **dependencia** de Ditto: subirle la versión es
un cambio que se revisa como cualquier otro.

Lo que se genera son tres cosas, y las tres salen del CSV y de ningún criterio
nuestro: los structs y los enums, el `Default` de cada struct, y el códec
—qué campo es qué chunk, cómo se codifica, y si se emite cuando vale el
default—.

## El formato, y las cuatro cosas que hacen difícil la vuelta exacta

Un archivo es un encabezado —un largo y un nombre— y atrás un struct. Un struct
es una tira de chunks `(id, largo, bytes)` cerrada por un id 0. Un array de
structs es una cantidad y, por cada elemento, su id y su struct. Los enteros van
en **BER**: siete bits por byte, el bit alto dice que sigue.

Hasta ahí es mecánico. Lo que cuesta es esto:

**1. Un campo que vale su default no se escribe.** Salvo los que `fields.csv`
marca con `PersistIfDefault`, que se escriben siempre —hasta con largo 0—. O
sea que leer y escribir no son simétricos por construcción: son simétricos
porque el default que rellena al leer es el mismo que decide omitir al
escribir, y los dos salen de la misma tabla. Ése es todo el truco, y es por eso
que el default tiene que salir del CSV y no del criterio de nadie.

**2. El largo de algunos vectores va en su propio chunk.** `fields.csv` los
marca con una `t` y les da un índice aparte, siempre el anterior al del dato.
Hay dos variantes y el CSV las distingue por el tipo: `Count<...>` guarda la
**cantidad de elementos** y el resto guarda los **bytes**. Ditto los recalcula
al escribir en vez de guardarlos en el JSON, que es lo que hace liblcf, y sobre
ABL eso da el mismo número en los 330 archivos.

**3. Seis structs no son chunk-based.** `Parameters`, `Equipment`, `Rect`,
`EventCommand`, `MoveCommand` y `TreeMap` van posicionales adentro de su chunk:
el CSV les declara los campos pero no los índices, porque no los tienen. liblcf
los resuelve a mano y acá también (`src/crudos.rs`). Los dos que tienen forma
propia:

* la lista de comandos de un evento **no** guarda cuántos son: termina con
  cuatro bytes en cero;
* una ruta de movimiento se lee hasta que se acaba el chunk, y cuántos
  parámetros lleva cada comando depende del código —sólo cuatro de los 35
  llevan alguno—.

**4. `Database` y `Save` no llevan el 0 del final.** liblcf avisa que
ponérselo rompe el parser de RPG_RT. Todos los demás structs sí.

### Detalles que muerden

* **`Int32` va en BER, `Vector<Int32>` no.** Adentro de un vector cada entero
  son cuatro bytes crudos. Lo mismo `Vector<UInt32>` y los `Rect`.
* **`DBBitArray` no es un bitfield**: es un byte entero por valor. El que sí es
  un bitfield es un campo `*_Flags`, y ahí `flags.csv` da el orden de los bits
  —del menos significativo para arriba— y las banderas que sólo existen en 2003
  **no ocupan bit** en un archivo de 2000.
* **El texto es cp1252**, con los cinco bytes que la tabla deja sin definir
  (0x81, 0x8D, 0x8F, 0x90, 0x9D) mapeados a su control C1, así la tabla es una
  biyección y ningún byte se pierde. ABL tiene un par de mensajes en Shift-JIS
  que el autor nunca tocó: en el JSON salen como caracteres raros y vuelven al
  binario idénticos. Traducirlos bien pediría adivinar la codificación campo
  por campo y costaría la vuelta exacta, que es lo único que hace útil a esto.
* **El encabezado se guarda en el JSON** en vez de darlo por sentado: liblcf
  tiene una opción para conservarlo justamente porque hay juegos con el nombre
  cambiado.
* **Los enums tienen un `Otro(n)`.** Un valor que `enums.csv` no nombra se
  guarda como número y vuelve igual, en vez de caer al default y perderse.
* **Cada struct tiene un `desconocidos`** donde va cualquier chunk que el
  esquema no nombre, para que vuelva al archivo en su lugar. Sobre ABL está
  vacío en los 330 archivos, y hay una prueba que lo exige.

## Lo que falta

* **`.lsd`** —las partidas guardadas—. Los structs están generados; el códec
  no. No está en el corpus con el que se mide la ida y vuelta, y sin eso no
  habría con qué comprobarlo.
* **Los campos de RPG Maker 2003.** El generador los saltea entero: este port
  es de 2000. Un archivo de 2003 leído con Ditto guardaría esos chunks en
  `desconocidos` y volvería igual, pero no se los vería en el JSON.
* **Reemplazar a `tools/lcf.py` y al conversor.** Ditto todavía no reemplaza a
  nadie: convive. Que los JSON sean la fuente de verdad de las ROMs es la
  decisión, pero el cambio es otra vuelta.

## Lo que viene, y una decisión ya tomada

El emisor hacia la SNES. Hoy el conversor escribe **texto de assembler**: para
`demo-ciudad` son 148.686 líneas y 11 MB, de las cuales 145.885 son `.byte` y
`.word`. Eso se ensambla en unos 11 segundos por build.

Ese `.inc` mezcla tres cosas y sólo una puede volverse binario opaco:

1. **Datos** —tilemaps, tablas de NPCs, bytecode de eventos—: el 98% de las
   líneas, y candidatos a `.incbin`.
2. **Constantes** (`MAPA_STRIDE = 128`, `OP_TELEPORT = $02`), que `main.s` usa
   como símbolos y tienen que seguir siendo texto.
3. **Referencias a símbolos del ensamblador** (`.loword(fuente_pre0)`), que
   dependen de dónde caiga el código y sólo las resuelve `w65`.

**Y la decisión, de taro, que hay que respetar desde el primer día del emisor:
sale con un sourcemap.** Cuando el dato pasa a binario deja de poder leerse, y
hoy los comentarios del `.inc` son lo que permite depurar; pero además esa
información **ya se evapora al ensamblar**, así que el mapa vale por sí mismo y
no sólo como compensación.

Es un sourcemap en el sentido literal: del offset del `.bin` a "el campo
`trigger` de la página 2 del evento 12 del mapa 8". Con dos saltos y no uno
—JSON → `.bin` → offset de ROM—, y el segundo lo aporta `w65`, que ya escribe
un `.sym` con los símbolos del código: esto es su extensión a los datos.

Para qué sirve, más allá de leer un dato:

* que un caso de prueba en rojo diga **qué dato** falla y no sólo cuántos
  pixeles difieren. Los tres bugs de esta semana que salieron como "la pantalla
  se hizo basura" eran punteros leyendo donde no debían;
* traducir un puntero leído de la RAM a qué apunta, con el juego corriendo.

Nace con el emisor o no nace: el serializador sabe en qué offset escribió cada
campo **mientras lo escribe**, y reconstruirlo después es recorrer todo de
nuevo.
