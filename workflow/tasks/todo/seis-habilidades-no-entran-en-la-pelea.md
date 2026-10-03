---
name: "Seis habilidades no entran en la pelea"
description: "Con la fuente de ancho variable y espaciado 0, 6 de los 367 nombres de habilidades se pasan de su lugar en la pelea"
type: bug
---

Lo midió Tordo el 2026-10-03, contando a mano contra el tope de celdas, al
hacer la perilla del espaciado (`workflow/tasks/testing/el-espaciado-entre-letras.md`).
No se corrió en la ROM: falta ver cuáles son, qué se ve, y si el conversor
debería avisarlo.

## Lo que encontró Benteveo, el 2026-10-03

Desde `el-espaciado-sin-tocar-codigo` el conversor las nombra: un WARNING
en `conversor.log`, "skill names in the battle don't fit in 11 cells", con
cada nombre, sus pixeles y lo que se ve.

Lo que más cortaba no eran los pixeles sino las letras: el cartucho guardaba
11 letras de cada nombre, de cuando una letra ocupaba una celda, y eso
cortaba 41 de las habilidades de la pelea de ABL con 0. Ahora guarda 13
—lo que deja el registro de una fila de la capa de texto, `TL_RECORD`, con
las dos columnas de la lista— y quedan 26, todas de catorce letras o más.
Por pixeles no entran 3 con 0 (las seis de Tordo eran sobre las 367 de la
base; el cartucho lleva las que el grupo puede usar) y 27 con 2.

Para que entren todas haría falta más lugar en la fila: correr el guión y
el costo, o un registro más grande, que no entra en la RAM de la capa
(`FAR_TEXT_LAYER` tiene 62 bytes libres y harían falta 432 para ocho
letras más). No se hizo.
