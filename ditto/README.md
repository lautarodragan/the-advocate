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
