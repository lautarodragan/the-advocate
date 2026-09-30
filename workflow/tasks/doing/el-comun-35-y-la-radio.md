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

# El común 35 (Aguará, 2026-09-30)

**Cómo corre en RM2k**, confirmado en el LDB y en los mapas: no hay nada
especial después de la pelea. 162 de las 300 tropas traen una página de
turno 0 que prende el 498 al abrir la pelea (en EasyRPG, `CheckTurns` con
0 y 0 es el turno 0: corre antes de las primeras órdenes). Y 74 mapas —82
páginas— traen la automática `AfterBattleMint`, con el 498 como condición,
que sólo hace `CallEvent` al común 35; al volver al mapa, la automática
corre y el común apaga el 498 al final. En `release` son 16 de sus mapas,
entre ellos el 60 del caso `pelea-invocacion`.

**Lo que hace**, además de devolver a Lerle: cura a las 18 invocaciones
(36 a 53), saca a la que esté y agrega a Lerle (26); apaga los switches de
Talan y le rearma los HP y SP desde las variables 134 a 138; le saca a
Emily (25) el accesorio y las cuatro cintas (385 a 388); y le rearma a AG7
(18) las habilidades de sus piezas.

**El arreglo**: el barrido de variables (`variables`, en `indices.rs` de
`rm2k-snes-events`) mira también los comunes. Las del juego pasaron de 132
a 169 y la más alta, de 201 a 204. Corre las ranuras: las partidas de los
cartuchos de antes no cargan bien en éste, y está aprobado.

**La prueba**: `test_despues_de_la_pelea_lerle_vuelve_al_grupo`, en
`test_sistemas_de_tropa.py`. **En rojo antes del arreglo**, medido: el 498
quedaba prendido después de la pelea. `test_la_invocacion_cambia_...`, que
miraba el grupo recién cerrada la pelea, ahora apaga el 498 antes de
cerrar, porque si no el común ya corrió cuando mira.

**El costo**: el común compila en el lugar de cada `CallEvent`, así que va
copiado en cada mapa con encuentros. `just espacio` en `release`: bancos de
datos de 116 a 117 usados (7 libres), huecos de 8.799 a 7.678 B. El banco 0
y el banco 1 no se movieron (13 B y 5.054 B). Es deuda: un cuerpo
compartido lo pagaría una sola vez.

**Ninguna golden se movió**: la tanda dio 893 en verde y la de las ranuras
en rojo, que es la que cuenta las variables (actualizada).
