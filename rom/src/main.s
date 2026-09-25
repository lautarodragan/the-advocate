; ---------------------------------------------------------------------------
; PoC de audio en Super Nintendo: reproduce un tema en loop, sin dibujar nada.
;
; El audio de la SNES lo maneja el SPC700, un procesador aparte con su propia
; memoria de 64 KB. El 65816 no puede tocar el DSP directamente: sólo puede
; hablarle al SPC700 por cuatro puertos.
;
; Al encender, el SPC700 corre una ROM interna que implementa un protocolo de
; carga. Lo usamos para meterle en memoria las muestras y un driver mínimo, y
; después ese driver se queda esperando pares (registro, valor) del DSP que le
; manda el 65816. O sea que toda la música la sigue manejando el 65816, igual
; que en la Mega Drive.
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
.include "batalla_lazo.s"
.include "batalla_tropa.s"
.include "batalla_escena.s"
.include "batalla_correr.s"
.include "banco_de_la_pantalla.s"
.include "encuentros.s"
.include "pantalla_de_equipo.s"
.include "tienda.s"
.include "cabecera.s"
