---
name: "Partir test_comandos_golden"
description: "Un archivo de prueba que junta muchos comandos de RM2k distintos"
type: test
---

`pruebas/rpgmaker/test_comandos_golden.py` compara contra goldens muchos
comandos de eventos distintos en un solo archivo. Su cabecera explica que se
agrupan por arnés, no por comando. En `ordenar-pruebas` (2026-09-25) se decidió
no partirlo: un archivo por comando es un cambio grande para lo que rinde, y
el índice de `pruebas/README.md` ya dice qué cubre. Vuelve a valer la pena si
el archivo sigue creciendo o si dos ramas empiezan a chocar ahí.
