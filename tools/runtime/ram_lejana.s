; --- the RAM in bank 1 ---------------------------------------------------------
; Bank 0's BSS is full —7680 of 7680— and so is the ZEROPAGE, 256 of 256; this
; used to say the ZEROPAGE had twelve to spare and that stopped being true a
; while ago. The console has 128 KB of WRAM and the ROM uses eight: the rest
; is reached through this same window, pointing WMADD and reading or writing
; $2180 with auto-increment. It is not normal addressing —it cannot be
; indexed— so it is good for what is stored and walked a little at a time,
; not for what is drawn.
;
; Today it holds the state of the parallel interpreters: 840 bytes that did
; not fit in bank 0. The day there are RM2k variables —five thousand, ten
; kilobytes— they go here too.
FAR_PAIR_STATE = $2000      ; EV_MAX entries of PAIR_BYTES
FAR_PAIR_LIST  = $2400      ; PARALELO_MAX entries of PAIR_LIST_BYTES
; The RM2k variables, one signed word per slot. How many there are is said by
; the converter —`VARIABLES_N`—, which gives a slot only to the ones named by
; the pages of the maps in the ROM; the bytecode talks in slots. They are read
; and written with `var_read` and `var_write`, and they travel in the save:
; `save_table` copies them from here, which the DMA reaches just like bank
; 0 because WMADD is a seventeen-bit address.
FAR_VARIABLES  = $2600
; And the inventory, after the variables —which are at most 256, the
; converter guarantees it—: one byte per LDB item, indexed by the RM2k number
; —0 is unused— and capped at ITEM_MAX, like `Game_Party::AddItem`. It
; travels in the save and is cleared with the variables.
FAR_ITEMS      = $2800
; And the equipment of each LDB actor, by actor number: five words —weapon,
; shield, armor, helmet, accessory— with the item number or 0. It starts with
; the database's initial equipment, which `initial_equipment_set` copies on
; reset, and travels in the save.
FAR_EQUIPMENT     = $2C00
; And the random state, two bytes before: a sixteen-bit xorshift, the same as
; `random_next` in eventos.py, seeded on reset. It goes here and not in the
; direct page because the direct page ended up at 258 of 256 when that was
; tried; randomness is asked for rarely and the port does not notice.
FAR_RANDOM       = $25FE
; And the hero's speed, 1 to 6, one byte before: move commands 28 and 29 of a
; forced move route raise and lower it and **it stays that way**, for the pad
; too —RM2k only restores the frequency when the move route ends,
; `original_move_frequency`; not the speed—. It travels in the save. It is
; read once per step.
FAR_HERO_SPEED   = $25FD
; And the permissions, one byte before: `ChangeSaveAccess`,
; `ChangeMainMenuAccess` and `ChangeEscapeAccess` turn them off and on, and
; bit 7 is RM2k's menu request, `menu_calling`: B sets it and the hero
; handles it when standing still. The bits are stored as "forbidden" so that
; the zero from reset means "everything allowed", which is how RM2k starts.
; It travels in the save, as it does there.
;
; The escape one is stored and **nobody reads it yet**: escaping belongs to
; the battle. It is here because it is one bit and because without it 30 of
; the game's 39 pages with `EnemyEncounter` that fail today do not compile;
; see ACCESO_BIT in eventos.py.
FAR_ACCESS     = $25FC
ACCESS_NO_SAVE = $01
ACCESS_NO_MENU    = $02
ACCESS_NO_ESCAPE = $04
ACCESS_REQUESTED      = $80
; --- the battle: its state in far RAM -------------------------------------------
;
; **Far RAM has a map and it has to be respected.** On 2026-09-12 the picture
; was put at $30E8, which was where the MSU-1 state lived, and the ROM stopped
; detecting the chip: the music went silent and no test saw it. From $2000 to
; $30FA everything is taken —the parallel interpreters, the variables, the
; inventory, the equipment, the weather, the sound effects, the rotation, the
; picture— and from $3100 to $3600 goes the ARAM allocation. So this starts at
; $3700, which is the first place where nobody is.
;
; The HP of each LDB actor, one word per actor number. **They are real state
; since there are battles**: until 2026-09-12 nobody went below their maximum
; and `ChangeHP` compiled to nothing. They travel in the save, after the
; equipment, and reset fills them up.
FAR_HP = $3700

; Far RAM with the bank in front, for the few who read it from outside with
; `lda f:`: it is the same as `BAT_LENGTH`, which kept a battle name.
FAR_LENGTH = $7E0000

; And the SP, which are state for the same reason as the HP since skills can
; be used: each one costs its `sp_cost` and `Scene_Battle` deducts it from
; whoever uses it. They start full from `actor_spmax` and travel in the save,
; after the HP. `FAR_HP` is ACTORES_N words —61 actors, 122 bytes— so it
; reaches $3779; this starts at $3780 and ends before $3800.
FAR_SP = $3780

; And which graphic a `ChangeSpriteAssociation` changed each LDB actor's
; sprite to, one byte per actor number: the index in the map's graphics table
; —the same one move command 34 of a move route resolves— or $FF if it keeps
; the LDB one. It travels in the save, as in RM2k, and **survives the
; teleport**: that is what sets it apart from move command 34 on the hero,
; which is restored on load.
;
; It goes at $3800 and the battle moves to $3A00. It could have gone right
; after `FAR_HP` —today there is more than enough room up to $37FF— but then
; its address would depend on `ACTORES_N`, which the converter emits, and the
; far RAM map would be at the mercy of a number not written here. See above:
; this map was stepped on once already and the music was silent for a whole
; day.
FAR_ACTOR_GFX = $3800
ACTOR_GFX_NONE = $FF

; And which skills each actor knows, since 2026-09-21: one bit per (actor,
; skill) pair, with the slot the converter gave each pair —see
; `HABILIDAD_RANURA` in eventos.py—. It starts with what the LDB says for the
; initial level, which `initial_skills_set` copies on reset, `ChangeSkills`
; sets and clears it, and it travels in the save. How many bytes it takes is
; said by `HAB_BYTES`, and the converter stops if they go past 256.
;
; **$6000 to $60FF belongs to this**: the range was reserved in advance, when
; splitting work among three jobs that ran at the same time and touched far
; RAM.
FAR_SKILL = $6000

; --- random encounters: their state in far RAM -------------------------------
;
; Nine bytes at $3900, which is the gap left between `FAR_ACTOR_GFX` —61
; bytes from $3800— and the battle. **It does not travel in the save**, just
; as the HP of an unfinished battle do not: on load, the accumulated count
; starts at zero, which is the same thing that happens on entering a map.
;
; It did not fit in bank 0: the BSS is at 7680 of 7680, measured on
; 2026-09-13 by adding a `.res 64` and looking at the assembler's cut.
FAR_ENCOUNTER = $3900
ENC_N     = FAR_ENCOUNTER + 0   ; steps taken since the last encounter
ENC_IDX   = FAR_ENCOUNTER + 1   ; the table row, which never goes down
ENC_ASKS  = FAR_ENCOUNTER + 2   ; one came up and is collected next frame
ENC_RNG   = FAR_ENCOUNTER + 3   ; word: the xorshift, with its own seed
ENC_BASE  = FAR_ENCOUNTER + 5   ; word: 1/steps in 1/65536; 0 is off
ENC_REG   = FAR_ENCOUNTER + 7   ; this map's record, or ENC_NONE
; A map with no troops of its own and no areas covering it.
ENC_NONE   = $FF
; The eight rows of `UpdateEncounterSteps`'s table, and how many threshold
; bytes each record carries: seven —row 0's is 0 and is not stored— plus one
; of padding, so that the index is a shift and not a multiplication.
ENC_ROWS  = 8
ENC_STRIDE = 8
; The current map's thresholds, copied from `enc_umbral_n` on entry: the step
; at which each row is crossed, from 1 to 7. They live in RAM and are not
; read from the table because `ChangeEncounterSteps` changes them along with
; `ENC_BASE`: the chance and the rows come from the same `encounter_steps`.
;
; $7E79C0 to $7E79C7, out of what was allotted to world milestone 2 on
; 2026-09-27 —$79C0 to $79DF—. Like the rest of the encounters, with a
; sixteen-bit address: it is read with the data bank at $7E.
ENC_THR   = $79C0
.assert ENC_THR + ENC_STRIDE <= $79E0, error, "the thresholds overflow their range"

; --- experience and level: their state in far RAM ----------------------------
;
; Four bytes per actor who can fight, in the order of the converter's
; `experiencia_ranuras` —`actor_exp_k` says which one each actor number gets,
; or $FF—: the 24-bit experience, which in RM2k reaches 999999, and the level.
; Having the level right next to the experience is what makes the save carry
; a single line for both. It starts from `exp_inicial` on reset and travels
; in the save.
;
; $6200 to $63FF is the place given to this on 2026-09-21, split among three
; branches: the map above ends at the battle, which does not go past $3CFF.
FAR_EXP     = $6200
EXP_LEVEL   = 3             ; the level, the fourth byte
; And, at the end of the same place, eight bytes where `text_level` and its
; siblings compose the level and the maximum the menu writes: they are
; numbers from the save and no longer strips from the cartridge. The slots
; reach 128 before stepping on them, and the converter stops much earlier:
; see `experiencia_asm`.
EXP_TEXT   = $7E63F8
; RM2k's `MaxExpValue()`, in its two halves.
EXP_CAP_HI = $0F
EXP_CAP_LO = $423F

; --- troop pages: their state in far RAM --------------------------------------
;
; $6400 to $65FF is the place given to this on 2026-09-21. **It does not
; travel in the save**, like nothing in the battle. It is named with a
; sixteen-bit address, same as `FAR_BATTLE`, because the battle code reads
; it with the data bank at $7E; the bridge from bank 0 puts `BAT_LENGTH` in
; front of it.
FAR_PAGE       = $6400
BT_PAGE_N      = FAR_PAGE + 0     ; how many pages this battle's troop brings
BT_PAGE_INIT    = FAR_PAGE + 1     ; word: the first, in the `tpag_*` tables
BT_PAGE_CODE    = FAR_PAGE + 3     ; word: where the running one starts, in the
                                ; bank of `tropa_codigo`
BT_PAGE_CUR    = FAR_PAGE + 5     ; word: its cursor, its own `ev_cur`
BT_PAGE_ACT    = FAR_PAGE + 7     ; whether it has not finished yet: its `ev_active`
BT_PAGE_MSG    = FAR_PAGE + 8     ; word: the message it asked for and is on
                                ; screen, in `mensajes_tropa`, or $FFFF
BT_PAGE_TICK = FAR_PAGE + 10    ; where the battle goes on when none are left:
                                ; 0 the next action, 1 ask for the commands
BT_PAGE_I      = FAR_PAGE + 11    ; which one the sweep is on
BT_PAGE_G      = FAR_PAGE + 12    ; word: that same one, in the `tpag_*` tables
BT_PAGE_DONE  = FAR_PAGE + 16    ; TROPA_PAG_MAX bytes: already ran this turn
; And what the turn and HP conditions and the commands that come with them
; added, on 2026-09-28: $7E7A10 to $7E7A3F, which is what was allotted to
; this. With a sixteen-bit address, like the rest of the battle.
BT_TURN      = $7A10           ; word: the turn, `Game_Party::GetTurns`
BT_PAGE_WAIT = $7A12           ; word: frames left in the wait of the
                                ; running page
BT_PCT_MIN    = $7A14           ; the HP range, in percent, that is checked
BT_PCT_MAX    = $7A15
BT_P24        = $7A16           ; three bytes: what `bt_mul24` leaves
BT_P_HP       = $7A19           ; three bytes: a hundred times the HP checked
BT_PAGE_FL     = $7A1C           ; the triggers of the page being tested
; And its header, copied from in front of its code: `eventos.cabecera_de_tropa`,
; in the same order.
BT_COND       = $7A20
BT_COND_BASE  = 0               ; word: the turn base, `turn_b`
BT_COND_MULT  = 2               ; word: and its multiple, `turn_a`
BT_COND_ENEMY   = 4               ; the enemy's place in the troop
BT_COND_EMIN  = 5               ; and its HP range, in percent
BT_COND_EMAX  = 6
BT_COND_ACT   = 7               ; the actor, by LDB number
BT_COND_AMIN  = 8
BT_COND_AMAX  = 9
.assert BT_COND + TPAG_CABECERA <= $7A40, error, "the pages' state overflows its range"

; --- a medicine outside battle: its scratch space in far RAM -----------------
;
; $6800 to $68FF belongs to this, reserved on 2026-09-21 when splitting.
; **It does not travel in the save**: it lasts as long as one A press in the
; actor choice. It is named with a sixteen-bit address because
; `medicine_use` runs with the data bank at $7E.
FAR_MED       = $6800
MED_ACTOR     = FAR_MED + 0     ; the actor, by LDB number
MED_FLAGS  = FAR_MED + 1     ; the item's `item_medicina` bits
MED_USED     = FAR_MED + 2     ; whether it worked: easyrpg's `was_used`
MED_REVIVED   = FAR_MED + 3     ; word: 1 if it revived it, the `revived`
MED_HP_MAX    = FAR_MED + 5     ; word: the max HP for its level
MED_SP_MAX    = FAR_MED + 7     ; word: and the SP
MED_HP        = FAR_MED + 9     ; word: the `hp_change`
MED_SP        = FAR_MED + 11    ; word: the `sp_change`
MED_P         = FAR_MED + 13    ; four bytes: the product, and the quotient
MED_R         = FAR_MED + 17    ; word: the remainder
MED_ID        = FAR_MED + 19    ; word: the item's RM2k number
; The `item_medicina` bits, which the converter emits. `medicine_use` writes
; them by number; the battle, which reads them since 2026-09-26, by name.
MED_KO_ONLY   = $01             ; only on a fallen one
MED_RAISES   = $02             ; removes the dead state: revives the fallen one

; What `pair_ev` holds while a troop page runs: neither the foreground ($FF)
; nor a map event, which are fewer than EV_MAX. It is what tells
; `op_message` that the message belongs to the battle. See `bt_t_page`.
PAIR_BATTLE = $FE
.assert EV_MAX < PAIR_BATTLE, error, "PAIR_BATTLE must not be an event"

; And the battle state, which does **not** travel in the save: a battle cannot
; be saved in RM2k either.
FAR_BATTLE = $3A00
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
BT_TROOP   = FAR_BATTLE + 0      ; the troop, as an RM2k number
BT_RESULT  = FAR_BATTLE + 2      ; 0 victory, 1 escape, 2 defeat
BT_SEED     = FAR_BATTLE + 3      ; the battle's xorshift, with its own seed
BT_NACT    = FAR_BATTLE + 5      ; how many actors
BT_KID    = FAR_BATTLE + 6      ; how many enemies
BT_MODE    = FAR_BATTLE + 7
BT_ACTOR   = FAR_BATTLE + 8      ; who is being asked for a command
BT_COMMAND   = FAR_BATTLE + 9      ; which command the cursor marks
BT_TARGET  = FAR_BATTLE + 10     ; which enemy the cursor marks
BT_ESCAPE   = FAR_BATTLE + 11     ; the chance to escape, which rises on failing
BT_I       = FAR_BATTLE + 12     ; which one of the execution the turn is on
BT_WAIT  = FAR_BATTLE + 13     ; frames the message has left
BT_MTIPO   = FAR_BATTLE + 14     ; what the message says
BT_MQUIEN  = FAR_BATTLE + 15
BT_MBLA    = FAR_BATTLE + 16
BT_MDANO   = FAR_BATTLE + 17     ; word
BT_NACC    = FAR_BATTLE + 19     ; how many actions the turn has
BT_T0      = FAR_BATTLE + 20     ; scratch words, which anyone clobbers
BT_T1      = FAR_BATTLE + 22
BT_T2      = FAR_BATTLE + 24
BT_S0      = FAR_BATTLE + 26     ; and the ones that survive a `jsr`
BT_S1      = FAR_BATTLE + 28
BT_S2      = FAR_BATTLE + 30
BT_S3      = FAR_BATTLE + 32
BT_S4      = FAR_BATTLE + 34
BT_S5      = FAR_BATTLE + 36
BT_S6      = FAR_BATTLE + 38
; Whether the line being composed also shows the max HP, that is, whether it
; belongs to the party. It has its own byte and not a borrowed `BT_T2 + 2`,
; which is what it was and it landed right on top of `BT_S0`: the enemy loop
; restarted by itself and the screen never got to appear.
BT_CONMAX  = FAR_BATTLE + 40
; The battle's audio, in the bytes that were left loose before `BT_ACC`.
; `BT_SONG_PREV` is the song that was playing on the map —$FF if nothing was—,
; which is RM2k's `before_battle_music`: when the battle ends it comes back.
; `BT_SE2` is the sound effect still to fire in the current message, or
; $FFFF: RM2k plays two per hit —the attack's and the damage's, separated by
; a wait— and here the second goes out when `BT_WAIT` reaches
; `BT_SE2_FRAMES`.
BT_SONG_PREV = FAR_BATTLE + 41
BT_SE2      = FAR_BATTLE + 42     ; word
; Whether there is a scene in BG1 —0— or this battle goes on black —$FF—: no
; background and no battler. See `scene_upload`.
BT_SCENE   = FAR_BATTLE + 44
; And at which place in `tropa_id` this battle's troop landed, which is what
; `escena_tropa_fondo` indexes. $FF: the cartridge does not carry it.
BT_TROOP_K  = FAR_BATTLE + 45
; And the item being used, since 2026-09-13. It goes **after `BT_ONE`**,
; which ends at +575, because between +40 and +48 nothing is left and moving
; `BT_ACC` would mean moving everything else.
;
; It was at +320 until `BT_BYTES` went from 18 to 40 —the SP and the four
; parameter modifiers of the skills— and `BT_ONE` ran into it.
BT_ITEM_N    = FAR_BATTLE + 576   ; how many are in the list
BT_ITEM_SEL  = FAR_BATTLE + 577   ; which one the cursor marks
BT_ITEM_ARR  = FAR_BATTLE + 578   ; the first one visible
BT_ITEM_BLA  = FAR_BATTLE + 579   ; which actor it is given to; since 2026-09-13
                                   ; also the target of a healing skill,
                                   ; which picks with the same mode
BT_MITEM     = FAR_BATTLE + 580   ; the `k` of the current message's item
BT_ACTOR2    = FAR_BATTLE + 581   ; an actor counter `BT_S0` cannot be
BT_MCURA     = FAR_BATTLE + 582   ; word: how much it healed
BT_ACC_ITEM  = FAR_BATTLE + 584   ; the `k` each actor chose, one per byte
BT_ITEM_LIST = FAR_BATTLE + 592  ; the list, one `k` per byte
BT_ITEM_MAX = 64
; --- skills, since 2026-09-13 ---------------------------------------------
;
; After `BT_ITEM_LIST`, which ends at +656.
BT_SKILL_N     = FAR_BATTLE + 656   ; how many the one giving commands knows
BT_SKILL_SEL   = FAR_BATTLE + 657   ; which one the cursor marks
BT_MHAB      = FAR_BATTLE + 658   ; the `k` of the current message's one
BT_ACC_SKILL   = FAR_BATTLE + 660   ; the `k` each actor chose, one per byte
BT_SKILL_LIST = FAR_BATTLE + 672   ; their list, one `k` per byte
BT_SKILL_MAX   = 16                  ; BA_HAB_FILAS times BA_HAB_COLUMNAS, with room to spare
BT_MEFECTO   = FAR_BATTLE + 688   ; signed word: how much the last one did
BT_ACC     = FAR_BATTLE + 48     ; two bytes per combatant: command and target
BT_EXEC    = FAR_BATTLE + 72     ; the execution order, one combatant per byte
BT_CAND    = FAR_BATTLE + 88     ; the living on one side, to pick a target
BT_ONE     = FAR_BATTLE + 96     ; the combatants, BT_BYTES each
; Whether the current message's item revived a fallen one: the second line
; changes. **Outside `FAR_BATTLE`**, at $7E7850-$7E785F, which is what was
; allotted to this on 2026-09-26 —other agents were choosing RAM at the same
; time—. Like everything in the battle, with a sixteen-bit address and the
; data bank at $7E.
BT_MREVIVIO = $7850

; The combatants: the first four are the party and the next eight the troop.
; That the place is fixed and not a compacted list is what keeps a dead one
; visible in its line, as on the screen.
BT_PARTY_MAX = 4
BT_ENEMIES_MAX = 8
BT_COMB_MAX = BT_PARTY_MAX + BT_ENEMIES_MAX
; It was 18 until 2026-09-13, which is when the SP came in along with the
; four parameter modifiers that two of the party's seven skills move. 40 is
; also convenient: the offset comes out of five `asl` and an addition, see
; `bt_x`.
BT_BYTES  = 40
BT_HP     = 0               ; word
BT_HPMAX  = 2
; **The four parameters here are the effective ones**, that is,
; game_battler.cpp's `AdjustParam`: `clamp(base + modifier, 1, 999)`. The
; base and the modifier live further down and are stored whole because a
; modifier that survives the clamp cannot be recovered from the subtraction;
; `bt_mod` recomputes them.
BT_ATK    = 4
BT_DEF    = 6
BT_AGI    = 8
BT_SORT   = 10              ; the `agi + random` the turn is sorted by
BT_TXT    = 12              ; the text number of its name
BT_HIT    = 14              ; byte
BT_CRIT   = 15
BT_FLAGS  = 16
BT_NUMBER = 17              ; the LDB actor, or the place in the troop
BT_SP     = 18              ; word: the SP it has left
BT_SPMAX  = 20
BT_MATK   = 22              ; the four modifiers, signed
BT_MDEF   = 24
BT_MSPI   = 26
BT_MAGI   = 28
BT_BATK   = 30              ; and the four bases
BT_BDEF   = 32
BT_BSPI   = 34
BT_BAGI   = 36
BT_SPI    = 38              ; the effective spirit, which `CalcSkillEffect` asks for
BAF_DEF   = $01             ; it is defending
BAF_ACTOR = $02             ; it belongs to the party
BAF_HAS   = $04             ; the slot is taken
; A hidden enemy —`invisible` in the troop— takes its place but **does not
; have `BAF_HAS`**: that way everything that looks at who is there
; —`bt_alive`, and with it the target, the actions, the victory and the
; scene— skips it without knowing anything about hidden ones, which is what
; `Exists()` does in easyrpg. `ShowHiddenMonster` swaps one bit for the
; other: see `bt_show_hidden`.
BAF_HIDDEN = $08

; The three results and the three commands, in the order of `tools/port/battle.py`.
BT_VICTORY = 0
BT_ESCAPE_R  = 1
BT_DEFEAT  = 2
BT_ATTACK   = 0
BT_DEFEND = 1
BT_FLEE     = 2
BT_ITEM     = 3
BT_SKILL = 4
; The screen modes, like `pantallas.BA_ELIGE_ORDEN` and company. **The order
; matters**: more than one place asks `cmp #BT_M_MESSAGE / bcs` to say
; "message or end", so the ones that choose something all go first.
BT_M_COMMAND  = 0
BT_M_TARGET = 1
BT_M_ITEM   = 2
BT_M_ACTOR  = 3
BT_M_SKILL    = 4
BT_M_MESSAGE = 5
BT_M_END    = 6
; Running a troop page, with or without its message on screen: see
; `modo_pagina`. It goes after the message ones because it chooses nothing.
BT_M_PAGE = 7
; What the message says.
BT_MSG_ATTACK = 0
BT_MSG_DEFENDS = 1
BT_MSG_NO_FLED = 2
BT_MSG_FLED = 3
BT_MSG_VICTORY = 4
BT_MSG_DEFEAT = 5
BT_MSG_ITEM = 6
BT_MSG_SKILL = 7
; How many frames a message stays if nobody presses A. Two seconds, which is
; how long a line takes to read, and A skips it.
BT_MSG_FRAMES = 120
; When the hit's second sound effect goes out: `Scene_Battle_Rpg2k` plays the
; attack's when the action starts and the damage's in the message sub-state,
; with a `SetWait(4,4)` in between. Here the message lasts `BT_MSG_FRAMES`
; and the second sound effect goes out twenty-four frames later. The
; twenty-four were chosen when sound effects had a single voice and the new
; one cut off the previous one's voice, so they had to stay apart by ear;
; since 8c9c182 they are two voices —see `efectos_de_sonido.s`— and two
; different sound effects no longer cut each other off; the same sound effect
; twice does, because `sound_play` fires it again on the voice that is
; already playing it.
BT_SE2_FRAMES = BT_MSG_FRAMES - 24
; The hit rate of an actor with no weapon that changes it:
; `Game_Actor::GetHitChance`.
BT_HIT_ACTOR = 90
; The damage cap —RM2k's `MaxDamageValue()`— and the cap on the average
; agility that goes into the escape computation: two hundred times the
; average has to fit in sixteen bits, and the game's most agile enemy has
; 300.
BT_DAMAGE_MAX = 999
BT_AGI_CAP = 320
; The cap on an effective parameter: `Game_Actor::GetAtk` and its siblings,
; that is, RM2k's `MaxStatBattleValue`.
BT_PARAM_MAX = 999
; `rpg::Skill::Type_switch`, the one that turns on a switch and does nothing
; else. It is the only type this port tells apart from normal: the seven the
; intro party knows are either `normal` or `switch`.
BT_SKILL_TYPE_SWITCH = 3
; The five scopes of `rpg::Skill::Scope`, which is what `hab_alcance` carries.
; Only `enemy` and `ally` ask for a target when chosen; for the other three
; the scope decides it: see `batalla.blancos_de_la_habilidad`.
BT_SCOPE_ENEMY  = 0
BT_SCOPE_ENEMIES = 1
BT_SCOPE_ONE      = 2
BT_SCOPE_ALLY   = 3
BT_SCOPE_PARTY    = 4
; An enemy action that is not a skill: the basic attack, in `eacc_hab`, and
; what `bt_enemy_action` answers when it has none left. See
; `batalla.accion_del_enemigo`.
BT_EACC_ATTACK = $FF
BT_EACC_NOTHING   = $FE
BT_EACC_NO_EFFECTIVE = $80       ; the `eacc_peso` bit

; Cursor (2), wait (2), whether it is running (1) and from which page (2).
; **Eight and not seven**: the index comes out of three `asl` instead of an
; `x * 8 - x`, which is six bytes of bank 0 and a few cycles for every
; parallel and every frame. EV_MAX times eight is 960 bytes, so it still fits
; below `FAR_PAIR_LIST`.
PAIR_BYTES = 8
; And the eighth, which was spare, is the event's move route slot plus one,
; or zero if it has none: `slot_record` sets it when one is given, and
; `clear_parallel` clears it when loading the map, next to `load_npcs`,
; which is where they are all freed. Within a map a slot is never released.
; It is what saves each parallel from looking for its own every frame: see
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
; PARALELO_MAX times eight is 384 bytes and up to `FAR_RANDOM` there are 508.
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
; $6A00 to $6B7F belongs to this, reserved on 2026-09-22. **It does not
; travel in the save**: it lasts one frame.
FAR_STRIP_ROW  = $7E6A00         ; WINDOW_COLS * 2
FAR_STRIP_ROW2 = $7E6A80         ; and the upper layer, adjacent as in bank 0
FAR_STRIP_COL  = $7E6B00         ; WINDOW_ROWS * 2
FAR_STRIP_COL2 = $7E6B40
; Adjacent, which is what `push_one_row` takes advantage of to reach the
; upper layer's by adding the length of the other, same as with the bank 0
; ones.
.assert FAR_STRIP_ROW2 = FAR_STRIP_ROW + WINDOW_COLS * 2, error, "row strips not adjacent"
.assert FAR_STRIP_COL2 = FAR_STRIP_COL + WINDOW_ROWS * 2, error, "column strips not adjacent"

; --- where the background tilemap is, in far RAM ----------------------------
;
; The VRAM word of the loaded map's BG1 tilemap. `enter_map` copies it from
; `M_VRAM_MAP` and `build_column` and `build_row` add it, since they cannot
; read the table because X is in use. It is $5800 in every layout but one:
; see LAYOUT_VENTANA_AMBOS. It does not fit in the BSS.
;
; $6B80 and $6B81 belong to this, reserved on 2026-09-25. **It does not
; travel in the save**: loading it loads the map, and that sets it again.
FAR_VRAM_MAP = $7E6B80

; --- the flash palettes, in far RAM -----------------------------------------
;
; One per flash slot, thirty-two bytes each, and the vblank uploads all the
; ones left pending. It has to be one per slot: with a single one, two live
; flashes in the same frame overwrote each other, the last one's was
; uploaded, and the frame that turns off the first never reached CGRAM. They
; do not fit in the BSS.
;
; $6900 to $69FF belongs to this, reserved on 2026-09-23. **It does not
; travel in the save**: it lasts one frame.
FAR_FLASH_PAL = $7E6900         ; FLASH_MAX * 32
.assert FLASH_MAX * 32 <= $100, error, "the flash palettes overflow their range"

; --- the music decoder, in far RAM -------------------------------------------
;
; The state of `music_frame`, which expands the per-note stream into DSP
; writes: see "el formato por nota" in tools/audio/snes_music.py. It is read
; and written by `irq_music`, which lands at any point in the main code, so
; it is reached with long addressing and never through the WMADD window.
;
; $6C00 to $6FFF belongs to this, reserved on 2026-09-26. **It does not
; travel in the save**: starting the song zeroes it.
;
;   MUS_SHADOW   the last thing the stream wrote to each voice register,
;                indexed by the register number —$v0 to $v7—, and in $v8,
;                which is ENVX and is not written, the release GAIN of the
;                sound of the voice's last note
;   MUS_WAIT   word: how many frames until the stream is read
;   MUS_KON      the voices that got a note in the frame being read
;   MUS_PLAYING  the ones keyed on when the previous one closed: released on opening
;   MUS_BASE     word: where the song's sounds start in `musica_sonidos`
;   MUS_VIEWS   the voices that have had a note since the song started
;   MUS_GAINS    the ones that have already received a GAIN
;   MUS_BIT      the voice bit of the event being read
;   MUS_T        scratch word
FAR_MUSIC   = $7E6C00
MUS_SHADOW   = FAR_MUSIC
MUS_WAIT   = FAR_MUSIC + $80
MUS_KON      = FAR_MUSIC + $82
MUS_PLAYING  = FAR_MUSIC + $83
MUS_BASE     = FAR_MUSIC + $84
MUS_VIEWS   = FAR_MUSIC + $86
MUS_GAINS    = FAR_MUSIC + $87
MUS_BIT      = FAR_MUSIC + $88
MUS_T        = FAR_MUSIC + $89
; The bytes from MUS_WAIT to MUS_T, which `music_clear` zeroes.
MUS_STATE_BYTES = $0B
; The log of what the stream asks of the DSP: `dsp_music` records each
; (register, value) pair here if MUS_LOG_YES is not zero, and
; MUS_LOG_I is where the next one goes, in bytes. It is the net of
; `test_musica_escrituras.py`: the test turns it on and reads it frame by
; frame. It wraps around at 512 bytes, 256 writes, and a music frame does not
; go past a hundred. Each music frame starts with a mark, register
; MUS_LOG_MARK —which the DSP does not have—: the IRQ of a heavy frame
; ends after the emulator has delivered the frame, and without the mark its
; last writes would look like they belong to the next one.
MUS_LOG_MARK = $FF
MUS_LOG_YES = FAR_MUSIC + $F0
MUS_LOG_I  = FAR_MUSIC + $F2     ; word
MUS_LOG    = FAR_MUSIC + $200
MUS_LOG_LENGTH = $200
.assert MUS_LOG + MUS_LOG_LENGTH <= $7E7000, error, "the log overflows its range"

; The `FadeOutBGM` factor on the voices' volume, from 0 to 256 —256 is full
; volume—: this frame's and the previous one's, which is the one the DSP has.
; `bgm_fade_tick` writes them and the music reads them, both inside
; `irq_music`. See `volume_refresh`.
;
; $7860 to $7863, out of what was allotted to this on 2026-09-26 —$7860 to
; $786F—: other agents were choosing RAM at the same time.
FADE_N     = $7E7860          ; word
FADE_BEFORE = $7E7862          ; word

; --- the battle animation frame, in far RAM ---------------------------------
;
; The 2 KB of the frame the vblank uploads to the box. The cartridge does not
; store them whole —only the tiles that are not all zero, see
; `cuadro_sin_vacios` in snes_convert.py— and `anim_frame_build` rebuilds
; them here, outside the vblank. The DMA in `anim_drawing_dma` comes from
; here and not from the cartridge.
;
; $7000 to $77FF belongs to this, reserved on 2026-09-26. **It does not
; travel in the save**: loading a map zeroes it.
ANIMB_BUF = $7E7000

; --- LZ2: what the cartridge carries compressed, in WRAM --------------------
;
; See `lz2_decompress` in descomprimir.s. Reserved on 2026-09-26:
;
;   $7E7800  the literal's `mvn` trampoline, four bytes built with each
;            call's banks, and the output bank
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
; The limits of each block are enforced by `descomprimir.s` against the ones
; the converter emits.
LZ2_TRAMPOLINE_LIT = $7E7800        ; mvn output, stream; rtl
LZ2_BANK      = $7E7804        ; the output bank

; --- what the victory counts -------------------------------------------------
;
; $7E7810 to $7E781F, reserved on 2026-09-26: the "N EXP" and "Level up!"
; pages of `batalla_victoria.s`. Like `FAR_BATTLE`, they are named with a
; sixteen-bit address because the battle reads them, with the data bank at
; $7E. `bt_vic_start` writes all of them on winning and nobody reads them
; before, so there is no need to set them to anything at startup.
BT_VIC        = $7810
BT_VIC_ACTOR  = BT_VIC + 0      ; whose page it is, or $FF the first
BT_VIC_BEFORE  = BT_VIC + 1      ; the level before winning, one per party
                                ; slot; 0 if it has no experience
BT_VIC_SKIP = BT_VIC + 5     ; the skill lines from earlier pages of the
                                ; same actor
BT_VIC_NEXT    = BT_VIC + 6      ; this one's and the earlier ones': what
                                ; the next one skips
BT_VIC_MORE    = BT_VIC + 7      ; whether skills were left for another page
BT_VIC_END    = BT_VIC + 8
.assert BT_VIC_END <= $7820, error, "the victory's state overflows its range"

; --- what the enemies dropped ------------------------------------------------
;
; $7E79E0 to $7E79FF, reserved on 2026-09-27: the items the victory won, so
; its page can list them. Like `BT_VIC`, with a sixteen-bit address, and
; `bt_vic_drop` writes them on winning before anyone reads them.
BT_DROP      = $79E0
BT_DROP_N    = BT_DROP + 0    ; how many
BT_DROP_K    = BT_DROP + 1    ; the `k` of each one, in troop order:
                                ; its name is text `3k`
BT_DROP_END  = BT_DROP_K + BT_ENEMIES_MAX
.assert BT_DROP_END <= $7A00, error, "what the enemies dropped overflows its range"

; --- experience in the menu --------------------------------------------------
;
; $7E7A40 to $7E7A4F, reserved on 2026-09-28: the thirteen letters of the
; experience line of a party row, which `menu_exp_paint` builds before
; turning them into sprites. It lives as long as that routine.
MENU_EXP_TEXT = $7E7A40
MENU_EXP_TEXT_END = $7E7A50

; --- the MSU-1 tracks that were missing --------------------------------------
;
; $7E7820 to $7E782F, reserved on 2026-09-26: one bit per song, set when the
; song had a track and the MSU-1 could not play it —it was not on the card,
; or it did not finish opening it in time— and it played through the SPC700.
; See `song_per_msu` in paquete_de_audio.s. `msu_detect` clears it on
; reset; it does not travel in the save, because what it says is about the
; card and not about the game.
MSU_MISSING      = $7E7820
MSU_MISSING_BYTES = 16
LZ2_BUFFER     = $7F0000
ANIM_DRAWINGS   = $7F6000
ANIM_DRAWINGS_END = $7F8000

; --- sound effects with MSU-1 ------------------------------------------------
;
; $7E78B0 to $7E78CF, reserved on 2026-09-26. See `efectos_con_msu.s`: voices
; 0 to 5 when the SPC700 is not playing music, and the `.msu`'s quality sound
; effects. `se_clear` zeroes it, on reset; it does not travel in the save.
EX_FRAMES  = $7E78B0           ; six words: how many frames the sound effect
                                ; on each voice has left, from 0 to 5
EX_IDX      = $7E78BC           ; six words: its row in `sonido_tabla`
EX_PEND     = $7E78C8           ; one bit per voice: the sound effect has not started yet
EX_BUSY     = $7E78C9           ; one bit per voice: it belongs to a sound effect
                                ; —pending, playing or being handed back— and
                                ; not to the music
EX_RETURN = $7E78CA           ; one bit per voice: it finished, and next frame
                                ; it is handed back to the music
MSU_SE      = $7E78CB           ; 0 not checked, 1 the `.msu` is this
                                ; cartridge's, 2 it is not or there is no MSU-1
MSU_SE_NEXT  = $7E78CC           ; three bytes: where the `.msu` stream was left
EX_END      = $7E78CF
.assert EX_END <= $7E78D0, error, "the MSU-1 sound effects overflow their range"

; --- which sound effect is in each directory place ---------------------------
;
; $7E78D0 to $7E78FF, reserved on 2026-09-26: one byte for each of the
; SE_LUGARES of the SPC700 directory that the sound effects share, with the
; number of the sound effect recorded there, or $FF. Several sound effects go
; to the same place —the ones that are never in the same package: see
; `lugares_de_efectos` in tools/audio/snes_music.py— and the directory does
; not say which one is there. See `record_effect` in paquete_de_audio.s.
; `aram_clear` sets it to $FF; it does not travel in the save.
FAR_EFFECT_IN = $7E78D0
.assert FAR_EFFECT_IN + SE_LUGARES <= $7E7900, error, "the sound effect places do not fit in FAR_EFFECT_IN: see SE_LUGARES_MAX in snes_music.py"

; --- the battle transition ---------------------------------------------------
;
; $7E7840 to $7E784F, reserved on 2026-09-26. See `fundido_de_pelea.s`.
BATTLE_ON = $7E7840        ; 1 if the battle got to turn its screen on

; --- the teleport transition ------------------------------------------------
;
; $7E7920 to $7E793F, reserved on 2026-09-27: the transition with which the
; teleport erases the screen and the one with which it shows it again, which
; `ChangeScreenTransitions` changes —`op_transition`— and `fade_mosaic`
; and `fade_from` read: TRANSICION_MOSAICO, TRANSICION_CORTE (only for
; erasing), or anything else for the fade.
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
TRANSITION_ERASE  = $7E7920
TRANSITION_SHOW = $7E7921

; --- the memorized song -------------------------------------------------------
;
; $7E7940 to $7E795F, reserved on 2026-09-27. `MemorizeBGM` records here
; which song was playing —its index in `Temas`, or $FF if none— and
; `PlayMemorizedBGM` plays it again: see `op_memorized_bgm`. Reset leaves it
; at $FF.
;
; **It does not travel in the save**, and in RM2k it does (`memorized_bgm`,
; in the system part). The two commands always go together in the same
; autorun page —the game's four tutorials, 58 and 162 to 164—, with no menu
; in between, so there is nowhere to save between one and the other.
REMEMBERED_SONG = $7E7940

; --- the weapons' SP, and the target of multi-target skills -----------------
;
; $7E7960 to $7E797F, reserved on 2026-09-27 for Lashe City milestone 4.
; `bt_build` builds it at the start of each battle, so it does not travel in
; the save and there is no need to set it on reset.
BT_WEAPON_SP = $7E7960            ; BT_PARTY_MAX bytes: what attacking costs
                                ; each party place, `batalla.sp_del_arma`
BT_SKILL_I   = $7E7964            ; which combatant a multi-target skill is on:
                                ; `bt_skill_use` calls `bt_skill_one` for each
                                ; one, and that one clobbers the `BA_S*`
.assert BT_SKILL_I < $7E7980, error, "milestone 4 overflows its range in far RAM"

; --- an NPC row, set aside ---------------------------------------------------
;
; $7E7980 to $7E799F, reserved on 2026-09-27 for the race's milestone 2.
; `fit_far` keeps here the row that changes place while it moves the
; others; it lasts as long as that routine.
NPC_ROW_SEPARATE = $7E7980           ; NPC_STRIDE bytes

; --- the Game Over screen ------------------------------------------------------
;
; $7E7A30 to $7E7A3F, reserved on 2026-09-28. See tools/runtime/game_over.s.
GO_LOSES  = $7E7A30            ; word: where losing the battle being fought
                                ; leads; $FFFF is Game Over
GO_WAIT  = $7E7A32            ; 1 while the screen waits for the button: it is
                                ; what the harness looks at, which has no other clock
GO_LEVEL   = $7E7A33            ; the fade's brightness
GO_FRAMES = $7E7A34            ; how many frames each fade level lasts

; --- the map grid, in WRAM --------------------------------------------------
;
; **$7E8000 to $7EFFFF belongs to the grid**, and it continues at $7F8000 if
; it goes past 32 KB: the upper half of the two banks, which has the shape of
; two consecutive LoROM banks —see `ptr_more`—. `lz2_grid` decompresses it
; when loading the map and everyone who asks about a cell reads it. Reserved
; on 2026-09-26, and it is a decision with a cost: it was half of the far RAM
; that was still free. What is lost, how it is reverted and what catches it,
; in workflow/decisiones/la-grilla-vive-en-la-wram.md;
; `test_reservas_de_la_wram.py` fails if another symbol lands inside.
;
; It shares the $7F half with `SCN_SCENE`: the battle overwrites it, and
; `back_from_battle` decompresses the whole grid again.
GRID      = $7E8000
GRID_END  = $7F0000
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
; It is sized for the startup map's package, and **the converter stops if it
; does not fit**: the estimate, on the high side, is `cuadros_del_arranque` in
; tools/audio/snes_music.py. Measured on 2026-09-26: `release`'s work ends on
; frame 30 and the estimate gives 34. It was 112 until that day, meant for
; uploading a full ARAM through the IPL; see
; workflow/decisiones/el-arranque-esta-dimensionado-para-el-paquete-de-arranque.md.
BOOT_FRAMES = 40
VIEW_ROWS = 29

; The message window: 256x80 flush with the bottom of a 224-line screen, that
; is, the ten cell rows going from 18 to 27. The same numbers are in
; `tools/port/window.py`, which is where they come from: 80 high and flush
; with the bottom, the way RM2k places it.
WINDOW_ROW  = 18
TEXT_WINDOW_ROWS = 10
WINDOW_LINE = WINDOW_ROW * 8        ; and in scanlines: 144
LINES = 224

; BG2's vertical scroll while the window is drawn. On the first scanline the
; PPU shows line `vofs + 1`, so for row 0 of its own tilemap to land on line
; 144 it takes `vofs + 1 + 144 = 0` modulo 256, which is the height of a
; 32x32 tilemap. Hence the 111. The horizontal one is zero.
WINDOW_VOFS = 111

; The 64x32 tilemap is two 32-wide screens side by side, and the second one
; does not live 32 words further on but 1024.
VIEW_COLS_TILEMAP = 32

