; --- the RAM in bank 1 ---------------------------------------------------------
; What bank 0's BSS and ZEROPAGE have left is said by `just space`: this
; used to say it in numbers, and they went stale. The console has 128 KB of
; WRAM and bank 0 sees eight: the rest is reached through this same window,
; pointing WMADD and reading or writing $2180 with auto-increment. It is not
; normal addressing —it cannot be indexed— so it is good for what is stored
; and walked a little at a time, not for what is drawn.
;
; **A new variable in far RAM does not get an address written by hand**: it
; goes in the file of its subsystem, with a `.res` in `FARBSS`, and the
; linker places it —
;
;     .pushseg
;     .segment "FARBSS"
;     my_state: .res 2
;     .popseg
;
; — the same as a new one in the `BSS` or the `ZEROPAGE`, which are declared
; the same way. Two branches that each add one do not touch the same line,
; and their variables cannot overlap: until 2026-10-16 the addresses were
; chosen by hand as "the next free one", and more than once two branches
; chose the same one without git seeing it. When `FARBSS` no longer fits, the link
; fails, and `just space` says how much is left.
;
; The segment is declared `far` here, before anyone uses it, so its labels
; carry the bank —`$7E`—: read plainly they are a long access, which is
; right whatever the data bank. Code that runs with the data bank at `$7E`
; —the battle, the text layer— writes `.loword(my_state)`, and so does a
; line of `save_table`, which is a `.word` and fails the link with a 24-bit
; value. **A label used before its declaration** in the order of `main.s` is
; taken as sixteen bits, and the link fails with a range error: that use
; goes with `f:`.
;
; **All of `$7E2000-$7E7FFF` is the segment's**, since 2026-10-16: what
; follows was a map of addresses written by hand until that day, with holes
; between its regions, and each region went into a `.res` of its own size
; in the same order —see `FAR_POOL_START` in
; rm2k-snes/cartridge/src/banks.rs—. Many keep their old names as sixteen-bit
; constants, `.loword` of the label, because the code that reads them runs
; with the data bank at `$7E` or points the WMADD window at them: the label
; is lowercase and the constant uppercase, `far_battle` and `FAR_BATTLE`.
; **A block that is walked as a range is one `.res` with offsets**, or
; several in a row with an `.assert` that they are adjacent: the linker
; places them in the order of the text, and nothing else promises it.
.pushseg
.segment "FARBSS": far
.popseg
;
; **What the game sizes is declared in far_ram_game.s**, after the
; cartridge's `.inc` says how big it is: the names stay here, with their
; why, and the `.res` goes there. What does not depend on the game goes
; here, at its own size.
FAR_PAIR_STATE = .loword(far_pair_state)    ; EV_MAX entries of PAIR_BYTES
FAR_PAIR_LIST  = .loword(far_pair_list)     ; PARALLEL_MAX entries of PAIR_LIST_BYTES
; The RM2k variables, one signed word per slot. How many there are is said by
; the converter —`VARIABLES_N`—, which gives a slot only to the ones named by
; the pages of the maps in the ROM; the bytecode talks in slots. They are read
; and written with `var_read` and `var_write`, and they travel in the save:
; `save_table` copies them from here, which the DMA reaches just like bank
; 0 because WMADD is a seventeen-bit address.
FAR_VARIABLES  = .loword(far_variables)
; And the inventory, after the variables: one byte per LDB item, indexed by
; the RM2k number —0 is unused— and capped at ITEM_MAX, like
; `Game_Party::AddItem`. It travels in the save and is cleared with the
; variables.
FAR_ITEMS      = .loword(far_items)
; And the random state: a sixteen-bit xorshift, the same as `random_next` in
; events.py, seeded on reset. It goes here and not in the direct page
; because the direct page ended up at 258 of 256 when that was tried;
; randomness is asked for rarely and the port does not notice.
FAR_RANDOM     = .loword(far_random)
; And the hero's speed, 1 to 6: move commands 28 and 29 of a forced move
; route raise and lower it and **it stays that way**, for the pad too —RM2k
; only restores the frequency when the move route ends,
; `original_move_frequency`; not the speed—. It travels in the save. It is
; read once per step.
FAR_HERO_SPEED = .loword(far_hero_speed)
; And the permissions: `ChangeSaveAccess`, `ChangeMainMenuAccess` and
; `ChangeEscapeAccess` turn them off and on, and bit 7 is RM2k's menu
; request, `menu_calling`: B sets it and the hero handles it when standing
; still. The bits are stored as "forbidden" so that the zero from reset
; means "everything allowed", which is how RM2k starts. It travels in the
; save, as it does there. And entering a map writes its save, escape and
; teleport over them: see `map_access_enter`.
;
; The escape one is stored and **nobody reads it yet**: it is the Escape
; skill's —not the battle's Escape command, which RM2k does not tie to it—,
; and that skill cannot be used from the menu yet. It is here because it is
; one bit and because without it 30 of the game's 39 pages with
; `EnemyEncounter` that fail today do not compile; see `ACCESS_BIT` in the
; event compiler.
FAR_ACCESS     = .loword(far_access)
; And `MessageOptions`: where and how the message window is drawn, which
; lasts until the next one and travels in the save, like `SaveSystem`'s four
; fields. `OP_MESSAGE_OPTIONS` writes it whole and `clear_variables` puts
; RM2k's default at reset: at the bottom, with its frame, moving out of the
; hero's way —`message_prevent_overlap` is 1 in liblcf— and with the events
; stopped.
FAR_MSG_OPTIONS = .loword(far_msg_options)
MSG_WHERE    = $03              ; 0 top, 1 middle, 2 bottom
MSG_BARE     = $04              ; without the frame and the background
MSG_DODGE    = $08              ; moves if it would cover the hero
MSG_CONTINUE = $10              ; the events go on moving during a page
MSG_DEFAULT  = 2 | MSG_DODGE
; **These six are one block, in this order**, in far_ram_game.s:
; `clear_variables` writes the first five bytes and clears the rest up to
; the inventory's end in one pass through the WMADD window.
; And the list of the items screen —and of the equipment's, the shop's selling
; one and the battle's—, one `k` per word: see items.s, which declares it.
FAR_ITEM_LIST  = .loword(far_item_list)
; And the equipment of each LDB actor, by actor number: five words —weapon,
; shield, armor, helmet, accessory— with the item number or 0. It starts with
; the database's initial equipment, which `initial_equipment_set` copies on
; reset, and travels in the save.
FAR_EQUIPMENT  = .loword(far_equipment)
; And how much the player added to that speed with L and R, signed, and which
; of the two were held on the last frame, for the edge: see
; `hero_speed_keys.s`. They do **not** travel in the save —it is a taste of
; whoever is playing, not world state— and reset clears them.
FAR_SPEED_BONUS = .loword(far_speed_bonus)
FAR_SPEED_KEYS  = .loword(far_speed_keys)
; And what the window that is on screen took from it when it opened, and the
; HDMA that puts it there: see `msg_place` and `msg_hdma_build`, in
; message_place.s. They do not travel in the save: they are the open window's,
; and `FAR_MSG_OPTIONS` is what lasts.
.pushseg
.segment "FARBSS"
far_speed_bonus: .res 1
far_speed_keys:  .res 1
MSG_PLACE:       .res 1         ; the position the window really took, plus MSG_BARE
MSG_SC:          .res 1         ; BG2SC of the window's tilemap: a big picture moves it
MSG_ENTRY:       .res 1         ; the window's stretch in `hdma_ofs`: 0, 5 or 10
MSG_VOFS:        .res 1         ; BG2VOFS while the window is drawn
; And the arrow of a message waiting for a key: how long it has been up, and
; what its cells say. See message_arrow.s.
MSG_ARROW_T:     .res 1
MSG_ARROW_WAY:   .res 2         ; `msg_arrow`'s scratch
MSG_ARROW_UP:    .res 1         ; whether its cells say it is up; $FF is not known
; And the +15 of the page `active_layer` found —its speed, and whether its
; graphic is fixed—, beside `found_flags`, for which bank 0 has no room left.
FOUND_SPEED:     .res 1
.popseg
ACCESS_NO_SAVE = $01
ACCESS_NO_MENU     = $02
ACCESS_NO_ESCAPE = $04
; Teleport is only ever forbidden by the map —`map_access_enter`—: no
; command sets it yet, and nothing reads it until the Teleport skill exists.
ACCESS_NO_TELEPORT = $08
; The ones a map writes when it is entered: see `map_access_enter`.
ACCESS_MAP = ACCESS_NO_SAVE | ACCESS_NO_ESCAPE | ACCESS_NO_TELEPORT
ACCESS_REQUESTED   = $80
; --- the actors: their state in far RAM ----------------------------------------
;
; The HP of each LDB actor, one word per actor number. **They are real state
; since there are battles**: until 2026-09-12 nobody went below their maximum
; and `ChangeHP` compiled to nothing. They travel in the save, after the
; equipment, and reset fills them up.
FAR_HP = .loword(far_hp)

; Far RAM with the bank in front, for the few who read it from outside with
; `lda f:`: it is the same as `BAT_LENGTH`, which kept a battle name.
FAR_LENGTH = $7E0000

; And the SP, which are state for the same reason as the HP since skills can
; be used: each one costs its `sp_cost` and `Scene_Battle` deducts it from
; whoever uses it. They start full from `actor_spmax` and travel in the save,
; after the HP.
FAR_SP = .loword(far_sp)

; And which graphic a `ChangeSpriteAssociation` changed each LDB actor's
; sprite to, one byte per actor number: the index in the map's graphics table
; —the same one move command 34 of a move route resolves— or $FF if it keeps
; the LDB one. It travels in the save, as in RM2k, and **survives the
; teleport**: that is what sets it apart from move command 34 on the hero,
; which is restored on load.
FAR_ACTOR_GFX = .loword(far_actor_gfx)
ACTOR_GFX_NONE = $FF
; The equipment, the HP, the SP and the graphic are tables by LDB actor
; number, `ACTORS_N` entries each —the highest number plus one—: they are
; declared in far_ram_game.s, sized by the game, so no game's actors can
; run one table into the next.

; The text layer of the screens: what each text row of the menu, the slots,
; the items, equipment, the shop and the battle says, the row being typeset
; and which tiles each cell took. See `text_layer.s`. It is named with a
; sixteen-bit address, like the battle's, and read with the data bank at
; $7E. It does not travel in the save: a screen fills it from scratch when it
; opens.
;
; `TL_BYTES` is what text_layer.s lays out, written as a number because
; the `.res` needs one before the layout exists; text_layer.s asserts that
; it is exactly that.
TL_BYTES = $224A
.pushseg
.segment "FARBSS"
far_text_layer: .res TL_BYTES
far_text_layer_end:
.popseg
FAR_TEXT_LAYER = .loword(far_text_layer)
FAR_TEXT_LAYER_END = .loword(far_text_layer_end)

; And which skills each actor knows, since 2026-09-21: one bit per (actor,
; skill) pair, with the slot the converter gave each pair —see
; `SKILL_SLOT` in events.py—. It starts with what the LDB says for the
; initial level, which `initial_skills_set` copies on reset, `ChangeSkills`
; sets and clears it, and it travels in the save. How many bytes it takes is
; said by `SKILL_BYTES`, and the converter stops if they go past 256. It
; is declared in far_ram_game.s.
FAR_SKILL = .loword(far_skill)

; --- random encounters: their state in far RAM -------------------------------
;
; Nine bytes. **It does not travel in the save**, just
; as the HP of an unfinished battle do not: on load, the accumulated count
; starts at zero, which is the same thing that happens on entering a map.
;
; It did not fit in bank 0: the BSS is at 7680 of 7680, measured on
; 2026-09-13 by adding a `.res 64` and looking at the assembler's cut.
.pushseg
.segment "FARBSS"
far_encounter: .res 9
.popseg
FAR_ENCOUNTER = .loword(far_encounter)
ENC_N     = FAR_ENCOUNTER + 0   ; steps taken since the last encounter
ENC_IDX   = FAR_ENCOUNTER + 1   ; the table row, which never goes down
ENC_ASKS  = FAR_ENCOUNTER + 2   ; one came up and is collected next frame
ENC_RNG   = FAR_ENCOUNTER + 3   ; word: the xorshift, with its own seed
ENC_BASE  = FAR_ENCOUNTER + 5   ; word: 1/steps in 1/65536; 0 is off
ENC_REG   = FAR_ENCOUNTER + 7   ; word: this map's record, or ENC_NONE
; A map with no troops of its own and no areas covering it. **A word since
; the encounter tables went to two bytes**: a game like Vampires Dawn has 779
; troops. No record is as high as $FF00 —the converter caps them at 8191, so
; that `record * 8` fits the table's 16-bit offset— so the high byte alone
; tells it, which is what the 8-bit code reads: `lda ENC_REG + 1`.
ENC_NONE  = $FFFF
; The eight rows of `UpdateEncounterSteps`'s table, and how many threshold
; bytes each record carries: seven —row 0's is 0 and is not stored— plus one
; of padding, so that the index is a shift and not a multiplication.
ENC_ROWS   = 8
ENC_STRIDE = 8
; The current map's thresholds, copied from `enc_threshold_n` on entry: the step
; at which each row is crossed, from 1 to 7. They live in RAM and are not
; read from the table because `ChangeEncounterSteps` changes them along with
; `ENC_BASE`: the chance and the rows come from the same `encounter_steps`.
;
; Like the rest of the encounters, with a sixteen-bit address: it is read
; with the data bank at $7E.
.pushseg
.segment "FARBSS"
far_enc_thr: .res ENC_STRIDE
.popseg
ENC_THR   = .loword(far_enc_thr)

; --- experience and level: their state in far RAM ----------------------------
;
; Four bytes per actor who can fight, in the order of the slots of
; `rm2k-snes-battle` —`actor_exp_k` says which one each actor number gets,
; or $FF—: the 24-bit experience, which in RM2k reaches 999999, and the level.
; Having the level right next to the experience is what makes the save carry
; a single line for both. It starts from `exp_initial` on reset and travels
; in the save.
; `EXP_K` slots: declared in far_ram_game.s.
FAR_EXP     = .loword(far_exp)
EXP_LEVEL   = 3             ; the level, the fourth byte
; And eight bytes where `text_level` and its siblings compose the level and
; the maximum the menu writes: they are numbers from the save and no longer
; strips from the cartridge.
.pushseg
.segment "FARBSS"
EXP_TEXT: .res 8
.popseg
; RM2k's `MaxExpValue()`, in its two halves.
EXP_CAP_HI = $0F
EXP_CAP_LO = $423F

; --- troop pages: their state in far RAM --------------------------------------
;
; **It does not travel in the save**, like nothing in the battle. It is named with a
; sixteen-bit address, same as `FAR_BATTLE`, because the battle code reads
; it with the data bank at $7E; the bridge from bank 0 puts `BAT_LENGTH` in
; front of it.
; Sixteen bytes and `TROOP_PAGE_MAX`: declared in far_ram_game.s.
FAR_PAGE      = .loword(far_page)
BA_PAGE_N     = FAR_PAGE + 0    ; how many pages this battle's troop brings
BA_PAGE_INIT  = FAR_PAGE + 1    ; word: the first, in the `tpage_*` tables
BA_PAGE_CODE  = FAR_PAGE + 3    ; word: where the running one starts, in the
                                ; bank of `troop_code`
BA_PAGE_CUR   = FAR_PAGE + 5    ; word: its cursor, its own `ev_cur`
BA_PAGE_ACT   = FAR_PAGE + 7    ; whether it has not finished yet: its `ev_active`
BA_PAGE_MSG   = FAR_PAGE + 8    ; word: the message it asked for and is on
                                ; screen, in `messages_troop`, or $FFFF
BA_PAGE_TICK = FAR_PAGE + 10    ; where the battle goes on when none are left:
                                ; 0 the next action, 1 ask for the commands
BA_PAGE_I     = FAR_PAGE + 11   ; which one the sweep is on
BA_PAGE_G     = FAR_PAGE + 12   ; word: that same one, in the `tpage_*` tables
BA_PAGE_DONE  = FAR_PAGE + 16   ; TROOP_PAGE_MAX bytes: already ran this turn
; And what the turn and HP conditions and the commands that come with them
; added, on 2026-09-28: one block of $20 bytes, with a sixteen-bit address,
; like the rest of the battle.
.pushseg
.segment "FARBSS"
far_ba_turn: .res $1B
.popseg
BA_TURN       = .loword(far_ba_turn)    ; word: the turn, `Game_Party::GetTurns`
BA_PAGE_WAIT = BA_TURN + $02    ; word: frames left in the wait of the
                                ; running page
BA_PCT_MIN    = BA_TURN + $04   ; the HP range, in percent, that is checked
BA_PCT_MAX    = BA_TURN + $05
BA_P24        = BA_TURN + $06   ; three bytes: what `ba_mul24` leaves
BA_P_HP       = BA_TURN + $09   ; three bytes: a hundred times the HP checked
BA_PAGE_FL    = BA_TURN + $0C   ; the triggers of the page being tested
; And its header, copied from in front of its code: `Trigger::header` in
; the event compiler, in the same order.
BA_COND       = BA_TURN + $10
BA_COND_BASE  = 0               ; word: the turn base, `turn_b`
BA_COND_MULT  = 2               ; word: and its multiple, `turn_a`
BA_COND_ENEMY = 4               ; the enemy's place in the troop
BA_COND_EMIN  = 5               ; and its HP range, in percent
BA_COND_EMAX  = 6
BA_COND_ACT   = 7               ; the actor, by LDB number
BA_COND_AMIN  = 8
BA_COND_AMAX  = 9
.assert BA_COND + TPAGE_HEADER <= BA_SYNC_I, error, "the pages' state overflows its range"
; And the one for the party a page changes, on 2026-09-30, after the header:
; which place of `party` `ba_sync_in` is on, which `ba_actor_setup` does not
; clobber.
BA_SYNC_I     = BA_TURN + $1A
.assert BA_SYNC_I < BA_TURN + $1B, error, "the pages' state overflows its range"
.assert BA_SYNC_I >= BA_COND + TPAGE_HEADER, error, "BA_SYNC_I steps on the header"

; --- a medicine outside battle: its scratch space in far RAM -----------------
;
; **It does not travel in the save**: it lasts as long as one A press in the
; actor choice. `medicine_use` runs with the data bank at $7E, so it names
; them by their `.loword`.
.pushseg
.segment "FARBSS"
MED_ACTOR:    .res 1            ; the actor, by LDB number
MED_FLAGS:    .res 1            ; the item's `item_medicine` bits
MED_USED:     .res 1            ; whether it worked: easyrpg's `was_used`
MED_REVIVED:  .res 2            ; word: 1 if it revived it, the `revived`
MED_HP_MAX:   .res 2            ; word: the max HP for its level
MED_SP_MAX:   .res 2            ; word: and the SP
MED_HP:       .res 2            ; word: the `hp_change`
MED_SP:       .res 2            ; word: the `sp_change`
MED_P:        .res 4            ; four bytes: the product, and the quotient
MED_R:        .res 2            ; word: the remainder
MED_ID:       .res 2            ; word: the item's RM2k number
.popseg
; The `item_medicine` bits, which the converter emits. `medicine_use` writes
; them by number; the battle, which reads them since 2026-09-26, by name.
MED_KO_ONLY   = $01             ; only on a fallen one
MED_RAISES    = $02             ; removes the dead state: revives the fallen one
MED_USES      = $04             ; it has uses: using it spends one
MED_MATERIAL  = $08             ; a material: it raises parameters, see `FAR_GROWTH`

; --- what the materials added: its state in far RAM ---------------------------
;
; What the items of type material —`Type_material`: the seeds, the pills—
; added to each actor for good: RM2k's `hp_mod`, `sp_mod`, `attack_mod`,
; `defense_mod`, `spirit_mod` and `agility_mod` of `SaveActor`. Six signed
; words per experience slot —the actors that can be in the party, in the
; order of `actor_exp_k`—, in the order of `level_param`'s Y: maximum HP,
; maximum SP, attack, defense, spirit and agility. `level_param` adds them,
; so everything that asks for an actor's parameter —the menu, the equipment,
; the battle, `FullHeal`— sees them. They start at zero on reset, travel in
; the save, and `medicine_use` adds to them. `ChangeParameters`, which is the
; other way RM2k has of moving them, the port does not compile.
;
; The table itself is a `.res` in `FARBSS`, in medicine.s, sized by the game
; —`EXP_K` rows—: it cannot be declared here, which comes before the
; cartridge's `.inc` says how many slots there are.
GROWTH_BYTES  = 12
GROWTH_MAX    = 999             ; `MaxHpValue`, `MaxSpValue` and `MaxStatBaseValue` of RM2k

; What `pair_ev` holds while a troop page runs: neither the foreground ($FF)
; nor a map event, which are fewer than EV_MAX. It is what tells
; `op_message` that the message belongs to the battle. See `ba_t_page`.
PAIR_BATTLE = $FE
.assert EV_MAX < PAIR_BATTLE, error, "PAIR_BATTLE must not be an event"

; And the battle state, which does **not** travel in the save: a battle cannot
; be saved in RM2k either.
; How many bytes the battle's state takes: up to `BA_HOFS_HDMA`'s ten.
BA_BATTLE_BYTES = 713
.pushseg
.segment "FARBSS"
far_battle: .res BA_BATTLE_BYTES
.popseg
FAR_BATTLE = .loword(far_battle)
; The same address but long, for the few who touch it from outside the
; battle: `op_battle` runs with the bytecode's data bank.
BAT_LENGTH = $7E0000
; **Everything here is named with a sixteen-bit address, not a long one**,
; and the battle code runs with the data bank at $7E. That is what lets it use
; absolute addressing: `inc`, `stz`, `ldx` and `cpy` have no long mode, so
; with `f:` each one would have to go through the accumulator. And it costs
; nothing to the rest: in bank $7E the addresses $0000 to $1FFF **are** bank
; 0's low RAM, so `temp`, `comp_*` and `party` are still read as always. What
; does change are the ROM tables, which go with `f:`.
BA_TROOP   = FAR_BATTLE + 0       ; the troop, as an RM2k number
BA_RESULT  = FAR_BATTLE + 2       ; 0 victory, 1 escape, 2 defeat
BA_SEED    = FAR_BATTLE + 3       ; the battle's xorshift, with its own seed
BA_NACTORS = FAR_BATTLE + 5       ; how many actors
BA_KID     = FAR_BATTLE + 6       ; how many enemies
BA_MODE    = FAR_BATTLE + 7
BA_ACTOR   = FAR_BATTLE + 8       ; who is being asked for a command
BA_COMMAND = FAR_BATTLE + 9       ; which command the cursor marks
BA_TARGET  = FAR_BATTLE + 10      ; which enemy the cursor marks
BA_ESCAPE  = FAR_BATTLE + 11      ; the chance to escape, which rises on failing
BA_I       = FAR_BATTLE + 12      ; which one of the execution the turn is on
BA_WAIT    = FAR_BATTLE + 13      ; frames the message has left
BA_MTYPE   = FAR_BATTLE + 14      ; what the message says
BA_MWHO    = FAR_BATTLE + 15
BA_MTGT    = FAR_BATTLE + 16
BA_MDMG    = FAR_BATTLE + 17      ; word
BA_NACTIONS = FAR_BATTLE + 19     ; how many actions the turn has
BA_T0      = FAR_BATTLE + 20      ; scratch words, which anyone clobbers
BA_T1      = FAR_BATTLE + 22
BA_T2      = FAR_BATTLE + 24
BA_S0      = FAR_BATTLE + 26      ; and the ones that survive a `jsr`
BA_S1      = FAR_BATTLE + 28
BA_S2      = FAR_BATTLE + 30
BA_S3      = FAR_BATTLE + 32
BA_S4      = FAR_BATTLE + 34
BA_S5      = FAR_BATTLE + 36
BA_S6      = FAR_BATTLE + 38
; `FAR_BATTLE + 40` was `BA_WITHMAX` —whether a line showed the max HP— until
; 2026-10-04, when the party and the enemies stopped sharing a line.
; The battle's audio, in the bytes that were left loose before `BA_ACC`.
; `BA_SONG_PREV` is the song that was playing on the map —$FF if nothing was—,
; which is RM2k's `before_battle_music`: when the battle ends it comes back.
; `BA_SE2` is the sound effect still to fire in the current message, or
; $FFFF: RM2k plays two per hit —the attack's and the damage's, separated by
; a wait— and here the second goes out when `BA_WAIT` reaches
; `BA_SE2_FRAMES`.
BA_SONG_PREV = FAR_BATTLE + 41
BA_SE2      = FAR_BATTLE + 42      ; word
; Whether there is a scene in BG1 —0— or this battle goes on black —$FF—: no
; background and no battler. See `scene_upload`.
BA_SCENE    = FAR_BATTLE + 44
; And at which place in `troop_id` this battle's troop landed, which is what
; `scene_troop_backdrop` indexes. **A word since 2026-10-11**, at +45 and
; +46: Vampires Dawn carries 277 troops. $FFFF: the cartridge does not carry
; it. No place is as high as $FF00 —the converter caps them at 32768, so
; that twice one indexes the word tables— so the high byte alone tells it,
; which is what the 8-bit code reads: `lda BA_TROOP_K + 1`, as `ENC_REG`.
BA_TROOP_K  = FAR_BATTLE + 45      ; word
; And the item being used, since 2026-09-13. It goes **after `BA_ONE`**,
; which ends at +575, because between +40 and +48 nothing is left and moving
; `BA_ACC` would mean moving everything else.
;
; It was at +320 until `BA_BYTES` went from 18 to 40 —the SP and the four
; parameter modifiers of the skills— and `BA_ONE` ran into it.
BA_ITEM_N    = FAR_BATTLE + 576    ; how many are in the list
BA_ITEM_SEL  = FAR_BATTLE + 577    ; which one the cursor marks
BA_ITEM_ARR  = FAR_BATTLE + 578    ; the first one visible
BA_ITEM_TGT  = FAR_BATTLE + 579    ; which actor it is given to; since 2026-09-13
                                   ; also the target of a healing skill,
                                   ; which picks with the same mode
; +580 was the `k` of the current message's item, a byte, until 2026-10-15.
BA_ACTOR2    = FAR_BATTLE + 581    ; an actor counter `BA_S0` cannot be
BA_MHEAL     = FAR_BATTLE + 582    ; word: how much it healed
; +584 to +591 were the `k` each actor chose, one per byte, until 2026-10-15,
; when a `k` became a word: ABL's whole game carries 264 items. The list
; then left for `FAR_ITEM_LIST`, which is the items screen's and nobody uses
; in a battle —the battle cannot be entered from the menu or a shop—, and the
; two words went into the 64 bytes it left.
BA_ITEM_LIST = FAR_ITEM_LIST       ; the list, one `k` per word
BA_ITEM_MAX = 64
.assert BA_ITEM_MAX <= ITEM_LIST_MAX, error, "the battle's item list overflows the items screen's"
BA_MITEM     = FAR_BATTLE + 592    ; word: the `k` of the current message's item
BA_ACC_ITEM  = FAR_BATTLE + 594    ; the `k` each actor chose, one per word
; --- skills, since 2026-09-13 ---------------------------------------------
;
; After `BA_ACC_ITEM`, which ends at +610; +610 to +655 are free.
BA_SKILL_N   = FAR_BATTLE + 656    ; how many the one giving commands knows
BA_SKILL_SEL = FAR_BATTLE + 657    ; which one the cursor marks, in the whole list
BA_MSKILL    = FAR_BATTLE + 658    ; the `k` of the current message's one
BA_ACC_SKILL = FAR_BATTLE + 660    ; the `k` each actor chose, one per byte
; **Only the visible page** of the list, one `k` per byte: place
; `2 * BA_SKILL_TOP` of the whole list goes at byte 0. The whole one does not
; fit here —Talan can know 54— and nothing needs it at once: see
; `ba_skill_list`. The enemies' choice of action uses these same bytes for
; its weights, which is why it is still 16 and not 14.
BA_SKILL_LIST = FAR_BATTLE + 672
BA_SKILL_MAX = 16                  ; BA_SKILL_ROWS times BA_SKILL_COLUMNS, with room to spare
BA_MEFFECT   = FAR_BATTLE + 688    ; signed word: how much the last one did
; The first visible row of the skill list, since 2026-10-04: the window
; scrolls, as RM2k's does.
BA_SKILL_TOP = FAR_BATTLE + 690
; Since 2026-10-04, with the windows in the band below the scene, as RM2k's:
; whether this battle can be escaped from —`op_battle` reads it from the
; escape's destination, an encounter always can—; the first visible place of
; the enemies' list; and whether the turn that starts comes from a failed
; escape, which shows its message first.
BA_CAN_FLEE   = FAR_BATTLE + 691
BA_TARGET_TOP = FAR_BATTLE + 692
BA_FLEE_FAILED = FAR_BATTLE + 693
; The windows the screen asks for —`ba_compose`— and the ones the tilemap
; shows —`ba_win_tick`—, four bytes each: the layout, set A's bar and set
; B's, $FF none, and whether the description's window is on top. And
; whether the windows went up this vblank, and the table of BG1's
; horizontal offset, which the HDMA writes per band: see `ba_shake`.
BA_WIN_KEY    = FAR_BATTLE + 694
BA_WIN_SHOWN  = FAR_BATTLE + 698
BA_WIN_DID    = FAR_BATTLE + 702
BA_HOFS_HDMA  = FAR_BATTLE + 703    ; 10 bytes
BA_BATTLE_END = FAR_BATTLE + BA_BATTLE_BYTES
.assert BA_HOFS_HDMA + 10 = BA_BATTLE_END, error, "BA_BATTLE_BYTES is not what the battle's state takes"
BA_ACC     = FAR_BATTLE + 48      ; two bytes per combatant: command and target
BA_EXEC    = FAR_BATTLE + 72      ; the execution order, one combatant per byte
BA_CAND    = FAR_BATTLE + 88      ; the living on one side, to pick a target
BA_ONE     = FAR_BATTLE + 96      ; the combatants, BA_BYTES each
; Whether the current message's item revived a fallen one: the second line
; changes. **Outside `FAR_BATTLE`**, in a block of its own. Like everything in the battle, with a sixteen-bit address and the
; data bank at $7E.
.pushseg
.segment "FARBSS"
far_ba_mrevived: .res 6
.popseg
BA_MREVIVED = .loword(far_ba_mrevived)
; And, in the same place, since 2026-10-04: whether the HP line goes, the SP
; the item got back —a word—, and whether its line is still to be shown, in a
; message of its own: see `ba_item_use`.
BA_MHPLINE  = BA_MREVIVED + $01
BA_MSP      = BA_MREVIVED + $02
BA_MSP_NEXT = BA_MREVIVED + $04
.assert BA_MSP_NEXT < BA_MREVIVED + 6, error, "the item's message overflows its block"

; The battle's message, put together before it is drawn: see `ba_message` and
; `ba_flow`. It lasts
; as long as one message is composed, so it does not travel in the save.
.pushseg
.segment "FARBSS"
far_ba_mbuf: .res $D6 + 3 * 4
.popseg
BA_MBUF       = .loword(far_ba_mbuf)           ; RM2k's two lines, BA_MBUF_MAX letters each
BA_MBUF_MAX   = 96
BA_MPTR       = BA_MBUF + $C0           ; word: where the next letter goes
BA_MLIM       = BA_MBUF + $C2           ; word: where the line being written ends
BA_MSTART     = BA_MBUF + $C4           ; two words: where each line starts
BA_MEND       = BA_MBUF + $C8           ; two words: and where it ends
BA_MP         = BA_MBUF + $CC           ; word: where `ba_flow` is cutting
BA_ME         = BA_MBUF + $CE           ; word: the end of what it cuts
BA_MB         = BA_MBUF + $D0           ; word: the space it cuts at
BA_MN         = BA_MBUF + $D2           ; how many of RM2k's lines: 1 or 2
BA_MCOUNT     = BA_MBUF + $D3           ; the letters a text has left to copy, or
                                ; whether a number wrote a digit already
BA_MDN        = BA_MBUF + $D4           ; how many lines go on the screen
BA_MI         = BA_MBUF + $D5           ; which one `ba_flow` is on
BA_MDL        = BA_MBUF + $D6           ; BA_MLINES_MAX of three bytes: where each
                                ; line on the screen starts, and its length
BA_MLINES_MAX = 4               ; the two message lines and the last two
                                ; of the party's
.assert BA_MBUF + 2 * BA_MBUF_MAX <= BA_MPTR, error, "the battle's message overflows its buffer"
.assert BA_MDL + 3 * BA_MLINES_MAX <= BA_MBUF + $D6 + 3 * 4, error, "the battle's message overflows its range"

; The combatants: the first four are the party and the next eight the troop.
; That the place is fixed and not a compacted list is what keeps a dead one
; visible in its line, as on the screen.
BA_PARTY_MAX = 4
BA_ENEMIES_MAX = 8
BA_COMB_MAX = BA_PARTY_MAX + BA_ENEMIES_MAX
; It was 18 until 2026-09-13, which is when the SP came in along with the
; four parameter modifiers that two of the party's seven skills move. 40 is
; also convenient: the offset comes out of five `asl` and an addition, see
; `ba_x`.
BA_BYTES  = 40
BA_HP     = 0               ; word
BA_HPMAX  = 2
; **The four parameters here are the effective ones**, that is,
; game_battler.cpp's `AdjustParam`: `clamp(base + modifier, 1, 999)`. The
; base and the modifier live further down and are stored whole because a
; modifier that survives the clamp cannot be recovered from the subtraction;
; `ba_mod` recomputes them.
BA_ATK    = 4
BA_DEF    = 6
BA_AGI    = 8
BA_SORT   = 10              ; the `agi + random` the turn is sorted by
BA_TXT    = 12              ; the text number of its name
BA_HIT    = 14              ; byte
BA_CRIT   = 15
BA_FLAGS  = 16
BA_NUMBER = 17              ; the LDB actor, or the place in the troop
BA_SP     = 18              ; word: the SP it has left
BA_SPMAX  = 20
BA_MATK   = 22              ; the four modifiers, signed
BA_MDEF   = 24
BA_MSPI   = 26
BA_MAGI   = 28
BA_BATK   = 30              ; and the four bases
BA_BDEF   = 32
BA_BSPI   = 34
BA_BAGI   = 36
BA_SPI    = 38              ; the effective spirit, which `CalcSkillEffect` asks for
BAF_DEF   = $01             ; it is defending
BAF_ACTOR = $02             ; it belongs to the party
BAF_HAS   = $04             ; the slot is taken
; A hidden enemy —`invisible` in the troop— takes its place but **does not
; have `BAF_HAS`**: that way everything that looks at who is there
; —`ba_alive`, and with it the target, the actions, the victory and the
; scene— skips it without knowing anything about hidden ones, which is what
; `Exists()` does in easyrpg. `ShowHiddenMonster` swaps one bit for the
; other: see `ba_show_hidden`.
BAF_HIDDEN = $08

; The three results and the commands, in the order of the battle's model.
BA_VICTORY = 0
BA_ESCAPE_R = 1
BA_DEFEAT   = 2
; And the fourth, which the model does not have: a troop page's
; `TerminateBattle`, EasyRPG's `BattleResult::Abort`. It is the index of
; `OP_BATTLE`'s fourth destination, past the handlers.
BA_ABORT_R  = 3
BA_ATTACK   = 0
BA_DEFEND = 1
BA_FLEE     = 2           ; nobody records it since 2026-10-04: see `ba_flee_failed`
BA_ITEM     = 3
BA_SKILL = 4
; No action, since 2026-10-12: one a condition does not let act, or whose
; action a condition took away —`Game_BattleAlgorithm::None`—. Nobody gives
; it as a command; see `battle_states.s`. It is the model's `COMMAND_NONE`.
BA_NONE     = 5
; The screen modes. **The order
; matters**: more than one place asks `cmp #BA_M_MESSAGE / bcs` to say
; "message or end", so the ones that choose something all go first.
BA_M_COMMAND = 0
BA_M_TARGET = 1
BA_M_ITEM   = 2
BA_M_ACTOR  = 3
BA_M_SKILL  = 4
BA_M_MESSAGE = 5
BA_M_END    = 6
; Running a troop page, with or without its message on screen: see
; `mode_page`. It goes after the message ones because it chooses nothing.
BA_M_PAGE = 7
; A troop page ended the battle with `TerminateBattle`: the loop closes it on
; its next frame, with no end screen. See `ba_page_step`.
BA_M_ABORT = 8
; What the message says.
BA_MSG_ATTACK = 0
BA_MSG_DEFENDS = 1
BA_MSG_NO_FLED = 2
BA_MSG_FLED = 3
BA_MSG_VICTORY = 4
BA_MSG_DEFEAT = 5
BA_MSG_ITEM = 6
BA_MSG_SKILL = 7
BA_MSG_ITEM_SP = 8          ; an item's SP line, after its HP one
BA_MSG_STATE = 9            ; a condition's: `ba_st_who` and `ba_st_text`
; How many frames a message stays if nobody presses A. Two seconds, which is
; how long a line takes to read, and A skips it.
BA_MSG_FRAMES = 120
; When the hit's second sound effect goes out: `Scene_Battle_Rpg2k` plays the
; attack's when the action starts and the damage's in the message sub-state,
; with a `SetWait(4,4)` in between. Here the message lasts `BA_MSG_FRAMES`
; and the second sound effect goes out twenty-four frames later. The
; twenty-four were chosen when sound effects had a single voice and the new
; one cut off the previous one's voice, so they had to stay apart by ear;
; since 8c9c182 they are two voices —see `sound_effects.s`— and two
; different sound effects no longer cut each other off; the same sound effect
; twice does, because `sound_play` fires it again on the voice that is
; already playing it.
BA_SE2_FRAMES = BA_MSG_FRAMES - 24
; The hit rate of an actor with no weapon that changes it:
; `Game_Actor::GetHitChance`.
BA_HIT_ACTOR = 90
; The damage cap —RM2k's `MaxDamageValue()`— and the cap on the average
; agility that goes into the escape computation: two hundred times the
; average has to fit in sixteen bits, and the game's most agile enemy has
; 300.
BA_DAMAGE_MAX = 999
BA_AGI_CAP = 320
; The cap on an effective parameter: `Game_Actor::GetAtk` and its siblings,
; that is, RM2k's `MaxStatBattleValue`.
BA_PARAM_MAX = 999
; `rpg::Skill::Type_switch`, the one that turns on a switch and does nothing
; else. It is the only type this port tells apart from normal: the seven the
; intro party knows are either `normal` or `switch`.
BA_SKILL_TYPE_SWITCH = 3
; The five scopes of `rpg::Skill::Scope`, which is what `skill_scope` carries.
; Only `enemy` and `ally` ask for a target when chosen; for the other three
; the scope decides it: see `skill_targets` in `rm2k-snes-battle`.
BA_SCOPE_ENEMY      = 0
BA_SCOPE_ENEMIES = 1
BA_SCOPE_ONE        = 2
BA_SCOPE_ALLY       = 3
BA_SCOPE_PARTY      = 4
; An enemy action that is not a skill: the basic attack, in `eacc_skill`, and
; what `ba_enemy_action` answers when it has none left. See `enemy_action`
; in `rm2k-snes-battle`.
BA_EACC_ATTACK = $FF
BA_EACC_NOTHING = $FE
BA_EACC_NO_EFFECTIVE = $80      ; the `eacc_weight` bit

; Cursor (2), wait (2), whether it is running (1) and from which page (2).
; **Eight and not seven**: the index comes out of three `asl` instead of an
; `x * 8 - x`, which is six bytes of bank 0 and a few cycles for every
; parallel and every frame. EV_MAX times eight is 960 bytes, so it still fits
; below `FAR_PAIR_LIST`.
PAIR_BYTES = 8
; And the eighth, which was spare, is the event's move route slot plus one,
; or zero if it has none: `slot_record` sets it when one is given, and
; `clear_parallel` clears it when loading the map, next to `load_npcs`,
; which is where they are all freed. Within a map a slot is only released
; when none is free and its route ended, and then `reclaim_slot` clears this
; too. It is what saves each parallel from looking for its own every frame: see
; `one_parallel`.
PAIR_SLOT = 7

; And what the parallel list keeps for each one: the event (1), the pointer
; to its bytecode (3) and which page it came from (2). The last three are
; what used to be fetched again from the cartridge every frame and for every
; parallel, with `page_from_pick`: twenty-four bytes of page header read
; through the bank window, to answer the same as the time before. The list is
; rebuilt whole in `apply_pages`, that is, exactly when the active page
; may have changed, so recording it there is the same answer and only once.
; Eight for the same reason as `PAIR_BYTES`: the two spare ones are paid for
; in far RAM, of which there is plenty, and saved in bank 0 and in cycles.
; PARALLEL_MAX times eight is 384 bytes and up to `FAR_RANDOM` there are 508.
PAIR_LIST_BYTES = 8
WMADDL   = $2181
WMADDM   = $2182
WMADDH   = $2183

; VRAM is addressed in words and it is 64 K in total. How it is split among
; the background tiles, the upper layer's, the sprites' and the two tilemaps
; is not here: the converter decides it map by map and it arrives in
; mapdata.inc, together with the already-built values of OBSEL and BG12NBA.
;
; It is not a convenience: the map that spends the most background tiles
; needs 620, and another with many characters needs 512 for sprites. The two
; together do not fit, and neither of the two layouts works for every map.

; Mode 3's priority order, front to back, is
;   objects 3 / BG1 1 / objects 2 / BG2 1 / objects 1 / BG1 0 / objects 0
; so with the map on BG1 priority 0, the hero on objects priority 1 and the
; upper layer on BG2 priority 1, RM2k's order comes out of the hardware
; without any trick. Events marked "above" go on objects priority 2, which is
; the only thing left above BG2.
; In the OAM attribute byte —vhoopppN— the priority is bits 5 and 4, so the
; value is shifted four places: priority 1 is $10 and not $20. With $20 the
; hero ended up on priority 2, which in this order is *in front of* BG2 1,
; and so it was drawn over the layer that was supposed to cover it.
;
; Both values are built by the converter —each NPC's already comes in its
; attribute byte— and the hero's arrives as HERO_PRIORITY in mapdata.inc.
; Having them here as well was the usual duplication: two sides that can be
; wrong the same way and a comparison that gives zero. The hero's is $10 in
; every ROM except `snes-encima`'s, which raises it to $20 to exercise
; priority 2.

; RM2k poses are 24x32 and the SNES has no such size, so the 32x32 object is
; used and a bit is left over on the sides. The OBSEL value, which carries
; that size and the tile page, is built by the converter.

; The 12 poses: 3 walking frames times 4 directions. In RM2k the directions
; go 0=up, 1=right, 2=down, 3=left, and the middle frame is the standing
; pose.
DIR_UP    = 0
DIR_RIGHT = 1
DIR_DOWN  = 2
DIR_LEFT  = 3

; At speed 4, which is the hero's, it moves two pixels per frame and the
; animation changes frame every six.
; WALK_SPEED no longer exists: the hero moves according to its speed, see
; `half_step_per_speed`. The line stays so nobody goes looking for it.
; ANIM_FRAMES = 6 was how many frames the walking frame changed every; now it
; depends on the hero's speed: see `anim_per_speed`.

; The sprite is drawn centered over its 16x16 cell and resting on its feet.
; From the 32 object the 4 spare on each side have to be subtracted as well.
SPRITE_OFF_X = 8
SPRITE_OFF_Y = 16

; --- the map window --------------------------------------------------------
; The PPU tilemap is 64x32 cells, that is 512x256 pixels, and the screen is
; 256x224. The whole map does not fit: the game's go up to 1000x80 cells.
; What is in VRAM is a window that moves with the camera.
;
; The window does not shift: it is treated as a torus. Map cell (mx,my)
; always lives in slot (mx mod 64, my mod 32), and the hardware scroll
; already wraps around by itself because 1024 —the register's maximum— is a
; multiple of 512. So when the camera crosses a cell edge, only the column or
; row that just came in has to be rewritten: the one going out is 32 columns
; or 4 rows off screen and nobody looks at it in the meantime.
WINDOW_COLS = 64
WINDOW_ROWS = 32

; How many 8x8 cells the screen can touch. Exactly 32 and 28 plus one,
; because the scroll almost never lands squarely on a cell.
VIEW_COLS = 33
; How many extra columns are kept loaded on each side of the screen. It is
; for the screen shake, which moves the drawing up to 19 pixels without
; moving the camera: with no margin, the column peeking in from the left is a
; torus slot nobody wrote. Four are 32 pixels, and the torus has 64 columns
; for 33 visible, so there are plenty to spare.
MARGIN_COLS = 4

; --- the spare strips, in far RAM -------------------------------------------
;
; The camera uncovers up to **two** rows or two columns per tick —see
; `stream_map`—, so two strips have to be built at once and the vblank
; uploads both. The second set lives here and not in bank 0 because it does
; not fit there: the BSS has 84 bytes left and this asks for 384.
;
; **It does not travel in the save**: it lasts one frame. The four go in
; this order and adjacent, which is what
; `push_one_row` takes advantage of to reach the upper layer's by adding the
; length of the other, same as with the bank 0 ones.
.pushseg
.segment "FARBSS"
FAR_STRIP_ROW:  .res WINDOW_COLS * 2
FAR_STRIP_ROW2: .res WINDOW_COLS * 2  ; and the upper layer
FAR_STRIP_COL:  .res WINDOW_ROWS * 2
FAR_STRIP_COL2: .res WINDOW_ROWS * 2
.popseg
.assert FAR_STRIP_ROW2 = FAR_STRIP_ROW + WINDOW_COLS * 2, error, "row strips not adjacent"
.assert FAR_STRIP_COL2 = FAR_STRIP_COL + WINDOW_ROWS * 2, error, "column strips not adjacent"

; --- where the background tilemap is, in far RAM ----------------------------
;
; The VRAM word of the loaded map's BG1 tilemap. `enter_map` copies it from
; `M_VRAM_MAP` and `build_column` and `build_row` add it, since they cannot
; read the table because X is in use. It is $5800 in every layout but one:
; see LAYOUT_VENTANA_AMBOS. It does not fit in the BSS.
;
; **It does not travel in the save**: loading it loads the map, and that
; sets it again.
.pushseg
.segment "FARBSS"
FAR_VRAM_MAP: .res 2
.popseg

; --- the music decoder, in far RAM -------------------------------------------
;
; The state of `music_frame`, which expands the per-note stream into DSP
; writes: see "the per-note format" in rm2k-snes/rm2k-snes-audio/src/stream.rs. It is read
; and written by `irq_music`, which lands at any point in the main code, so
; it is reached with long addressing and never through the WMADD window.
;
; One block of 1 KB, with the log at its second half. **It does not travel
; in the save**: starting the song zeroes it.
;
;   MUS_SHADOW   the last thing the stream wrote to each voice register,
;                indexed by the register number —$v0 to $v7—, and in $v8,
;                which is ENVX and is not written, the release GAIN of the
;                sound of the voice's last note
;   MUS_WAIT   word: how many frames until the stream is read
;   MUS_KON      the voices that got a note in the frame being read
;   MUS_PLAYING  the ones keyed on when the previous one closed: released on opening
;   MUS_BASE     word: where the sounds the notes name start in `music_sounds`:
;                the song's, plus its `OP_SOUND_PAGE`'s
;   MUS_VIEWS   the voices that have had a note since the song started
;   MUS_GAINS    the ones that have already received a GAIN
;   MUS_BIT      the voice bit of the event being read
;   MUS_T        scratch word
;   MUS_BACK_TO  long: where an `OP_REPEAT` comes back to
;   MUS_LEFT     the events the `OP_REPEAT` has left to read, plus one; zero
;                outside one. See `music_frame::read`
.pushseg
.segment "FARBSS"
FAR_MUSIC: .res $400
.popseg
MUS_SHADOW   = FAR_MUSIC
MUS_WAIT     = FAR_MUSIC + $80
MUS_KON      = FAR_MUSIC + $82
MUS_PLAYING  = FAR_MUSIC + $83
MUS_BASE     = FAR_MUSIC + $84
MUS_VIEWS    = FAR_MUSIC + $86
MUS_GAINS    = FAR_MUSIC + $87
MUS_BIT      = FAR_MUSIC + $88
MUS_T        = FAR_MUSIC + $89
MUS_BACK_TO  = FAR_MUSIC + $8B
MUS_LEFT     = FAR_MUSIC + $8E
; `mpym`'s byte and its scratch: see music.s. Taken on 2026-10-03 from the
; gap after MUS_LEFT, which is this range's.
MUS_MPY_B    = FAR_MUSIC + $90
MUS_MPY_M    = FAR_MUSIC + $91
; The bytes from MUS_WAIT to MUS_LEFT, which `music_clear` zeroes.
MUS_STATE_BYTES = $0F
; The log of what the stream asks of the DSP: `dsp_music` records each
; (register, value) pair here if MUS_LOG_ON is not zero, and
; MUS_LOG_I is where the next one goes, in bytes. It is the net of
; `test_music_writes.py`: the test turns it on and reads it frame by
; frame. It wraps around at 512 bytes, 256 writes, and a music frame does not
; go past a hundred. Each music frame starts with a mark, register
; MUS_LOG_MARK —which the DSP does not have—: the IRQ of a heavy frame
; ends after the emulator has delivered the frame, and without the mark its
; last writes would look like they belong to the next one.
MUS_LOG_MARK = $FF
MUS_LOG_ON = FAR_MUSIC + $F0
MUS_LOG_I       = FAR_MUSIC + $F2      ; word
MUS_LOG         = FAR_MUSIC + $200
MUS_LOG_LENGTH = $200
.assert MUS_LOG + MUS_LOG_LENGTH <= FAR_MUSIC + $400, error, "the log overflows its range"

; The `FadeOutBGM` factor on the voices' volume, from 0 to 256 —256 is full
; volume—: this frame's and the previous one's, which is the one the DSP has.
; `bgm_fade_tick` writes them and the music reads them, both inside
; `irq_music`. See `volume_refresh`.

.pushseg
.segment "FARBSS"
FADE_N: .res 4          ; word
.popseg
FADE_BEFORE = FADE_N + $02            ; word

; How loud and how fast the song plays, which is what a `PlayBGM` asks for
; besides the song: see `bgm_level_set`, in bgm_level.s. Each level is four
; bytes, as `OP_BGM` carries them: the gain of the left and the right side in
; 128ths, and the music frames per video frame in 256ths. 128, 128 and 256 is
; the song as written.
;
;   BGM_ASK     the one the next `music_play` puts on
;   BGM_NOW     the one playing; `irq_music` reads its step
;   BGM_BEFORE_BATTLE  the map's, put back when the battle ends
;   BGM_REMEMBERED     `MemorizeBGM`'s, next to `REMEMBERED_SONG`
;   SONG_GAIN   BGM_NOW's two gains as `song_gain_scale` multiplies them,
;               from 0 to 256 (word each, left first)
;   TEMPO_ACC   the music frames owed, in 256ths: see `music_tempo`
;   MSU_BASE    the MSU-1 volume at that gain (word, high byte at zero)
;   SONG_SCALED whether the gains are not both 128: without it, no multiply
;   GAIN_DIRTY  the gain changed with the song playing: `irq_music` rewrites
;               the volume of every voice
;
; **They do not travel in the save**: a loaded game plays its song as
; written. Reset gives them a value: see `bgm_level_reset`.
BGM_ASK           = MSU_BASE + $16        ; 4 bytes
BGM_NOW           = MSU_BASE + $12        ; 4 bytes
BGM_BEFORE_BATTLE = MSU_BASE + $0E        ; 4 bytes
BGM_REMEMBERED    = MSU_BASE + $0A        ; 4 bytes
SONG_GAIN         = MSU_BASE + $06        ; 2 words
TEMPO_ACC         = MSU_BASE + $04        ; word
GAIN_DIRTY        = MSU_BASE + $03
SONG_SCALED       = MSU_BASE + $02
.pushseg
.segment "FARBSS"
MSU_BASE: .res $1A        ; word
.popseg

; --- the ShowPicture pictures: their slots -------------------------------------
;
; See picture_far.s. `PIC_SLOTS` pictures at a time, each slot one entry of
; every array: which picture of the map's table it shows, or `PIC_NONE`;
; its corner —on the screen, or on the map for one that goes with it—; its
; flags; its tone, three bytes; its transparency. And **one** ramp of
; `MovePicture` for all of them: the slot it moves, where it comes from and
; where it goes —tone and transparency—, and how far along it is. The game
; never moves two pictures at once; if a page does, the one that was moving
; arrives where it was going in that same frame.
;
; In two blocks, because until 2026-10-16 they were two places of a map
; written by hand. **They do not travel in the save**, and a map change clears
; them: RM2k 2000 erases its pictures there (`erase_on_map_change`).
PIC_SLOTS   = 2
.pushseg
.segment "FARBSS"
PIC_IMG: .res $F              ; PIC_SLOTS bytes
.popseg
PIC_X       = PIC_IMG + $02              ; PIC_SLOTS words
PIC_Y       = PIC_IMG + $06              ; PIC_SLOTS words
PIC_TRANS   = PIC_IMG + $0A              ; PIC_SLOTS bytes
PIC_FLAGS   = PIC_IMG + $0C              ; PIC_SLOTS bytes
PIC_STEPS   = PIC_IMG + $0E
.assert PIC_STEPS < PIC_IMG + $F, error, "the pictures overflow their block"
.pushseg
.segment "FARBSS"
PIC_TONE: .res $10              ; three bytes per slot
.popseg
PIC_RAMP    = PIC_TONE + $06              ; the slot the ramp moves, or PIC_NONE
PIC_FROM    = PIC_TONE + $07              ; r, g, b and transparency
PIC_TO      = PIC_TONE + $0B
PIC_STEP    = PIC_TONE + $0F
.assert PIC_TONE + 3 * PIC_SLOTS <= PIC_RAMP, error, "the pictures' tones overflow"
PIC_NONE    = $FF
; OP_PICTURE's mode, which the slot keeps in its flags: the centre came from
; two variables, and the picture goes with the map. See `PICTURE_BY_VARIABLE`
; and `PICTURE_MAP_FIXED` in the event compiler.
PIC_BY_VARIABLE = $01
PIC_MAP_FIXED   = $02
; And the slot's palette is waiting for the vblank.
PIC_PENDING     = $80

; --- the big picture: the one in the background layer ---------------------------
;
; See big_picture.s. One at a time —no scene of the game shows two big ones
; at once—, and the ramp of its `MovePicture` is the slots' one, with
; `PIC_RAMP` at `PIC_BIG`: its tone and transparency go through `PIC_FROM`
; and `PIC_TO`, and what only it moves —the scroll and the wave— through
; its own bytes here.
;
; They do not travel in the save, and a map change clears them.
.pushseg
.segment "FARBSS"
BIG_IMG: .res $10          ; its entry of `big_table`, or PIC_NONE
.popseg
BIG_FLAGS     = BIG_IMG + $01          ; BIG_ON, BIG_DOWN, BIG_WAVE_ON, BIG_B, BIG_PENDING
BIG_TONE      = BIG_IMG + $02          ; r, g, b
BIG_TRANS     = BIG_IMG + $05
BIG_SAT       = BIG_IMG + $06
BIG_WAVE      = BIG_IMG + $07          ; the wave's strength, 0 to 10
BIG_PHASE     = BIG_IMG + $08          ; and where it is, 256 to a turn
BIG_Y         = BIG_IMG + $09          ; word: the scroll, in lines
BIG_Y_FROM    = BIG_IMG + $0B          ; word: where the ramp's started
BIG_DY        = BIG_IMG + $0D          ; how far it goes from there
BIG_WAVE_FROM = BIG_IMG + $0E
BIG_WAVE_TO   = BIG_IMG + $0F
; The flags. BIG_ON is bit 0, so `lsr` leaves it in the carry; BIG_WAVE_ON
; is HDMA channel 4's bit, so it goes straight into HDMAEN; BIG_PENDING is
; bit 7, so `bpl` asks for it.
BIG_ON      = $01                ; the layer is up: mode 1, the map hidden
BIG_DOWN    = $02                ; the ramp's scroll goes down from BIG_Y_FROM
BIG_TEXTURE = $04                ; it has a mode 7 texture: see big_picture_zoom.s
BIG_M7      = $08                ; mode 7 is on screen: `irq_music` multiplies by hand
BIG_ZOOMING = $40                ; the ramp moves its size too
BIG_WAVE_ON = $10                ; the wave's HDMA, on
BIG_B       = $20                ; the HDMA reads the second wave table
BIG_PENDING = $80                ; its palette is waiting for the vblank
; `PIC_RAMP` when the ramp is the big one's: bit 7, like PIC_NONE, so that
; `bmi` tells the slots' ramps from the rest. And it is the slot
; OP_PICTURE_ERASE takes it down with: see `PICTURE_BIG` in the compiler.
PIC_BIG     = $80

; While the layer is up, part of LZ2_BUFFER is the picture's: its tilemap is
; decompressed below `CODE_CARRY` —see `big_load`—, and its palette tinted
; and the two tables of the wave go in the part that the ChipSet's
; animation uses on the map, which is not drawn meanwhile. The map reloads
; both when the picture goes.
BIG_PAL     = $7F6000            ; BIG_PALETTES * 32 bytes
BIG_WAVE_A  = $7F6100            ; BIG_WAVE_BYTES each
BIG_WAVE_B  = $7F6300
; And the zoom's, for a picture with a mode 7 texture: see
; big_picture_zoom.s. `big_load` writes all of them before the first vblank
; reads them.
BIG_M7_SHOW  = $7F6500           ; what the vblank shows: BIG_M7_STILL, _ZOOM, _GONE, and BIG_M7_SPENT
BIG_M7_PIECE = $7F6501           ; the piece of VRAM that goes up next
BIG_M7_DONE  = $7F6502           ; word: its bytes already up
BIG_MAG      = $7F6504           ; its size now, in percent of the one shown
BIG_MAG_FROM = $7F6505           ; and where the ramp's size starts and ends
BIG_MAG_TO   = $7F6506
BIG_M7_A     = $7F6507           ; word: the matrix's A and D, 8.8; BIG_M7_HIDDEN if too small
BIG_M7_DIVISOR = $7F6509         ; word: `big_m7_matrix`'s
BIG_M7_SIZE  = $7F650B           ; word: the piece's bytes
BIG_M7_END   = $7F650D

; --- the slots still events take turns in ---------------------------------------
;
; See shared_poses.s. How many shared slots the loaded map has —0 in every
; map that does not need them— and which pose each one holds, by its index
; in the map's pose table, or $FF if nobody knows: `load_sprite` has just
; uploaded the bank. **They do not travel in the save**: they describe VRAM,
; and loading a map uploads it again.
;
; `SHARE_MAX` is also `SHARED_MAX` in `rm2k-snes-mapdata` and
; in Wally's `sprites`: the `.inc` asserts every map against it.
.pushseg
.segment "FARBSS"
SHARE_N: .res $10
.popseg
SHARE_OWNER  = SHARE_N + $01             ; SHARE_MAX bytes
SHARE_MAX    = 15
.assert SHARE_OWNER + SHARE_MAX <= SHARE_N + $10, error, "the shared slots overflow their RAM"
; And bit 7 of `SHARE_N` says the map has a cache of slots instead: see
; cache_slots.s.

; --- the cache of slots ---------------------------------------------------------
;
; See cache_slots.s. How many slots the loaded map's cache has, where its
; record is in `cache_data`, what each slot holds and how many frames ago it
; was drawn, and which slot each event last got —by event, not by row: rows
; change places when someone walks—. And what `cache_want` hands
; `cache_took`. They are only read in a map with a cache, which
; `cache_load` sets up when loading it, and **they do not travel in the
; save**: they describe VRAM.
;
; `CACHE_MAX` is also Wally's, in `sprites::cache`,
; and the `.inc` asserts every map against it.
; `CACHE_N` and what follows, `$50` bytes and `EV_MAX`, are declared in
; far_ram_game.s.
CACHE_REC    = CACHE_N + $01             ; word
CACHE_T_KEY  = CACHE_N + $03
CACHE_T_SLOT = CACHE_N + $04
CACHE_T_AGE  = CACHE_N + $05
CACHE_T_EV   = CACHE_N + $06
CACHE_T_POSE = CACHE_N + $07
CACHE_T_ROW  = CACHE_N + $08             ; word
CACHE_KEY    = CACHE_N + $10             ; CACHE_MAX bytes
CACHE_AGE    = CACHE_N + $30             ; CACHE_MAX bytes
CACHE_EV     = CACHE_N + $50             ; EV_MAX bytes: asserted in cache_slots.s
CACHE_MAX    = 32
.assert CACHE_KEY + CACHE_MAX <= CACHE_AGE, error, "the cache's keys overflow"
.assert CACHE_AGE + CACHE_MAX <= CACHE_EV, error, "the cache's ages overflow"

; --- `InputNumber`: the digits' line ------------------------------------------
;
; The line the composer reads for the digits —see number_input.s—: its length
; and two letters per digit, the cursor's column and the digit itself, in the
; font's numbering. `msg_ptr` points here while the line is being composed, and
; the digits the player has entered are the ones on it: there is no other copy.
; And the number, once A is pressed, before it goes to the variable.
;
; **They do not travel in the save**: an open number input is a
; page blocked in the middle, which the save does not keep either.
.pushseg
.segment "FARBSS"
NUMBER_LINE: .res $10             ; 1 + 2 * NUMBER_DIGITS_MAX bytes
.popseg
NUMBER_VALUE = NUMBER_LINE + $0E             ; word
NUMBER_DIGITS_MAX = 6
.assert NUMBER_LINE + 1 + 2 * NUMBER_DIGITS_MAX <= NUMBER_VALUE, error, "the digits' line overflows"

; --- the battle animation frame, in far RAM ---------------------------------
;
; The 2 KB of the frame the vblank uploads to the box. The cartridge does not
; store them whole —only the tiles that are not all zero, see
; `frame_without_gaps` in snes_convert.py— and `anim_frame_build` rebuilds
; them here, outside the vblank. The DMA in `anim_drawing_dma` comes from
; here and not from the cartridge.
;
; 2 KB. **It does not travel in the save**: loading a map zeroes it.
;
; **And while a screen is up it is the text layer's stage**, `TL_STAGE`,
; since 2026-10-04: the frame is only built on the map, and every way back
; to it clears the buffer —`anim_buf_clear`, in `back_to_map` and in
; `enter_map`—, because it is rebuilt from nothing. A screen that went back
; to the map some other way would show the stage's garbage in the box.
.pushseg
.segment "FARBSS"
ANIMB_BUF: .res $800
.popseg

; --- LZ2: what the cartridge carries compressed, in WRAM --------------------
;
; See `lz2_decompress` in decompress.s:
;
;   LZ2_TRAMPOLINE_LIT  the literal's `mvn` trampoline, four bytes built with each
;            call's banks, and the output bank, in far RAM
;   $7F0000  the load buffer: each tile block is decompressed here and
;            uploaded to VRAM with the same DMA as before. It is valid only
;            while loading; the battle scene uses all of bank $7F —see
;            `SCN_CLEAN`—, and nothing here has to outlive it
;   $7F6000  the drawings of the map's ChipSet animation, which `anim_upload`
;            uploads every time the clock changes: **they live as long as
;            one is on the map**, and that is why they go above the buffer
;            and are decompressed after the background tiles and before the
;            upper layer and the sprites. What does take them away is the
;            battle, and `back_to_map` decompresses them again
;
; The limits of each block are enforced by `decompress.s` against the ones
; the converter emits.
.pushseg
.segment "FARBSS"
LZ2_TRAMPOLINE_LIT: .res 5    ; mvn output, stream; rtl
.popseg
LZ2_BANK       = LZ2_TRAMPOLINE_LIT + $04        ; the output bank

; --- what the victory counts -------------------------------------------------
;
; The "N EXP" and "Level up!"
; pages of `battle_victory.s`. Like `FAR_BATTLE`, they are named with a
; sixteen-bit address because the battle reads them, with the data bank at
; $7E. `ba_vic_start` writes all of them on winning and nobody reads them
; before, so there is no need to set them to anything at startup.
.pushseg
.segment "FARBSS"
far_ba_vic: .res 8
.popseg
BA_VIC        = .loword(far_ba_vic)
BA_VIC_ACTOR  = BA_VIC + 0      ; whose page it is, or $FF the first
BA_VIC_BEFORE = BA_VIC + 1      ; the level before winning, one per party
                                ; slot; 0 if it has no experience
BA_VIC_SKIP = BA_VIC + 5        ; the skill lines from earlier pages of the
                                ; same actor
BA_VIC_NEXT   = BA_VIC + 6      ; this one's and the earlier ones': what
                                ; the next one skips
BA_VIC_MORE   = BA_VIC + 7      ; whether skills were left for another page
BA_VIC_END    = BA_VIC + 8
.assert BA_VIC_END <= BA_VIC + 8, error, "the victory's state overflows its range"

; --- what the enemies dropped ------------------------------------------------
;
; The items the victory won, so
; its page can list them. Like `BA_VIC`, with a sixteen-bit address, and
; `ba_vic_drop` writes them on winning before anyone reads them.
.pushseg
.segment "FARBSS"
far_ba_drop: .res 1 + 2 * BA_ENEMIES_MAX
.popseg
BA_DROP       = .loword(far_ba_drop)
BA_DROP_N     = BA_DROP + 0     ; how many
BA_DROP_K     = BA_DROP + 1     ; the `k` of each one, a word since
                                ; 2026-10-15, in troop order: its name is
                                ; text `3k`
BA_DROP_END   = BA_DROP_K + 2 * BA_ENEMIES_MAX
.assert BA_DROP_END <= BA_DROP + 1 + 2 * BA_ENEMIES_MAX, error, "what the enemies dropped overflows its range"

; --- experience in the menu --------------------------------------------------
;
; The thirteen letters of the
; experience line of a party row, which `menu_exp_paint` builds before
; turning them into sprites. It lives as long as that routine.
.pushseg
.segment "FARBSS"
MENU_EXP_TEXT: .res $10
.popseg
MENU_EXP_TEXT_END = MENU_EXP_TEXT + $10

; --- `ChangeExp` and `ChangeLevel` from an event ------------------------------
;
; What `exp_change` works with, and
; the lines of the level-up message it notes for `OP_LEVEL_PAGE`: a word
; each, `$8000 | level << 8 | actor` for an actor's level line —which is
; also where its page starts— and the pair's slot for a skill's. Sixteen-bit
; addresses, like the battle's: `level.s` runs this with the data bank at
; $7E. **It does not travel in the save**: the lines live from the `OP_EXP`
; to the `OP_LEVEL_PAGE` right behind it, inside the same page.
.pushseg
.segment "FARBSS"
far_lvl: .res $B0
.popseg
LVL         = .loword(far_lvl)
LVL_WHAT    = LVL + 0           ; OP_EXP's `what`
LVL_ACTOR   = LVL + 1           ; the actor being changed
LVL_K       = LVL + 2           ; word: its experience slot
LVL_OFS     = LVL + 4           ; word: the slot times four, in `FAR_EXP`
LVL_AMOUNT  = LVL + 6           ; four bytes: the change, signed
LVL_VALUE   = LVL + 10          ; four bytes: the new experience, signed
LVL_T       = LVL + 14          ; four bytes: a row of `exp_table`, or scratch
LVL_OLD     = LVL + 18          ; the level before
LVL_NEW     = LVL + 19          ; and after
LVL_N       = LVL + 20          ; how many lines are noted
LVL_AT      = LVL + 21          ; the first not shown yet
LVL_CUR     = LVL + 22          ; word: where the box is being written
LVL_START   = LVL + 24          ; word: where the line being written starts
LVL_LEN     = LVL + 26          ; its letters
LVL_ROWS    = LVL + 27          ; the page's lines
LVL_LEFT    = LVL + 28          ; letters of a text still to copy
LVL_LINES   = LVL + 30          ; LVL_LINES_MAX words
; A constant, and not `(end - LVL_LINES) / 2`: it is an 8-bit immediate,
; and an address the linker places would not fit one for the assembler.
LVL_LINES_MAX = ($B0 - 30) / 2
.assert LVL_LINES = LVL + 30, error, "LVL_LINES_MAX counts from LVL_LINES"
.assert LVL_LINES + 2 * LVL_LINES_MAX <= LVL + $B0, error, "the level-up lines overflow their range"

; And the page of that message the window is showing, composed as the text
; block's boxes are —a header with how many lines, and each line's length
; before its letters, which are the font's: ASCII minus 32— so that
; `msg_start` reads it like any other. It only has
; to last while the composer reads it, which is before the window opens.
LVL_LINE_MAX  = 48              ; letters a line keeps: the window cuts sooner
.pushseg
.segment "FARBSS"
LVL_BOX: .res 1 + 4 * (1 + LVL_LINE_MAX)
.popseg

; --- the MSU-1 tracks that were missing --------------------------------------
;
; One bit per song, set when the
; song had a track and the MSU-1 could not play it —it was not on the card,
; or it did not finish opening it in time— and it played through the SPC700.
; See `song_per_msu` in audio_package.s. `msu_detect` clears it on
; reset; it does not travel in the save, because what it says is about the
; card and not about the game.
.pushseg
.segment "FARBSS"
MSU_MISSING: .res $10
.popseg
MSU_MISSING_BYTES = 16

; --- what goes on running after a teleport -----------------------------------
;
; The event bytecode lives in WRAM, behind the map's grid, since 2026-10-01,
; and the next map's takes its place. A page that goes on after a `Teleport`
; to another map —a cutscene that jumps and keeps talking, and every test
; case of the harness— would read the new map's: `code_carry_before` and
; `code_carry_after`, in decompress.s, carry it.
;
; Two blocks of far RAM:
;
;   CARRY_MAP    which map's bytecode is in `CODE_CARRY`, word; $FFFF none
;   ROUTE_CARRY  the hero's move route, copied whole when the map changes under
;            it: it is at most 255 bytes, which is what `route_n` counts
;
; And `CODE_CARRY`, in `LZ2_BUFFER`, which on the map is free once it is
; loaded: above the two places of the battle animation's frame —see
; `anim_frame_build`— and below the ChipSet animation's drawings. Loading a
; map overwrites it, and so does `back_to_map` —after the menu, the shop, the
; slots or a battle—: both decompress it again at the end.
.pushseg
.segment "FARBSS"
CARRY_MAP: .res 2
.popseg
.pushseg
.segment "FARBSS"
ROUTE_CARRY: .res $100
.popseg
.assert ROUTE_CARRY + 256 <= GRID, error, "the carried move route would go into the grid"
CODE_CARRY     = LZ2_BUFFER + $1100
LZ2_BUFFER     = $7F0000
ANIM_DRAWINGS  = $7F6000
ANIM_DRAWINGS_END = $7F8000

; --- sound effects with MSU-1 ------------------------------------------------
;
; See `msu_effects.s`: voices
; 0 to 5 when the SPC700 is not playing music, and the `.msu`'s quality sound
; effects. `se_clear` zeroes it, on reset; it does not travel in the save.
.pushseg
.segment "FARBSS"
EX_FRAMES: .res $1F           ; six words: how many frames the sound effect
.popseg
                                ; on each voice has left, from 0 to 5
EX_IDX      = EX_FRAMES + $0C           ; six words: its row in `sound_table`
EX_PEND     = EX_FRAMES + $18           ; one bit per voice: the sound effect has not started yet
EX_BUSY     = EX_FRAMES + $19           ; one bit per voice: it belongs to a sound effect
                                ; —pending, playing or being handed back— and
                                ; not to the music
EX_RETURN = EX_FRAMES + $1A             ; one bit per voice: it finished, and next frame
                                ; it is handed back to the music
MSU_SE      = EX_FRAMES + $1B           ; 0 not checked, 1 the `.msu` is this
                                ; cartridge's, 2 it is not or there is no MSU-1
MSU_SE_NEXT = EX_FRAMES + $1C           ; three bytes: where the `.msu` stream was left
EX_END      = EX_FRAMES + $1F
.assert EX_END <= EX_FRAMES + $1F, error, "the MSU-1 sound effects overflow their range"

; --- which sound effect is in each directory place ---------------------------
;
; One byte for each of the
; SE_PLACES of the SPC700 directory that the sound effects share, with the
; number of the sound effect recorded there, or $FF. Several sound effects go
; to the same place —the ones that are never in the same package: see
; `effect_places` in rm2k-snes/rm2k-snes-audio/src/bank.rs— and the directory does
; not say which one is there. See `record_effect` in audio_package.s.
; `aram_clear` sets it to $FF; it does not travel in the save.
; `SE_PLACES` bytes, declared in far_ram_game.s.

; --- the battle transition ---------------------------------------------------
;
; See `battle_fade.s`.
.pushseg
.segment "FARBSS"
BATTLE_ON: .res 1             ; 1 if the battle got to turn its screen on
.popseg

; --- the teleport transition ------------------------------------------------
;
; The transition with which the
; teleport erases the screen and the one with which it shows it again, which
; `ChangeScreenTransitions` changes —`op_transition`— and `fade_mosaic`,
; `fade_from` and `fade_tick` read: TRANSITION_MOSAIC, TRANSITION_CUTOFF,
; or anything else for the fade.
;
; `boot_transition` sets them to the fade, on reset: bsnes starts WRAM
; with garbage, and without that the first teleport could come out as mosaic.
; **It does not travel in the save**, and in RM2k it does. That is on
; purpose: the two places in the game that change it are chains of autorun
; pages that set it back to the fade when they finish —Boss Wick's hideout,
; from the mosaic of page 1 of 42 to the fade of page 4 of 40, and Eisen's
; story, from "none" in 93 to the fade of page 5 of 6 of 81—, and saving it
; would mean changing the save format for a value that in nearly every saved
; game holds the same.
;
; The "nearly" is the minigame on 95, which is inside Eisen's story and has a
; save point: a game saved there comes back with the fade instead of the cut,
; and the only thing that notices is the jump with which 95 sends Eisen back
; to the start when his fortitude runs out. The one that leaves the minigame
; asks for the cut itself before jumping.
.pushseg
.segment "FARBSS"
TRANSITION_ERASE: .res 2
.popseg
TRANSITION_SHOW = TRANSITION_ERASE + $01

; --- the memorized song -------------------------------------------------------
;
; `MemorizeBGM` records here
; which song was playing —its index in `Songs`, or $FF if none— and
; `PlayMemorizedBGM` plays it again: see `op_memorized_bgm`. Reset leaves it
; at $FF.
;
; **It does not travel in the save**, and in RM2k it does (`memorized_bgm`,
; in the system part). The two commands always go together in the same
; autorun page —the game's four tutorials, 58 and 162 to 164—, with no menu
; in between, so there is nowhere to save between one and the other.
.pushseg
.segment "FARBSS"
REMEMBERED_SONG: .res 1
.popseg

; --- the weapons' SP, and the target of multi-target skills -----------------
;
; `ba_build` builds it at the start of each battle, so it does not travel in
; the save and there is no need to set it on reset.
.pushseg
.segment "FARBSS"
BA_WEAPON_SP: .res BA_PARTY_MAX + 1          ; BA_PARTY_MAX bytes: what attacking costs
.popseg
                                ; each party place, `weapon_sp_of`
BA_SKILL_I = BA_WEAPON_SP + $04            ; which combatant a multi-target skill is on:
                                ; `ba_skill_use` calls `ba_skill_one` for each
                                ; one, and that one clobbers the `BA_S*`

; --- an NPC row, set aside ---------------------------------------------------
;
; `fit_far` keeps here the row that changes place while it moves the
; others; it lasts as long as that routine.
; `NPC_STRIDE` bytes, declared in far_ram_game.s: NPC_ROW_SEPARATE.

; --- the Game Over screen ------------------------------------------------------
;
; See runtime/game_over.s.
.pushseg
.segment "FARBSS"
GO_LOSES: .res 5            ; word: where losing the battle being fought
.popseg
                                ; leads; $FFFF is Game Over
GO_WAIT    = GO_LOSES + $02            ; 1 while the screen waits for the button: it is
                                ; what the harness looks at, which has no other clock
GO_LEVEL   = GO_LOSES + $03            ; the fade's brightness
GO_FRAMES = GO_LOSES + $04             ; how many frames each fade level lasts

; --- the map grid, in WRAM --------------------------------------------------
;
; **$7E8000 to $7EFFFF belongs to the grid**, and it continues at $7F8000 if
; it goes past 32 KB: the upper half of the two banks, which has the shape of
; two consecutive LoROM banks —see `ptr_more`—. `lz2_grid` decompresses it
; when loading the map and everyone who asks about a cell reads it. Reserved
; on 2026-09-26, and it is a decision with a cost: it was half of the far RAM
; that was still free. What is lost, how it is reverted and what catches it,
; in optimizations/lossless/the-map/the-grid-in-wram.md in the book;
; `test_wram_reservations.py` fails if another symbol lands inside.
;
; Right behind it, in $7F's half, go the block table and its passability,
; which `lz2_grid` decompresses with it: see there.
;
; It shares the $7F half with `SCN_SCENE`: the battle overwrites it, and
; `back_from_battle` decompresses the whole grid again.
GRID        = $7E8000
GRID_END    = $7F0000
GRID_HIGH = $7F8000

; On which frame startup ends, counted from reset. Startup —loading the map,
; uploading the driver to the SPC700 and the map's audio package— takes as
; long as it takes, and that changed with every code or data change: one more
; loop and the main loop started a frame later, and every recipe that
; compares frames in motion carries that number measured by hand. Now it
; waits until this frame and the loop always starts on the same one. A ROM
; whose startup takes longer than this goes without waiting, later, but just
; as fixed for it.
;
; **`BOOT_FRAMES` itself is not here: each cartridge carries its own**, at
; the end of its `musicdata.inc`, and it is this floor or the estimate for
; its startup map's package, whichever is larger —on the high side, it is
; `boot_frames` in rm2k-snes/rm2k-snes-audio/src/emit.rs—. Since 2026-10-11:
; Vampires Dawn's startup map asked for 46 and this was a constant, so
; raising it for one game moved the loop's frame in all of them. The floor
; is what keeps a cartridge whose package is small —ABL's— starting on the
; frame its tests already count, byte for byte the same ROM.
;
; Measured on 2026-09-26: `release`'s work ends on frame 30 and the estimate
; gives 34. It was 112 until that day, meant for uploading a full ARAM
; through the IPL; see "Boot is sized for the boot package" in
; optimizations/lossless/audio.md in the book. 40 until 2026-10-02: with the first
; day in Paradise in the cartridge the startup map's package went from
; 14,976 to 15,651 B —the samples are shared out over every package— and
; the estimate reached 40.
BOOT_FRAMES_FLOOR = 44
VIEW_ROWS = 29

; The message window: 256x80, and at the bottom of a 224-line screen —RM2k's
; default— the ten cell rows going from 18 to 27. The same numbers are in
; `rm2k-snes/screens/src/layout.rs`, which is where they come from. `MessageOptions`
; can put it at the top or in the middle: see message_place.s, which works
; out its scroll for each.
WINDOW_ROW    = 18
TEXT_WINDOW_ROWS = 10
WINDOW_LINE = WINDOW_ROW * 8            ; and in scanlines: 144
LINES = 224

; The 64x32 tilemap is two 32-wide screens side by side, and the second one
; does not live 32 words further on but 1024.
VIEW_COLS_TILEMAP = 32

