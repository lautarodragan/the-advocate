.segment "CODE"

; --- la batalla -----------------------------------------------------------------
;
; `EnemyEncounter`, abierto por `OP_BATTLE` desde el intérprete: como la
; tienda y como guardar, la pantalla bloquea adentro de la página, `vueltas` no
; avanza mientras se ve y **no cuesta ningún tick**. Lo que la diferencia de
; las otras dos es que el resultado **elige por dónde sigue la página**: el
; opcode lleva los tres destinos y acá se le asigna al cursor el que toque.
;
; Las reglas —daño, acierto, crítico, varianza, orden de turnos, huida— salen
; de easyrpg-player y están escritas dos veces: acá y en `tools/port/batalla.py`,
; que es lo que le permite a `pruebas/rpgmaker/test_batalla.py` predecir el número
; exacto que cada HP va a tener. La pantalla es de texto, sobre negro.
;
; **El código de la pelea no vive en el banco 0**: son unos dos kilobytes y en
; el banco 0 quedaban trescientos bytes. Vive en RODATA —ver `batalla_correr`,
; en `batalla_correr.s`— y se entra con `jsl`. De allá para acá no se puede
; volver con `jsr`, que no cambia el banco de programa, así que las rutinas del
; banco 0 que la pelea necesita se llaman por estos puentes de cuatro bytes.
; El banco de datos sigue siendo el 0 en los dos lados, así que un puente no
; tiene que tocarlo: lo único que hace es cambiar de banco de programa y
; volver.
;
; **Cada puente repone el banco de datos**, que del otro lado es $7E. No es un
; detalle: `eq_parametro` lee `actor_params` y `ranura_ppu_prender` escribe
; BG2SC, las dos con direccionamiento absoluto, y con el banco en $7E la
; primera leería WRAM y la segunda escribiría en la RAM en vez del PPU. Costó
; una tarde: los tres parámetros de cada actor salían en 999.
;
; `phk` acá empuja el banco de este código, que es el 0 porque el `jsl` llega
; con una dirección de $00xxxx.
ba_t_vblank:
    phb
    phk
    plb
    jsr wait_vblank
    plb
    rtl
ba_t_pad:
    phb
    phk
    plb
    jsr read_pad
    plb
    rtl
ba_t_subir:
    phb
    phk
    plb
    jsr pant_subir
    plb
    rtl
ba_t_limpiar:
    phb
    phk
    plb
    jsr pant_limpiar
    plb
    rtl
ba_t_texto:
    phb
    phk
    plb
    jsr pant_texto
    plb
    rtl
ba_t_numero:
    phb
    phk
    plb
    jsr pant_numero
    plb
    rtl
ba_t_glifo:
    phb
    phk
    plb
    jsr pant_glifo
    plb
    rtl
ba_t_banco:
    phb
    phk
    plb
    jsl f:items_banco_subir
    plb
    rtl
ba_t_ppu:
    phb
    phk
    plb
    jsr ranura_ppu_prender
    plb
    rtl
ba_t_param:
    phb
    phk
    plb
    jsl f:eq_parametro
    plb
    rtl
; Los dos del audio, que son de esta vuelta: un efecto de sonido —A16 el
; índice en `sonido_tabla`, $FFFF ninguno— y el tema, con A8.
ba_t_sonido:
    phb
    phk
    plb
    jsr sonido_tocar
    plb
    rtl
ba_t_bgm:
    phb
    phk
    plb
    jsr batalla_bgm
    plb
    rtl

; Y los dos de la tienda y el equipo, que también viven afuera: la lista de
; ítems del inventario y armarla. `ti_lista_venta` y `eq_de_lista` las llaman.
ba_t_lista:
    phb
    phk
    plb
    jsr item_de_lista
    plb
    rtl
ba_t_armar:
    phb
    phk
    plb
    jsr items_armar_lista
    plb
    rtl

; `correr_codigo` para quien vive afuera del banco 0 y ya puso el contexto:
; `comunes_del_equipo`, en equipo_desde_eventos.s.
correr_codigo_largo:
    jsr correr_codigo
    rtl

; Un tramo de la página de tropa que la pelea tiene a medio correr: hasta que
; pide un mensaje o termina. Es `Game_Interpreter_Battle`, y **es el mismo
; intérprete de los mapas**, `correr_codigo`: lo que cambia es de dónde sale el
; contexto.
;
; El del mapa se guarda en la pila y vuelve al final, como en `paralelos_tick`,
; y no es una precaución: una pelea se abre desde **adentro** del
; intérprete —`op_battle`— y al volver sigue leyendo la página del mapa con
; el `cod_ptr` y el Y que tenía. El de la tropa vive en la RAM lejana entre un
; tramo y otro, porque un mensaje la frena varios cuadros.
;
; `par_ev` en `PAR_PELEA` es lo que le dice a `op_message` que el mensaje es de
; la pelea. Los opcodes que corren acá son sólo los de `TROPA_COMANDOS`, en
; eventos.py: ningún otro sabe que no hay mapa.
ba_t_pagina:
    phb
    phk
    plb
    rep #$20
.a16
    lda ev_cur
    pha
    lda cod_ptr
    pha
    lda f:BAT_LARGO + BA_PAG_CUR
    sta ev_cur
    lda f:BAT_LARGO + BA_PAG_COD
    sta cod_ptr
    sep #$20
.a8
    lda cod_ptr + 2
    pha
    lda ev_activo
    pha
    lda par_ev
    pha
    lda #^tropa_codigo
    sta cod_ptr + 2
    lda #PAR_PELEA
    sta par_ev
    lda #1
    sta ev_activo
    jsr correr_codigo
    lda ev_activo
    sta f:BAT_LARGO + BA_PAG_ACT
    rep #$20
.a16
    lda ev_cur
    sta f:BAT_LARGO + BA_PAG_CUR
    sep #$20
.a8
    pla
    sta par_ev
    pla
    sta ev_activo
    pla
    sta cod_ptr + 2
    rep #$20
.a16
    pla
    sta cod_ptr
    pla
    sta ev_cur
    sep #$20
.a8
    plb
    rtl

; El paquete de audio A —el de la pelea al entrar, el del mapa al salir—, con
; la música callada primero.
;
; Callar antes no es un detalle: `paquete_cargar` deja **quietas** las muestras
; del tema que dice estar sonando, y ésas son justamente las que hay que
; desalojar para hacerle lugar al paquete nuevo. Es lo mismo que hace
; `tema_asegurar` antes de rearmar.
;
; El índice viene en **X y de dieciséis bits**, no en A: el paquete de la pelea
; va detrás de los de los mapas, así que con los 328 del juego entero no entra
; en un byte —y `mapa_actual`, que es lo que se pasa al salir, tampoco—.
;
; Con `BA_PAQUETE` en $FFFF —una ROM sin peleas— no hay nada que cargar; no
; puede pasar, porque acá se llega desde `op_battle`, pero el opcode existe
; en el bytecode de todas.
.proc batalla_audio_cargar
.a8
.i16
    cpx #$FFFF
    beq listo
    phx
    lda #$FF
    jsr batalla_bgm             ; callar, para que nada quede fijo
    plx
    rep #$20
.a16
    txa
    sta f:PAQ_MAPA
    sep #$20
.a8
    jsr paquete_cargar_ya
listo:
    rts
.endproc

; El tema de la pelea: A es el índice, o $FF para dejarla callada. Lo llaman
; `op_battle` —al entrar y al salir— y la pelea al ganar, por el puente de
; arriba.
;
; Callar no es `FadeOutBGM`: es lo mismo que hace `tema_asegurar` antes de
; rearmar el paquete, o sea soltar las ocho voces y poner `music_apagada`. Un
; mapa sin música es lo normal en este juego —los primeros no traen y la
; prende un `PlayBGM`—, así que volver de una pelea a un mapa callado tiene
; que callar de verdad y no dejar sonando el tema de batalla.
.proc batalla_bgm
.a8
.i16
    cmp #$FF
    beq callar
    jmp music_start
callar:
    php
    sei
    lda #1
    sta music_apagada
    lda #$FF
    ldx #SE_KOF
    jsr dsp_par                 ; las ocho voces sueltan
    plp
    rts
.endproc

