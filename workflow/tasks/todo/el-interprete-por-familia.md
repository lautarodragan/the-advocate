---
name: "El intérprete por familia"
description: "Juntar los manejadores de opcode de cada familia en un solo archivo, cuando el despacho sea por tabla"
type: refactor
---

**Espera a la parte C de `main-s-segunda-etapa`** —el despacho por tabla—.

Desde la parte B cada manejador de opcode es su propio `.proc`, repartidos en
`rom/src/interprete_*.s` por tramo contiguo con un tema, no por familia: las
familias están intercaladas en el orden de la ROM (las escenas caen en cinco
tramos) y juntarlas era mover código. Con el despacho por tabla, dónde vive
cada manejador deja de importar, así que juntar cada familia en su archivo es
mover `.proc` enteros **dentro del mismo segmento**, igual que las once
mudanzas de la segunda etapa.

Se verifica igual que ellas: `just pruebas` sin ninguna golden cambiada, y el
listado de `ca65` comparado rutina por rutina para que ningún manejador quede
con otro ancho (el script de esa comparación estaba en el scratchpad de la
segunda etapa: rehacerlo si se perdió). Una familia por commit, sin tocar el
texto movido, para que `git blame -C --diff-algorithm=histogram` la siga.

Decidido con taro el 2026-09-25: el intérprete sí, y **no** reordenar todo
`rom/src/` —el banco 0 va justo, hay código sensible al tiempo, choca con
cada rama abierta, y para depurar en un emulador alcanza con los símbolos del
`.dbg`—.
