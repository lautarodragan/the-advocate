---
name: "La guarda de los bancos"
description: "Una prueba que recorra el .dbg y marque todo jsr/jmp absoluto que cae en otro banco y toda lectura absoluta de ROM fuera del banco 0: la regla de main.s que el ensamblador no revisa"
type: feature
assignee: Ratona
---

Lo propuso Pepitero (`testing/el-banco-1-se-lleno.md`), sin hacerlo: el
script descartable con el que verificó las mudanzas a `FAR2` dio 0 antes y
después de cada una, y la regla de dónde va el código (encabezado de
`tools/runtime/main.s`) "nada de esto lo revisa el ensamblador". Un `jsr` a
una rutina de otro banco salta al lugar equivocado sin ningún error.
