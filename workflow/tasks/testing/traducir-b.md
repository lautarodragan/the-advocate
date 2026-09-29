---
name: "Traducir las herramientas al inglés, fase 1: el resto de port"
description: "Comentarios, docstrings, mensajes y prosa al inglés, sin tocar nombres de código: tools/port/, todo menos snes_convert.py"
type: refactor
assignee: taro
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
* Citas que otros archivos hacen de títulos que cambiaron de nombre, fuera
  de este alcance: `tools/runtime/ranuras.s` cita "lo que depende del
  actor" —ahora "what depends on the actor", en `menus.py`—, y
  `snes_convert.py`, ya traducido por Aromo, sigue citando "Qué
  fondos hay" (escena.py), GIRO —ahora TURN— y "las variables de RM2k"
  —ahora "RM2k's variables"— (eventos.py), y "lo que depende del actor".

## Verificado

Sobre el árbol con `main` mergeado (`106da9f8`, con lo de Aromo, Coronillo y
Palmar adentro):

* `SIN_CACHE=1 just cartuchos`: los `.sfc`, `.msu`, `.pcm` y `.sym` de
  `rom/build/` con el mismo sha256 que antes de empezar. Lo único distinto
  es `memoria.cfg`, cuyo encabezado tradujo Coronillo. Ningún módulo de
  esta parte escribe en los `.inc`: antes de mergear salían idénticos, y
  lo que cambia en ellos después es de `snes_convert.py`.
* `just pruebas`: 874 pasan.
* `just -f tools/justfile pruebas`: 132 pasan y 2 se saltean.

## Qué mirar

Nada que se juegue: la ROM es la misma byte por byte. Lo que hay para
leer es el `git diff`, sobre todo `eventos.py`, y la decisión de los
comentarios de los `.toml` de `rom/parches/auto/`.
