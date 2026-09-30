---
name: "Rust: los parches"
description: "tools/port/patches.py (rm2k-snes-patches: escribe y verifica los TOML de rom/parches/auto/) a Rust, con el mismo ejecutable y los mismos archivos byte por byte"
type: refactor
assignee: Yacutoro
---

De taro, el 2026-09-30, en la migración del conversor a Rust. `patches.py`
ya es un ejecutable propio (`rm2k-snes-patches`, que llaman `just parches`
y `just parches-check`) con entrada y salida claras.

## Dónde quedó y por qué (Yacutoro, 2026-09-30)

Un crate propio, `tools/rm2k-snes/patches/` (`rm2k-snes-patches`, proyecto
`patches` del justfile), y no un binario más de `cartridge`. La capa es
`rm2k-snes/` porque sabe de las dos cosas —ids de mapa, animaciones y
battlers de RM2k, colores de 15 bits y CGRAM—. Crate aparte porque es otra
responsabilidad: `cartridge` arma cartuchos, y esto escribe, copia y
compara decisiones; lo único que le pide a `cartridge` es la lista de
cartuchos y dónde se arma cada uno, para `--check` sin argumentos, y eso lo
toma como biblioteca (`Cartridges::load`, `names`, `directory`) en vez de
correr `rm2k-snes-cartridges --list --json` como hacía el Python.

## La frontera con el conversor

El conversor importaba `patches.py` en el mismo proceso: `write_maps`,
`write_animations` y `write_battlers` armaban el texto de los TOML desde lo
que el conversor decidió, y `write_uses` escribía `parches/usos.json`.

* **Lo que viaja es la decisión**, en un pedido JSON: el conversor corre
  `rm2k-snes-patches --request <pedido> <build>` —`stage.hand_over`, nuevo,
  al lado de `stage.run`—, y el ejecutable vacía y escribe
  `<build>/parches/auto/{mapas,animaciones,battlers}/` e imprime las mismas
  tres líneas que imprimía el conversor. El pedido lo arman
  `patch_of_map`, `patch_of_animation` y `patch_of_battler` en
  `snes_convert.py`. De un battler viaja **cuántas** fusiones, que es lo
  único que se escribe, y no la lista.
* **`usos.json` lo sigue escribiendo el conversor**, que es quien sabe
  quién pidió cada cosa: `write_patch_uses` pasó a `battle_scenes.py`, al
  lado de `patch_uses`, y el ejecutable sólo lo lee. Así además el archivo
  sale byte por byte igual sin reimplementar en Rust el orden de
  `sorted(..., key=str)` sobre pares de Python.
* `--request` es un flag nuevo; los de antes —`--project`,
  `--test-cartridges`, los directorios y `--check`— siguen iguales, así que
  `just parches` y `just parches-check` no cambian. `--request` no busca el
  proyecto: sólo escribe en el build lo que le dan.
* `rm2k-snes-patches` entra en la huella de los cartuchos
  (`CONVERTER_TOOLS` de `cartridge`): lo que escribe va al lado de la ROM y
  el check lo lee de ahí.
