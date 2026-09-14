# Ditto

Lee los archivos de RPG Maker 2000 —`.ldb`, `.lmu`, `.lmt`, `.lsd`— y los
vuelca a JSON. Se llama así porque hace una sola cosa: copiar la forma de otro.

## Por qué existe

Hasta el 2026-09-14 el conversor a SNES leía los binarios de RM2k **cada vez**,
con un lector propio en Python (`tools/lcf.py`), y el volcado a `data/*.json`
era un camino paralelo con su propio decodificador. Dos caminos para el mismo
formato, y los dos con los defaults escritos a mano.

Eso se pagó: el `max_hp` de un enemigo llegaba con 1 donde el formato dice 10,
porque **el binario no guarda un campo cuando vale el default** y el default
nuestro estaba mal. Un enemigo del juego moría de un golpe y nadie lo notó
hasta que taro lo jugó.

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
