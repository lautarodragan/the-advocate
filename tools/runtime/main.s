; ---------------------------------------------------------------------------
; The whole ROM, in a single assembly: this is the only thing `ca65` sees.
;
; The `.s` files next to this one **are not assembled on their own**: they are
; stretches of a single text, and `.include` pastes them in this order. Three
; things follow from that which you do not see by opening one of them:
;
; * **The order of the list is the order in the ROM.** Moving an `.include`,
;   or a `.proc` from one file to another, changes addresses and bytes;
;   splitting does not, because what reaches `ca65` is the same text. Until
;   2026-09-25 this was a single file of thirty-four thousand lines, and it
;   was split without changing a byte: that is why some files end with a
;   routine that belongs to another topic, and moving it is a ROM change that
;   gets verified on its own.
; * **Each file inherits the state of the previous one**: the `.a8`/`.i16`
;   widths and the segment. The `.segment` at the top of each one is written
;   for the reader, and it is the same one that was already in effect.
; * **Anonymous labels and the local labels of a `.proc` are resolved over the
;   pasted text**, so the script that did the split refused to cut inside a
;   block or between a `:+` and its `:`, and any new cut has to respect the
;   same.
;
; And two traps that hold for every file and have no line to live on:
;
; * **The width of A and of X/Y is state, and `ca65` believes it without
;   checking.** `.a8` and `.a16` do not describe: they dictate how each
;   immediate is emitted. A label that is jumped to from another width has to
;   declare its own —see `low` in `celdas.s`—, or the immediate comes out as
;   two bytes, the CPU in 8-bit mode reads one, and the leftover `$00` runs as
;   a `BRK`. The ROM goes off the rails, and neither the diff nor the
;   pixel-by-pixel comparison sees it, and bisecting with `rts` does not work
;   because it unbalances the stack: if a ROM goes off the rails for no
;   apparent reason, look here first. The same goes for transfers between
;   different widths —`tax` with a 16-bit X, `ldx` from a one-byte variable—,
;   which drag in the neighboring byte.
; * **There is no calling convention**: a `jsr` returns X and Y however suits
;   the routine. If an index has to survive the call —the interpreter's
;   bytecode cursor—, the caller saves it with `phy`, since it is the only one
;   that knows it is needed.
;
; What stays written here is what is not a subsystem: where the generated
; `.inc` files come in —the two bytecodes and the cartridge's data—. A new
; file is added to the list at the place it belongs in the ROM; the
; fingerprint in `tools/ensamblado/cartuchos.py` already covers all of
; `tools/runtime/`.
; ---------------------------------------------------------------------------

.p816
.smart

.include "registros.s"
.include "ram_lejana.s"
; The two bytecodes this ROM reads, generated from tools/protocol/: the events
; one, which `run_code` interprets, and the music stream, which
; `irq_music` reads. Each one is declared by a file that belongs neither to
; the side that emits the bytes nor to the side that reads them.
;
; The events one came inside mapdata.inc until 2026-09-14, which means an
; opcode's number arrived here inside a map's data; the music one was written
; by hand on both sides until 2026-09-15.
.include "event_opcodes.inc"
.include "music_opcodes.inc"

.include "musicdata.inc"
.include "mapdata.inc"

; The text area is eight cell rows, that is four lines of two rows each, and
; the composer's buffer is one line long. They go down here and not above
; because `WINDOW_TEXT_COLS` is emitted by the converter.
WINDOW_TEXT_LINES = WINDOW_TEXT_ROWS / 2
TEXT_BUF_BYTES = WINDOW_TEXT_COLS * 2 * 32

.include "pagina_cero.s"
.include "arranque.s"
.include "cargar_mapa.s"
.include "paginas_de_eventos.s"
.include "interprete.s"
.include "interprete_mensaje.s"
.include "interprete_condiciones.s"
.include "interprete_oro_e_items.s"
.include "interprete_tienda_y_pelea.s"
.include "interprete_efectos.s"
.include "interprete_movimiento.s"
.include "interprete_destellos.s"
.include "interprete_cronometro.s"
.include "interprete_musica.s"
.include "interprete_guardar.s"
.include "interprete_variables.s"
.include "interprete_grupo.s"
.include "interprete_game_over.s"
.include "interprete_mapa.s"
.include "interprete_teclas_y_esperas.s"
.include "interprete_camara_y_tinte.s"
.include "interprete_teletransporte.s"
.include "fundido_de_pelea.s"
.include "transicion_del_teletransporte.s"
.include "variables.s"
.include "tinte.s"
.include "grupo.s"
.include "ruta_del_heroe.s"
.include "cargar_graficos.s"
.include "rutas_de_eventos.s"
.include "tecla_de_accion.s"
.include "destello_de_personaje.s"
.include "eventos_caminando.s"
.include "partida.s"
.include "titulo.s"
.include "ranuras.s"
.include "menu.s"
.include "pantallas_de_texto.s"
.include "batalla_puentes.s"
.include "lluvia.s"
.include "msu1.s"
.include "paquete_de_audio.s"
.include "efectos_de_sonido.s"
.include "items.s"
.include "quietos_que_animan.s"
.include "imagen.s"
.include "animacion_de_batalla.s"
.include "giro_hacia_el_heroe.s"
.include "npcs.s"
.include "celdas.s"
.include "destello_de_pantalla.s"
.include "camara.s"
.include "ventana_del_mapa.s"
.include "mensajes.s"
.include "vblank.s"
.include "animacion_del_chipset.s"
.include "heroe.s"
.include "cronometro.s"
.include "oam.s"
.include "control.s"
.include "spc700.s"
.include "ram_baja.s"
.include "musica.s"
.include "banco1.s"
.include "nivel.s"
.include "medicina.s"
.include "equipo_desde_eventos.s"
.include "batalla.s"
.include "batalla_items.s"
.include "batalla_habilidades.s"
.include "game_over.s"
.include "batalla_lazo.s"
.include "batalla_tropa.s"
.include "batalla_victoria.s"
.include "batalla_escena.s"
.include "batalla_correr.s"
.include "banco_de_la_pantalla.s"
.include "encuentros.s"
.include "animacion_de_batalla_cuadros.s"
.include "descomprimir.s"
.include "pantalla_de_equipo.s"
.include "eleccion_de_actor.s"
.include "tienda.s"
.include "efectos_con_msu.s"
.include "lugar_y_tema_recordados.s"
.include "interprete_celdas.s"
.include "npcs_lejos.s"
.include "experiencia_en_el_menu.s"
.include "fin_del_juego.s"
.include "cabecera.s"
