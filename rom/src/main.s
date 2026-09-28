; ---------------------------------------------------------------------------
; La ROM entera, en un solo ensamblado: esto es lo único que ve `ca65`.
;
; Los `.s` de al lado **no se ensamblan solos**: son tramos de un solo texto,
; y `.include` los pega en este orden. De ahí salen tres cosas que no se ven
; abriendo uno:
;
; * **El orden de la lista es el orden en la ROM.** Mover un `.include`, o un
;   `.proc` de un archivo a otro, cambia direcciones y bytes; partir no, porque
;   lo que llega a `ca65` es el mismo texto. Hasta el 2026-09-25 esto era un
;   solo archivo de treinta y cuatro mil líneas, y se partió sin cambiar un
;   byte: por eso algunos archivos terminan con una rutina que es de otro
;   tema, y moverla es un cambio de ROM que se verifica aparte.
; * **Cada archivo hereda el estado del anterior**: los anchos `.a8`/`.i16` y
;   el segmento. El `.segment` del principio de cada uno está escrito para el
;   que lee, y es el mismo que ya traía.
; * **Las etiquetas anónimas y las locales de un `.proc` se resuelven sobre el
;   texto pegado**, así que el script que partió se negó a cortar adentro de
;   un bloque o entre un `:+` y su `:`, y cualquier corte nuevo tiene que
;   respetar lo mismo.
;
; Y dos trampas que valen para todos los archivos y no tienen una línea donde
; vivir:
;
; * **El ancho de A y de X/Y es estado, y `ca65` lo cree sin comprobarlo.**
;   `.a8` y `.a16` no describen: mandan cómo se emite cada inmediato. Una
;   etiqueta a la que se salta desde otro ancho tiene que declarar el suyo
;   —ver `baja` en `celdas.s`—, o el inmediato sale de dos bytes, la CPU en
;   ocho lee uno, y el `$00` que sobra se ejecuta como `BRK`. La ROM se va por
;   la ventana, no lo ve el diff ni la comparación pixel a pixel, y bisecar
;   con `rts` no sirve porque desbalancea la pila: si una ROM se va por la
;   ventana sin razón aparente, mirar primero acá. Lo mismo las
;   transferencias entre anchos distintos —`tax` con X de 16 bits, `ldx` de
;   una variable de un byte—, que se llevan el byte de al lado.
; * **No hay convención de llamada**: un `jsr` devuelve X e Y como le
;   convenga a la rutina. Si un índice tiene que sobrevivir a la llamada —el
;   cursor del bytecode del intérprete—, lo guarda con `phy` el que llama, que
;   es el único que sabe que hace falta.
;
; Lo que se queda escrito acá es lo que no es un subsistema: dónde entran los
; `.inc` generados —los dos bytecodes y los datos del cartucho—. Un archivo
; nuevo se agrega a la lista en el lugar que le toca en la ROM; la huella de
; `tools/ensamblado/cartuchos.py` ya cubre todo `rom/src/`.
; ---------------------------------------------------------------------------

.p816
.smart

.include "registros.s"
.include "ram_lejana.s"
; Los dos bytecodes que esta ROM lee, generados desde tools/protocol/: el de los
; eventos, que interpreta `correr_codigo`, y el del stream de música, que lee
; `irq_musica`. Cada uno lo declara un archivo que no es ni del que emite los
; bytes ni del que los lee.
;
; El de eventos venía adentro de mapdata.inc hasta el 2026-09-14, o sea que el
; número de un opcode llegaba acá dentro de los datos de un mapa; el de música
; estaba escrito a mano de los dos lados hasta el 2026-09-15.
.include "event_opcodes.inc"
.include "music_opcodes.inc"

.include "musicdata.inc"
.include "mapdata.inc"

; El área de texto son ocho filas de celda, o sea cuatro renglones de a dos, y
; el buffer del compositor mide un renglón. Van acá abajo y no arriba porque
; `VENTANA_TEXTO_COLS` lo emite el conversor.
VENTANA_LINEAS_TEXTO = VENTANA_TEXTO_FILAS / 2
TEXTO_BUF_BYTES = VENTANA_TEXTO_COLS * 2 * 32

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
.include "tienda.s"
.include "efectos_con_msu.s"
.include "lugar_y_tema_recordados.s"
.include "interprete_celdas.s"
.include "npcs_lejos.s"
.include "experiencia_en_el_menu.s"
.include "fin_del_juego.s"
.include "cabecera.s"
