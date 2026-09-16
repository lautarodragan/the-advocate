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
con un lector propio en Python —el `tools/lcf.py` de entonces—, y el volcado a
`data/*.json`
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

**Ya pasó.** Desde el 2026-09-14, `data/` es el volcado de Ditto y
`tools/lcf.py` lo lee: el conversor, la referencia en Python y las pruebas
están todas mirando esos archivos, y ningún `.lmu` se abre para armar una ROM.
Los tres pasos, decididos con taro:

1. Que Ditto **omita los defaults** al serializar y emita **la estructura de
   `data/`**. Hecho; es la sección de abajo.
2. **Volcar los JSON una vez y versionarlos.** Hecho: `just datos` escribe
   `data/`, y el volcado que ganó fue el de Ditto —lo eligió taro—.
3. Que **`tools/lcf.py` los lea**, con sus 51 consumidores intactos. Hecho, y
   los 51 quedaron intactos.

### Paso 3: cómo quedó `tools/lcf.py`, y qué costó

Las clases —`Map`, `Database`, `TreeMap` y todo lo que cuelga— tienen los
mismos atributos que antes, con los mismos tipos, y siguen recibiendo la ruta a
un `.lmu` o a un `RPG_RT.ldb`. De esa ruta ahora sólo se usa **el nombre**, y
el directorio sólo si tiene adentro un volcado propio (un `ditto.json`): así un
juego que no es éste se lee pasándole su propio volcado, y `--game-dir` sigue
queriendo decir de dónde salen los PNG y los MIDI, que no se mudaron.

**Lo que sí cambió de fondo: los defaults ya no se escriben en `lcf.py`.** El
JSON omite todo campo que valga el suyo, la misma regla que el binario, así que
leerlo es saber qué vale un campo ausente. Eso sale de `tools/ditto_schema.py`,
que **se genera desde el esquema de Ditto** —`tools/gen_ditto_schema.py`— y
trae, por campo: su chunk, su default, su enum si tiene, si el formato lo
escribe aunque valga el default (`PersistIfDefault`) y qué struct lleva
adentro. Es la misma idea con la que se generaba el esquema del lector viejo,
con la fuente corrida un lugar: liblcf genera el esquema de Ditto y Ditto genera
éste.

Los enums vienen por nombre —`"same"`, `"auto_start"`, `"ShowMessage"`— y
vuelven al número con las tablas de ese mismo archivo.

**Tres consumidores tuvieron que cambiar, y ninguno de los 51.** Los que
cambiaron no llamaban a `lcf.Map`: metían la mano **por debajo** de la capa, a
los chunks crudos de `db.fields`, que ya no existen porque no hay binario.

* `tools/eventos.py` y `tools/destraba.py` armaban los eventos comunes leyendo
  el chunk 0x19 de la base y el 0x16 de cada uno; ahora es `db.common_events`,
  que la capa arma.
* `pruebas/test_encuentros.py` leía los terrenos y el `terrain_set` de las
  tropas igual; ahora salen de `db.decode()`.

`db.terminos` —los términos por número de chunk, que es como los pide la
tienda— **no** cambió: la capa lo sigue dando en bytes.

### Y el único dato del juego que cambió

**Uno, medido, y es un arreglo.** `Learning.skill_id` —qué habilidad aprende un
actor en tal nivel— vale **1** cuando el archivo no lo trae, que es lo que dice
`fields.csv`; en `lcf.py` estaba escrito 0. Le pasa a un solo actor, **Alex, el
1**, que es del RTP y este juego no usa: aprende la habilidad 1 en el nivel 1,
y antes eso llegaba como la 0 y se caía. Son **dos bytes** en la tabla
`sabe_hab`.

Está medido con el criterio que pidió taro: se armaron `demo-ciudad` y
`demo-titulo` antes y después. Con ese default puesto de vuelta en 0, el
`mapdata.inc` de `demo-ciudad` sale **byte por byte idéntico** al de antes
—mismo md5—; con el default del formato, la única diferencia en las 148.686
líneas es esa tabla. Así que la migración no movió ningún otro dato.

### Lo que la mudanza destapó

**Una prueba que no medía nada.** `test_ninguna_tropa_filtra_por_terreno` leía
el `terrain_set` del chunk **0x13** de la base, que es `animations` y no
`troops` —el de las tropas es el 0x0F—: preguntaba por un chunk que ninguna
animación tiene, siempre daba vacío y siempre pasaba. Con los JSON, que se leen
por nombre, apareció lo que había: **doce de las tropas que salen en encuentros
al azar sí filtran por terreno**.

La simplificación del port se sostiene igual, pero por otra razón que la que
decía la prueba: ninguna de esas doce excluye un terreno que su mapa **pise de
verdad** —medido mapa por mapa y celda por celda; los mapas con encuentros
pisan el terreno 1 casi siempre, y el 12, el 13, el 14 y los del 15 al 25 en
seis mapas—. La prueba ahora mide eso, que es lo que hay que cuidar.

## Paso 1: el volcado por directorios, y cuánto pesa

`ditto unpack <juego> <dir>` escribe el árbol y `ditto pack <dir> <juego>` lo
vuelve a armar. La estructura es la que pidió taro, que es la que ya tiene
`data/`: `maps.json` con el árbol, un archivo por mapa en `maps/`, las capas de
tiles aparte en `maps/Map0001.tiles`, y las 15 secciones de la base en `db/`.
El porqué de cada decisión está en `ditto/README.md`, en inglés; acá va lo que
es de este repo.

Los pesos, sobre el mismo juego:

    17.569.229   el .ldb como un solo JSON, omitiendo defaults
    25.675.888   el .ldb como un solo JSON, como estaba antes
    19.445.521   el volcado de Ditto entero, 674 archivos: lo que hoy es data/
    16.121.259   el volcado que reemplazó, el de tools/export_json.py

O sea: omitir los defaults saca **un tercio** del `.ldb` suelto, y `data/` pesa
**21% más** que el volcado de Python que reemplazó. La diferencia no es grasa:
el de Python era una *lectura* del juego —un comando de evento en una línea, y
los campos que al port no le sirven no estaban—, y el de Ditto tiene que poder
volver a escribir el binario, así que lleva todo. Un mapa concreto, el 8, pasó
de 439.222 bytes como un JSON suelto a 99.915 de JSON más 67.902 de `.tiles`.

Ese 21% se pagó a propósito. El volcado viejo —`tools/export_json.py`, con su
lector de binarios `lcf_bin.py` y el esquema que `gen_schema.py` sacaba de
liblcf— **se borró el 2026-09-14**, 3.133 líneas: quedó sin dueño el día que
`data/` pasó a ser el volcado de Ditto, y lo único que aportaba era esa lectura
más corta. Tener dos lectores del mismo formato, cada uno con sus defaults
escritos a mano, es exactamente el bug que abre este archivo.

## El corpus

Ditto se mide contra el juego original, que adentro del contenedor está en
`/extras/abl-rm` —lo mismo que lee `GAME_DIR` en el resto del repo—. Ditto no
lo sabe: se lo pasa el justfile.

    just ditto-pruebas          # una muestra de mapas, un segundo
    just ditto-vuelta-entera    # los 330, con el número impreso

Las dos recetas exportan `DITTO_CORPUS=/extras/abl-rm`. Corrido a mano sin esa
variable, las pruebas que necesitan el juego **se saltean con un mensaje** en
vez de fallar; las que no lo necesitan —los defaults del esquema, y el corpus
sintético— corren siempre.

### El corpus que Ditto se escribe solo

`ditto/tests/synthetic.rs` no necesita juego: arma los archivos él mismo. Está
para que un clon sin corpus —el día que Ditto viva en su propio repo— mida algo
de verdad en vez de saltear todo.

La mitad de ese archivo **no es una vuelta ida y vuelta**, y es a propósito:
una vuelta sólo prueba que el lector y el escritor se entienden entre ellos, y
si los dos se equivocan igual la comparación da cero —la regla de `AGENTS.md`,
otra vez—. Así que esas pruebas escriben **los bytes a mano** —un entero BER y
los límites donde crece, un chunk `(id, largo, cuerpo)`, un mapa entero byte por
byte— y afirman qué valor es cada uno. Un lector que se inventara el formato
las rompe.

La otra mitad arma documentos con lo que un juego real casi no tiene: los
extremos del BER, texto en el rango donde cp1252 se separa de Latin-1, vectores
vacíos al lado de llenos, un campo puesto en su default a propósito, y un chunk
que el esquema no nombra.

Los dos corpus contestan preguntas distintas y ninguno reemplaza al otro: el
sintético prueba que la implementación es consistente; el juego real prueba que
el formato es el que el RPG Maker escribe de verdad. Un proyecto recién creado
con el editor vale más acá que un juego terminado, porque tiene casi todo en el
valor de fábrica, que es justo de lo que se trata la regla de omisión.

De paso salió un límite que no sabíamos: **un comando de código 0 termina la
lista**. La lista de comandos de un evento no lleva cuenta —cierra con cuatro
bytes en cero, que es un comando de código 0—, así que un JSON editado a mano
que meta uno en el medio **pierde todo lo que sigue**, y en silencio, porque el
archivo que sale es válido. Está fijado en
`a_command_of_code_zero_ends_the_list`.

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
   dependen de dónde caiga el código y sólo las resuelve `ld65`.

**Y la decisión, de taro, que hay que respetar desde el primer día del emisor:
sale con un sourcemap.** Cuando el dato pasa a binario deja de poder leerse, y
hoy los comentarios del `.inc` son lo que permite depurar; pero además esa
información **ya se evapora al ensamblar**, así que el mapa vale por sí mismo y
no sólo como compensación.

Es un sourcemap en el sentido literal: del offset del `.bin` a "el campo
`trigger` de la página 2 del evento 12 del mapa 8". Con dos saltos y no uno
—JSON → `.bin` → offset de ROM—, y el segundo lo aporta `tools/ensamblar.py`,
que ya escribe un `.sym` con los símbolos del código: esto es su extensión a
los datos.

Para qué sirve, más allá de leer un dato:

* que un caso de prueba en rojo diga **qué dato** falla y no sólo cuántos
  pixeles difieren. Los tres bugs de esa semana que salieron como "la pantalla
  se hizo basura" eran punteros leyendo donde no debían;
* traducir un puntero leído de la RAM a qué apunta, con el juego corriendo.

Nace con el emisor o no nace: el serializador sabe en qué offset escribió cada
campo **mientras lo escribe**, y reconstruirlo después es recorrer todo de
nuevo.
