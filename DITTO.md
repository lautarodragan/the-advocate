# Ditto en este repo

`ditto/` es una herramienta que lee los archivos de RPG Maker 2000 —`.ldb`,
`.lmu`, `.lmt`—, los vuelca a JSON y los **vuelve a escribir desde el JSON**,
byte por byte. Es un **proyecto independiente**: está escrito en inglés, no
sabe nada de este port, y sus pruebas corren contra cualquier juego de RM2k que
se le pase en `DITTO_CORPUS`. Cómo funciona y qué trampas tiene el formato está
en `ditto/README.md`, también en inglés.

Este archivo es la otra mitad: **por qué existe acá**, qué decisión de este
repo implementa, y en qué estado está esa decisión. Si Ditto se mudara a su
propio repositorio, lo de acá se quedaría y lo de allá se iría con él.

## El bug que lo originó

Hasta el 2026-09-14 el conversor a SNES leía los binarios de RM2k **cada vez**,
con un lector propio en Python (`tools/lcf.py`), y el volcado a `data/*.json`
era un camino paralelo con su propio decodificador. Dos caminos para el mismo
formato, y los dos con los defaults escritos a mano.

Eso se pagó: el `max_hp` de un enemigo llegaba con 1 donde el formato dice 10,
porque **el binario no guarda un campo cuando vale el default** y el default
nuestro estaba mal. Un enemigo del juego moría de un golpe y nadie lo notó
hasta que taro lo jugó. En el volcado de Ditto son **24 los enemigos de ABL con
`max_hp` en 10, y ninguno con 1**.

Es el caso de manual de la regla de este repo: los dos lados se equivocaban
igual, así que no había con qué comparar. La respuesta fue sacar el default del
criterio de nadie y ponerlo donde lo declara liblcf, una sola vez.

## La decisión: los JSON son la fuente de verdad de las ROMs

El formato de RM2k se lee **una sola vez**, en Ditto, y de ahí sale el JSON que
el resto del toolchain consume. No se lee el binario en cada build ni se
mantienen dos decodificadores.

**Todavía no pasó.** Ditto no reemplaza a nadie: convive con `tools/lcf.py` y
con el conversor, que siguen leyendo los binarios. La decisión está tomada y el
cambio son tres pasos, decididos con taro:

1. Que Ditto **omita los defaults** al serializar y emita **la estructura de
   `data/`**. Hecho el 2026-09-14; es lo que cuenta la sección de abajo.
2. **Volcar los JSON una vez y versionarlos.**
3. Que **`tools/lcf.py` los lea**, con sus 51 consumidores intactos.

## Paso 1: el volcado por directorios, y cuánto pesa

`ditto unpack <juego> <dir>` escribe el árbol y `ditto pack <dir> <juego>` lo
vuelve a armar. La estructura es la que pidió taro, que es la que ya tiene
`data/`: `maps.json` con el árbol, un archivo por mapa en `maps/`, las capas de
tiles aparte en `maps/Map0001.tiles`, y las 15 secciones de la base en `db/`.
El porqué de cada decisión está en `ditto/README.md`, en inglés; acá va lo que
es de este repo.

**Ditto no reemplaza a `tools/export_json.py` en esta vuelta, y no escribió una
sola línea en `data/`.** Cuál de los dos gana es el paso 2 y lo decide taro con
los dos volcados a la vista. Lo que sí se puede comparar ya son los números,
sobre el mismo juego:

    17.569.229   el .ldb como un solo JSON, omitiendo defaults
    25.675.888   el .ldb como un solo JSON, como estaba antes
    19.506.490   el volcado de Ditto entero, 674 archivos
    16.121.259   el volcado de hoy, el de tools/export_json.py

O sea: omitir los defaults saca **un tercio** del `.ldb` suelto, y el volcado
completo de Ditto queda **21% por encima** del de hoy. La diferencia no es
grasa: el de Python es una *lectura* del juego —un comando de evento entra en
una línea, y los campos que al port no le sirven no están—, y el de Ditto tiene
que poder volver a escribir el binario, así que lleva todo. Un mapa concreto,
el 8, pasó de 439.222 bytes como un JSON suelto a 99.915 de JSON más 67.902 de
`.tiles`.

**Lo que hay que mirar al elegir en el paso 2** es que los dos volcados no
dicen lo mismo: `data/maps.json` de hoy trae `file`, `size` y nombres que el
conversor usa, y el de Ditto trae el `.lmt` tal cual. El paso 3 —que
`tools/lcf.py` lea JSON— es el que va a decir cuál de las dos formas le sirve a
los 51 consumidores.

## El corpus

Ditto se mide contra el juego original, que adentro del contenedor está en
`/extras/abl-rm` —lo mismo que lee `GAME_DIR` en el resto del repo—. Ditto no
lo sabe: se lo pasa el justfile.

    just ditto-pruebas          # una muestra de mapas, un segundo
    just ditto-vuelta-entera    # los 330, con el número impreso

Las dos recetas exportan `DITTO_CORPUS=/extras/abl-rm`. Corrido a mano sin esa
variable, las pruebas que necesitan el juego **se saltean con un mensaje** en
vez de fallar; las que no lo necesitan —los defaults del esquema— corren
siempre.

Al 2026-09-14 la vuelta da **330 de 330** archivos idénticos: los 328 `.lmu`,
el `RPG_RT.ldb` y el `RPG_RT.lmt`. Y desde el volcado por directorios, otros
**330 de 330**: `unpack` el juego entero, `pack` de vuelta, y los mismos 330
archivos byte por byte. Ésa es la prueba de que la estructura no perdió nada, y
está en `ditto/tests/directory_dump.rs`.

Y el número de la otra mitad, que es el que hace que ese 330 no sea suerte:
sobre los 328 mapas, RPG Maker 2000 **omitió 8.461 campos** de 10.824 posibles
por valer su default. Que vuelvan iguales es la prueba de que el editor sigue
la misma regla que Ditto. El límite conocido —un chunk escrito a mano con su
valor default se pierde, son 3 bytes— está medido en `ditto/tests/omission.rs`
y anotado en `ditto/README.md` con la salida barata por si alguna vez aparece
una tercera herramienta que lo dispare. No se implementó: ni RPG Maker ni
EasyRPG lo disparan.

## Lo que viene, y una decisión ya tomada: el emisor hacia la SNES

Hoy el conversor escribe **texto de assembler**: para `demo-ciudad` son 148.686
líneas y 11 MB, de las cuales 145.885 son `.byte` y `.word`. Eso se ensambla en
unos 11 segundos por build.

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
  pixeles difieren. Los tres bugs de esa semana que salieron como "la pantalla
  se hizo basura" eran punteros leyendo donde no debían;
* traducir un puntero leído de la RAM a qué apunta, con el juego corriendo.

Nace con el emisor o no nace: el serializador sabe en qué offset escribió cada
campo **mientras lo escribe**, y reconstruirlo después es recorrer todo de
nuevo.
