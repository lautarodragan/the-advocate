---
name: "Rust: los parches"
description: "tools/port/patches.py (rm2k-snes-patches: escribe y verifica los TOML de rom/parches/auto/) a Rust, con el mismo ejecutable y los mismos archivos byte por byte"
type: refactor
assignee: taro
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

## La comparación

Guiones descartables en el scratchpad (`yacutoro/`): `base.sh` arma con
`NO_CACHE=1 just cartuchos` y saca el sha256 de todo `rom/build/` (menos
caché, `.o`, `sello.txt` y `conversor.log`; el `.dbg` sin `mtime`);
`salidas.sh` corre `just parches-check` limpio, `just parches-check` con
cinco TOML tocados a mano —el `colores` de un mapa, el tamaño y la hoja de
una animación, un color, el tono y las fusiones de un battler, un mapa
versionado borrado y uno de más— y `just parches` sobre un battler tocado y
un mapa de más, y guarda salida, error, código y el sha256 de los 137 TOML.

* Python contra el ejecutable de Rust sobre los mismos builds: todo igual,
  salida de error incluida.
* Con el conversor ya pasando el pedido (`NO_CACHE=1`): las 1032 huellas
  iguales salvo los `.dbg` de los tres cartuchos, y `salidas.sh` igual a
  Python otra vez.
* `cargo test` del crate compara contra lo que `patches.py` contestó, antes
  de borrarlo, para el juego de `tests/game/` (`tests/python.json`): los
  sha256 de los diez TOML, lo que copia y borra, lo versionado, las quejas
  del check y lo propio de cada cartucho.

## Al mergear

* `just -f tools/justfile install patches cartridge`, desde el checkout
  principal: `patches` es nuevo, y `cartridge` cambió la huella. Esa receta
  borra primero los symlinks `rm2k-snes-*` y rearma los de Python, así que
  el symlink global de `rm2k-snes-patches` a `port/patches.py`, que queda
  colgando, lo reemplaza el binario. No hace falta `install-scripts` aparte.
* Todos los cartuchos quedan viejos (cambió la huella): `just cartuchos`.

## Las tandas

Sobre el árbol con `main` mergeado (`550ccfeb`): `just cartuchos`,
`just parches-check` en verde, `just pruebas` **878** —eran 880: las dos
que no dependían del juego, que armar otra vez no deja parches viejos y qué
es "sólo de la tanda", pasaron al crate—, `just -f tools/justfile test`
**85** (`main` sacó cinco), y `cargo test` de `patches` y de `cartridge`.
Las ROMs, iguales a las de antes de empezar.

## Qué se borró

`tools/port/patches.py` entero (792 líneas) y su symlink en `install`. De lo
que hacía, `write_uses` no se fue: pasó a `battle_scenes.py` como
`write_patch_uses`. Las dos pruebas de `rom/pruebas/herramientas/test_parches.py`
que no dependían del juego pasaron a `tools/rm2k-snes/patches/tests/`; las
otras dos quedaron, llamando al ejecutable y leyendo los TOML con `tomllib`.

Sin README propio el crate: su documentación es el `//!` de `lib.rs`, que
trae la del docstring de `patches.py`.
