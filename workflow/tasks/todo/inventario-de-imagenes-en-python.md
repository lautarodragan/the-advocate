---
name: "Inventario: imágenes a tiles en Python"
description: "Qué conversiones de imagen a tiles siguen en Python y cuáles puede hacer Voodoo"
---

**Contar qué conversiones de imagen a tiles siguen hechas en Python**, y para
cada una, si Voodoo la puede hacer con su contrato de hoy: PNG indexado que
entra, tiles, paleta y tilemap que salen, sin decidir colores.

Voodoo ya convierte la capa de encima de los mapas, desde el paso 8c. Lo que
se sabe que sigue en Python: la escena de la pelea arma sus tiles en
`tools/port/escena.py`. Probablemente hay más —sprites, fuente, ventana,
título, animaciones—, y no están contadas.

Es sólo medición: por cada una, qué hace, si entra en el contrato de Voodoo, si
la ROM sale byte por byte igual pasándola por Voodoo, y cuánto Python se iría.
