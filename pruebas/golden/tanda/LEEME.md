# Lo que la referencia decía el 2026-09-15

Son los 1.017 artefactos que `tools/snes_expect.py` produce para los 170 casos
de `rom/hitos.txt`, congelados: 466 imágenes esperadas, 535 máscaras de líneas
a excluir y 16 planes.

**Por qué existen.** Hasta ahora cada caso de la tanda corría la referencia y
comparaba la ROM contra lo que ésta acababa de calcular. Eso tiene un agujero
que este repo ya pagó dos veces: el conversor alimenta **los dos lados**, así
que un error suyo mueve la ROM y la referencia juntas y la comparación da cero
—pasó con los códigos de comando de las puertas y con la prioridad de OAM—.
Contra un archivo congelado, ese cambio se ve.

**Cómo se hicieron.** Corriendo la tanda con los 170 casos en verde y copiando
lo que la referencia produjo. No hubo que bendecir nada a mano: **es
exactamente lo que la tanda ya aceptaba**. Y se verificó re-derivándolos: una
segunda corrida completa dio los 1.017 byte por byte iguales, así que la
referencia es determinista y el congelado es fiel.

**La regla, que es lo único que hace que esto sirva.** Cambiar uno de estos
archivos tiene que ser un **acto deliberado**: va a git, se mira, y se explica
en el commit por qué el render cambió. Si regenerarlos fuera automático —o si
la tanda lo hiciera sola— dejarían de cumplir ninguna función, que es lo mismo
que pasa con cualquier snapshot testing.

Los nombres son únicos entre casos: se comprobó sobre los 1.017 que ninguno se
repite, así que la clave es el nombre del archivo y no el número de caso, que
es posicional y se correría al insertar uno.
