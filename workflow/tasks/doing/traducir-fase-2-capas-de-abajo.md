---
name: "Traducir las herramientas, fase 2: las capas de abajo"
description: "Los nombres de código de tools/comun, rpgmaker, render y emulador al inglés, con todos sus usos"
type: refactor
assignee: Mburucuyá
---

Fase 2 de la traducción de `tools/` al inglés (taro, 2026-09-29): los nombres
de código, de abajo hacia arriba, un área por vez. Ésta es la primera:
`tools/comun/`, `tools/rpgmaker/`, `tools/render/` y `tools/emulador/`, con
todos sus usos en `tools/` y en `rom/pruebas/`. Los nombres de las carpetas
también: `comun` → `common`, `emulador` → `emulator`.

## Cómo se hace

De a un módulo por commit, y cada uno verificado solo: `SIN_CACHE=1 just
cartuchos` con los `.sfc`, `.msu`, `.pcm`, `.inc` y `.dbg` (sin la fecha)
iguales a los de `c60949e0`, `just pruebas`, `just -f tools/justfile
pruebas`, pyflakes sin avisos nuevos, y un chequeo de que cada
`modulo.nombre` de estos paquetes exista. Los renombres los hace un script
por tokens —no por texto—, así que no entra en los strings: lo que es dato
no se toca, y los strings que son código (una ruta, un `import` adentro de
un `-c`) se buscan aparte con grep.

## Hecho

1. `comun/` → `common/`, la carpeta sola.
2. `proyecto.py` → `project.py`, con `--proyecto` → `--project`.
3. `perillas.py` → `settings.py`.
4. `ambiente.py` → `environment.py`, con `--reemplazos` → `--replacements` y `--compartido` → `--shared`.
5. `cache_disco.py` → `disk_cache.py`.
6. `paralelo.py` → `parallel.py`.
7. `rpgmaker/recursos.py` → `rpgmaker/resources.py`.
8. `rpgmaker/fork.py`, sus nombres.
9. `rpgmaker/lcf.py` y `rpgmaker/event_codes.py`, sus nombres, con los atributos en castellano de las clases del juego.
10. `rpgmaker/rm2k.py`, sus nombres, y los dos atributos que el render le pone al mapa: `chipset_nombre` → `chipset_filename` y `pasabilidad_tiles` → `passability_table`.
