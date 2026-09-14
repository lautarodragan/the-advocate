# El juego en JSON

Esto es *A Blurred Line* volcado de los formatos binarios de RPG Maker 2000 a
JSON y a texto plano. Lo escribe **Ditto** (`just datos`), y **es lo que lee el
port**: `tools/lcf.py` sale de acá y de ningún otro lado, así que el conversor,
la referencia en Python y las pruebas están todos mirando estos archivos y no
los `.lmu`. El porqué de esa decisión está en `DITTO.md`, en la raíz.

    ditto.json           la versión del formato del volcado y el header de cada archivo
    maps.json            el árbol de mapas, los encuentros y dónde arranca la partida
    maps/Map0001.json    el mapa: chipset, parallax y los eventos con sus scripts
    maps/Map0001.tiles   sus dos capas de tiles, una fila por línea
    db/actors.json       el RPG_RT.ldb, una sección por archivo (15 de ellas)
    db/database.json     lo que queda de la base: su `version`

Se regenera entero en cualquier momento con `just datos`, que vacía `maps/` y
`db/` y los vuelve a escribir. **Es derivado**: si algo de acá no coincide con
los `.lmu`, el que está mal es esto. Y el que manda después de regenerar es el
`git diff`: si el juego no cambió, tiene que dar vacío.

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

**Un campo que no está vale su default.** El binario no guarda un campo que
valga el valor por omisión del formato, y el JSON hace exactamente lo mismo,
por la misma razón y con la misma tabla. Así que "`max_hp` no aparece" no
quiere decir 0: quiere decir 10. Los defaults están en
`tools/ditto_schema.py`, generado desde el esquema de Ditto, que a su vez sale
de liblcf.

**Los enums van por nombre.** `"trigger": "auto_start"`, `"layer": "same"`,
`"code": "ShowMessage"`. Un número no le dice nada a nadie; el nombre sí, y es
el de liblcf. `tools/lcf.py` los vuelve al número que espera el port.

**Los tiles van aparte y en texto**, una fila por línea, porque son lo único
voluminoso: meterlos en el JSON haría los diffs ilegibles justo donde más
importa mirarlos, y así un tile cambiado cae en la línea de su fila y en la
columna de su celda.

**El texto es cp1252**, y un par de mensajes que el autor nunca tocó siguen en
Shift-JIS: en el JSON salen como caracteres raros y vuelven al binario
idénticos. Decodificarlos adivinando le costaría a Ditto la vuelta exacta, que
es lo único que lo hace útil, así que el que adivina es `tools/lcf.py`.

## De dónde salen los nombres

De **liblcf**, que es donde EasyRPG declara el formato en un juego de tablas
CSV. `ditto/src/schema/` se genera de ahí y está en git; `tools/ditto_schema.py`
se genera de eso. Ningún número de este directorio se escribió de memoria: ya
pasó una vez que tres códigos de comando se pusieron así y estaban mal, y de
ahí salió la regla.

## Esto no es de A Blurred Line

Ditto lee RPG Maker 2000 y no sabe nada de este juego ni de este port: sirve
para cualquier juego de RM2k cambiándole el directorio. Y la vuelta es exacta
—`ditto pack` rearma los 330 archivos byte por byte—, así que este árbol no es
sólo una lectura: es el juego.
