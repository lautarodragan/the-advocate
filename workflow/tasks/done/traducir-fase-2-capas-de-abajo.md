---
name: "Traducir las herramientas, fase 2: las capas de abajo"
description: "Los nombres de código de tools/common (antes comun), rpgmaker, render y emulator (antes emulador) al inglés, con todos sus usos"
type: refactor
assignee: taro
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
11. `render/render_map.py` y `render/chipset.py`, sus nombres.
12. `render/chipset_del_fork.py` → `render/chipset_recipe.py`: lo que hace es aplicar la receta del fork al PNG.
13. `emulador/` → `emulator/`, con `retro.Consola` → `retro.Console` y sus métodos.
14. Lo que quedó: `nodo` en `lcf.py`, `tools/README.md` y la tarea pendiente del MSU-1, que citaban los nombres viejos.
15. Los archivos de prueba de `tools/pruebas/` y sus funciones, al inglés.
16. Dos citas en prosa que quedaban en `snes_convert.py` y `parches.py`.

Los `.sfc`, el `.msu` y los `.pcm` salen iguales a los de `c60949e0` en
cada commit. Los `.dbg` cambian desde el 10 en una sola cosa: el `size`
de `animacion_del_chipset.s`, cuyo comentario cita un nombre de acá.

## Lo que quedó sin traducir, a propósito

Todo es dato o es de otra área:

* **Las claves y los valores que están en archivos del juego o que lee
  otro**: las de `rom/data/`, las de la receta de un ChipSet del fork
  (`podar`, `desde_imagen`, `cabeza`…), el `arbol` de un mapa nuevo, las
  categorías del caché (`capas`, `brr`, `muestras`, `msu`), los sufijos
  de CharSet (`~trama`, `~horneado`, `~aparte`), los nombres de las
  tramas (`damero`, `cinco_de_ocho`…), las familias `agua` y `animado`, la
  carpeta de salida `parches-manual/`.
* **Las claves del diccionario de cada NPC** que arma `rm2k.collect_npcs`
  (`evento`, `cambia`, `graficos`, `tile_pasa`, `velocidad`…): son la
  interfaz con el conversor, que las lee en `port/`. Cambian con esa área.
* **Las variables de ambiente** `SIN_CACHE`, `TRAMA_PATRON` y
  `MODO_TRANSLUCIDO`: son interfaz como un flag, pero `SIN_CACHE` la usan
  `AGENTS.md` y la verificación de todo esto. Queda para decidir.
* **`envolvente`** en `test_music_stream.py`: pisa el método de
  `snes_music.Banco`, que es de `audio/`.
* **Las variables y constantes de adentro de las pruebas de
  `tools/pruebas/`**: el encargo pedía los archivos y las funciones.
* **Los homónimos de otras áreas**: `batalla.py` tiene su `self.activos`,
  `eventos.py` su `estado.lider()` y su `self.donde`, `Partida` sus
  `correr` e `imagen`, y el runtime sus rutinas `cargar_mapa` y
  `grafico_de_pagina`.

## Para taro

* `AGENTS.md` nombra todavía `tools/comun/cache_disco.py` (ahora
  `tools/common/disk_cache.py`), los flags `--reemplazos` y `--compartido`
  (ahora `--replacements` y `--shared`) y
  `test_ningun_opcode_comparte_numero_con_otro` (ahora
  `test_no_opcode_shares_a_number_with_another`). No lo toqué: es el
  archivo de las reglas.
* Nada de esto se juega: los `.sfc` son los mismos bytes.
