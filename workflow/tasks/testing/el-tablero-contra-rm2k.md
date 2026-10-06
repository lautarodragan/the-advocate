---
name: "El tablero contra RM2k entero"
description: "Un artifact con el estado del motor relativo a todo lo que RM2k tiene: comandos de eventos, pestañas de la base de datos, tipos de asset, pantallas; cada uno hecho, parcial, degradado o faltante"
type: feature
agents: [Aguará]
assignee: taro
---

taro, el 2026-10-06: verlo "relativo al proyecto 100% completo", sin
perderse en el detalle. Aguará arma el inventario —sale del código, no de
memoria— y Hornero arma y publica la página. Es una foto con fecha y commit:
el inventario se rehace, no se edita a mano.

Publicado el 2026-10-06 en https://claude.ai/artifact/653GinqFcNdQ31osLYd1VZ,
foto de 3d0c787c: 271 ítems. Lo genera `gen.py` de Aguará, que quedó en su
scratch (`tablero/`); la página la arma Hornero metiéndole el JSON adentro.

Lo que encontró de paso, sin arreglar: `ChangeFaceGraphic` compila a nada
pero **no está en `ACCEPTED_UNDONE`**, así que `page_debts` no avisa que la
cara se pierde. Y los comunes en paralelo no corren —6 en ABL, 35 en
Vampires Dawn—, que no estaba en ningún estudio.
