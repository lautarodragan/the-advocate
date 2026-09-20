# El juego en JSON

Esto es *A Blurred Line* volcado de los formatos binarios de RPG Maker 2000 a
JSON y a texto plano. Lo escribe **Ditto** (`just datos`), y **es lo que lee el
port**: `tools/rpgmaker/lcf.py` sale de acá y de ningún otro lado, así que el conversor,
la referencia en Python y las pruebas están todos mirando estos archivos y no
los `.lmu`. El porqué de esa decisión está en `DITTO.md`, en la raíz.

    ditto.json           la versión del volcado, cuál de las dos vistas es, y
                         el header de cada archivo
    maps.json            el árbol de mapas, los encuentros y dónde arranca la partida
    maps/Map0001.json    el mapa: chipset, parallax y los eventos con sus scripts
    maps/Map0001.tiles   sus dos capas de tiles, una fila por línea
    db/actors.json       el RPG_RT.ldb, una sección por archivo (15 de ellas)
    db/database.json     lo que queda de la base: su `version`

Se regenera entero en cualquier momento con `just datos`, que vacía `maps/` y
`db/` y los vuelve a escribir. **Es derivado**: si algo de acá no coincide con
los `.lmu`, el que está mal es esto. Y el que manda después de regenerar es el
`git diff`: si el juego no cambió, tiene que dar vacío.

## Esto es la vista resuelta, y hay otra

`just datos` escribe **dos** árboles con la misma forma, en la misma corrida.
Éste es la **vista resuelta**, y el otro —`rom/build/ditto-exacto/`, que no se
versiona— es el **volcado exacto**. Cuál es cuál lo dice `ditto.json`.

La diferencia es qué tanto hay que saber para leerlo:

* acá **están todos los campos**, con su default ya aplicado, y **los enums son
  números**. Leer es leer: `datos["max_hp"]` y listo.
* el exacto tiene la forma del binario —un campo que vale su default no se
  escribe, y un enum va por su nombre: `"auto_start"`, `"same"`,
  `"ShowMessage"`—. Es un 37% más chico, es el único que `ditto pack` puede
  volver a escribir, y es el que hay que mirar para ver el juego **con los
  nombres puestos**. Leerlo pide el esquema del formato, que publica
  `ditto schema`.

Hasta el 2026-09-20 el versionado era el exacto, y `tools/rpgmaker/lcf.py`
llevaba el esquema al lado para poder entenderlo. Eso era el formato viviendo
del lado del que lee; hoy lo resuelve el que lo tiene. Perder los nombres de acá
es aceptado a propósito y el camino de vuelta está pensado: si el proceso entero
termina en Rust, Ditto pasa a ser una lib que exporta sus structs con sus
definiciones de serde y los nombres vuelven sin código ni JSON de más.

Que las dos vistas salgan de la misma corrida no es comodidad: generadas por
separado, es cuestión de tiempo que una sea de una corrida y la otra de otra, y
compararlas deje de significar algo.

## Por qué está en el repo si es derivado

Por dos razones distintas, y la segunda es nueva.

**Para leerlo.** Un `.lmu` es un formato binario con chunks de largo variable:
no se puede mirar, no se puede buscar con grep, y un `git diff` de dos
versiones no dice nada. En JSON sí. Cuando hubo que averiguar qué comandos
tiene la cinemática de apertura, o qué actores mete un `ChangePartyMembers`, la
respuesta salió de acá.

**Y porque es la fuente de verdad del build.** El formato de RM2k se lee **una
sola vez**, en Ditto; el resto del toolchain consume esto. Antes había dos
decodificadores —el volcado y el lector del conversor—, cada uno con los
defaults escritos a mano, y se pagó: el `max_hp` de un enemigo llegaba con 1
donde el formato dice 10, y el DirtShadow moría de un golpe.

## Lo que hay que saber para leerlo

**No hay nada que saber: están todos los campos.** Un `max_hp` que el binario
no guardaba porque valía el default del formato acá está escrito en 10, que es
lo que vale. Ése fue el bug que originó a Ditto —llegaba 1, y el DirtShadow
moría de un golpe—, y hoy no hay tabla que consultar ni default que aplicar:
quien lee, lee.

**Los enums son números**, que es lo que el port quiere. El nombre —`"same"`,
`"auto_start"`, `"ShowMessage"`— está en el volcado exacto, que es donde uno va
a mirar el juego.

**Los tiles van aparte y en texto**, una fila por línea, porque son lo único
voluminoso: meterlos en el JSON haría los diffs ilegibles justo donde más
importa mirarlos, y así un tile cambiado cae en la línea de su fila y en la
columna de su celda.

**El texto es cp1252**, y un par de mensajes que el autor nunca tocó siguen en
Shift-JIS: en el JSON salen como caracteres raros y vuelven al binario
idénticos. Decodificarlos adivinando le costaría a Ditto la vuelta exacta, que
es lo único que lo hace útil, así que el que adivina es `tools/rpgmaker/lcf.py`.

## De dónde salen los nombres

De **liblcf**, que es donde EasyRPG declara el formato en un juego de tablas
CSV. `tools/ditto/src/schema/` se genera de ahí y está versionado, y de ahí
salen tanto los nombres del volcado exacto como los defaults y los números que
están escritos acá. Ningún número de este directorio se escribió de memoria: ya
pasó una vez que tres códigos de comando se pusieron así y estaban mal, y de
ahí salió la regla.

## Esto no es de A Blurred Line

Ditto lee RPG Maker 2000 y no sabe nada de este juego ni de este port: sirve
para cualquier juego de RM2k cambiándole el directorio. Y la vuelta es exacta
—`ditto pack` rearma los 330 archivos byte por byte—, así que este árbol no es
sólo una lectura: es el juego.
