---
name: "Un linter de 65816, en Rust"
description: "Chequeos de trampas comunes que ensamblan bien pero están mal: pl* antes de un salto condicional, jsl/rtl contra jsr/rts, la pila desbalanceada, y el ancho de los registros como estudio; una herramienta de tools/ que no sabe de ABL, con las excepciones del juego en rom/"
type: feature
assignee: taro
---

De taro, el 2026-10-02: "¿hay equivalentes a linters, formatters u otras
herramientas de análisis estático para assembler? En particular, tal vez
aportaría valor algún chequeo de trampas comunes —cosas que compilan bien
pero seguro estén mal—". Para 65816 no hay nada que valga la pena adoptar,
así que se hace: "y que esté hecho en Rust".

El antecedente es la guarda de los bancos de Ratona
(`testing/la-guarda-de-los-bancos.md`), que lee el `.dbg` y marca los saltos
a otro banco. La trampa 1 es la de `AGENTS.md`, "La trampa que más veces
mordió".

## Lo hecho (2026-10-02, Carpintero, sobre `a6ba9693`)

**Goombario**, `tools/snes/goombario/`, en el PATH como `goombario`. El
nombre es de Goombario, el compañero de Paper Mario cuyo poder es "Tattle":
contar lo que sabe de cada uno. Un linter es eso. taro lo puede cambiar.

Lee **la ROM, el `.dbg` y el fuente**, igual que la guarda de los bancos de
Ratona: no desensambla adivinando, cada línea del `.dbg` dice dónde fueron
sus bytes y la instrucción se lee de la ROM ahí. El fuente se lee para los
anchos declarados —`.a8`/`.a16`, y `rep`/`sep` bajo `.smart`—, siguiendo
los `.include` desde `main.s` y reproduciendo el cuerpo de cada macro donde
se usa. **Los inmediatos verifican esa lectura**: el tamaño con que `ca65`
armó cada uno tiene que ser el ancho que se leyó del fuente, y sobre el
runtime de hoy son cero los que no cuadran.

Cuatro chequeos; el README dice cómo mira cada uno y qué no ve:

1. **`pull-branch`**: desde cada `pl*`, por todos los caminos hasta que
   cada bandera que puso se vuelva a poner, un salto condicional que la
   mira. N y Z para `pla`/`plx`/`ply`/`plb`/`pld`; las cuatro para `plp`.
2. **`call-return`**: camina cada rutina desde su entrada —cada destino de
   `jsr`, `jsl` y `jsr (tabla, x)`, y los vectores— por todas las ramas y
   saltos, incluso hacia otras rutinas, y marca cada `rts`/`rtl`/`rti` que
   no corresponde a cómo la entró algún llamador.
3. **`stack`**: en la misma caminata, los bytes empujados desde la entrada,
   con el ancho de cada `pha`/`phx`. Lo que no se sigue —un bucle que
   empuja, `tcs`/`txs`, un salto por puntero— no es error: `--unfollowed`
   lo lista. Sobre el release son cuatro lugares: dos bucles que empujan
   (`big_palette_build`, `pic_tick`) y los dos `jsl` al trampolín en RAM
   del LZ2.
4. **`width`**: ver abajo.

Del lado de ABL: `rom/pruebas/herramientas/test_linter.py`, sobre los tres
cartuchos, y `rom/excepciones-del-linter.txt`.

### Lo que encontró en el runtime

**Tres declaraciones de ancho que no eran lo que corre** (chequeo 4), en su
commit: `op_var` después de `jsr random_next`, `medicine_use` después de
cada `jsr per_hundred` —las dos vuelven con A16, y el código lo sabe— y
`ba_t_sound`, que se entra con A16 (así la llaman los siete `jsl` de la
pelea) y heredaba el `.a8` del puente anterior. **No cambian un byte**: no
había ningún inmediato entre la declaración vieja y la siguiente. Eran la
trampa del encabezado de `main.s` esperando el primero que se agregue.
`git blame` cae en los commits de traducción; la intención la dicen los
comentarios de cada lugar ("the dividend, sixteen bits", "returns with
A16", "A16 the index"). Como no cambian la ROM, la prueba que los muestra
es la del linter: antes del arreglo daba esas 16 líneas.

**Excepciones**: doce `pull-branch` donde el salto mira a propósito lo que
se sacó —`pla` y `beq` es también la forma corta de preguntar si es
cero—, y la salida compartida de `slots_screen` (`close`), que saca la
dirección de retorno para llegar a lo que empujó su llamador, como dice su
comentario. Cada una con su porqué en el archivo.

**Ningún `jsl` contra `rts` ni pila desbalanceada** de verdad.

### El rojo que vi

Cuatro roturas a la vez, una por chequeo, y la prueba las marcó en los tres
cartuchos:

    event_routes.s:686  sin el `cmp #0` después del `plx` (el error histórico)
      "pull-branch: in `ev_route_frame`, `bne no_blocked`: `bne` looks at Z,
      and the last instruction to set it is the `plx` at event_routes.s:680"
    battle_bridges.s:96  el `rtl` de `ba_t_ppu` cambiado a `rts`
      "call-return: `ba_t_ppu` is entered with jsl (at menu_experience.s:113),
      and this path out of it is an `rts`, which pulls 2 bytes …"
    medicine.s:245  un `phx` de más al entrar a `k_in_x`
      "stack: `rts` leaves `k_in_x` with 2 bytes still pushed, by `phx` at
      medicine.s:245"
    audio_package.s:170  sin el `sep #$20` antes de `.a8` y `lda #3`
      "width: `lda` was assembled for a 8-bit A, and on the path from
      `upload_sample` A is 16 bits wide here: the CPU reads it with a
      different length"

La primera vez salieron además dos falsos: el `.align` de `header.s` y un
`.dword` de `mapdata.inc` leídos como código, porque `ca65` no les pone
tipo. Se arregló en su propio commit (la directiva de la línea decide) y la
segunda vez salieron sólo las cuatro. Todo vuelto atrás.

### El ancho: salió como chequeo

Medido sobre el release, con `--stats`:

* **inmediatos** (`lda #`, `ldx #`…): 4010 decididos, 0 mal; 210 sin decidir;
* **las otras instrucciones que dependen del ancho** (cargas, guardados,
  aritmética, empujes, transferencias): 13676 decididas, 0 mal; 460 sin
  decidir.
  Antes de los arreglos daba 8 mal, todas de las tres declaraciones;
* **llamadas** contra el ancho que el llamado declara en su entrada, para
  los registros que usa antes de ponerlos: 2606 decididas, 0 sin decidir.
  Antes, 8 mal: las siete de `ba_t_sound` y la de adentro.

Sin decidir es lo que viene después de un `xce`, de un `plp` sin su `php`
o de una llamada que vuelve con anchos distintos según el camino. Cero
falsos positivos después de lo de las macros —sus `.a8` de adentro, y los
`.repeat` adentro de una macro, que el `.dbg` no marca como de macro—, así
que va como chequeo y no como estudio.

## Los números

`just pruebas`: 1008 (1005 + los tres cartuchos de `test_linter.py`).
`just -f tools/justfile test`: 39. `cargo test -p goombario`: 5 + 8.
`abl.sfc` de `release`: `35c76500…`, el de la base: `NO_CACHE=1 just
cartuchos` antes y después de las declaraciones, y `just cartuchos` al final,
con los tres `.sfc` y los tres `.msu` byte por byte iguales. Ninguna golden se
movió. `main` no se movió mientras tanto (`a6ba9693`): no hubo nada que
mergear.

## Lo que queda

* El chequeo de `pull-branch` no sabe distinguir el salto que mira lo sacado
  a propósito del que quería mirar lo de antes: eso lo dice la excepción.
* Un bucle que empuja deja sin revisar la pila de toda su rutina (hoy dos).
* Una rutina que vuelve con N/Z de un `pl*` y un llamador que salta sobre eso
  después del `jsr` no se mira: el chequeo 1 no cruza llamadas.

## Al mergear

**Instalar `goombario` en el global**: `just -f tools/justfile install
goombario`, desde el checkout principal. Sin eso `test_linter.py` no
encuentra el ejecutable. Nada más: `cartridge` se instaló en el `bin/` local
sólo para armar con el runtime del worktree, y no cambió.
