; --- phasing: Select walks the hero through everything -----------------------
;
; RPG_RT's test play walks the hero through walls and events while Ctrl is
; held: easyrpg's `Game_Player::UpdateNextMovementAction` sets `through`
; around the pad's `Move` when `Player::debug_flag` is on and
; `DEBUG_THROUGH` is pressed. Here **Select toggles it**, which is what taro
; asked for and a key nothing else reads; that difference is in the book,
; in Zounds' page and the divergence `phasing-is-a-toggle-on-select`.
;
; What it lets through is RM2k's `through`, and the runtime already had it:
; `crossing`, the flag a move route's `ThroughOn` turns on around its step.
; `move_hero` sets it from `phasing` around the pad's step only, as RPG_RT
; does, so a move route still walks with its own. What follows from that,
; and is RPG_RT's too:
;
;   * the tiles, the tile events and the events on the hero's layer let him
;     through; the map's edge does not, unless the map loops;
;   * stepping on a cell still fires its touch pages below and above the
;     hero, and a bump no longer happens —no step is refused but at the
;     edge—;
;   * events walking into the hero are still stopped by him;
;   * no random encounters while it is on: `UpdateEncounterSteps` returns
;     first thing. The steps still count for the states' damage.
;
; While it is on the hero blinks, so it shows on the console.
;
; It exists only with `[debug] phasing` in the project, which the
; converter turns into `DEBUG_PHASING`: without it this file assembles to
; nothing and every caller is under the same `.if`, so the ROM is the one
; without it byte for byte.

.if ::DEBUG_PHASING

.pushseg
.segment "BSS"
; 1 while Select left it on, 0 off. Reset turns it off; the save does not
; carry it.
phasing: .res 1
.popseg

.pushseg
.segment "FAR3"

; Once per frame, from the main loop before `move_hero`, with the pad
; already read: Select's rising edge toggles it. Clobbers A.
.proc phasing_keys
.a8
.i16
    lda pad
    eor pad_prev
    and pad
    and #PAD_SELECT
    beq done
    lda f:phasing
    eor #1
    sta f:phasing
done:
    rtl
.endproc
.popseg

.endif
