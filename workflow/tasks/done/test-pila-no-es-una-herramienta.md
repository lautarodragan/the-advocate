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

## Hecho, 2026-09-26

Fue a `rpgmaker/`: mide la ROM corriendo y no sabe nada de ABL más allá del
material que usan todas. En el índice quedó al lado de `test_cores.py`, que es
la otra red contra lo que las goldens no ven. Se fue la excepción de la línea
de `herramientas/` en `pruebas/README.md`, y las cuatro citas a la ruta vieja
—`consola.py`, `bancos.py`, `paginas_de_eventos.s` y `workflow/ESTADO.md`—.
