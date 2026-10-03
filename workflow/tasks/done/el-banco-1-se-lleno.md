---
name: "El banco 1 se llenó"
description: "Después de los comunes de Picaflor y las imágenes grandes de Aguilucho, al banco 1 de release le quedan 131 B: mudar código al banco lejano para que las features siguientes tengan lugar"
type: refactor
assignee: taro
---

De taro, el 2026-10-02: "el refactor para liberar esos bancos". El banco 1
de `release` quedó con 131 B libres (`just espacio`), entre los comunes
automáticos y el `CallEvent` compartido (Picaflor) y las imágenes grandes
(Aguilucho). Es como lo que hizo Pirincho con las tablas del banco 0
(`testing/las-tablas-de-items-al-banco-1.md`), pero con código.

## Lo medido antes (2026-10-02, Pepitero, sobre `cb333da4`)

`just espacio`, banco 0 / banco 1:

    release                    1.063 B / 131 B
    test-special               1.081 B / 131 B
    test-encounter-every-step  1.077 B / 131 B

`abl.sfc` de `release`: `6643d2c1…`.

**`FAR` es el banco 1**: el `.cfg` lo carga en `BANK01`, `$01:8000`. No hay un
"banco lejano" aparte adonde mudar lo del banco 1: el código a mano tenía dos
bancos, `CODE` (el 0) y `FAR` (el 1), y los dos estaban llenos. Así que lo
primero fue **abrir un tercero**.

Lo que ocupa el banco 1, por archivo, con el `.dbg` (cada línea con su span):
la pelea son 15.589 B —`battle_scene.s` 5.261, `battle.s` 2.804,
`battle_skills.s` 2.253, `battle_troop.s` 1.548, `battle_run.s` 1.262,
`battle_victory.s` 1.123, `battle_loop.s` 953, `battle_items.s` 385—; después
`shop.s` 2.267, `msu_effects.s` 1.631, `level.s` 1.537,
`equipment_screen.s` 1.486, `big_picture.s` 1.346, `picture_far.s` 1.225,
`decompress.s` 1.189, y el resto por debajo del KB.

## El tercer banco de código: `FAR2`, en la mitad baja de `$C0`

Era el último lugar de datos de los 4 MB rápidos, y ningún cartucho lo usaba
(`release` deja libres las mitades bajas de `$C0` y `$C1`). Como mitad de
ExHiROM es rápida siempre, sin espejo: lo que vive ahí se entra con `jsl` a
su dirección, y no necesita la copia en los segundos 4 MB que tienen los
bancos 0 y 1. `banks::FAR2` en `rm2k-snes-cartridge`, y `just espacio` lo
muestra como "bank $C0".

El commit que lo abre no mueve la ROM: los tres cartuchos salen byte por byte
iguales, porque esa mitad estaba en ceros. `ld65` avisa que el segmento
`FAR2` no existe hasta que algo lo usa, en el commit siguiente.

## Lo mudado

**La pelea, del banco 1 a `FAR2`** (`222007f6`), con un commit antes
(`ad142a2c`) que pasa a `jsl` lo que llamaba afuera. Los ocho `battle*.s` de
la lista de arriba son un grupo cerrado: entre ellos se llaman con `jsr`, y
afuera sólo llamaban con `jsr` a cuatro cosas, que pasaron a `jsl`:

    exp_add              level.s         rts -> rtl; battle_loop.s con jsl
    gold_add             shop.s          rts -> rtl; shop.s y battle_victory.s con jsl
    battle_fade_showing  battle_fade.s   rts -> rtl; battle_run.s con jsl
    msu_data_seek/valid  msu1.s          entradas msu_data_seek_l y
                                         msu_data_valid_l; battle_scene.s
                                         las usa, msu_effects.s sigue con jsr

Los que entran a la pelea ya usaban `jsl f:` sin `+ FAST` —`battle_run`,
`ba_enemy_change`, `ba_show_hidden` (interpreter_shop_and_battle.s) y
`scene_cgram_restore` (enter_map.s)— y no cambiaron. El único `+ FAST` que
apuntaba adentro era el `jsl` a `scn_double`, desde la misma battle_scene.s.
Las tablas de la pelea ya se leían con `f:`, porque el banco de datos es
`$7E` mientras dura.

**Lo que cambia sin verse**: la pelea corría desde `$01`, la copia lenta del
banco 1, y ahora corre desde los 4 MB rápidos. Las goldens no se movieron.

**El paquete de audio, del banco 0 a `FAR2`** (`d09c4232`): `audio_package.s`
es lo más grande del banco 0 que no corre en cada cuadro —se llama al cargar
un mapa, al arrancar y al empezar un tema—, y corre a la misma velocidad,
porque el banco 0 corre desde `$80`. Cuatro entradas `_l` al final del
archivo, y sus llamadores pasan a `jsl`: `aram_clear_l` y `package_load_l`
(boot.s), `package_load_l` (enter_map.s), `package_load_done_l`
(battle_bridges.s) y `song_ensure_l` (music.s). Adentro llamaba a `dsp_pair`
con `jsr`, y pasó a `dsp_pair_l`, que ya existía.

**Cómo se buscaron los llamadores**: además del `grep` de cada rutina, un
script descartable que recorre el `.dbg` —cada línea de `tools/runtime/` con
su dirección— y marca todo `jsr`/`jmp` absoluto cuyo destino está en otro
banco, y toda lectura absoluta de una etiqueta de ROM fuera del banco 0. Dio
0 en la base, y 0 después de cada mudanza.

## Lo que quedó sin mudar

* **El resto del banco 1** no hacía falta: quedó con 14 KB libres. Lo más
  grande que sigue ahí —`shop.s`, `msu_effects.s`, `level.s`,
  `equipment_screen.s`, las imágenes— es frío y se podría mudar igual: la
  tienda y el equipo forman un grupo (`shop.s` llama a `equipment_screen.s`
  con `jsr`), y las imágenes otro (`picture_far.s` y `big_picture.s`).
* **Del banco 0, lo caliente**: `event_pages.s`, `music.s` (`irq_music`),
  `oam.s`, `vblank.s`, `event_routes.s`, `tint.s`, `hero.s`, `cells.s`. Corren
  en cada cuadro o en la interrupción, y llaman a todo con `jsr`.
* **Del banco 0, lo frío que no rinde**: las pantallas del menú (`menu.s`,
  `slots.s`, `items.s`, `title.s`) son frías, pero llaman a muchas rutinas del
  banco 0 —`title.s` a catorce—, y cada una pide un puente de cuatro bytes:
  `title.s` liberaría unos 240 B de 313. `save_game.s` (365 B) sí rinde
  —llama a una sola rutina afuera—, pero la llaman desde seis archivos.

## La regla

En el encabezado de `tools/runtime/main.s` (`598376c9`), que es donde la ve
quien agrega un archivo: qué va en `CODE`, en `FAR` y en `FAR2`; que un
subsistema va entero en un banco; que entre bancos es `jsl`/`rtl` con una
entrada `_l`; que a `FAR2` se entra **sin** `+ FAST`; y que nada de eso lo
revisa el ensamblador. El README del proyecto suma una línea en la sección de
ExHiROM que apunta ahí.

**Propuesta, sin hacer**: el script del `.dbg` como prueba de
`rom/pruebas/herramientas/`, para que "nada lo revisa" deje de ser cierto. Lee
el operando del fuente con una expresión regular, así que es heurístico.

## Los números

`just espacio`, antes y después:

    banco 0   release 1.063 -> 2.868 B; test-special 1.081 -> 2.886;
              test-encounter-every-step 1.077 -> 2.882
    banco 1   131 -> 14.204 B en los tres
    $C0       (no existía) -> 16.852 B libres de 32.768, en los tres

Los commits:

    f026d255  el tercer banco: los tres cartuchos byte por byte iguales
    ad142a2c  lo que la pelea llama afuera, con jsl
    222007f6  la pelea a FAR2
    d09c4232  el paquete de audio a FAR2
    598376c9  la regla en main.s y la prosa vieja: sólo comentarios, ROM igual
    d5013576  `bank_far2` en el JSON de rm2k-snes-space y en test_espacio.py

Cada commit que mueve la ROM, con `just pruebas` en verde —1000, y 1001 con
la prueba de espacio nueva— y las goldens idénticas. `abl.sfc` final:
`35c76500…`. `NO_CACHE=1 just cartuchos` da el mismo. `just -f tools/justfile
test`: 39. `cargo test -p rm2k-snes-cartridge`: en verde.
`test_musica_techos.py` y `test_cores.py` pasan dentro de `just pruebas`.

**Al mergear**: `just -f tools/justfile install cartridge` —cambió
`banks.rs` (el `.cfg`) y `rm2k-snes-space`—. Sin eso, el ensamblador global
no declara `FAR2` y el armado falla.
