---
name: "EraseEvent de verdad"
description: "Lo único que traba el camino al día siguiente: un EraseEvent en el mapa 150 que tiene que borrar el evento de verdad (el salto es dentro del mismo mapa), y otro en el común 36 que RM2k no hace nada y alcanza con aceptarlo"
type: feature
agents: [Aguará, Hurón]
assignee: Hurón
---

Del estudio de Aguará, `docs/research/2026-10-05-los-comandos-que-faltan.md`; lo midió `rm2k-snes-events culprits`. taro, el 2026-10-05: dejarlas en todo, sin lanzar todavía. Es lo primero que recomienda: uno chico y uno mediano.

2026-10-06, Hornero: en Desert Nightmare `EraseEvent` es lo que más páginas
deja afuera solo —127 de las 157 que lo usan, medido con `culprits
--every-map`—, y es el sospechoso de que su intro se congele: una página
automática que se borra sola, si no compila, no deja seguir la escena. El
Dorado tiene 3. Se hace entero: borrar el evento hasta que se recargue el
mapa, en mapas y en la cantera de ABL; el del común sigue sin hacer nada.
taro: "vamos con esos dos en paralelo", con Sonnet.
