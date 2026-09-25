---
name: "El tinte no tiñe al que comparte paleta con el cronómetro"
description: "tinte.s saltea la paleta del cronómetro, y desde el 09-07 la comparte un personaje, que queda sin teñir"
type: bug
---

Encontrado midiendo si se juntan `release` y `test-main` (ver
`juntar-release-y-test-main.md`), el 2026-09-25. **Pasa hoy en `release`**.

`rom/src/tinte.s` vuelve a subir las paletas teñidas salteando la del
cronómetro, porque "los dígitos tienen una paleta para ellos solos" (`5be4ade`,
2026-09-04). Desde `034d721` (2026-09-07) esa paleta la comparten con un
personaje, y ese personaje queda sin teñir cuando la pantalla se tiñe.

En la tanda no se ve porque `test-main` arma con `--sin-timer`. Con el
cronómetro puesto, cinco goldens de la puerta del mapa 7 lo muestran:
`sacudir-60`, `cerrar-400`, `cerrar-right-400`, `autocierre-63` y
`autocierre-3-185`. Arreglarlo antes de juntar los cartuchos, así esas cinco
se re-congelan una sola vez y ya bien.
