---
name: "Las herramientas encuentran el proyecto"
description: "Las herramientas dejan de saber que ABL vive en rom/ y de leer ABL_*: buscan rm2k-snes.toml hacia arriba, sus rutas salen del archivo, y el ambiente llega por flags"
type: refactor
assignee: Timbó
---

Lo que queda para que `tools/` no sepa nada de dónde ni cómo está ABL, después
de `testing/el-archivo-de-proyecto.md` (Molle). Lo decidió Hornero, con la
autorización de taro del 2026-09-29 para decidir sin esperarlo:

- **Las herramientas encuentran el proyecto como cargo encuentra el suyo**:
  buscan `rm2k-snes.toml` hacia arriba desde el directorio actual, o lo
  reciben por `--proyecto <dir>`. `proyecto.abl()` desaparece.
- **Las rutas del proyecto** (`data/`, `parches/`, `build/`, lo que haga
  falta) **las declara el archivo**, relativas a él. El runtime no: es de
  las herramientas.
- **El ambiente llega por flags** (`--game-dir`, `--rtp-dir`,
  `--soundfont`…), como dejó escrito Molle en su tarea; `rom/justfile`
  traduce `$ABL_GAME_DIR` y las demás. Las herramientas no leen ninguna
  `ABL_*`.

## Cómo va (Timbó, 2026-09-29)

La red de cada commit: `SIN_CACHE=1 just cartuchos` antes de tocar nada y
después de cada uno, con los sha256 de todo `rom/build/` —el script de Molle,
con el mismo criterio: sin `cache/`, `.o`, `sello.txt` ni `conversor.log`, y
los `.dbg` sin `mtime`—.

1. **Encontrar el proyecto.** `proyecto.directorio()` busca `rm2k-snes.toml`
   desde el directorio actual hacia arriba la primera vez que alguien lo
   pide, y `proyecto.fijar()` lo fija sin buscar. `--proyecto` lo lee cada
   ejecutable con `desde_la_linea_de_comandos`, que toma sólo ese flag
   antes del `parse_args` de su `main`: `cartuchos` y `entregar` leen el
   archivo al importarse, así que en ésos va antes que nada. Si no lo
   encuentra, `NoHayProyecto` —un `SystemExit`, así el ejecutable corta con
   el mensaje y sin traza— dice desde dónde buscó.
   - **Nada se calcula al importar.** Las constantes que salían del proyecto
     —`lcf.DATOS`, `fork.MAPAS`/`NUEVOS`/`CHIPSETS`/`DEL_JUEGO`,
     `chipset_del_fork.GENERADO`, `snes_music.TECHOS`, `cache_disco.DONDE`,
     `techos.MEDIDA`— pasaron a ser funciones o a calcularse adentro de la
     que las usa. Si no, importar el conversor desde `tools/` —lo que hacen
     las pruebas de las herramientas— buscaría un juego. La prueba de
     `test_perillas.py` que lo cuidaba ahora corre parada en un directorio
     vacío, y al final pide el proyecto para ver que no había uno.
   - **`parches.py` recibía la raíz del repo** y le sumaba
     `rom/parches/auto/`: ahora sus funciones reciben el directorio de lo
     automático (`proyecto.parches_auto()`), y los mensajes nombran las
     rutas relativas al directorio actual.
   - **El conversor corre parado en la raíz del repo** —ahí están las rutas
     relativas que terminan en el `.dbg`—, así que `cartuchos` le pasa
     `--proyecto`.
   - **Las pruebas de ABL fijan el proyecto por su ubicación**:
     `pruebas/arnes/lugares.py`, que importan primero `conftest.py`,
     `consola.py` y `video.py`.
   - `render_map` sigue buscando recursos también en `proyecto.raiz()`: es
     de 2026-08-31 (`00d96428`, cuando el RTP podía vivir en el repo) y hoy
     no encuentra nada ahí, porque la raíz no tiene carpetas de RM2k. No es
     llegar a ABL, así que no se tocó.
