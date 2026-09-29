# tools/

Todo lo que corre fuera de la consola: lo que lee el juego de RPG Maker, lo que
lo convierte, lo que arma la ROM y lo que la corre en las pruebas. Nada suelto:
cada cosa está en la carpeta de su responsabilidad.

## Las capas

De abajo hacia arriba. Una carpeta importa sólo de las que tiene abajo, nunca de
una de su misma fila ni de más arriba.

    rpgmaker/    el juego como datos: el volcado a JSON de data/ (lcf), los
                 códigos de comando de RM2k (event_codes) y sus reglas
                 (rm2k). Ninguna regla del formato vive acá: data/ viene
                 resuelto. Tiene su propio README
    comun/       el caché en disco del conversor (cache_disco) y el reparto de
                 lo puro en procesos bifurcados (paralelo)
    ensamblado/  el mapa de memoria (bancos), el que arma la ROM (ensamblar) y
                 qué ROMs hay y con qué flags (cartuchos, que usa `just build`)
    emulador/    el core de libretro desde Python (retro), y el parche de
                 bsnes-libretro que le expone la WRAM

    render/      un mapa, un chipset y un charset como imágenes; usa rpgmaker

    audio/       del MIDI al SPC700: snes_music, midi, musica, sdsp, spc700,
                 muestras_brr, snes_samples, music_opcodes, y las pistas de
                 MSU-1 (msu); usa rpgmaker, render y comun

    port/        el conversor a SNES —snes_convert— y todo lo que sólo él usa:
                 eventos, event_opcodes, batalla, pantallas, imagen, titulo,
                 ventana, fuente, escena, animacion, asignador, tiles_bin,
                 comprimir

Y los proyectos de Rust, que no son capas del port sino herramientas aparte,
en inglés y sin una mención a este juego (ver AGENTS.md):

    ditto/       lee y escribe los formatos de RPG Maker 2000
    protocol/    declara un bytecode y genera las constantes de sus dos lados
    gunter/      Gunter: códec BRR y lector de SoundFont
    voodoo/      Voodoo: de una imagen a tiles, paletas y tilemap
    lz2/         el LC_LZ2 de Nintendo, con un parser óptimo

Se instalan con `just -f tools/justfile herramientas` y se usan desde el
PATH: ningún `.py` de acá los compila ni los busca en `target/`. Los scripts de Python que se
ejecutan también: ver "Los que se ejecutan".

## `port/` no está partido todavía

Es un bloque a propósito: seis de sus módulos —`eventos`, `batalla`,
`pantallas`, `imagen`, `titulo` y `experiencia`— forman un solo ciclo de
imports, y `snes_convert` ↔ `pantalla_completa` otro. Todos los cierra un
import adentro de una función, que es con lo que se los esquivó. `titulo`,
además, tiene adentro la reducción de color, los menús y la fuente de los
menús, que usan varios. Separarlo pide decidir quién es dueño de qué, y eso
es trabajo de criterio que no entró en la mudanza.

Las capas tampoco se cumplen del todo: `ensamblado/cartuchos.py` importa de
`port/` y de `audio/`, y `rpgmaker/fork.py` de `render/`, además de
cerrar un ciclo con `lcf`. Qué usa cada uno,
cómo sacar las dos cosas y el script que imprime el grafo están en
`docs/research/el-mapa-de-las-herramientas-de-python.md`.

## Cómo se importa

Cada carpeta es un paquete de Python, y se importa por su nombre, con `tools/`
—y sólo `tools/`— en el `sys.path`:

    from rpgmaker import lcf
    from render.render_map import GAME_DIR

Un `import lcf` suelto falla, y es a propósito: si también anduviera, el mismo
módulo se podría cargar dos veces con dos nombres, y lo que uno le cambia al
otro —`snes_convert` le cambia `DECORAR_TRANSLUCIDO` a `lcf`— no llegaría.

## Los que se ejecutan

Los scripts que se corren son ejecutables —hashbang y `chmod +x`— y `just
herramientas` los instala como symlinks en el mismo `bin/` que los proyectos
de Rust. El `justfile` los llama por su nombre y no sabe dónde están:

    rm2k-snes-cartridges        ensamblado/cartuchos.py
    rm2k-snes-assemble          ensamblado/ensamblar.py
    rm2k-snes-space             ensamblado/espacio.py
    rm2k-snes-convert           port/snes_convert.py
    rm2k-snes-patches           port/parches.py
    rm2k-snes-msu               audio/msu.py
    rm2k-snes-volume-ceilings   audio/techos.py
    abl-entregar                ensamblado/entregar.py

El porqué de los nombres está en `tools/justfile`. Uno nuevo se agrega en
`_instalar`, y el `.py` busca sus paquetes resolviendo el symlink con
`realpath`, porque `__file__` es la ruta del PATH. Las pruebas ponen `tools/`
en el camino ellas mismas, desde `pytest.ini`: las de A Blurred Line, desde el
de la raíz, y las de las herramientas —`pruebas/`, las que no necesitan el
juego—, desde el de acá. Ver `pruebas/README.md`.

Un worktree que modifica las herramientas usa las suyas con `just -f
tools/justfile herramientas-locales`, que arma un `bin/` propio en la raíz
del checkout; los dos `justfile` lo ponen adelante en el PATH: ver la
receta, y "Sub-agentes" en AGENTS.md.

## `tools/justfile`

Las recetas de las herramientas —generar el bytecode, correr sus pruebas,
instalar— viven en `tools/justfile`, y las de A
Blurred Line en el de la raíz, que nombra este directorio una sola vez: para
decir cómo se instalan las herramientas de un worktree. Desde la raíz
se corren con `just -f tools/justfile <receta>`; parado acá, con `just
<receta>`. Las dos formas corren la receta parada en `tools/`.

## El parche de bsnes

`emulador/bsnes-wram.patch` es para **bsnes-libretro**, no para este repo.
bsnes no expone la WRAM —`retro_get_memory_data` devuelve nulo para todos los
ids— y el reloj de las pruebas le pregunta a la ROM en qué vuelta del lazo va,
que vive en `vueltas`, en la WRAM. Sin el parche, lo que corre bajo bsnes cae
a contar cuadros de hardware, que sirve mientras la ROM no se atrase. Y sin
bsnes no hay con qué contestar lo que `pruebas/rpgmaker/test_cores.py` existe
para contestar.

El parche expone sólo `RETRO_MEMORY_SYSTEM_RAM` y deja el resto como está: el
comentario de bsnes sobre esa función es por la SRAM, que no se toca, y por
eso es defendible río arriba. Su mensaje de commit dice el resto.

Para armarlo hace falta `gcc` y `make`, y nada más:

    git clone https://github.com/libretro/bsnes-libretro
    cd bsnes-libretro
    git am < .../tools/emulador/bsnes-wram.patch
    make -j$(nproc)
    cp bsnes_libretro.so /usr/lib/libretro/
