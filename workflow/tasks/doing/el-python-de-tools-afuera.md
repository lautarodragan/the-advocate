---
name: "El Python de tools/, afuera: common/ a Rust y el arnés a tests/"
assignee: Tero
---

# El Python de `tools/`, afuera

De taro, el 2026-10-02. En `tools/` quedan dos paquetes de Python que el
conversor ya no usa: los importa el arnés de pruebas de ABL —unos 24
archivos— a través de `rm2k-snes-python-path`.

- `common/` (`project.py`, `settings.py`, `environment.py`): un segundo
  lector del `rm2k-snes.toml` y de los flags de la máquina, al lado de
  `rm2k-project`, que es el de Rust. Dos modelos del mismo formato es lo que
  la guarda de Ditto prohíbe para el volcado.
- `emulator/retro.py`: el que maneja un core de libretro cuadro por cuadro.
  Es de las pruebas y nada más.

## Lo decidido

- **`common/` se va.** El arnés le pregunta a un binario de Rust lo que hoy
  le pregunta a `common/` —por ejemplo `rm2k-snes-project`, que imprime la
  configuración resuelta en JSON—, y `rm2k-project` es el único que lee el
  `rm2k-snes.toml`. Se van también sus pruebas, `test_project.py` y
  `test_settings.py`, o lo que cubrían pasa a pruebas del crate.
- **Las pruebas se quedan en Python.** Lo que es sólo de pruebas **se
  mueve, no se migra**: sale de `tools/` a una carpeta de pruebas, sin
  reescribirlo. `retro.py` es el caso.

## Lo que queda por decidir acá

- Dónde cae lo que se mueve, y cómo lo encuentra ABL si
  `rm2k-snes-python-path` deja de tener un `.py` donde vivir.
- Si `tools/tests/` —las pruebas de la estructura del repo— se mueve
  también o se queda.
