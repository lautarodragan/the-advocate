---
name: "El común 35 y la música de la radio"
description: "Lo que dejó abierto Yarará en los sistemas de batalla: ResetAfterBattles, para que la invocación devuelva a Lerle, y los tres temas de Play Radio en la pelea"
type: feature
assignee: Aguará
---

De taro, el 2026-09-30, al contestar sobre `testing/eventos-de-tropa-en-la-pelea.md`
(Yarará):

- **El común 35 (`ResetAfterBattles`).** Sin él, la invocación queda en el
  grupo en lugar de Lerle después de la pelea. Sus comandos ya compilan; lo
  que lo traba es que las variables que sólo nombra un común no tienen ranura
  en la partida, y sumarlas corre las de las demás. taro: romper la
  compatibilidad de las partidas **nunca es un problema**.
- **La música de `Play Radio` (809).** Su `PlayBGM` hoy se acepta y no se
  hace. taro: con la calidad tan baja como haga falta en la ROM y tan alta
  como se pueda en el `.msu`; si separarlas es más difícil que bajarle la
  calidad al tema de batalla u otros, se baja y listo.

Ver `decisiones/primero-el-juego-entero-despues-la-calidad.md`.

Sale de `main` en el commit que lanza la tarea. Ahí: `NO_CACHE=1 just
cartuchos` da `abl.sfc` `e20182d1bd905de7…`; `just pruebas` 893,
`just -f tools/justfile test` 46.
