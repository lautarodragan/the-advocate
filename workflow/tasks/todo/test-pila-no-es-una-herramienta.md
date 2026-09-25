---
name: "test_pila no es una herramienta"
description: "herramientas/test_pila.py corre la ROM, y herramientas/ son las pruebas que no"
type: test
---

`pruebas/README.md` dice que `pruebas/herramientas/` son las pruebas que no
corren la ROM, y `test_pila.py` sí la corre: mide cuánto baja la pila. Quedó
anotado como excepción en el README el 2026-09-25, en vez de moverlo, porque
es una decisión de carpeta y no de nombre. Decidir a cuál va (`rpgmaker/`
parece lo natural: mide la ROM, no el juego) y moverlo con `git mv`, junto
con su línea del índice del README —`test_indice.py` lo cobra—.
