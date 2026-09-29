---
name: "El archivo de proyecto de ABL"
description: "Los pasos 3 y 4 del plan: las perillas de ABL salen del código a rom/rm2k-snes.toml, y cartuchos.py queda como el mecanismo que lo lee"
type: refactor
assignee: Molle
---

Pasos 3 y 4 del plan de `docs/research/el-mapa-de-las-herramientas-de-python.md`
(§4, y la tabla de §3 con los ganchos). taro autorizó el 2026-09-29 a
Hornero a decidir lo abierto sin esperarlo. Lo decidido:

- **El archivo es `rom/rm2k-snes.toml`**: se llama como la suite que lo lee,
  igual que `Cargo.toml`, y vive en la raíz de ABL.
- **Las claves van en inglés** —son la interfaz de las herramientas, que van
  a ir en inglés, y renombrarlas después rompería el archivo de cada juego—;
  **los comentarios van en castellano**, porque el archivo es de ABL.
- **Una perilla por commit, con el mismo valor**, y la ROM byte por byte
  igual en cada uno.
- **`cartuchos.py` se queda como el mecanismo** que lee el archivo y arma
  (`rm2k-snes-cartridges`); lo de ABL —qué mapas, qué cartuchos, qué casos—
  pasa al archivo. La clave del caché sigue siendo el hash de los binarios
  hasta que haya versiones de verdad.
- **Los límites del motor medidos sobre ABL** (clase c del research) **no**
  van al archivo: se quedan en el código con un comentario que diga que se
  midieron contra A Blurred Line (decisión de taro).
