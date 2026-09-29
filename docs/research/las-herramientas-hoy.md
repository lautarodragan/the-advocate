# Las herramientas hoy, y su camino a Rust

> **Foto del 2026-09-29, sobre el commit `66152183`**, con los pasos 1 a 5
> del plan de separación hechos y antes de traducir los nombres al inglés.
> Las líneas salen de `wc -l` (sin pruebas ni código generado cuando se
> dice); las dependencias, de `grep` sobre los `import` y los `subprocess`.
> Los esfuerzos son estimaciones de Hornero, no mediciones.

## Resumen

`tools/` tiene tres cosas:

* **cinco proyectos de Rust**, ya en inglés y sin nada del juego: unas 20.800
  líneas, de las cuales 15.400 son Ditto;
* **el conversor y sus capas en Python**: unas 33.000 líneas, 23.000 de ellas
  en `port/`, y dos archivos concentran la mitad (`snes_convert.py` 9.550 y
  `eventos.py` 5.440);
* **el runtime**, el motor de la SNES en ensamblador: unas 44.000 líneas en
  95 archivos. No se migra: es lo que corre en la consola.

El Python depende de **dos bibliotecas** —Pillow en 20 módulos y numpy en
seis— y de **binarios externos** por `subprocess`: `ca65` y `ld65`
(cc65), `fluidsynth` y `ffmpeg`, además de los cinco nuestros.

**Lo más barato es que desaparezcan los puentes.** Cuatro módulos de Python
son sólo el pegamento entre el conversor y un binario de Rust que ya existe;
cuando quien los llama sea Rust, se vuelven una llamada a una biblioteca:

| módulo | líneas | se vuelve parte de |
|---|--:|---|
| `port/comprimir.py` | 117 | `lz2` |
| `port/tiles_bin.py` | 123 | `voodoo` |
| `audio/muestras_brr.py` | 306 | `gunter` |
| `audio/snes_samples.py` | 353 | `gunter`, que ya lee SoundFonts |

Y dos más ya los genera un binario: `audio/music_opcodes.py` y
`port/event_opcodes.py` salen de `protocol`, que puede emitir Rust en vez de
Python.

**Ditto es el otro imán.** `rpgmaker/lcf.py` (940) lee el volcado JSON que
escribe Ditto, que en Rust ya tiene el modelo entero del formato; las reglas
de RM2k de `rpgmaker/rm2k.py` (509) —pasabilidad, capas, poses— son
semántica del formato y encajan como biblioteca de Ditto. `rpgmaker/fork.py`
(269) y `render/chipset_del_fork.py` (342) aplican los parches a mano: son
del conversor, no del formato.

**Lo que no va a Voodoo:** el asignador (`port/asignador.py`, 217), que
decide qué colores se pierden. AGENTS.md dice que Voodoo no decide colores y
que eso no se arregla; en Rust tiene que ser su propia herramienta, o parte
del conversor.

## Las herramientas nuevas, por tamaño

Talles por lo que cuesta, no por las líneas: **S** es un día de un agente,
**M** unos pocos, **L** una semana, **XL** varias y por partes.

| herramienta en Rust | sale de | líneas de Python | talle | lo difícil |
|---|---|--:|:-:|---|
| biblioteca común | `comun/` (proyecto, perillas, ambiente, caché, paralelo) | 550 | S | la clave del caché: hoy hashea los `.py` por su ruta |
| `rm2k-snes-build` | `ensamblado/` (bancos, ensamblar, espacio, cartuchos) | 1.260 | M | el reparto en bancos y el `.cfg` de `ld65`; sigue llamando a `ca65`/`ld65` |
| `rm2k-render` | `render/` | 1.020 | M | los autotiles; Pillow → el crate `image` |
| reglas de RM2k en Ditto | `rpgmaker/lcf.py`, `rm2k.py`, `event_codes.py` | 1.470 | M | `lcf.py` desaparece: Ditto ya tiene el modelo |
| `rm2k-snes-audio` | `audio/` sin los puentes (midi, musica, sdsp, spc700, snes_music, efectos_msu, msu, techos) | 4.000 | L | `snes_music.py` (2.550) es el paquete de audio por mapa; `msu` y `techos` usan `fluidsynth` y `ffmpeg` |
| el conversor | `port/` sin los puentes | 22.500 | XL | `eventos.py` es un compilador de bytecode; `snes_convert.py` todavía mezcla todo |

Van por fuera de esta tabla:

* **`emulador/retro.py`** (441): el core de libretro desde Python. Lo usan
  las pruebas de ABL, que son Python, así que se queda mientras ellas lo
  sean.
* **`ensamblado/entregar.py`**: es del flujo de trabajo de ABL, no de la
  suite. Se va con ABL, o se vuelve una receta.
* **`parches.py`** (762): escribe y verifica las decisiones con pérdida como
  TOML; va con el conversor.

## Las dependencias, y qué las reemplaza en Rust

| hoy | lo usan | en Rust |
|---|---|---|
| Pillow | 20 módulos: `render/`, casi todo `port/`, `msu`, `techos`, `retro` | el crate `image`, o `png` solo |
| numpy | `snes_convert`, `asignador`, `menus`, `snes_samples`, `msu` y `techos` | vectores; nada lo pide de verdad |
| `ca65` + `ld65` | `ensamblar` | se siguen llamando: son el ensamblador |
| `fluidsynth` | `msu`, `techos` | se puede seguir llamando; `rustysynth` sintetiza SoundFonts en Rust puro, y sacaría una dependencia del sistema |
| `ffmpeg` | `msu`, `techos` | medir el volumen se puede con el crate `ebur128`; codificar, seguir llamándolo |

## El orden que recomiendo

1. **Los puentes y los generados**, porque desaparecen solos: cuando el que
   los llama es Rust, son una dependencia de crate. No hace falta migrarlos
   antes: se van con su llamador.
2. **`rm2k-snes-build`** y la biblioteca común: chicos, con entradas y
   salidas claras, y son los que corre `just cartuchos`.
3. **`rm2k-render`** y **las reglas de RM2k en Ditto**: hojas, sin nada
   del juego.
4. **El audio**: grande pero aislado, con su propia prueba de verdad (los
   techos miden el audio de la ROM).
5. **El conversor**, al final y por partes, después de partir
   `snes_convert.py` como pide `workflow/tasks/todo/las-responsabilidades-de-snes-convert.md`.
   `eventos.py` es la pieza más cara: conviene migrarlo con el bytecode
   declarado en `protocol`, que ya genera las constantes de los dos lados.

Mientras dure la mezcla, un binario de Rust y el Python conviven por el
PATH, como hoy `ditto`, `voodoo` o `lz2`: cada paso se verifica igual que
los de la separación, con las ROMs byte por byte iguales.
