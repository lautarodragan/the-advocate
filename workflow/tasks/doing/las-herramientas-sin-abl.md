---
name: "Las herramientas sin datos ni código de ABL"
description: "Lo que en tools/ nombra o trae algo de ABL fuera de los comentarios: datos de prueba, fixtures copiados del juego, defaults y literales en el código; los comentarios se quedan por la decisión de las herramientas"
type: refactor
assignee: Monterita
---

De taro, el 2026-10-02, al ver que una prueba del compilador de eventos usa
`PhoneCallDiff` como dato: "dale". Un `grep` de nombres de ABL (personajes,
lugares, imágenes, la sigla) da 125 líneas en unos 50 archivos de `tools/`.

**Los comentarios del motor que nombran a ABL se quedan**, como dice
`decisiones/las-herramientas-se-separan-de-abl.md` ("por ahora, por
cuidado"), y los límites medidos contra ABL siguen con su comentario. Lo que
se limpia es lo otro: datos de prueba y fixtures, defaults, literales en el
código. Y hace falta para el juego de pruebas: este repo no tiene que
llevar nada de ABL (`testing/el-juego-de-pruebas.md`).
