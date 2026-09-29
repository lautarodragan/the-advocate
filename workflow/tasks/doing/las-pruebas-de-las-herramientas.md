---
name: "Las pruebas de las herramientas, en tools/"
description: "Las pruebas que no necesitan el juego se mudan a tools/pruebas/; las de Ditto dejan de caer en el juego de ABL, y ABL comprueba su ida y vuelta con el ditto del PATH"
type: refactor
assignee: Chañar
---

Sale de lo que dejó abierto `testing/el-justfile-de-las-herramientas.md`
(Espinillo). taro pidió el 2026-09-29 que Hornero decida lo abierto y haga
una primera versión sin esperarlo. Lo decidido:

- **Las pruebas que no necesitan el juego ni una ROM van a `tools/pruebas/`**,
  con un `tools/pytest.ini` propio y una receta `pruebas` en `tools/justfile`.
  Van en castellano, como el Python de `tools/`: se traducen todas juntas.
- **`ditto-pruebas` y `ditto-vuelta-entera` exigen `DITTO_CORPUS`** y no
  caen en `ABL_GAME_DIR`: las herramientas no saben de ningún juego. Sin la
  variable, las que necesitan corpus se saltean, como ya hacen.
- **ABL comprueba que su juego hace la ida y vuelta** con una receta propia
  que usa el ejecutable `ditto` del PATH (`unpack` y `pack`), sin compilar
  nada.
