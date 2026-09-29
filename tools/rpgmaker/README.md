# tools/rpgmaker/

El juego de RPG Maker 2000 como datos: el volcado a JSON de `rom/data/`, las
tablas del formato y las reglas de RM2k que el port tiene que imitar. Es la
capa de más abajo de `tools/` —ver `tools/README.md`—: no importa de ninguna
otra.

    lcf.py              el juego, leído del volcado de `rom/data/`
    event_codes.json    generado: los nombres de los comandos de evento
    event_codes.py      lo carga y lo expone como `EVENT_CODES`
    rm2k.py             las reglas del juego original: pasabilidad, autotiles,
                        animación del chipset, sprites de una página

## Acá no vive ninguna regla del formato, y eso fue una decisión

`lcf.py` lee `rom/data/`, que desde el 2026-09-20 es la **vista resuelta** que
emite Ditto: todos los campos escritos, con su default ya aplicado, y los enums
en número. Así que `campo` son tres líneas y un campo que falte es un
`KeyError` —que es lo que se quiere: quiere decir que `rom/data/` quedó viejo, no
que valga cero—.

Hasta ese día `rom/data/` era el volcado exacto —defaults omitidos, enums por
nombre— y para entenderlo hacían falta acá adentro un `ditto_schema.json` con
los defaults y las tablas de enums, y un `ditto_schema.py` que lo cargara. Eran
111 KB de esquema del formato viviendo del lado del que lee, y se fueron con
`just esquema` y con la prueba que los cuidaba. `ditto schema` sigue existiendo
del lado de Ditto, porque el volcado exacto se sigue emitiendo y leerlo lo
necesita; lo que ya no pasa es que el port lo consuma.

Lo único que sigue siendo criterio de acá es **adivinar la codificación de un
texto** —ver `lcf.texto`—, que es lo contrario de una regla del formato: el
formato no dice en qué juego de caracteres está una cadena.

Y una cosa más, que no viene de `rom/data/`: los 183 casos de `rom/pruebas/casos/*.json`
los escribimos nosotros, en la taquigrafía que se puede escribir a mano —el
comando por su nombre y sólo los campos que dicen algo—. Los lee
`lcf.comandos_escritos`, que no es `lcf.comandos`: el único dato de afuera que
usa es `event_codes.json`.

## Los códigos de comando de evento

`event_codes.json` es de número a nombre —`10110` es `ShowMessage`—, y
`event_codes.py` lo carga como `EVENT_CODES`. Era un diccionario escrito
adentro del `.py`; desde el 2026-09-20 es un archivo de datos, porque eso es lo
que siempre fue: 165 pares y ninguna lógica. Está commiteado a propósito: es lo
que hace que armar una ROM no necesite tener ninguna herramienta de Rust
instalada.

Sale del **enum `Code` de liblcf** —`src/generated/lcf/rpg/eventcommand.h`— y
de ningún otro lado. Ahí están los 165, contra los 128 de `enums.csv`: los 37
que faltan en la CSV son las extensiones, los `EasyRpg_*` y los `Maniac_*`, y
aunque RPG Maker 2000 no los escriba nunca no cuesta nada tenerlos nombrados.

De dónde salen importa porque ya se pagó: la primera versión del filtro que
decidía qué comandos podía acompañar un teletransporte sin dejar de ser una
puerta —filtro que ya no existe, porque las puertas cruzan por el intérprete
como cualquier otro evento— los puso de memoria, y **tres estaban mal**
—`PlayBGM` y `ChangeSpriteAssociation` entre ellos—. Ninguna comparación puede
ver ese error, porque una lista equivocada compila una ROM equivocada y la
golden es la captura de esa ROM.

Se rearma cuando se bumpea liblcf, que hasta hoy pasó cero veces, así que no
tiene receta: el comando entero es éste, y sale byte por byte igual al
commiteado.

    python3 - <clon de liblcf> > tools/rpgmaker/event_codes.json <<'PY'
    import json, re, sys
    fuente = sys.argv[1] + "/src/generated/lcf/rpg/eventcommand.h"
    cuerpo = re.search(r"enum class Code\s*\{(.*?)\n\s*\};",
                       open(fuente, encoding="utf-8").read(), re.S).group(1)
    codigos = {int(v): n for n, v in
               re.findall(r"(\w+)\s*=\s*(\d+)\s*(?:,|$)", cuerpo, re.M)}
    print(json.dumps({str(c): codigos[c] for c in sorted(codigos)}, indent=2))
    PY

Un código que la tabla no nombre se imprime como número pelado, que es lo que
ya hacía.

## `rm2k.py` es lo que el port tiene que imitar

Lo demás de acá lee un archivo; esto decide. La pasabilidad de una celda, cómo
se expanden los autotiles, cada cuántos cuadros avanza el agua: son las reglas
del juego original, leídas de EasyRPG, y la ROM las reimplementa en 65816. Si
las dos se separan, el juego camina distinto.

Por eso **lo que sólo usa una prueba no vive acá**: `puede_pasar` —si desde una
celda se puede dar un paso a la de al lado— se mudó a
`rom/pruebas/arnes/recorrido.py` el 2026-09-20, que era su único llamador. El rumbo
es que en Python quede lo de las pruebas y el resto se vaya a Rust.
