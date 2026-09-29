---
name: "Rust: la biblioteca del proyecto y el armado de cartuchos"
description: "El primer paso a Rust: tools/project/ (encontrar el proyecto, las perillas, el ambiente, la clave del caché) y tools/cartridge/ con rm2k-snes-assemble, rm2k-snes-space y rm2k-snes-cartridges, reemplazando a tools/assembly/ con las ROMs byte por byte iguales"
type: refactor
assignee: Carancho
---

De taro, el 2026-09-29: encarar las herramientas nuevas en Rust en el orden
de `docs/research/las-herramientas-hoy.md`. Éste es el primero: la
biblioteca común y `rm2k-snes-build` (que Hornero decidió partir en los tres
ejecutables que ya existen, con los mismos nombres, para que nadie que los
llama tenga que cambiar).

- `tools/project/`: crate de biblioteca, `rm2k-project`.
- `tools/cartridge/`: crate con los tres ejecutables. Reemplaza a
  `tools/assembly/{assemble,banks,space,cartridges}.py`; `entregar.py` es de
  ABL y queda.

## Lo que se decidió, y por qué

**Dos crates, y el reparto.** `rm2k-project` es lo que hoy es
`tools/common/` sin lo que es del conversor: encontrar `rm2k-snes.toml`
(hacia arriba o `--project`), las perillas con errores que nombran la clave
—`missing key cartridges.test-special.party`—, las rutas de `[paths]`, los
flags del ambiente (`environment::arguments`, `Environment::as_flags`) y la
clave del caché, que da **exactamente** la de `disk_cache.key` de Python
(una prueba lo compara contra un valor sacado de Python), así que los dos
lados comparten el caché. `parallel.py` no se portó: nadie en Rust lo
necesita todavía. El Python de `common/` sigue, porque el conversor es
Python. `rm2k-snes-cartridge` es una biblioteca con los tres ejecutables
encima (`src/bin/`): comparten el reparto, la lectura del `.dbg` y la de
los cartuchos, y `space` necesita a `cartridges` para saber si uno está
viejo.

**Las dependencias**: `toml` (con `preserve_order`, porque el orden de
`[cartridges]` es el orden en que se arman e imprimen), `serde_json` (leer
`maps.json`, los casos y los mapas nuevos; escribir `--json`), `sha2` (la
huella y la clave del caché) y `clap` (con la API de builder, no derive:
así la biblioteca le da a cada ejecutable sólo los flags de ambiente que
usa, con la misma ayuda, como hacía `environment.add_arguments`). Nada de
`regex`: lo que se parsea —directivas de ca65, registros del `.dbg`, el
`.cfg`— son formatos chicos y se leen a mano.

**El reparto en bancos se mudó del conversor al ensamblador.** Hasta hoy
`snes_convert.py` llamaba a `banks.resolve` y escribía `memoria.cfg`; ahora
el conversor deja todo en `RODATA` con sus `.block`/`.crossbank` y
`rm2k-snes-assemble` reparte, reescribe los `.inc` en el lugar —como hacía
el Python— y escribe el `.cfg` antes de correr `ca65`. Es lo que pedía el
plan ("el reparto en bancos y el `.cfg` de `ld65`") y además es el lugar
natural: el reparto es la otra mitad de lo que `ld65` no sabe hacer. Cuáles
son los archivos a repartir ya no es una lista de nombres
(`mapdata.inc`, `musicdata.inc`): son los `.include` que se encuentran en el
directorio de `-I`, en el orden en que los lee `ca65`. La misma regla da el
chequeo de "un generado tapado": uno que está en `-I` y también al lado del
archivo que lo incluye. Correr el reparto dos veces no cambia nada (hay una
prueba).

Consecuencia: la línea "bank packing: N piece(s) in M bank(s)" pasa de
`conversor.log` a la salida de `rm2k-snes-assemble`, o sea a la de
`just cartuchos`.

**Dónde está el runtime.** Un binario instalado no tiene `__file__`: el
crate guarda en tiempo de compilación dónde estaba su fuente
(`CARGO_MANIFEST_DIR`), y de ahí salen `tools/`, la raíz y
`tools/runtime/`. Es lo mismo que hacía el symlink de un script: el binario
responde por el checkout desde el que se instaló.

**La huella** sigue cubriendo lo que cubría —todo `tools/runtime/`, `ca65`,
`ld65`, los binarios que corre el conversor (`voodoo`, `gunter`, `lz2` y,
desde el merge con Hurón, `rm2k-render`), los
`.py` de `tools/*/` menos `tests/`, `parches/manual/*/*`, el archivo de
proyecto y los techos de volumen por su valor— y **suma el binario de
`rm2k-snes-assemble`**, porque ahora el reparto vive ahí: un cambio en el
reparto tiene que rearmar. Los `.py` siguen adentro mientras el conversor
sea Python.

**`sello.txt` cambió de formato.** Era la huella y un `repr` de Python de
(flags, [(caso, texto entero del JSON)]); ahora son líneas:

    inputs <huella>
    flags ["--party", "10", …]
    case <nombre> <sha256 del JSON>

Todos los cartuchos armados antes de esto quedan viejos una vez, y se
rearman solos.

**Lo que las pruebas de ABL necesitan, por la línea de comandos.**
`rm2k-snes-cartridges --list --json` (dónde está cada cartucho y su ROM, sus
flags, sus casos y cuáles empiezan con `Teleport`, si está viejo y por qué,
en qué cartucho corre cada caso, los mapas, lo que cubre la huella),
`rm2k-snes-space --json`, `rm2k-snes-assemble --sources` y
`rm2k-snes-assemble --memory-map` (la pila). El arnés lo pide en
`rom/pruebas/arnes/cartuchos.py`, una vez por proceso. Las pruebas de
`tools/tests/` que leían el runtime pegado usan `--sources` desde un
fixture de `tests/conftest.py`.

**Flags nuevos**, además de los de siempre, que quedan iguales:
`--list --json`; `--convert-into DIR -- <flags del conversor>` y
`--without-tracks`, que son lo que `rm2k-snes-volume-ceilings` hacía
importando `cartridges.convert` y `cartridges.build`; y en
`rm2k-snes-msu`, `--quiet` y una última línea "MSU-1 tracks, N made and M
that were already there", que `rm2k-snes-cartridges` imprime como
"release: …" en su lugar, igual que antes. `rm2k-snes-patches` saca los
mapas de prueba del archivo de proyecto y los directorios de
`--list --json`.

**Los nombres en castellano que quedan en el crate** —`prueba.sfc`,
`sello.txt`, `conversor.log`, `memoria.cfg`, `nuevos/`, `musica/techos.toml`
con sus `temas` y su `aire`, el nodo `arbol` de un mapa nuevo, el área
`RESERVADO` del `.cfg`— no son de ABL sino convenciones de la suite que
comparte con el conversor de Python, y cambiarlas cambia lo que sale. Van
cuando se porte el conversor.

**El `install` de `tools/justfile`**: `project` y `cartridge` entran en
`rust_projects`; una biblioteca se saltea al instalar (no tiene binario), y
los symlinks de la suite se borran antes de `cargo install`, porque cargo
no escribe encima de lo que no instaló y `rm2k-snes-assemble` era un
symlink. Los tres symlinks a los `.py` que se reemplazan salen en el mismo
commit que pone a Rust en su lugar —no en el del borrado—: con el reparto
fuera del conversor, el `assemble.py` de Python ya no arma una ROM buena, y
un `install-scripts` que lo volviera a enlazar la rompería.

## Al mergear

Desde el checkout principal:

    just -f tools/justfile install project cartridge
    just -f tools/justfile install-scripts

El primero compila sólo esos dos (y rearma los symlinks); el segundo es
por si acaso, y no toca Rust.
