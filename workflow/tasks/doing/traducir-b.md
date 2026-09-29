---
name: "Traducir las herramientas al inglés, fase 1: el resto de port"
description: "Comentarios, docstrings, mensajes y prosa al inglés, sin tocar nombres de código: tools/port/, todo menos snes_convert.py"
type: refactor
assignee: Cina
---

De taro, el 2026-09-29: "traducir las herramientas a inglés". Es la regla de
AGENTS.md para los proyectos aparte, que ahora alcanza a todo `tools/`
(ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md`).

**Fase 1**, repartida entre cuatro agentes por área: comentarios, docstrings,
mensajes de error, `help=` y prosa. **Los nombres de código no se tocan** —
módulos, funciones, variables, símbolos del runtime, flags—: eso es la fase
2, de a un área por vez, porque un nombre cambia en todos los que lo
importan. Los términos salen de `tools/GLOSSARY.md`.

Alcance de esta parte: tools/port/, todo menos snes_convert.py.

## Cómo se verifica

Cada grupo de archivos va en su commit, y se verifica con tres cosas:

* el AST de cada archivo contra `66152183`, sin docstrings: sólo pueden
  cambiar strings, y cada string que cambió se mira a mano —mensaje o
  dato—;
* `SIN_CACHE=1 just cartuchos` y el sha256 de todos los `.sfc`, `.msu` y
  `.pcm` de `rom/build/` contra los de antes de empezar;
* los `.inc` generados, con un diff que sólo puede mostrar comentarios.

## Hecho

* Los módulos chicos: `animacion`, `asignador`, `color`, `comprimir`,
  `constantes`, `experiencia`, `fin_del_juego`, `formato_snes`, `fuente`,
  `imagen`, `msu_datos`, `paleta`, `pantalla_completa`, `reglas`, `textos`,
  `tiles_bin`, `titulo`, `ventana`. `event_opcodes.py` es generado y ya
  estaba en inglés.
* La pelea, los menús y las pantallas: `batalla`, `escena`, `menus`,
  `pantallas`, `parches`.
* `eventos`, que es casi la mitad del alcance.

## Lo que quedó en castellano a propósito

* **Los comentarios que `parches.py` escribe adentro de los `.toml`** de
  `rom/parches/auto/`. Son lo versionado del juego: traducirlos acá deja
  esos archivos viejos en cada comentario hasta el próximo `just parches`,
  que reescribiría los de `rom/` —fuera del alcance—. `--check` compara lo
  parseado, así que no falla por eso. Es una decisión para taro: si van en
  inglés, es cambiar esas líneas y correr `just parches`, en un commit
  propio.
* Todo lo que es dato: los términos del LDB, "- Empty -", ">", "Yes" y
  "No" de repuesto de End Game, las claves de los diccionarios y de los
  `.toml`, el "(OFF)" de RM2k, el centinela `FONDO_DEL_LUGAR`, los nombres
  de clase de `pantalla_ranuras` ("cabecera", "menu_opcion"…).

## Lo que quedó colgando

* `docs/port/msu-datos.md` cita dos secciones de `escena.py` por su título
  en castellano ("El respaldo liviano", "Qué fondos hay"); ahora se llaman
  "The light fallback" y "Which backdrops there are, and which ones the
  cartridge carries". `docs/` no es de esta fase.
