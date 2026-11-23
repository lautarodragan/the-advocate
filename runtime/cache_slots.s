.segment "FAR"
.a8
.i16

; What `cache_was_note` keeps: four bytes a row —its event, or $FF in a
; free one, the key it showed, its attributes, and whether it was shown
; since the last `cache_age`: noted, or drawn by `cache_was_draw`—. See "a
; still one whose look changes" below.
CACHE_WAS_MAX = 4
CACHE_WAS_SIZE = 4
.pushseg
.segment "FARBSS"
CACHE_WAS: .res CACHE_WAS_SIZE * CACHE_WAS_MAX
.popseg

; --- a cache of slots -----------------------------------------------------------
;
; Every other map gives each event drawn a VRAM slot for the whole map: the
; walking ones one each, the still ones one per pose. A map with a crowd
; —ABL's farm, 127: twenty-nine people on one screen, and fifteen more in
; the next scene— asks for more slots than the bank has even with the still
; ones taking turns (shared_poses.s). In such a map, and only there, nobody
; owns a slot: an event asks for one when `place_npc` is about to draw it,
; and the console uploads its pose there with `vram_queue`, like every
; hot-swapped pose. Which maps, and how many slots, Wally decides:
; `sprites::cache`.
;
; What a slot holds is its key:
;
;   0 to 127    a still pose, which every still event showing it shares.
;               The row carries it in its tile byte (+6), and so do the
;               pages of the ones that change graphic; the cartridge's
;               `cache_data` says where its pose is in `npc_poses`
;   128 + e     event e's own: it walks or animates in place, and changes
;               pose by itself through `upload_npc_pose`, which asks
;               `cache_dest` where its slot is. The still ones that animate
;               with it —its twins, `animates_with` in Wally— ask for this
;               same key, which their rows carry in the tile byte: whichever
;               comes into view first gets the slot and uploads its column,
;               and from then on e keeps it up to date, even out of view
;   $FF         nothing
;
; A slot is free when nobody drew it in the last two frames: every frame
; `build_oam` ages them all —`cache_age`—, and drawing one brings its age
; back to 0. Of the free ones, the one drawn longest ago goes. That is the
; margin: one that steps out of view and back finds its pose still up,
; unless the cache needed the slot meanwhile; and one that left this frame
; is not taken from under it by one drawn before it in the same pass.
;
; **If the cache is full** —every slot was drawn this frame or the last— the
; one asking is not drawn, and asks again next frame: it waits for someone to
; leave the screen. It never hangs, and who waits is whoever `build_oam`
; reaches last, which is the one furthest back. Wally warns when the events'
; starting places can put more on screen than the cache has; in ABL's farm
; they cannot, because its two crowds are never there together.
;
; A row that gets a slot is not drawn in the frame that queues its pose but
; in the next, with the pose up, like shared_poses.s; and the first frame of
; a map goes through `build_oam_settled`, which uploads with the screen off
; until nobody is missing. A still one facing the hero is drawn from the
; turn slot and does not ask; one that walks turns in its own: see
; `turn_fire`.
;
; **But a still one whose look changes on screen keeps its old one meanwhile**:
; a page that gives it another graphic —`page_graphic`— or a route that
; turns it —`still_turn`— hands it a key that is not up, and waiting for it
; with nothing drawn took the row off the screen for that frame, two when a
; tick lasts two. RM2k changes it at once. Desert Nightmare's trash can by
; the motel, on map 2, is two events whose page goes from the closed can to
; the open one when it opens: the closed lid went missing for two frames
; before the open can showed. So `cache_was_note` keeps, for the rows that
; were drawn, the key and attributes they showed, and if their new pose is
; not up `cache_was_draw` draws the old one, which is still in its slot: it
; was drawn last frame, so no one could take that slot, and drawing it keeps
; it so. **It is kept for as long as the row waits**, not for a frame: a row
; that finds the cache full waits more than one. The two cans left of the
; motel's door open with two lids above them, four new looks at once, and
; with room for three the last can lost its old look after a frame and
; waited two more with nothing drawn, until its own old slot aged out
; (taro's second report). `cache_age` forgets a kept look on the first
; frame that did not draw it: the row showed its new one, or left the view.
;
; And waiting on a full cache while holding the old slot would wait for
; ever if no one else left: so a row in that case **takes its old slot for
; the new pose** —`cache_was_own`—, if no one drew that slot yet in this
; pass, and is drawn from it at once, the new pose going up in the vblank
; that shows it, with the attributes it had for that frame. What it does
; not cover: a row whose look changes in the same tick it comes into view,
; which has no old look in any slot, or whose old key someone else queued
; that same frame, which is shown before it is up; a row further on in the
; pass that shows the same still pose as the one taking its old slot, which
; loses it and waits; and more than `CACHE_WAS_MAX` rows changing at once,
; the rest of which wait with nothing drawn.
;
; Whether the map has a cache is bit 7 of `SHARE_N`, so that `place_npc`
; looks at a single byte for both: no map has both, because the cache is
; what is left when taking turns is not enough.

; From `load_sprite`, after `share_load`: the loaded map's cache, and nobody
; holds anything.
.proc cache_load
.a8
.i16
    rep #$20
.a16
    lda map_current
    asl a
    tax
    lda f:cache_maps, x
    sta f:CACHE_REC
    tax
    sep #$20
.a8
    cpx #0
    beq none                    ; this map has no cache
    lda f:cache_data, x         ; how many slots
    sta f:CACHE_N
    lda #$80
    sta f:SHARE_N               ; `place_npc` asks the cache
    lda #$FF
    ldx #CACHE_MAX - 1
slots:
    sta f:CACHE_KEY, x
    sta f:CACHE_AGE, x          ; nobody drew it for ages
    dex
    bpl slots
    ldx #EV_MAX - 1
events:
    sta f:CACHE_EV, x
    dex
    bpl events
    jsr cache_was_forget
none:
    rtl
.endproc

; Every slot free, keeping what it holds: from `build_oam_settled`, before a
; frame that draws the screen anew —entering the map, a teleport within it,
; coming back from a battle—. What the last frame drew is no reason to keep
; a slot from whoever is on screen now, and without this the settled frame
; ended with some rows waiting: everything drawn just before the teleport
; was too recent to be taken.
.proc cache_settle
.a8
.i16
    jsr cache_last
    lda #$FF
old:
    sta f:CACHE_AGE, x
    dex
    bpl old
    rtl
.endproc

; One frame older, every slot: from `build_oam`, before drawing. $FF stays.
.proc cache_age
.a8
.i16
    rep #$20
.a16
    lda f:CACHE_N
    and #$00FF
    dec a
    tax
    sep #$20
.a8
older:
    lda f:CACHE_AGE, x
    inc a
    beq keep                    ; it was $FF
    sta f:CACHE_AGE, x
keep:
    dex
    bpl older
    ; And the old looks `cache_was_note` kept: one that was not shown since
    ; the last frame is forgotten —its row showed its new look, or nothing—,
    ; and the rest have to be shown again in this one to stay.
    ldx #CACHE_WAS_SIZE * (CACHE_WAS_MAX - 1)
was:
    lda f:CACHE_WAS + 3, x
    bne shown
    lda #$FF
    sta f:CACHE_WAS, x
shown:
    lda #0
    sta f:CACHE_WAS + 3, x
    dex
    dex
    dex
    dex
    bpl was
    rtl
.endproc

; Forgets every old look `cache_was_note` kept. X is lost.
.proc cache_was_forget
.a8
.i16
    ldx #CACHE_WAS_SIZE * (CACHE_WAS_MAX - 1)
free:
    lda #$FF
    sta f:CACHE_WAS, x
    lda #0
    sta f:CACHE_WAS + 3, x
    dex
    dex
    dex
    dex
    bpl free
    rts
.endproc

; Row Y's look is about to become key A: from `page_graphic` and
; `still_turn`, before they write it, in any map. In a map with a cache, if
; the row is drawn and its key changes, what it shows now is kept for
; `cache_was_draw`. The one facing the hero is left out: its tile byte is
; the turn slot's, not a key. Keeps A, X and Y.
.proc cache_was_note
.a8
.i16
    pha
    phx
    sta f:CACHE_T_KEY           ; the new key: nobody's until `cache_want`
    lda f:SHARE_N
    bpl done                    ; no cache
    lda npc_buf + 14, y
    dec a                       ; drawn: as `build_oam` looks at it
    cmp #(TRANSP_HIDDEN * 2)
    bcs done
    lda npc_buf + 6, y
    cmp f:CACHE_T_KEY
    beq done                    ; the same key: its slot is up
    lda npc_buf + 8, y
    cmp f:TURN_EV
    beq done
.ifdef posed_stills
    lda npc_buf + 7, y          ; nor one drawn into the background: posed.s
    and #$30
    cmp #$30
    beq done
.endif
    ; A row whose look changes again while it still shows the kept one
    ; —noted this frame, or drawn by the last— keeps that one: it is the one
    ; on screen. If the last frame did not draw it, the row showed its own.
    lda npc_buf + 8, y
    ldx #CACHE_WAS_SIZE * (CACHE_WAS_MAX - 1)
seen:
    cmp f:CACHE_WAS, x
    beq again
    dex
    dex
    dex
    dex
    bpl seen
    ldx #CACHE_WAS_SIZE * (CACHE_WAS_MAX - 1)
free:
    lda f:CACHE_WAS, x
    cmp #$FF
    beq take
    dex
    dex
    dex
    dex
    bpl free
    bra done                    ; full: this one waits with nothing drawn
again:
    lda f:CACHE_WAS + 3, x
    bne done
take:
    lda npc_buf + 8, y
    sta f:CACHE_WAS, x
    lda npc_buf + 6, y
    sta f:CACHE_WAS + 1, x
    lda npc_buf + 7, y
    sta f:CACHE_WAS + 2, x
    lda #1
    sta f:CACHE_WAS + 3, x      ; on screen until a frame does not draw it
done:
    plx
    pla
    rtl
.endproc

; Row `CACHE_T_ROW`, which `cache_want` did not draw: carry clear if it is
; drawn with the look `cache_was_note` kept for it, `obj_tile` and
; `obj_attr` set, and its slot and the look kept for the frame; carry set if
; it has none, or no slot holds it any more. From `place_npc`.
.proc cache_was_draw
.a8
.i16
    jsr cache_was_find
    bcc found
    rtl
found:
    phx
    lda f:CACHE_WAS + 2, x
    sta temp + 1                ; its attributes
    lda f:CACHE_WAS + 1, x
    sta temp                    ; and its key
    jsr cache_last
seek:
    lda f:CACHE_KEY, x
    cmp temp
    beq up
    dex
    bpl seek
    plx
    sec                         ; no slot holds it
    rtl
up:
    lda #0
    sta f:CACHE_AGE, x          ; drawn: nobody takes it this frame
    jsr cache_tile
.a16
    sta temp + 2
    sep #$20
.a8
    lda temp + 2
    sta obj_tile
    lda temp + 3
    and #$01                    ; bit 8 of the tile lives in the attributes
    sta obj_attr
    lda temp + 1
    and #$FE
    ora obj_attr
    sta obj_attr
    plx
    lda #1
    sta f:CACHE_WAS + 3, x      ; shown: kept for the next frame
    clc
    rtl
.endproc

; X: the entry `cache_was_note` kept for row `CACHE_T_ROW`, carry clear; or
; carry set if it has none. Y is the row.
.proc cache_was_find
.a8
.i16
    rep #$20
.a16
    lda f:CACHE_T_ROW
    tay
    sep #$20
.a8
    lda npc_buf + 8, y          ; its event: `CACHE_T_EV` is a twin's by now
    ldx #CACHE_WAS_SIZE * (CACHE_WAS_MAX - 1)
find:
    cmp f:CACHE_WAS, x
    beq found
    dex
    dex
    dex
    dex
    bpl find
    sec
    rts
found:
    clc
    rts
.endproc

; From `cache_want`, with the cache full: row `CACHE_T_ROW` takes the slot
; of the look `cache_was_note` kept for it, for its new still pose. Carry
; clear and A the slot, whose pose goes up now. Carry set if it has no kept
; look, or no slot holds it; or someone already drew that slot in this pass
; —a row showing the same still pose, which would lose it in the middle of
; the frame—; or either key is not a still pose —a walking one's slot is
; shared with whoever animates with it—; or the queue has no room, and then
; it is drawn with the kept look and tries again next frame. The kept
; look's key becomes the new one, so `cache_was_draw` draws the row from
; that slot on this same frame, with the attributes it had: the pose goes
; up in the vblank that shows it.
.proc cache_was_own
.a8
.i16
    lda f:CACHE_T_KEY
    bmi no
    lda vq_n
    cmp #VQ_MAX - 1
    bcs no                      ; `vram_queue` would refuse it
    jsr cache_was_find
    bcs no
    lda f:CACHE_WAS + 1, x
    bmi no
    sta temp
    phx
    jsr cache_last
seek:
    lda f:CACHE_KEY, x
    cmp temp
    beq up
    dex
    bpl seek
    plx
no:
    sec
    rts
up:
    lda f:CACHE_AGE, x
    beq drawn                   ; someone drew it in this pass
    txa
    sta f:CACHE_T_SLOT
    plx
    lda f:CACHE_T_KEY
    sta f:CACHE_WAS + 1, x
    lda f:CACHE_T_SLOT
    clc
    rts
drawn:
    plx
    sec
    rts
.endproc

; Row X, about to be drawn in a map with a cache. Carry clear: it is drawn,
; with `obj_tile` and `obj_attr` already set. Carry set and A zero: it is not
; drawn this frame —the cache is full—. Carry set and A not zero: its pose
; goes up first —`vq_src` and `vq_dest` ready for `vram_queue`, and
; `cache_took` if it got in— and it is drawn from the next frame on.
.proc cache_want
.a8
.i16
    rep #$20
.a16
    txa
    sta f:CACHE_T_ROW
    sep #$20
.a8
    txy                         ; Y: the row, until the upload
    lda npc_buf + 8, y          ; its event
    sta f:CACHE_T_EV
    ; The one facing the hero is in the turn slot, which its row points at,
    ; if it is a still one: one that walks or animates turns in its own
    ; slot —`turn_apply`—, and its row's tile is nobody's. Taking it drew
    ; Arden as the hero on map 38: tile 0 is his.
    cmp f:TURN_EV
    bne asks
    lda npc_buf + 9, y
    cmp #NPC_STILL
    bne asks
    lda npc_buf + 6, y
    sta obj_tile
    lda npc_buf + 7, y
    sta obj_attr
    clc
    rtl
asks:
    ; What it asks for: the still pose its row carries, or its own, or a
    ; twin's, which its row carries like a still pose.
    lda npc_buf + 9, y
    cmp #NPC_STILL
    beq still
    lda npc_buf + 6, y
    bmi keyed                   ; a twin's: 128 plus the one it animates with
    lda npc_buf + 8, y
    ora #$80
    bra keyed
still:
    lda npc_buf + 6, y
keyed:
    sta f:CACHE_T_KEY
    ; The slot it had, if it still holds that.
    jsr cache_event_x
    lda f:CACHE_EV, x
    cmp #$FF
    beq seek
    jsr cache_a_to_x
    lda f:CACHE_KEY, x
    cmp f:CACHE_T_KEY
    beq drawn
seek:
    ; A key someone else already has up: a still pose, or a twin's slot.
    jsr cache_last
seek_one:
    lda f:CACHE_KEY, x
    cmp f:CACHE_T_KEY
    beq found
    dex
    bpl seek_one
evict:
    ; The free one drawn longest ago: two frames or more.
    lda #1
    sta f:CACHE_T_AGE
    lda #$FF
    sta f:CACHE_T_SLOT
    jsr cache_last
oldest:
    lda f:CACHE_AGE, x
    cmp f:CACHE_T_AGE
    bcc younger
    beq younger
    sta f:CACHE_T_AGE
    txa
    sta f:CACHE_T_SLOT
younger:
    dex
    bpl oldest
    lda f:CACHE_T_SLOT
    cmp #$FF
    bne upload
    ; Full: a row whose look changed on screen takes the slot of the one it
    ; had, and the rest wait.
    jsr cache_was_own
    bcc upload
    lda #0
    sec
    rtl

found:
    ; It is its slot from now on.
    txa
    pha
    jsr cache_event_x
    pla
    sta f:CACHE_EV, x
    jsr cache_a_to_x
drawn:
    ; Drawn: its age back to 0, and its tile with the row's attributes.
    lda #0
    sta f:CACHE_AGE, x
    jsr cache_tile
.a16
    sta temp
    lda f:CACHE_T_ROW
    tax                         ; X as it came
    sep #$20
.a8
    lda temp
    sta obj_tile
    lda temp + 1
    and #$01                    ; bit 8 of the tile lives in the attributes
    sta obj_attr
    lda npc_buf + 7, x
    and #$FE
    ora obj_attr
    sta obj_attr
    clc
    rtl

upload:
    ; Where it goes: the slot's tile times sixteen words from the sprites'
    ; base, which is the map's.
    jsr cache_a_to_x
    jsr cache_tile
.a16
    asl a
    asl a
    asl a
    asl a
    ldx map_ofs
    clc
    adc f:map_table + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    ; And where it comes from: its place in `npc_poses`, (k * 12 + pose) * 3.
    lda f:CACHE_T_KEY
    bmi own
    rep #$20
.a16
    and #$00FF
    asl a
    sta temp
    lda f:CACHE_REC
    tax
    lda f:cache_data + 1, x     ; where the map's still poses start
    clc
    adc temp
    tax
    lda f:cache_data, x
    bra source
.a8
own:
    ; Its pose is the one its row last asked for; a row nobody refreshed
    ; since the map loaded faces where its page says, standing.
    rep #$20
.a16
    lda f:CACHE_T_ROW
    tax
    sep #$20
.a8
    lda npc_buf + 12, x
    cmp #$FF
    bne with_pose
    lda npc_buf + 10, x
    sta temp
    asl a
    clc
    adc temp                    ; the direction times three
    inc a                       ; the middle column
with_pose:
    sta f:CACHE_T_POSE
    rep #$20
.a16
    and #$00FF
    sta temp
    asl a
    clc
    adc temp                    ; the pose times three
    sta temp
    lda npc_buf + 9, x
    and #$00FF
    asl a
    asl a                       ; times four
    sta temp + 2
    asl a
    asl a
    asl a                       ; times thirty-two
    clc
    adc temp + 2                ; thirty-six per character
    clc
    adc temp
source:
.a16
    tay
    lda [poses_ptr], y
    sta vq_src
    sep #$20
.a8
    iny
    iny
    lda [poses_ptr], y
    sta vq_src + 2
    rep #$20
.a16
    lda f:CACHE_T_ROW
    tax                         ; X as it came
    sep #$20
.a8
    lda #1
    sec
    rtl
.endproc

; The pose `cache_want` asked for got into the queue: the slot holds it from
; the next vblank on, and it is the row's.
.proc cache_took
.a8
.i16
    lda f:CACHE_T_SLOT
    jsr cache_a_to_x
    lda f:CACHE_T_KEY
    sta f:CACHE_KEY, x
    lda #0
    sta f:CACHE_AGE, x
    jsr cache_event_x
    lda f:CACHE_T_SLOT
    sta f:CACHE_EV, x
    lda f:CACHE_T_KEY
    bpl ready
    ; A twin's is also the slot of the one it animates with, whose uploads
    ; keep it up to date: see `cache_dest`.
    and #$7F
    cmp f:CACHE_T_EV
    beq own
    sta f:CACHE_T_EV
    jsr cache_event_x
    lda f:CACHE_T_SLOT
    sta f:CACHE_EV, x
own:
    ; Its own: the pose in the slot is the one `upload_npc_pose` compares.
    rep #$20
.a16
    lda f:CACHE_T_ROW
    tax
    sep #$20
.a8
    lda f:CACHE_T_POSE
    sta npc_buf + 12, x
    lda #1                      ; and if it animates standing still, its
    sta f:still_dirty           ; column goes up next frame: animated_stills.s
ready:
    rtl
.endproc

; Where row Y's own slot is, for `upload_npc_pose`: carry clear and
; `vq_dest` set, or carry set if it has none —it is out of view, and the pose
; it asked for waits in its row for `cache_want`—. Y as it came.
.proc cache_dest
.a8
.i16
    lda npc_buf + 8, y
    sta f:CACHE_T_EV
    jsr cache_event_x
    lda f:CACHE_EV, x
    cmp #$FF
    beq none
    jsr cache_a_to_x
    lda npc_buf + 8, y
    ora #$80
    cmp f:CACHE_KEY, x
    bne none                    ; someone else's by now
    jsr cache_tile
.a16
    asl a
    asl a
    asl a
    asl a
    ldx map_ofs
    clc
    adc f:map_table + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    clc
    rtl
none:
    sec
    rtl
.endproc

; A still row that a route turned, to pose A, from `refresh_npc`: Y the row.
; In a map with a cache it asks for the still pose that faces there instead
; of its own. Wally keeps still the ones that routes only turn —`turners`
; in its `moves`— and puts every pose of their characters among the
; cache's still poses, which are sorted: a character's twelve go together,
; so the new key is the old one moved by as much as the pose moves. The old
; pose is read from the key's entry, `(k * 12 + pose) * 3`, and not from
; +12, which a bank reloaded after a battle leaves at $FF. Zounds' map 96:
; fifty-six floor switches that turn when pressed, two poses for all of
; them instead of a slot each.
;
; Elsewhere no still row is sent a route that turns it —it walks in a slot
; of its own—, and there is nothing to do. X is lost, as `refresh_npc`
; allows.
.proc still_turn
.a8
.i16
.ifdef posed_stills
    ; One drawn into the background only changes pose: its cell follows it
    ; in `posed_row`. See posed.s.
    pha
    lda npc_buf + 7, y
    and #$30
    cmp #$30
    bne an_object
    pla
    sta npc_buf + 12, y
    rtl
an_object:
    pla
.endif
    sta f:CACHE_T_POSE          ; the new pose
    lda f:SHARE_N
    bmi cache
    rtl
cache:
    rep #$20
.a16
    lda npc_buf + 6, y          ; its still pose's key
    and #$00FF
    asl a
    pha
    lda f:CACHE_REC
    tax
    lda f:cache_data + 1, x     ; where the map's still poses start
    clc
    adc 1, s
    tax
    pla
    lda f:cache_data, x         ; (k * 12 + pose) * 3
character:
    cmp #36
    bcc in_character
    sbc #36                     ; the carry is set
    bra character
in_character:
    sep #$20
.a8
    ldx #$0000                  ; the old pose, three at a time
thirds:
    cmp #3
    bcc counted
    sbc #3                      ; the carry is set
    inx
    bra thirds
counted:
    txa
    sta f:CACHE_T_KEY
    lda npc_buf + 6, y
    sec
    sbc f:CACHE_T_KEY
    clc
    adc f:CACHE_T_POSE
    jsl f:cache_was_note + FAST ; the look it had, while the new one goes up
    sta npc_buf + 6, y
    lda f:CACHE_T_POSE
    sta npc_buf + 12, y
    rtl
.endproc

; X: the event in `CACHE_T_EV`, to index `CACHE_EV`. Keeps A.
.proc cache_event_x
.a8
.i16
    pha
    rep #$20
.a16
    lda f:CACHE_T_EV
    and #$00FF
    tax
    sep #$20
.a8
    pla
    rts
.endproc

; X: A, a slot.
.proc cache_a_to_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    rts
.endproc

; X: the cache's last slot, to walk them down to 0.
.proc cache_last
.a8
.i16
    rep #$20
.a16
    lda f:CACHE_N
    and #$00FF
    dec a
    tax
    sep #$20
.a8
    rts
.endproc

; Slot X's first tile in the sprite bank, in A, which comes back in sixteen
; bits.
.proc cache_tile
.a8
.i16
    rep #$20
.a16
    txa
    asl a
    clc
    adc f:CACHE_REC
    tax
    lda f:cache_data + 3, x
    rts
.endproc

.assert CACHE_EV + EV_MAX <= CACHE_N + $50 + EV_MAX, error, "the cache's events overflow its RAM"

