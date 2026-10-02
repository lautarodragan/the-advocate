---
name: "ABL a su propio repo"
description: "Fase 1 del juego de pruebas: todo lo de ABL —rom/, su justfile, sus pruebas y goldens, sus parches, su parte de docs/ y workflow/— a un repo aparte, nacido de cero; este repo queda con las herramientas y el runtime"
type: refactor
assignee: Ñandú-petiso
---

De taro, el 2026-10-02, con el plan de
`docs/research/2026-10-02-el-juego-de-pruebas.md` (Leñatero, fase 1):
"empezaría por asegurarme de que todas las cosas de ABL existan en un solo
lugar. Es más, creo que las sacaría del repo y las movería a un repo
propio, y `git init` ahí". Sin `git filter-repo`: "seguimos teniendo el git
log acá, y lo que va a quedar del lado de ABL debería ser muy poco". El repo
nuevo nace de cero con los archivos de hoy.

El riesgo que señaló Leñatero: entre esta fase y la 2 el motor se queda sin
pruebas de ROM propias. Por eso la fase 2 va enseguida.
