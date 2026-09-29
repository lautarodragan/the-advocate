---
name: "El mapa de las herramientas de Python"
description: "Grafo de dependencias, responsabilidades y qué es agnóstico a ABL en los .py de tools/, con un plan por partes para separar herramientas y juego en dos repos"
type: docs
assignee: Quebracho
---

De taro, el 2026-09-28: "me gustaría retomar el refactor de las
herramientas hechas en python. [...] Me gustaría entender el grafo de
dependencias entre los distintos archivos python, qué responsabilidad tiene
cada cosa, y qué es agnóstico al ABL y qué no. Uno de los siguientes pasos
que quiero encarar es dividir el repo en dos: las herramientas por un lado,
todo agnóstico a cualquier juego, y un repo dedicado a A Blurred Line. Ese
proyecto no va a ser completamente trivial y lo tendremos que encarar por
partes. Este plan nos va a ayudar a ello."

Es investigación y plan, no código. El resultado es un research en
`docs/research/`.

Relacionadas: `todo/las-responsabilidades-de-snes-convert.md` y
`wishlist/un-juego-golden-y-dos-repos.md`.
