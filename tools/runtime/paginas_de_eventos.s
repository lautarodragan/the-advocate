.segment "CODE"

; --- the event interpreter -------------------------------------------------
;
; RM2k keeps the highest-numbered page whose conditions are all met. Pages
; come grouped by event and in order, so a single pass is enough: the last one
; that met them is remembered, and when the event changes, whichever was left
; is executed.
;
; Only the autostart ones are run. The touch ones are already covered by the
; doors, and the button ones need a button to press.

; The fields of the page at page_ofs, into variables.
.proc read_page
.a8
.i16
    ldy page_ofs
    rep #$20
.a16
    lda [page_ptr], y            ; +0  which event it belongs to
    sta pg_event
    sep #$20
.a8
    iny
    iny
    iny
    lda [page_ptr], y            ; +3  what triggers it. One byte at a time: reading it two
    sta pg_trigger              ;     at a time would take the next switch along with it
    iny
    rep #$20
.a16
    lda [page_ptr], y            ; +4  the switch it requires, or 0
    sta pg_sa
    iny
    iny
    lda [page_ptr], y            ; +6  the second one, or 0
    sta pg_sb
    iny
    iny
    lda [page_ptr], y            ; +8  its code: the low 16 bits
    sta pg_code
    sep #$20
.a8
    iny
    iny
    lda [page_ptr], y            ; +10 and its bank
    sta pg_code + 2
    iny
    lda [page_ptr], y            ; +11 the actor it requires in the party, or 0
    sta pg_actor
    iny
    lda [page_ptr], y            ; +12 its layer
    sta pg_layer
    iny
    lda [page_ptr], y            ; +13 the flags of its own move route
    sta pg_flags
    iny
    lda [page_ptr], y            ; +14 its frequency
    sta pg_freq
    iny
    lda [page_ptr], y            ; +15 the page's speed
    sta pg_speed
    iny
    lda [page_ptr], y            ; +16 the commands of its own move route
    sta pg_route
    iny
    lda [page_ptr], y
    sta pg_route + 1
    iny
    lda [page_ptr], y
    sta pg_route + 2
    iny
    lda [page_ptr], y            ; +19 how many
    sta pg_route_n
    iny
    lda [page_ptr], y            ; +20 what the page draws, for events that
    sta pg_tile                 ;     change graphic: the tile,
    iny
    lda [page_ptr], y            ; +21 the attributes with palette and priority,
    sta pg_attr
    iny
    lda [page_ptr], y            ; +22 the pose, with bit 7 if there is a graphic,
    sta pg_pose
    iny
    lda [page_ptr], y            ; +23 and its tile's passability bits, or $FF
    sta pg_pass
    rts
.endproc

; The active page of each event and, with it, the move route of its own that
; is due. It is `Game_Map::Refresh` with `Game_Event::SetupFromPage`: on
; loading the map and every time a switch or the party changes. An event
; whose active page is the same as before is left alone, and its route goes on
; where it was; one whose page changed loads the new one's route from the
; start, with the turn's wait before the first command; and one whose new page
; has no route is left with no commands. The page's speed stays in
; `vel_por_ev` for forced move routes.
;
; It is two passes and not one loop inside the other: the page table is walked
; only once noting each event's winner, and then events are looked at one by
; one. With events times pages it cost more than a frame, and a frame lost on
; a switch delays everything that comes after by a frame.
; `Game_Map::Refresh` whole: choose the active pages and apply them.
.proc page_routes
.a8
.i16
    jsr pick_pages
    jmp apply_pages
.endproc

; Like `pick_pages`, but looking **only** at events with autostart pages.
;
; It is what the refresh from inside the command loop runs, and it is the
; only thing that refresh needs to do on the spot: what the next command may
; end up looking at is which event has an active autostart. On map 2 that is
; four pages out of sixty-three, against the twenty-three the full one looks
; at. The full one runs anyway, at the start of the next frame.
.proc pick_autostart
.a8
.i16
    lda #1
    sta only_auto
    jmp pick_with_filter
.endproc

; The first half: which page stays active in each event, and along the way
; each one's `FLAG_AUTO`.
.proc pick_pages
.a8
.i16
    stz only_auto
    jmp pick_with_filter
.endproc

; The body of both, with `only_auto` saying which one it is.
.proc pick_with_filter
.a8
.i16
    ; `FLAG_AUTO` is not cleared with a separate loop but on each event's first
    ; page, further down: a hundred and twenty iterations on every refresh
    ; cost the whole frame when the refresh landed on something expensive.
    lda only_auto
    beq vaciar_todo
    rep #$20
.a16
    lda #$FFFF
    sta rp_ev_prev
    bra sin_vaciar              ; the short pass does not clobber the routes' data
.a8
vaciar_todo:
    rep #$20
.a16
    ldx #$0000
    lda ev_total
    asl a
    sta rp_ev_prev               ; the limit in bytes, borrowed for a moment
vaciar:
    lda #$FFFF
    sta pick_by_ev, x
    inx
    inx
    cpx rp_ev_prev
    bne vaciar
    lda #$FFFF
    sta rp_ev_prev               ; and now, "no event seen yet"
.a16
sin_vaciar:
    ldx map_ofs
    lda f:mapa_tabla + M_PAGINA_COUNT, x
    bne hay_paginas
    jmp sin_paginas             ; too far for a short branch
hay_paginas:
    sta pages_left
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta page_ptr
    stz page_ofs
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta page_ptr + 2
recorrer:
    ; Only the pages of events that have some page with its own route, or a
    ; graphic that follows the page, or some autostart: bits 5, 6 and 7 of +13
    ; say so, and only that byte is read. With every page read whole this cost
    ; more than a frame, and the frame was lost.
    ;
    ; The three things are resolved in **a single** walk on purpose. With the
    ; autostart one separate —which is how it was born— the refresh made two
    ; rounds and lost the frame again: it looked like the `snes-pan` tint
    ; arriving one late.
    rep #$20
.a16
    lda page_ofs
    clc
    adc #13
    tay
    sep #$20
.a8
    ; With A and not with an `ldx`: X is 16 bits and would also take
    ; `auto_n`, the next byte, so with an autostart running the full pass
    ; would filter like the short one.
    lda only_auto
    beq filtro_completo
    lda [page_ptr], y
    and #$80                    ; the short pass: only autostart pages
    bra con_filtro
filtro_completo:
    lda [page_ptr], y
    and #$E0
con_filtro:
    bne mirar_pagina
    jmp siguiente               ; the walk grew and no longer fits in a beq
mirar_pagina:
    jsr read_page
    ; The first page of an event with autostart pages clears its `FLAG_AUTO`:
    ; the last of its pages that meets its conditions sets it again, further
    ; down. An event's pages come together, so checking whether it changed is
    ; enough.
    lda pg_flags
    and #$80
    beq no_es_auto
    rep #$20
.a16
    lda pg_event
    cmp rp_ev_prev
    beq mismo_ev16
    sta rp_ev_prev
    tax
    sep #$20
.a8
    cpx #EV_MAX
    bcs no_es_auto
    lda ev_flags, x
    and #FLAG_AUTO
    beq ya_apagada
    dec auto_n
ya_apagada:
    ; **Both** bits, and the last page that meets its conditions sets them
    ; again. The waiting one too: if no page of the event qualifies, it is left
    ; with no active page and the mark has to go, which is the
    ; `ClearWaitingForegroundExecution` that `RefreshPage` does when it finds
    ; none. Leaving it set, the page that had just finished started again: in
    ; the opening cutscene that restarted the whole scene at frame 692.
    jsr unmark_waiting     ; the waiting one, with its count
    stz ev_flags, x             ; and the autostart one, whose count already went down
    bra no_es_auto
.a16
mismo_ev16:
    sep #$20
.a8
no_es_auto:
    jsr conditions_ok
    beq no_cumple
    ; It qualifies, so for now it is its event's active page. If the event
    ; has autostart pages, this is where it is decided whether the active one
    ; is one: writing on every qualifying page leaves in the end what the last
    ; one says, which is the one that wins.
    lda pg_flags
    and #$80
    beq sin_auto
    ldx pg_event
    cpx #EV_MAX
    bcs sin_auto
    lda ev_flags, x
    and #FLAG_AUTO
    beq sigue_apagada
    dec auto_n
sigue_apagada:
    lda ev_flags, x
    and #FLAG_WAIT            ; cleared, and set again below if due
    sta ev_flags, x
    lda pg_trigger
    cmp #TRIGGER_AUTOMATICO
    bne no_gana_una_auto
    lda pg_code
    ora pg_code + 1
    ora pg_code + 2
    beq no_gana_una_auto        ; did not compile: nothing to start
    lda ev_flags, x
    ora #FLAG_AUTO
    sta ev_flags, x
    inc auto_n
    jsr mark_waiting        ; still autostart: the mark comes back
    bra sin_auto
no_gana_una_auto:
    ; The winner is not autostart, so the event **stops** waiting. It is
    ; written on every qualifying page and the last one wins, which is the
    ; active one; by marking and not unmarking, an event's page 0 left the
    ; mark set even if page 1 won. It is the `ClearWaitingForegroundExecution`
    ; that `Game_Event::RefreshPage` does when it changes page.
    jsr unmark_waiting
sin_auto:
    ; The active page is noted for all three cases, not only for the route or
    ; graphic ones: `start_waiting` reads it from here instead of walking
    ; the map's pages again. On map 2 that is sixty-three pages for each page
    ; that starts, and the frame was lost. The second pass, which is the one
    ; that touches routes and graphics, skips the ones without those bits.
    rep #$20
.a16
    lda pg_event
    asl a
    tax
    lda page_ofs
    sta pick_by_ev, x          ; the last one that qualifies wins
    sep #$20
.a8
    bra siguiente
no_cumple:
    lda pg_flags
    and #$60
    bne con_rutas
    jmp siguiente               ; autostart only: it was already cleared above
con_rutas:
    ; An event with routes and no qualifying page yet: $FFFE, so the second
    ; pass can tell it apart from those without routes.
    rep #$20
.a16
    lda pg_event
    asl a
    tax
    lda pick_by_ev, x
    cmp #$FFFF
    bne ya_tiene
    ; No qualifying page, for now: $FFFE, or $FFFD if the graphic follows
    ; the page, which is the one that has to be hidden.
    lda #$FFFE
    sta pick_by_ev, x
    sep #$20
.a8
    lda pg_flags
    and #$20
    beq ya_tiene8
    rep #$20
.a16
    lda #$FFFD
    sta pick_by_ev, x
    sep #$20
.a8
ya_tiene8:
    rep #$20
.a16
ya_tiene:
    sep #$20
.a8
siguiente:
    rep #$20
.a16
    lda page_ofs
    clc
    adc #PAGINA_BYTES
    sta page_ofs
    dec pages_left
    sep #$20
.a8
    beq listo_eligiendo
    jmp recorrer                ; the walk grew and no longer fits in a bcc
listo_eligiendo:
    rts
sin_paginas:
    sep #$20
.a8
    rts
.endproc

; The second half: each event with the route and graphic of its active page.
; It walks the map's events reloading OAM rows and move route slots, so it is
; the expensive one: doing it in the middle of a frame cost the whole frame
; on map 2. That is why the mid-command refresh leaves it for the start of
; the next frame, where nothing changes: what it touches is not seen until it
; is drawn.
.proc apply_pages
.a8
.i16
    ; The turn first, with the new pages already chosen and before the rows
    ; are rewritten: see `turn_check` and `turn_restore`.
    jsr turn_check
    ; The pointer to the pages is rebuilt here and not inherited from
    ; `pick_pages`: a whole frame may have passed between the two.
    ldx map_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta page_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta page_ptr + 2
    stz pair_n                   ; the list of parallels is rebuilt from scratch
    stz rp_ev
    stz rp_ev + 1
cada_evento:
    rep #$20
.a16
    lda rp_ev
    cmp ev_total
    bcc :+
    jmp fin16                   ; far for a short branch
:
    asl a
    tax
    lda pick_by_ev, x
    cmp #$FFFF
    bne :+
    jmp proximo                 ; no routes of its own: nothing to look at
:
    cmp #$FFFE
    bne :+
    jmp sin_activa16            ; with routes, and no qualifying page
:
    cmp #$FFFD
    bne :+
    jmp esconder16              ; with a page graphic, and none: it is hidden
:
    sta page_ofs
    sep #$20
.a8
    jsr read_page
    ; If the winner is parallel, the event goes into the list that
    ; `parallel_tick` runs. It is built here and not every frame because
    ; which page is active only changes on a refresh, and walking the hundred
    ; and twenty events every frame is exactly what this refresh exists to
    ; avoid.
    lda pg_trigger
    cmp #TRIGGER_PARALELO
    bne no_es_paralela
    lda pg_code
    ora pg_code + 1
    ora pg_code + 2
    beq no_es_paralela          ; did not compile: nothing to run
    jsr record_parallel
no_es_paralela:
    lda pg_flags
    and #$60
    bne con_ruta_o_grafico
    jmp proximo                 ; autostart only: the note is for something else
con_ruta_o_grafico:
    jsr page_graphic       ; what the page draws, to the NPC's row
    lda rp_ev
    jsr event_slot       ; X = its slot, or $FFFF
    lda pg_flags
    and #$01
    beq sin_ruta
    cpx #$FFFF
    beq nueva
    rep #$20
.a16
    lda route_ev + 20, x
    cmp page_ofs
    sep #$20
.a8
    bne :+
    jmp proximo                 ; the same page as before: it goes on where it was
:
    bra cargar
nueva:
    lda rp_ev
    jsr turn_per_route
    jsr free_slot
    cpx #$FFFF
    bne :+
    jmp proximo                 ; no room: it stays still
:
    lda rp_ev
    sta route_ev + 0, x
    jsl f:slot_record + FAST
    stz route_ev + 6, x
    stz route_ev + 7, x
    lda #ROUTE_EV_NO_FACE
    sta route_ev + 8, x
    stz route_ev + 12, x
    stz route_ev + 13, x
    lda #1
    sta route_ev + 10, x
    stz route_ev + 11, x
    stz route_ev + 22, x
    stz route_ev + 23, x
cargar:
    phx
    lda rp_ev
    jsr turn_per_route           ; with a route, the route decides where it faces
    plx
    jsr load_page_into_slot
    jmp proximo
sin_ruta:
    cpx #$FFFF
    bne :+
    jmp proximo
:
    jsr remove_page_from_slot
    jmp proximo
.a16
esconder16:
    sep #$20
.a8
    lda rp_ev
    jsr hide_npc
    jmp proximo
.a16
sin_activa16:
    sep #$20
.a8
    lda rp_ev
    jsr event_slot
    cpx #$FFFF
    bne :+
    jmp proximo
:
    jsr remove_page_from_slot
proximo:
    rep #$20
.a16
    inc rp_ev
    sep #$20
.a8
    jmp cada_evento
.a16
fin16:
sin_paginas:
    sep #$20
.a8
    rts
.endproc

; What in `Game_Map::Update` runs **before** the player: the pending refresh
; and `UpdateMapEvents` —`game_map.cpp:1259` and `:1274`, against the
; `game_player->Update()` at `:1288`—.
;
; It is split from `events_tick` precisely for that: the foreground falls on
; the other side of the hero, and that way what a step queues is handled in
; the same frame. See the main loop.
.proc map_events
.a8
.i16
    ; The pending refresh, before everything: it is when `Game_Map::Update`
    ; looks at `GetNeedRefresh`.
    lda refresh
    ora refresh_frame         ; or one from inside the command loop, which
    beq sin_refresco            ; did the short pass and left this one owed
    stz refresh
    stz refresh_frame
    jsr page_routes         ; which also rebuilds each event's `FLAG_AUTO`:
                                ; the active page changed
sin_refresco:
    ; `Game_Event::CheckEventAutostart`, which hangs off
    ; `Game_Event::UpdateNextMovementAction` —`game_event.cpp:409`— and that is
    ; why it runs in here: every event with an active autostart page is left
    ; waiting, once per frame and **before** the interpreter. Marking it later
    ; —when a page ends— moved the ones that get activated in the middle of
    ; another one a frame earlier.
    ;
    ; `auto_n` is there so the loop over a hundred and twenty does not run
    ; when there are none, which is almost always: running it anyway lost the
    ; frame right where something expensive landed, like the `snes-pan` tint.
    lda auto_n
    beq sin_automaticas
    jsr wait_autostart
sin_automaticas:
    ; The parallels, which are the other half of `UpdateMapEvents`
    ; —`game_event.cpp:590`—: they run before the hero, before the message and
    ; before the foreground. That is, a parallel event keeps running with a
    ; text box open and with another page in progress, which is exactly what
    ; it exists for.
    jmp parallel_tick
.endproc

; One frame of the foreground interpreter, from the main loop:
; `Game_Map::UpdateForegroundEvents` —`game_map.cpp:1310`— with the
; `UpdateMessage` at `:1297` stuck in front.
;
; This is where the fundamental change was: before, `enter_map` ran all the
; pages in one go, with the screen off, and came back with everything done.
; Time was collapsed —waits were skipped, and what happened before a teleport
; was never seen— and that is why none of it could be verified.
;
; A teleport is handled here and not inside the interpreter: calling
; `enter_map` from there would be recursion, and two maps pointing at each
; other would make it infinite. The jump cap stays for the same reason.
.proc events_tick
.a8
.i16
    rep #$20
.a16
    lda ev_waiting
    beq sin_espera
    dec a
    sta ev_waiting
    sep #$20
.a8
    rts
sin_espera:
.a16
    ; it arrives at sixteen; the `sep` below shrinks it
    sep #$20
.a8

    ; With a message on screen the page stays blocked, which is what
    ; `Game_Message` does. Everything else goes on: the hero's forced move
    ; route walks and the camera follows him, because in easyrpg's
    ; `game_player.cpp` `UpdateMoveRoute` runs **before** the
    ; `IsMessageActive` guard. In this game there are 186 pages where that
    ; happens, and the first one is on map 1.
    ; An open choice overrides the message: the window is the same but A does
    ; not close it, it resolves it.
    lda pick_active
    beq sin_eleccion
    jsr choice_tick
    bne sin_mensaje             ; it chose: the page goes on this same frame
    rts
sin_eleccion:
    lda msg_open
    ora msg_state              ; also while it is being composed
    beq sin_mensaje
    ; The `\|` pause, if the box has one. It is counted **from when the page
    ; asked for the message** and not from when the window finished composing:
    ; that way it does not depend on how long composing takes, which goes from
    ; nine to nineteen frames depending on the text. With a pause of 61 the
    ; composing finishes long before, so the screen shows the same thing.
    ; **A does not skip it**: in `Window_Message::Update` the
    ; `if (wait_count > 0)` goes before `WaitForInput()`, so while the pause
    ; runs the button is not looked at. That is why it goes at the very top
    ; and not after the edge.
    rep #$20
.a16
    lda f:FAR_MSG_PAUSE
    beq sin_pausa
    dec a
    sta f:FAR_MSG_PAUSE
    sep #$20
.a8
    rts
.a16
sin_pausa:
    sep #$20
.a8
    lda f:FAR_MSG_AUTO
    beq espera_boton
    ; The `\^`: the box closes by itself, without anyone pressing anything.
    ; The composer is turned off too, and it is not theoretical: a box with
    ; `\^` and no pause closes before it finishes composing, and without this
    ; `flush_video` would turn on the window of a message already closed.
    lda #0
    sta f:FAR_MSG_AUTO
    stz msg_state
    stz msg_upload
    stz msg_open
    bra sigue
espera_boton:
    lda msg_open
    beq no_avanza               ; has not finished composing yet
    lda pad_a
    beq no_avanza               ; nobody pressed: the message stays
    lda pad_a_prev
    bne no_avanza               ; it was already held: not an edge
    stz msg_open             ; and with that `flush_video` turns off the HDMA: closing
                                ; the window does not write a single byte of VRAM
    ; And the edge is consumed, like B's in the choice. If the message was a
    ; parallel's there is no page to go on, so this same frame falls into
    ; `try_action` with A still "just pressed" and talked to whatever event
    ; the hero had in front of him. In RM2k the message stays active some eight
    ; more frames, while the close animates (easyrpg
    ; `window_message.cpp:379-403`), and with a message active the hero does
    ; not look for events (`game_player.cpp:297`). It is enforced by
    ; `test_la_a_que_cierra_el_
    ; mensaje_no_le_habla_al_de_enfrente`.
    lda pad_a
    sta pad_a_prev
sigue:
    ; And the page goes on **in this same frame**, falling into the usual
    ; `jsr run_code`. Closing here and resuming the next frame would cost
    ; a frame to every page that closes a message.
    bra sin_mensaje
no_avanza:
    rts
sin_mensaje:

    lda ev_active
    bne corriendo
    ; No page half run: take the one of the first event that is waiting.
    lda waiting_n
    bne hay_esperando

    ; Nothing running and nothing waiting: the player has control, so the
    ; chain of teleports is over and the budget is replenished.
    ;
    ; Before, only `enter_map` replenished it, and by then the only thing
    ; calling it was a **door**: a `Teleport` command loads the map through
    ; `enter_map_no_events`, which does not touch it. So eight teleports
    ; spent the budget for the whole game and from the ninth on the
    ; `beq nada` below dropped them **silently**. The whole opening is
    ; chained teleports and has almost no doors: by the time map 4's
    ; dispatcher wanted to send the player to Talan's pad there were none
    ; left, the jump was lost, and since its page is autostart and its switch
    ; stays on it started again by itself forever. taro saw it on 2026-09-07
    ; as an empty map there was no way out of, with the music fading out and
    ; starting again in a loop; the RAM dump said `map_current` = 4 with event
    ; 1 running.
    lda #JUMPS_MAX
    sta jumps_left

    ; The queue is empty, so the edge on A is for talking. In RM2k it is the
    ; same button that closes a message and that confirms, and the order
    ; matters: with a message open the player is not updated —above, it exits
    ; through `no_avanza`— so he cannot talk to anyone while reading.
    ;
    ; And only with the hero standing still: `CheckActionEvent` hangs off the
    ; `if (IsStopping())` in `Game_Player::UpdateNextMovementAction`.
    lda pad_a
    beq nothing
    lda pad_a_prev
    bne nothing                    ; it was already held: not an edge
    lda step_left
    bne nothing                    ; no talking in the middle of a step
    ; The hero's forced move route is checked inside: see `try_action`.
    jsr try_action
    beq nothing
    ; It marked an event: it starts this same frame.
hay_esperando:
    jsr start_waiting
    beq nothing                    ; none had a page to run with

corriendo:
    ; The `while (!interp.IsRunning())` of `Game_Map::UpdateForegroundEvents`:
    ; if the page ends, the next one waiting starts **in this same frame** and
    ; not the next one. Chaining them to the next frame added one frame of
    ; difference per page, and a cutscene is dozens.
    lda #STARTS_MAX
    sta boots
seguir_corriendo:
    jsr run_code
    ; If the page ended and it was the turning event's, it goes back to its
    ; pose: the `UpdateFacing` of `OnFinishForegroundEvent`.
    lda ev_active
    bne sin_fin_de_giro
    lda f:TURN_EV
    cmp ev_running
    bne sin_fin_de_giro
    jsr turn_undo
sin_fin_de_giro:
    ; The pending refresh, **on leaving the interpreter**: it is the
    ; `if (Game_Map::GetNeedRefresh()) Game_Map::Refresh();` at the end of
    ; `Game_Interpreter::Update`, and RM2k's idiom depends on it working. A
    ; page that turns on the switch that deactivates it stops being the active
    ; one before deciding what runs next; without this, on ending it still
    ; looked autostart and started again in the same frame, over and over
    ; until the `STARTS_MAX` budget ran out.
    ;
    ; EasyRPG also refreshes **before each command**, at the top of the loop.
    ; Here it is not needed and it is expensive: none of the existing opcodes
    ; reads which page of an event is active —the only one that reads it is
    ; `start_waiting`, which runs right below here—. Doing it per
    ; command, the opening cutscene lost five frames: its pages turn on
    ; switches by the heap. The day an opcode appears that does read it, this
    ; goes back into the loop.
    lda refresh
    beq sin_refresco_aca
    stz refresh
    lda #1
    sta refresh_frame         ; the full one, at the start of the next frame
    jsr pick_autostart
sin_refresco_aca:
    lda jump_has
    bne hubo_salto
    lda ev_active
    bne nothing                    ; still running: the frame is over
    lda waiting_n
    beq nothing
    dec boots
    beq nothing                    ; the frame's budget ran out
    jsr start_waiting
    bne seguir_corriendo
    rts
hubo_salto:
    stz jump_has
    rep #$20
.a16
    lda jump_x
    sta entry_x
    lda jump_y
    sta entry_y
    sep #$20
.a8
    ; Nothing is loaded from here: the fade is requested and the map is loaded
    ; inside it, on the first black frame. See `fade_tick`. What does get
    ; decided here is **which** of the two cases it is, because `map_current`
    ; will have changed by the time it is due.
    ;
    ; A jump **to the same map** reloads nothing: it only moves the hero. It is
    ; the `map_changed = (GetMapId() != teleport_target.GetMapId())` of
    ; `Game_Player::PerformTeleport`. Reloading it queued the autostart events
    ; again, and with that the opening cutscene —which jumps twice inside map
    ; 1— restarted by itself forever. Fading, on the other hand, fades all
    ; the same: in RM2k the `TeleportParams` always goes out with
    ; `erase_screen = true`, wherever the jump points.
    ; The map index is sixteen bits —see `map_current`— and this goes through
    ; X and not A precisely for that: X is already sixteen, so copying and
    ; comparing does not cost the `rep`/`sep` it would through the
    ; accumulator. And it is not a matter of elegance: with the four extra
    ; bytes, the `beq nada` in `events_tick` went past the 128 a relative
    ; branch reaches.
    ldx jump_map
    stx fade_map
    cpx map_current
    bne otro_mapa
    lda #FADE_SAME          ; a jump to the same map reloads nothing
    bra pedir_fundido
otro_mapa:
    ; The jump budget is spent **here and not before**, that is, only when the
    ; map changes: a jump to the same map does not touch it.
    ;
    ; Charging it to jumps to the same map —which is what it did— drained the
    ; budget without ever replenishing it, because a jump to the same map does
    ; not call `enter_map`, which is what replenishes it. Talan's scene jumps
    ; three times inside map 3 and the opening twice inside map 1: after eight,
    ; **every teleport was silently dropped**. taro saw it as doors that open
    ; and lead nowhere, and as something that "sometimes happens and sometimes
    ; doesn't": it depended on how many jumps the game had taken.
    ;
    ; And it is checked before decrementing, not after: with `dec` on zero the
    ; byte wrapped to 255 and the cap failed **only once** and then let two
    ; hundred and fifty-five more through.
    lda jumps_left
    bne hay_presupuesto
    lda #PANIC_JUMPS
    jmp enter_panic        ; and there is no coming back from there
hay_presupuesto:
    dec jumps_left
    lda #FADE_JUMP
pedir_fundido:
    jsr start_fade
    ; The page that asked for the jump keeps running on the other side: its
    ; code is in the ROM and the cursor was saved. The new map's pages are
    ; queued only when this one ends.
nothing:
    rts
.endproc

; The half of `events_tick` that handles a pending jump, for the main loop:
; the `Teleport` of a parallel with the foreground idle. With a global name
; because `arranque.s` comes earlier in the assembly, and `ca65` does not
; resolve `events_tick::hubo_salto` forward.
events_handle_jump = events_tick::hubo_salto

; --- the parallel interpreters ----------------------------------------------
; `Game_Map::UpdateMapEvents`: each event with a parallel page has **its own
; interpreter** and runs every frame, apart from the foreground one, with a
; message open and with another page in progress. When its page ends, the
; next frame starts it again: RPG_RT does the `Push` before each `Update` if
; the interpreter is not running, so a page that runs out in one frame
; restarts forever. It is what makes the four cars of Lashe City go, whose
; whole page is a `MoveEvent`.
;
; They run with the **same** globals as the foreground —`code_ptr`, `ev_cur`,
; `ev_waiting`, `ev_active`, `ev_running`— so that context is saved on
; the stack and given back at the end. Twelve bytes, and how much stack is
; left below is measured by `rom/pruebas/rpgmaker/test_pila.py`: this path is
; one of the ones it runs.
;
; The state of each one goes in bank 1 RAM and **indexed by event**, not by
; slot, and records which page it belongs to: if the active page changes,
; RM2k rebuilds the interpreter (`Game_Event::Setup`), so it starts from
; zero. Without that, a refresh in the middle of a wait left it halfway
; running another page's code.
.proc clear_parallel
.a8
.i16
    stz pair_n
    rep #$20
.a16
    lda #FAR_PAIR_STATE
    sta WMADDL                  ; the two low bytes of the address
    sep #$20
.a8
    stz WMADDH
    ldx #(EV_MAX * PAIR_BYTES)
borrar:
    stz WMDATA                  ; the port auto-increments
    dex
    bne borrar
    rts
.endproc

; The bank window pointed at the list entry A carries. It is the same
; arithmetic for writing it and for reading it, and it was copied on both
; sides.
.proc pair_list_point
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; times PAIR_LIST_BYTES
    clc
    adc #FAR_PAIR_LIST
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; Notes event `rp_ev` in the map's list of parallels, with the page that just
; won: it enters with that page's `pg_*` and with `page_ofs` at its offset,
; which is how `apply_pages` has it read.
.proc record_parallel
.a8
.i16
    lda pair_n
    cmp #PARALELO_MAX
    bcc hay_lugar
    rts                         ; the converter cuts off before this happens
hay_lugar:
    jsr pair_list_point
    lda rp_ev
    sta WMDATA
    lda pg_code
    sta WMDATA
    lda pg_code + 1
    sta WMDATA
    lda pg_code + 2
    sta WMDATA
    lda page_ofs
    sta WMDATA
    lda page_ofs + 1
    sta WMDATA
    inc pair_n
    rts
.endproc

; One frame of each event with a parallel page.
.proc parallel_tick
.a8
.i16
    lda pair_n
    bne hay
    rts
hay:
    rep #$20
.a16
    lda ev_cur
    pha
    lda ev_waiting
    pha
    lda ev_running
    pha
    lda code_ptr
    pha
    sep #$20
.a8
    lda code_ptr + 2
    pha
    lda ev_active
    pha

    stz pair_i
lazo:
    ; First the ones that are resolved without an interpreter:
    ; `parallel_cell`, in bank 1, runs straight through the ones that start
    ; with `OP_CELL_TEST` and go no further, and stops at the first one that
    ; is not like that. With carry at 1 it stopped at one whose condition was
    ; met: it goes on from Y, with its interpreter.
    jsl f:parallel_cell + FAST  ; see MEMSEL
    bcc lento
    jsr one_parallel_continue
    bra siguiente
lento:
    lda pair_i
    cmp pair_n
    bcs listos
    ; The list entry, with long indexed addressing and not through the WMADD
    ; window: pointing the port cost more than reading, and this runs for each
    ; parallel on every frame —forty-one on each lap of the race—.
    rep #$20
.a16
    lda pair_i
    and #$00FF
    asl a
    asl a
    asl a                       ; times PAIR_LIST_BYTES
    tax
    lda f:FAR_LENGTH + FAR_PAIR_LIST + 1, x
    sta code_ptr                 ; its page, already resolved by the refresh:
    lda f:FAR_LENGTH + FAR_PAIR_LIST + 4, x
    sta page_ofs                 ; straight to the interpreter's cursor, which is
    lda f:FAR_LENGTH + FAR_PAIR_LIST + 0, x
    and #$00FF                  ; all `one_parallel` was going to do with it
    asl a
    asl a
    asl a                       ; times PAIR_BYTES: where its state lands
    sta pair_dir
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_PAIR_LIST + 0, x
    sta pair_ev                  ; which event it belongs to
    lda f:FAR_LENGTH + FAR_PAIR_LIST + 3, x
    sta code_ptr + 2
    jsr one_parallel
siguiente:
    inc pair_i
    lda pair_i
    cmp pair_n
    bcc lazo
listos:

    ; Outside the loop there is no parallel, and that is what `op_message`
    ; looks at to know whether the message it opens is a parallel's or the
    ; foreground's.
    lda #$FF
    sta pair_ev

    pla
    sta ev_active
    pla
    sta code_ptr + 2
    rep #$20
.a16
    pla
    sta code_ptr
    pla
    sta ev_running
    pla
    sta ev_waiting
    pla
    sta ev_cur
    sep #$20
.a8
    rts
.endproc

; One frame of event `pair_ev`, with `code_ptr`, `page_ofs` and `pair_dir` —where
; its state lands— already set by the loop from the list of parallels.
;
; Here the page is **not** chosen again nor read from the cartridge. That was
; what cost the frame in the Lazer Teeth HQ —eleven parallels, and the tenth
; went over— and it could not give a different answer: the list and what it
; carries are rebuilt by `apply_pages`, which is `Game_Map::Refresh`,
; that is, the only moment the active page changes. Nor is there any need to
; ask whether the page is parallel and whether it compiled: if it were not,
; the event would not be on the list.
.proc one_parallel
.a8
.i16
    ; With a message on screen a parallel keeps running —that is what it
    ; exists for—, **unless the message is its own**: the guard in
    ; `Game_Interpreter::Update` is `IsMessageActive() && _state.show_message`
    ; (easyrpg `game_interpreter.cpp:434-441`). Without this, the parallel of
    ; the guard in the `Lazer Teeth HQ` turned on its two switches and set off
    ; walking a tick after asking for its own message.
    ;
    ; Its state is neither read nor saved: this frame does not touch it. The
    ; event's step does happen, because `Game_Event::Update` calls
    ; `Game_Character::Update()` whatever happens with the interpreter.
    lda msg_open
    ora msg_state              ; also while it is being composed
    ora pick_active
    beq no_es_mio
    lda msg_owner
    cmp pair_ev
    bne no_es_mio
    jmp dar_el_paso             ; `beq` does not reach: the body is in between
no_es_mio:
    ; Its state, at `FAR_PAIR_STATE` + `pair_dir`, with long indexed
    ; addressing: like the list, and for the same reason. Only what is needed
    ; is read and written: with a wait in progress the wait changes and
    ; nothing else.
    rep #$20
.a16
    ldx pair_dir
    lda f:FAR_LENGTH + FAR_PAIR_STATE + 5, x
    cmp page_ofs                 ; which page this state belonged to
    bne otra_pagina
    ; The wait, same as the foreground's.
    lda f:FAR_LENGTH + FAR_PAIR_STATE + 2, x
    bne esperando
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_PAIR_STATE + 4, x
    beq empezar                 ; it was not running
    sta ev_active               ; it was: it goes on where it left off
    rep #$20
.a16
    stz ev_waiting
    lda f:FAR_LENGTH + FAR_PAIR_STATE + 0, x
    sta ev_cur
    sep #$20
.a8
    bra corriendo
.a16
esperando:
    dec a
    sta f:FAR_LENGTH + FAR_PAIR_STATE + 2, x
    sep #$20
.a8
    ; And whether it is running, which is what its step looks at: a route of
    ; its own does not read new commands with the page in progress
    ; (`ev_route_frame`).
    lda f:FAR_LENGTH + FAR_PAIR_STATE + 4, x
    sta ev_active
    jmp dar_el_paso             ; this frame goes by waiting
.a16
otra_pagina:
    ; Another page: another interpreter, and its number is noted down. RM2k
    ; rebuilds it in `Game_Event::Setup`, so it starts from zero. The wait and
    ; whether it was running are written now, as zero, and not when saving:
    ; the shortcut below does not save.
    lda page_ofs
    sta f:FAR_LENGTH + FAR_PAIR_STATE + 5, x
    lda #0
    sta f:FAR_LENGTH + FAR_PAIR_STATE + 2, x
    sep #$20
.a8
    sta f:FAR_LENGTH + FAR_PAIR_STATE + 4, x
empezar:
    ; It was not running: the page starts over. It is the `Push` RPG_RT does
    ; before each `Update`, and that is why it does not restart when it ends
    ; but on the next frame.
    ;
    ; **The `OP_CELL_TEST` shortcut.** A page that starts with it —those of
    ; the race cars, the lights on map 11— almost always fails the condition
    ; and ends right there: its condition is evaluated here, without going
    ; through `run_code`, and if what follows is the `OP_DONE` the page
    ; is over and its state is already as it has to stay —no wait and not
    ; running—, so it is not saved. It is exactly the interpreter's first
    ; round and its second; if what follows is something else, the
    ; interpreter goes on from there. It is almost two lines of the frame's
    ; 262 per page: see workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.
    lda [code_ptr]               ; the first opcode
    cmp #OP_CELL_TEST
    bne desde_cero
    ldy #1
    jsl f:cell_test + FAST   ; see MEMSEL
    lda [code_ptr], y
    bne seguir                  ; it is not the OP_DONE
    stz ev_active               ; what `op_done` would do
    jmp dar_el_paso
desde_cero:
    ldy #0
::one_parallel_continue:
seguir:
    rep #$20
.a16
    sty ev_cur
    stz ev_waiting
    sep #$20
.a8
    lda #1
    sta ev_active
corriendo:
    rep #$20
.a16
    lda pair_ev
    and #$00FF
    sta ev_running            ; whose page it is, for a MoveEvent of its own
    sep #$20
.a8
    jsr run_code
    rep #$20
.a16
    ldx pair_dir
    lda ev_cur
    sta f:FAR_LENGTH + FAR_PAIR_STATE + 0, x
    lda ev_waiting
    sta f:FAR_LENGTH + FAR_PAIR_STATE + 2, x
    sep #$20
.a8
    lda ev_active
    sta f:FAR_LENGTH + FAR_PAIR_STATE + 4, x

dar_el_paso:
    ; And the step of **this** event, right here and not at the end of the
    ; round. `Game_Event::Update` runs the parallel interpreter and right after
    ; calls `Game_Character::Update()` —easyrpg, `game_event.cpp:580`—, and
    ; `UpdateMapEvents` does that event by event. It is not the same as running
    ; all the interpreters and then moving everyone: it shows when a parallel
    ; page forces a move route on **another** event. In Lashe City `Car4`
    ; overwrites `Car2`'s route every frame —both point at RM2k id 3, which
    ; there is `Car2`— and with all the steps at the end the overwrite wins and
    ; `Car2` never walks. taro saw it, and in EasyRPG and in the original RPG
    ; Maker the four cars move.
    ;
    ; The slot comes from the mark `slot_record` leaves, and not from
    ; looking it up with `event_slot`: the lookup walked every used slot
    ; for each parallel on every frame, and in the race, with five cars moving
    ; and forty parallels, it was thirty lines of the frame's 262.
    ldx pair_dir
    lda f:FAR_LENGTH + FAR_PAIR_STATE + PAIR_SLOT, x
    beq sin_ranura
    dec a
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times ROUTE_EV_STRIDE
    tax
    sep #$20
.a8
    phx
    jsr ev_route_frame
    plx
    phx
    jsr animate_ev_route
    plx
    phx
    jsr refresh_npc
    plx
    lda route_ev + 18, x
    ora #$40                    ; it already took its step: `move_events` skips it
    sta route_ev + 18, x
sin_ranura:
    rts
.endproc

; The move route slot of the event whose index comes in A: X, or $FFFF if it
; has none.
; What the active page of an event that changes graphic draws, copied to its
; NPC row: the tile, the attributes —palette and its layer's priority—, the
; pose and which way it faces, whether it is visible, and its tile's
; passability bits. And the draw key with the page's layer, which can change
; —the elevator on map 2 moves from the hero's layer to the one below when it
; opens—, so the row is re-sorted like that of an event that walks. It is
; `SetupFromPage` for the graphic, and it is what opens this game's doors:
; the page with the rubble tile appears where there was nothing before.
; Enters with the active page's `pg_*` and the event in `rp_ev`.
.proc page_graphic
.a8
.i16
    ; Bit 5 says the row follows the page, and it means two things depending
    ; on the row:
    ;
    ; * **if it does not walk**, everything comes from the active page: the
    ;   tile, the palette, the pose and whether it is visible. It is what opens
    ;   this game's doors.
    ; * **if it walks**, all of that except the tile and the palette, which
    ;   point at its slot of twelve poses, and overwriting them would leave it
    ;   still.
    ;
    ; The distinction exists because an event can walk **and** appear with
    ; the page, and before 2026-09-08 the converter had to choose: it chose
    ; walking, and then the row —which is born hidden when no page qualifies
    ; on loading the map— never appeared. taro found it with the `Bum` and the
    ; `Mechanic` of Lashe City; RM2k draws them and the ROM does not, 245 and
    ; 191 pixels.
    ;
    ; It is not a new bit because there is none left in +13: with a route of
    ; its own the five low ones are the route's flags. And it is not needed,
    ; because **the row already says it**: +9 holds NPC_QUIETO or the bank of
    ; its poses.
    lda pg_flags
    and #$20
    bne hay_algo
    rts                         ; its row does not follow the page
hay_algo:
    lda rp_ev
    jsr event_npc
    cpy #$FFFF
    bne hay_fila
    rts                         ; no row: nothing to draw
hay_fila:
    sty npc_row
    lda pg_pose
    bmi con_grafico
    lda #0                      ; the page draws nothing: hidden
    sta npc_buf + 14, y
    lda #$FF
    sta npc_buf + 15, y
    rts
con_grafico:
    and #$0F
    sta npc_buf + 12, y         ; the pose in VRAM is this one
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:pose_dir, x
    sta npc_buf + 10, y
    ; The tile and the palette only if the row does not walk. If it walks,
    ; they point at its slot of twelve poses and overwriting them would leave
    ; it still; the pose above does go, as it is the one the page declares and
    ; the one the refresh uploads from the bank.
    lda npc_buf + 9, y
    cmp #NPC_QUIETO
    bne sin_tocar_el_tile
    lda pg_tile
    sta npc_buf + 6, y
    lda pg_attr
    sta npc_buf + 7, y
sin_tocar_el_tile:
    lda #1
    sta npc_buf + 14, y
    lda pg_pass
    sta npc_buf + 15, y
    cmp #$FF
    beq :+
    sta pass_has                ; it imposes: `pass_with_event` has to look
:
    ; The key: the page's layer, with the row's Y.
    rep #$20
.a16
    lda npc_buf + 4, y
    and #$0FFF
    sta temp
    lda pg_layer
    and #$00FF
    xba
    asl a
    asl a
    asl a
    asl a
    ora temp
    sta npc_buf + 4, y
    sep #$20
.a8
    phy
    jsr turn_restore            ; if it is the turning one, it turns again
    ply
    jmp fit_npc
ready:
    rts
.endproc

; Hides the row of the event in A, if it has one: it is not drawn and its tile
; imposes nothing on the cell.
.proc hide_npc
.a8
.i16
    jsr event_npc
    cpy #$FFFF
    beq ready
    lda #0
    sta npc_buf + 14, y
    lda #$FF
    sta npc_buf + 15, y
ready:
    rts
.endproc

.proc event_slot
.a8
.i16
    sta other_ev
    ; From the highest one used downward, and not from zero upward: that way
    ; the stop is `X == 0`, which `tax` leaves in Z for free, and there is no
    ; need for a sixteen-bit limit in RAM —there is none—. An event has at
    ; most one slot —it is only given one when `event_slot` found none
    ; for it— so the order does not change the answer.
    lda route_ev_cap
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; times ROUTE_EV_STRIDE
    tax
    sep #$20
.a8
buscar:
    cpx #$0000
    beq no_tiene
    rep #$20
.a16
    txa
    sec
    sbc #ROUTE_EV_STRIDE
    tax
    sep #$20
.a8
    lda route_ev, x
    cmp other_ev
    bne buscar
    rts                         ; X = its slot
no_tiene:
    ldx #$FFFF
    rts
.endproc

; A free move route slot: X, or $FFFF if none is left.
.proc free_slot
.a8
.i16
    ldx #$0000
buscar:
    lda route_ev, x
    cmp #ROUTE_EV_FREE
    beq ready
    rep #$20
.a16
    txa
    clc
    adc #ROUTE_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * ROUTE_EV_STRIDE
    sep #$20
.a8
    bcc buscar
    ldx #$FFFF
    rts                         ; no room: the limit is not touched
ready:
    ; The slot now has an owner, so the limit goes up if it ended up above the
    ; one there was. It is the only place a slot is taken through: both —the
    ; page's own route and the forced one— ask here.
    rep #$20
.a16
    txa
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; from bytes to slot number
    inc a
    sep #$20
.a8
    cmp route_ev_cap
    bcc ya_estaba
    sta route_ev_cap
ya_estaba:
    rts
.endproc

; The move route of the page just read, into slot X, from the start. It is
; also saved separately —+24 to +29— to go back to it when a forced move
; route on the same event ends.
.proc load_page_into_slot
.a8
.i16
    lda pg_route
    sta route_ev + 1, x
    sta route_ev + 24, x
    lda pg_route + 1
    sta route_ev + 2, x
    sta route_ev + 25, x
    lda pg_route + 2
    sta route_ev + 3, x
    sta route_ev + 26, x
    lda pg_route_n
    sta route_ev + 4, x
    sta route_ev + 27, x
    stz route_ev + 5, x
    lda pg_freq
    sta route_ev + 16, x
    sta route_ev + 28, x
    lda pg_speed
    sta route_ev + 17, x
    sta route_ev + 29, x
    lda pg_flags
    and #$1E
    ora #$01                    ; a page one
    sta route_ev + 18, x
    lda pg_layer
    sta route_ev + 31, x         ; its layer, for colliding with the others
    rep #$20
.a16
    lda page_ofs
    sta route_ev + 20, x
    sep #$20
.a8
    lda pg_freq
    jsr after_turn               ; `SetMaxStopCountForTurn` before the first one
    sta route_ev + 9, x
    rts
.endproc

; The new page of the event in slot X has no route: it is left with no
; commands and no page to go back to.
.proc remove_page_from_slot
.a8
.i16
    lda route_ev + 18, x
    and #$01
    beq ready                   ; a forced one was running: leave it alone
    stz route_ev + 4, x
    stz route_ev + 5, x
    stz route_ev + 9, x
    lda route_ev + 18, x
    and #$FE
    sta route_ev + 18, x
ready:
    stz route_ev + 27, x
    rep #$20
.a16
    lda #$FFFF
    sta route_ev + 20, x
    sep #$20
.a8
    rts
.endproc

; How much the step of slot X advances per frame, into `temp`, sixteen bits.
.proc step_slot
.a8
.i16
    lda route_ev + 17, x
    dec a
    asl a
    rep #$20
.a16
    and #$00FF
    tay
    phx                         ; X holds the slot and the caller counts on it
    tyx
    lda f:step_per_speed, x
    plx
    sta temp
    sep #$20
.a8
    rts
.endproc

; How much the jump of slot X advances per frame, in A.
.proc slot_jump
.a8
.i16
    lda route_ev + 17, x
    dec a
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    phx                         ; X holds the slot and the caller counts on it
    tyx
    lda f:jump_per_speed, x
    plx
    rts
.endproc

; How much the hero's jump advances per frame, in A: RM2k's
; `jump_speed[move_speed - 1]`, with the speed the last route left him. Keeps
; X.
.proc hero_jump
.a8
.i16
    phx
    jsr hero_speed_read
    rep #$20
.a16
    and #$00FF
    dec a
    tax
    sep #$20
.a8
    lda f:jump_per_speed, x
    plx
    rts
.endproc

; The layer of the active page of the event whose index comes in A, or $FF if
; it has none. It is the same pass as `queue_by_action`: the last page
; whose conditions are met wins. Keeps X and Y; clobbers `pag_*` and `pg_*`,
; which nobody has half used when this runs —it is called from a step, not
; from inside a page search—.
.proc active_layer
.a8
.i16
    phx
    phy
    rep #$20
.a16
    and #$00FF
    sta layer_ev
    sep #$20
.a8
    lda #$FF
    sta found_layer
    ldx map_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_PAGINA_COUNT, x
    beq sin_paginas
    sta pages_left
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta page_ptr
    stz page_ofs
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta page_ptr + 2
recorrer:
    ; Only the event being looked for: of the other pages only the event is
    ; read and nothing else. Reading them whole cost, with a droid pushing
    ; against the hero frame after frame, more than a frame every so often.
    rep #$20
.a16
    ldy page_ofs
    lda [page_ptr], y            ; +0 which event it belongs to
    cmp layer_ev
    sep #$20
.a8
    bne siguiente
    jsr read_page
    jsr conditions_ok
    beq siguiente
    lda pg_layer
    sta found_layer
siguiente:
    rep #$20
.a16
    lda page_ofs
    clc
    adc #PAGINA_BYTES
    sta page_ofs
    dec pages_left
    sep #$20
.a8
    bne recorrer
    lda found_layer
    ply
    plx
    rts
sin_paginas:
.a16
    sep #$20
.a8
    lda #$FF
    ply
    plx
    rts
.endproc

; Whether the event whose index comes in A is walking through walls: it has a
; move route slot and the slot carries the bit. Returns A nonzero if so.
; Clobbers X.
.proc event_crossable
.a8
.i16
    sta other_ev
    ldx #$0000
buscar:
    lda route_ev, x
    cmp other_ev
    bne siguiente
    lda route_ev + 12, x
    and #$01
    rts
siguiente:
    rep #$20
.a16
    txa
    clc
    adc #ROUTE_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * ROUTE_EV_STRIDE
    sep #$20
.a8
    bcc buscar
    lda #0
    rts
.endproc

; Is someone standing on `dest_x`/`dest_y` who blocks `walker`'s way? Returns
; A nonzero if so.
;
; It is `WouldCollide` from `game_map.cpp` with what this repo models: two
; characters collide if they are on the same layer —the hero's is
; HERO_LAYER_INDEX— and do not collide if either of them walks through walls. An
; event with no active page is not there and does not collide. Each event's
; cell is the one in `ev_pos_buf`, which moves at the **start** of the step:
; it is `IsInPosition` on `GetX()`, that is, the destination while it walks;
; and the hero's is `tile_x`/`tile_y`, which `begin_step` moves the same way.
; What is not modeled is `overlap_forbidden` —17 pages in the game— and the
; conflict of an event with a tile graphic against its own block. Clobbers X
; and Y.
.proc cell_blocked
.a8
.i16
    lda walker_layer
    cmp #$FF
    beq libre_cerca             ; with no active page it collides with nobody
    lda walker
    cmp #HERO_WALKER
    beq es_heroe
    jsr event_crossable
    bne libre_cerca
    bra recorrer
es_heroe:
    ; **`crossing` and not `route_crosses`**, which is the divergence
    ; declared in workflow/divergencias/atravesar-paredes-vale-mientras-dura-la-ruta.md:
    ; the flag command 36 leaves holds while the step is given by the forced
    ; move route —there `step_route` copies it to `crossing`— and not for
    ; walking with the pad, which leaves it at zero. Reading the sticky one,
    ; any page that turned on 36 and did not turn it off left the hero walking
    ; over **every** event for the rest of the game, and walls still stopped
    ; him because `can_leave` and `can_enter` already looked at
    ; `crossing`: the same hero went through events and not walls. taro saw
    ; it playing, with the chests in Sector 30, and the culprit is the
    ; Hover-Tram (map 13, EV0028), which turns on 36 and never turns it off.
    lda crossing
    beq recorrer
libre_cerca:
    jmp libre                   ; `libre` is too far for a short branch
recorrer:
    ; Back to front and in sixteen bits, with Y on each event's cell: the
    ; answer is a yes or a no, so the order does not change it, and that way
    ; the loop is half as long. It runs on every step that starts —three of
    ; these and of `pass_with_event` per step—, and in the race, with forty
    ; cars, it was nine lines each: see
    ; workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.
    rep #$20
.a16
    lda ev_total
    asl a
    asl a                       ; times EV_STRIDE
    tay
    bra siguiente
otro:
    lda ev_pos_buf, y
    cmp dest_x
    beq misma_x
siguiente:
    dey
    dey
    dey
    dey                         ; EV_STRIDE
    bpl otro
    sep #$20
.a8
    bra eventos_listos
.a16
misma_x:
    lda ev_pos_buf + 2, y
    cmp dest_y
    bne siguiente
    tya
    lsr a
    lsr a                       ; the index fits in a byte: EV_MAX is 128
    sep #$20
.a8
    cmp walker
    beq siguiente8              ; not with itself
    sta other_ev
    phy
    jsr event_crossable
    bne no_choca
    lda other_ev
    jsr active_layer
    cmp walker_layer
    bne no_choca
    ply
    lda #1
    rts
no_choca:
    ply
siguiente8:
    rep #$20
.a16
    bra siguiente
.a8
eventos_listos:
    ; And the hero, when whoever is moving is an event on his layer.
    lda walker
    cmp #HERO_WALKER
    beq libre
    lda walker_layer
    cmp #HERO_LAYER_INDEX
    bne libre
    lda route_crosses
    bne libre
    rep #$20
.a16
    lda tile_x
    cmp dest_x
    bne libre16
    lda tile_y
    cmp dest_y
    bne libre16
    sep #$20
.a8
    lda #1
    rts
libre16:
.a16
    sep #$20
.a8
libre:
    lda #0
    rts
.endproc

; `cell_blocked` for the hero: the destination cell is already in dest_x/dest_y.
.proc hero_blocked
.a8
.i16
    lda #HERO_WALKER
    sta walker
    lda #HERO_LAYER_INDEX
    sta walker_layer
    jmp cell_blocked
.endproc

; `walker` and `walker_layer` from the move route slot X points at. Keeps X.
.proc prepare_walker
.a8
.i16
    lda route_ev + 0, x
    sta walker
    lda route_ev + 31, x         ; the layer the slot has carried since it was loaded
    sta walker_layer
    rts
.endproc

; Are the conditions of the page just read met? Returns with Z=0 if so.
; A switch at 0 means "this page does not require it".
.proc conditions_ok
.a8
.i16
    rep #$20
.a16
    lda pg_sa
    beq mirar_b
    jsr switch_on
    beq fails
mirar_b:
    lda pg_sb
    beq cumple
    jsr switch_on
    beq fails
cumple:
    sep #$20
.a8
    ; And the party condition: a 0 means "this page requires nobody".
    lda pg_actor
    beq mirar_var
    jsr in_party
    beq falla8
mirar_var:
    ; And the item and the variable, which are read from the table and not
    ; from a copy —the BSS is full—: +28 the item or 0, and +24 the slot or $FF
    ; for "requires none", +25 how it compares and +26 against what. It is the
    ; same signed comparison as
    ; `ConditionalBranch`, `compare_var`, with the same six codes: RM2k uses
    ; `CheckOperator` for both. Clobbers X and Y, as `switch_on`
    ; already did.
    ldy page_ofs
    rep #$20
.a16
    tya
    clc
    adc #28
    tay
    lda [page_ptr], y            ; +28 the item it requires, or 0
    beq sin_item
    ; With the inventory in far RAM: the item's count, and at zero it is not
    ; there. It is `GetItemCount(id) + GetEquippedItemCount(id)` without
    ; equipment.
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    beq falla8
    rep #$20
.a16
sin_item:
    tya
    sec
    sbc #4
    tay                         ; +24
    sep #$20
.a8
    lda [page_ptr], y            ; +24 the slot
    cmp #$FF
    beq cumple8
    pha
    iny
    lda [page_ptr], y            ; +25 the comparison
    sta temp + 1
    iny
    rep #$20
.a16
    lda [page_ptr], y            ; +26 against what, signed
    sta temp + 2
    sep #$20
.a8
    pla
    jsr var_read                ; A = the variable, sixteen bits
.a16
    jsr compare_var
.a8
    beq falla8
cumple8:
    lda #1                      ; Z=0
    rts
falla8:
    lda #0                      ; Z=1
    rts
sin_usar:
    sep #$20
.a8
    lda #1                      ; Z=0
    rts
fails:
.a16
    ; it arrives at sixteen; the `sep` below shrinks it
    sep #$20
.a8
    lda #0                      ; Z=1
    rts
.endproc

; Is the switch whose number comes in A on? Returns with Z=0 if so.
.proc switch_on
.a16
.i16
    pha
    and #$0007
    tax                         ; the bit within the byte
    pla
    lsr a
    lsr a
    lsr a
    tay                         ; and which byte of the bitmap
    sep #$20
.a8
    lda switches, y
    and f:mask, x
    rep #$20
.a16
    rts                         ; rep does not touch Z, so the and still holds
.endproc

; The queuing part, shared by the autostart ones and the action button.
; No event waiting and none autostart: on entering a map the previous one's
; marks are worth nothing, and their event indexes would point at other
; events. The map load calls it **before** the refresh, which is what turns
; `FLAG_AUTO` back on for the ones it applies to.
.proc clear_waits
.a8
.i16
    ldx #$0000
:   stz ev_flags, x
    inx
    cpx #EV_MAX
    bne :-
    stz waiting_n
    stz auto_n
    stz refresh_frame
    ; And whose page is running: if it survived a teleport, its index no
    ; longer means anything on the new map.
    rep #$20
.a16
    lda #$FFFF
    sta ev_running
    sep #$20
.a8
    rts
.endproc

; Every event with an active autostart page goes back to waiting. It is
; `Game_Event::CheckEventAutostart`, which runs once per frame and for all of
; them. `events_tick` calls it before the interpreter, and only if `auto_n`
; says there is one.
.proc wait_autostart
.a8
.i16
    ldx #$0000
mirar:
    lda ev_flags, x
    and #FLAG_AUTO
    beq siguiente
    jsr mark_waiting
siguiente:
    inx
    cpx ev_total
    bne mirar
    rts
.endproc

; The active page the refresh noted for event X, into `chosen`. Z=1 if none
; is noted and it has to be searched for.
;
; It exists so that starting a page does not cost a walk through all the
; map's pages. The refresh already resolved it; resolving it again here was
; doing the same work twice, and the second time landed on any old frame.
.proc page_from_pick
.a8
.i16
    stz chosen_any
    cpx #EV_MAX
    bcs no
    rep #$20
.a16
    txa
    asl a
    tay
    lda pick_by_ev, y
    cmp #$FFFD                  ; $FFFD, $FFFE and $FFFF are sentinels
    bcc anotada
    sep #$20
.a8
no:
    lda #0
    rts
.a16
anotada:
    sta page_ofs
    ; With X, and not with Y as until `mapa_tabla` moved to RODATA: the
    ; 65816's long absolute indexed addressing only exists with X. X holds
    ; the event and the caller counts on it, so it goes out and back through
    ; the stack; the `plx` leaves N and Z of the value it pulls, and that is
    ; why what follows is a `jsr` and not a branch.
    phx
    ldx map_ofs
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta page_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta page_ptr + 2
    plx
    jsr read_page
    lda pg_trigger
    sta chosen_trigger
    rep #$20
.a16
    lda pg_code
    sta chosen
    sep #$20
.a8
    lda pg_code + 2
    sta chosen + 2
    lda #1
    sta chosen_any
    rts
.endproc

; Starts the page of the first event that is waiting. Returns 0 if none
; started. The order is by event number, which is the same one in which
; `Game_Map::Update` walks `events`.
;
; The page is resolved **here**, not when the event was marked: between the
; one and the other a refresh may have happened and another one may be
; active.
.proc start_waiting
.a8
.i16
    ldx #$0000
buscar:
    lda ev_flags, x
    and #FLAG_WAIT
    bne encontrado
    inx
    cpx ev_total
    bne buscar
    lda #0
    rts
encontrado:
    ; It is unmarked before knowing whether there is anything to run, just
    ; like the `ClearWaitingForegroundExecution` in `Game_Map::Update`, which
    ; always runs. If the page did not compile, the event loses its turn; and
    ; if it is autostart, the next frame's sweep marks it again.
    lda ev_flags, x
    and #(FLAG_AUTO)            ; keeps only the autostart one
    sta ev_flags, x
    dec waiting_n
    phx
    jsr page_from_pick
    bne con_pagina
    rep #$20
.a16
    txa
    sta ev_sought
    sep #$20
.a8
    jsr seek_event_page
con_pagina:
    plx
    lda chosen_any
    beq buscar_mas
    lda chosen
    ora chosen + 1
    ora chosen + 2
    beq buscar_mas              ; the active page could not be compiled
    rep #$20
.a16
    lda chosen
    sta code_ptr
    stz ev_cur
    sep #$20
.a8
    lda chosen + 2
    sta code_ptr + 2
    rep #$20
.a16
    txa
    sta ev_running            ; so it can be re-marked when it ends
    sep #$20
.a8
    lda #1
    sta ev_active
    rts
buscar_mas:
    inx
    cpx ev_total
    bne buscar
    lda #0
    rts
.endproc

; The opposite of `mark_waiting`, with the same count.
.proc unmark_waiting
.a8
.i16
    cpx #EV_MAX
    bcs no
    lda ev_flags, x
    and #FLAG_WAIT
    beq no                      ; it was not: not discounted again
    lda ev_flags, x
    and #(FLAG_AUTO)            ; keeps only the autostart one
    sta ev_flags, x
    dec waiting_n
no:
    rts
.endproc

; Marks event X as having a page waiting its turn. It is
; `Game_Event::ScheduleForegroundExecution`: one bit per event, not a queue.
; Marking it twice does not queue it twice, which is what was needed so that
; each frame's sweep can re-mark without fear.
.proc mark_waiting
.a8
.i16
    cpx #EV_MAX
    bcs no
    lda ev_flags, x
    and #FLAG_WAIT
    bne no                      ; it already was: not counted again
    lda ev_flags, x
    ora #FLAG_WAIT
    sta ev_flags, x
    inc waiting_n
no:
    rts
.endproc

