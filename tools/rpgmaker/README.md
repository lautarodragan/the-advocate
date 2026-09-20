# tools/rpgmaker/

El juego de RPG Maker 2000 como datos: el volcado a JSON de `data/`, las
tablas del formato y las reglas de RM2k que el port tiene que imitar. Es la
capa de más abajo de `tools/` —ver `tools/README.md`—: no importa de ninguna
otra.

    lcf.py              el juego, leído del volcado de `data/`
    ditto_schema.json   generado: el esquema del formato, que publica Ditto
    ditto_schema.py     lo carga y lo expone como `CAMPOS` y `ENUMS`
    event_codes.json    generado: los nombres de los comandos de evento
    event_codes.py      lo carga y lo expone como `EVENT_CODES`
    rm2k.py             las reglas del juego original: pasabilidad, autotiles,
                        animación del chipset, sprites de una página

## Los dos JSON no se editan a mano

Los dos son datos de otro —del formato, no de este juego—, y los dos están
commiteados a propósito: es lo que hace que armar una ROM no necesite tener
ninguna herramienta de Rust instalada.

    just esquema        ditto_schema.json, desde `ditto schema`
    (ver abajo)         event_codes.json, desde liblcf

`ditto_schema.json` es lo que hace falta para leer `data/`, y hace falta porque
el volcado **omite todo campo que valga su default** —la misma regla que el
binario, y lo que lo hace un tercio más chico— y guarda **los enums por
nombre**: `"same"`, `"auto_start"`, `"ShowMessage"`. Un campo ausente no vale
cero, vale lo que dice el formato; y `"auto_start"` es un 3 que sólo sabe la
tabla.

Ese dato lo tiene Ditto, que lo saca de las CSV de liblcf —`fields.csv`,
`enums.csv`, `constants.csv`—, y **lo publica**: `ditto schema` lo escribe como
JSON y acá se lee. Hasta el 2026-09-20 era al revés: un `gen_ditto_schema.py`
le sacaba los defaults y las tablas al código de Rust de Ditto **con
expresiones regulares**, para escribir 1.688 líneas de Python. Funcionaba, y de
paso leía `9 * 256` como 9 en cinco campos de los archivos de guardado, que
este port no lee. El que tiene el dato lo publica; el que lo necesita no lo
scrapea. Es el mismo trato que `tools/protocol/` tiene con los dos bytecodes.

Que el JSON no se haya quedado viejo lo cobra
`pruebas/herramientas/test_esquema.py`, que vuelve a correr `ditto schema` y
exige que no cambie nada.

## Los códigos de comando de evento

`event_codes.json` es de número a nombre —`10110` es `ShowMessage`—, y
`event_codes.py` lo carga como `EVENT_CODES`. Era un diccionario escrito
adentro del `.py`; desde el 2026-09-20 es un archivo de datos, porque eso es lo
que siempre fue: 165 pares y ninguna lógica.

Sale del **enum `Code` de liblcf** —`src/generated/lcf/rpg/eventcommand.h`— y
de ningún otro lado. Ahí están los 165, contra los 128 de `enums.csv`: los 37
que faltan en la CSV son las extensiones, los `EasyRpg_*` y los `Maniac_*`, y
aunque RPG Maker 2000 no los escriba nunca no cuesta nada tenerlos nombrados.

De dónde salen importa porque ya se pagó: la primera versión del filtro que
decide qué comandos puede acompañar un teletransporte sin dejar de ser una
puerta los puso de memoria, y **tres estaban mal** —`PlayBGM` y
`ChangeSpriteAssociation` entre ellos—. Ninguna comparación puede ver ese
error, porque una lista equivocada compila una ROM equivocada y la golden es la
captura de esa ROM.

Se rearma cuando se bumpea liblcf, que hasta hoy pasó cero veces, así que no
tiene receta: el comando entero es éste, y sale byte por byte igual al
commiteado.

    python3 - /extras/ref/liblcf > tools/rpgmaker/event_codes.json <<'PY'
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
