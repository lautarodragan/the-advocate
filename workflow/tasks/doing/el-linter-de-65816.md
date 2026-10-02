---
name: "Un linter de 65816, en Rust"
description: "Chequeos de trampas comunes que ensamblan bien pero están mal: pl* antes de un salto condicional, jsl/rtl contra jsr/rts, la pila desbalanceada, y el ancho de los registros como estudio; una herramienta de tools/ que no sabe de ABL, con las excepciones del juego en rom/"
type: feature
assignee: Carpintero
---

De taro, el 2026-10-02: "¿hay equivalentes a linters, formatters u otras
herramientas de análisis estático para assembler? En particular, tal vez
aportaría valor algún chequeo de trampas comunes —cosas que compilan bien
pero seguro estén mal—". Para 65816 no hay nada que valga la pena adoptar,
así que se hace: "y que esté hecho en Rust".

El antecedente es la guarda de los bancos de Ratona
(`testing/la-guarda-de-los-bancos.md`), que lee el `.dbg` y marca los saltos
a otro banco. La trampa 1 es la de `AGENTS.md`, "La trampa que más veces
mordió".
