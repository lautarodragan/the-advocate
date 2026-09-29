---
name: "Rust: el render de mapas"
description: "tools/render en Rust: rm2k-render dibuja las capas de un mapa desde el volcado y el ChipSet, y el conversor lo llama por el PATH en lugar de importar Renderer, con las ROMs byte por byte iguales"
type: refactor
assignee: Hurón
---

Segundo paso del camino a Rust de `docs/research/las-herramientas-hoy.md`,
en paralelo con Carancho (`rust-el-armado-de-cartuchos.md`). Lo decidió
Hornero: el conversor usa el render para dos cosas, `Renderer` (las capas de
cada mapa, que se cachean) y `load_image` (cargar una imagen con su color
clave, desde varios módulos). Pasa a Rust lo primero, como un ejecutable
que el conversor llama por el PATH; `load_image` se queda en Python mientras
el conversor lo sea.
