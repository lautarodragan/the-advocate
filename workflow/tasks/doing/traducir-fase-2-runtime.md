---
name: "Traducir las herramientas, fase 2: el runtime y lo que cruza"
description: "Los símbolos, etiquetas y archivos del runtime al inglés, junto con lo que el conversor escribe en los .inc, las pruebas que leen símbolos por nombre, y los datos que quedaron en castellano"
type: refactor
assignee: Yacaré
---

Última área de la fase 2 de la traducción de `tools/` al inglés. Es la más
acoplada: el conversor escribe símbolos en los `.inc`, el runtime los usa
por nombre, y las pruebas de ABL leen los símbolos del runtime por nombre.

Hornero decidió (con la autorización de taro para decidir sin esperarlo)
que acá también van los datos que quedaron en castellano por ser la
interfaz entre dos programas: la línea `; Temas:` de `musicdata.inc` y quien
la lee, las claves de `rm2k.collect_npcs`, la clave `aire_de_medida` de
`techos.toml` (a mano, sin volver a medir), los comentarios que
`patches.py` escribe en `rom/parches/auto/` (con `just parches`), y las
variables `SIN_CACHE`, `TRAMA_PATRON` y `MODO_TRANSLUCIDO`. Lo que va a la
ROM y lo que es del juego no se toca: el `.sfc` sale igual.
