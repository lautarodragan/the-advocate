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
    comun/       el caché en disco del conversor (cache_disco)
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
                 ventana, fuente, escena, animacion, asignador, tiles_bin

Y los cuatro proyectos de Rust, que no son capas del port sino herramientas
aparte, en inglés y sin una mención a este juego (ver AGENTS.md):

    ditto/       lee y escribe los formatos de RPG Maker 2000
    protocol/    declara un bytecode y genera las constantes de sus dos lados
    gunter/      Gunter: códec BRR y lector de SoundFont
    voodoo/      Voodoo: de una imagen a tiles, paletas y tilemap

Se instalan con `just herramientas` y se usan desde el PATH: ningún `.py` de
acá los compila ni los busca en `target/`.

## `port/` no está partido todavía

Es un bloque a propósito: tiene tres ciclos de imports adentro —`eventos` ↔
`batalla`, `batalla` ↔ `pantallas`, `eventos` ↔ `imagen`— y `titulo` tiene
helpers de paleta que usan varios. Separarlo pide decidir quién es dueño de
qué, y eso es trabajo de criterio que no entró en la mudanza.

## Cómo se importa

Cada carpeta es un paquete de Python, y se importa por su nombre, con `tools/`
—y sólo `tools/`— en el `sys.path`:

    from rpgmaker import lcf
    from render.render_map import GAME_DIR

Un `import lcf` suelto falla, y es a propósito: si también anduviera, el mismo
módulo se podría cargar dos veces con dos nombres, y lo que uno le cambia al
otro —`snes_convert` le cambia `DECORAR_TRANSLUCIDO` a `lcf`— no llegaría.

Los scripts se corren por su ruta, desde donde sea:

    python3 tools/port/snes_convert.py --help
    python3 tools/ensamblado/ensamblar.py --help
    python3 tools/audio/msu.py --help

Los que importan paquetes —`snes_convert` y `msu`— cambian, sólo si corren
como script, la carpeta que Python les pone al frente del `sys.path` por
`tools/`. Las pruebas ponen `tools/` ellas mismas.

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
