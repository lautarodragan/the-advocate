//! RPG Maker 2000's numbers: the event commands, the move route commands,
//! a page's triggers.
//!
//! They are liblcf's —`rpg::EventCommand::Code`, `rpg::MoveCommand::Code`—
//! and not written from memory: the test at the bottom holds each one to
//! the name Ditto's schema, generated from liblcf, gives that number. The
//! first door filter this port had wrote three of them by eye, and they
//! were wrong.

pub const END: i32 = 10;
pub const SHOW_MESSAGE: i32 = 10110;
pub const MESSAGE_OPTIONS: i32 = 10120;
pub const SHOW_CHOICE: i32 = 10140;
pub const CONTROL_SWITCHES: i32 = 10210;
pub const CONTROL_VARS: i32 = 10220;
pub const TIMER_OPERATION: i32 = 10230;
pub const CHANGE_GOLD: i32 = 10310;
pub const CHANGE_ITEMS: i32 = 10320;
pub const CHANGE_PARTY_MEMBERS: i32 = 10330;
pub const CHANGE_SKILLS: i32 = 10440;
pub const CHANGE_EQUIPMENT: i32 = 10450;
pub const CHANGE_HP: i32 = 10460;
pub const CHANGE_SP: i32 = 10470;
pub const CHANGE_CONDITION: i32 = 10480;
pub const FULL_HEAL: i32 = 10490;
pub const CHANGE_HERO_TITLE: i32 = 10620;
pub const CHANGE_SPRITE_ASSOCIATION: i32 = 10630;
pub const CHANGE_SYSTEM_BGM: i32 = 10660;
pub const CHANGE_SCREEN_TRANSITIONS: i32 = 10690;
pub const ENEMY_ENCOUNTER: i32 = 10710;
pub const OPEN_SHOP: i32 = 10720;
pub const SHOW_INN: i32 = 10730;
pub const TELEPORT: i32 = 10810;
pub const MEMORIZE_LOCATION: i32 = 10820;
pub const RECALL_TO_LOCATION: i32 = 10830;
pub const CHANGE_EVENT_LOCATION: i32 = 10860;
pub const TRADE_EVENT_LOCATIONS: i32 = 10870;
pub const STORE_TERRAIN_ID: i32 = 10910;
pub const TINT_SCREEN: i32 = 11030;
pub const FLASH_SCREEN: i32 = 11040;
pub const SHAKE_SCREEN: i32 = 11050;
pub const PAN_SCREEN: i32 = 11060;
pub const WEATHER_EFFECTS: i32 = 11070;
pub const SHOW_PICTURE: i32 = 11110;
pub const MOVE_PICTURE: i32 = 11120;
pub const ERASE_PICTURE: i32 = 11130;
pub const SHOW_BATTLE_ANIMATION: i32 = 11210;
pub const FLASH_SPRITE: i32 = 11320;
pub const MOVE_EVENT: i32 = 11330;
pub const PROCEED_WITH_MOVEMENT: i32 = 11340;
pub const HALT_ALL_MOVEMENT: i32 = 11350;
pub const WAIT: i32 = 11410;
pub const PLAY_BGM: i32 = 11510;
pub const FADE_OUT_BGM: i32 = 11520;
pub const MEMORIZE_BGM: i32 = 11530;
pub const PLAY_MEMORIZED_BGM: i32 = 11540;
pub const PLAY_SOUND: i32 = 11550;
pub const KEY_INPUT_PROC: i32 = 11610;
pub const CHANGE_PBG: i32 = 11720;
pub const CHANGE_ENCOUNTER_STEPS: i32 = 11740;
pub const TILE_SUBSTITUTION: i32 = 11750;
pub const CHANGE_ESCAPE_ACCESS: i32 = 11840;
pub const OPEN_SAVE_MENU: i32 = 11910;
pub const CHANGE_SAVE_ACCESS: i32 = 11930;
pub const CHANGE_MENU_ACCESS: i32 = 11960;
pub const COND_BRANCH: i32 = 12010;
pub const LABEL: i32 = 12110;
pub const JUMP_TO_LABEL: i32 = 12120;
pub const LOOP: i32 = 12210;
pub const BREAK_LOOP: i32 = 12220;
pub const END_EVENT_PROCESSING: i32 = 12310;
pub const CALL_EVENT: i32 = 12330;
pub const COMMENT: i32 = 12410;
pub const GAME_OVER: i32 = 12420;
pub const RETURN_TO_TITLE: i32 = 12510;
pub const CHANGE_MONSTER_HP: i32 = 13110;
pub const CHANGE_MONSTER_MP: i32 = 13120;
pub const SHOW_HIDDEN_MONSTER: i32 = 13150;
pub const CHANGE_BATTLE_BG: i32 = 13210;
pub const BATTLE_COND_BRANCH: i32 = 13310;
pub const SHOW_MESSAGE_2: i32 = 20110;
pub const SHOW_CHOICE_OPTION: i32 = 20140;
pub const SHOW_CHOICE_END: i32 = 20141;
pub const VICTORY_HANDLER: i32 = 20710;
pub const ESCAPE_HANDLER: i32 = 20711;
pub const DEFEAT_HANDLER: i32 = 20712;
pub const END_BATTLE: i32 = 20713;
pub const INN_STAY: i32 = 20730;
pub const INN_NO_STAY: i32 = 20731;
pub const INN_END: i32 = 20732;
pub const COND_ELSE: i32 = 22010;
pub const COND_END: i32 = 22011;
pub const END_LOOP: i32 = 22210;
pub const COMMENT_2: i32 = 22410;
pub const BATTLE_COND_ELSE: i32 = 23310;
pub const BATTLE_COND_END: i32 = 23311;

// --- the move route commands, `rpg::MoveCommand::Code` ----------------------

pub const ROUTE_TOWARD_HERO: i32 = 9;
pub const ROUTE_FACE_HERO: i32 = 21;
pub const ROUTE_WAIT: i32 = 23;
pub const ROUTE_JUMP_START: i32 = 24;
pub const ROUTE_JUMP_END: i32 = 25;
pub const ROUTE_LOCK_DIR: i32 = 26;
pub const ROUTE_UNLOCK_DIR: i32 = 27;
pub const ROUTE_SPEED_UP: i32 = 28;
pub const ROUTE_SPEED_DOWN: i32 = 29;
pub const ROUTE_FREQ_UP: i32 = 30;
pub const ROUTE_FREQ_DOWN: i32 = 31;
pub const ROUTE_SWITCH_ON: i32 = 32;
pub const ROUTE_SWITCH_OFF: i32 = 33;
pub const ROUTE_CHANGE_GRAPHIC: i32 = 34;
pub const ROUTE_SOUND: i32 = 35;
pub const ROUTE_THROUGH_ON: i32 = 36;
pub const ROUTE_THROUGH_OFF: i32 = 37;
pub const ROUTE_ANIM_STOP: i32 = 38;
pub const ROUTE_ANIM_RESUME: i32 = 39;
/// Raising and lowering the transparency by an eighth.
pub const ROUTE_TRANSPARENCY: [i32; 2] = [40, 41];

// --- a page, `rpg::EventPage` ------------------------------------------------

pub const TRIGGER_ACTION: i32 = 0;
pub const TRIGGER_TOUCH_HERO: i32 = 1;
pub const TRIGGER_AUTOSTART: i32 = 3;
pub const TRIGGER_PARALLEL: i32 = 4;
/// The hero's layer: `Layers_same`.
pub const LAYER_SAME: i32 = 1;
/// `MoveType_custom`: the page walks a route of its own.
pub const MOVE_CUSTOM: i32 = 6;
/// The `AnimType`s.
pub const ANIM_CONTINUOUS: i32 = 1;
pub const ANIM_FIXED_NOT_CONTINUOUS: i32 = 2;
pub const ANIM_FIXED_CONTINUOUS: i32 = 3;
pub const ANIM_FIXED_GRAPHIC: i32 = 4;
pub const ANIM_SPIN: i32 = 5;
/// The `rpg::CommonEvent` trigger that runs in parallel.
pub const COMMON_PARALLEL: i32 = 4;

#[cfg(test)]
mod tests {
    use super::*;
    use ditto::schema::{EventCommandCode as C, MoveCommandCode as M};

    #[test]
    fn every_command_code_is_the_one_liblcf_gives_its_name() {
        for (ours, theirs) in [
            (END, C::END),
            (SHOW_MESSAGE, C::ShowMessage),
            (MESSAGE_OPTIONS, C::MessageOptions),
            (SHOW_CHOICE, C::ShowChoice),
            (CONTROL_SWITCHES, C::ControlSwitches),
            (CONTROL_VARS, C::ControlVars),
            (TIMER_OPERATION, C::TimerOperation),
            (CHANGE_GOLD, C::ChangeGold),
            (CHANGE_ITEMS, C::ChangeItems),
            (CHANGE_PARTY_MEMBERS, C::ChangePartyMembers),
            (CHANGE_SKILLS, C::ChangeSkills),
            (CHANGE_EQUIPMENT, C::ChangeEquipment),
            (CHANGE_HP, C::ChangeHP),
            (CHANGE_SP, C::ChangeSP),
            (CHANGE_CONDITION, C::ChangeCondition),
            (FULL_HEAL, C::FullHeal),
            (CHANGE_HERO_TITLE, C::ChangeHeroTitle),
            (CHANGE_SPRITE_ASSOCIATION, C::ChangeSpriteAssociation),
            (CHANGE_SYSTEM_BGM, C::ChangeSystemBGM),
            (CHANGE_SCREEN_TRANSITIONS, C::ChangeScreenTransitions),
            (ENEMY_ENCOUNTER, C::EnemyEncounter),
            (OPEN_SHOP, C::OpenShop),
            (SHOW_INN, C::ShowInn),
            (TELEPORT, C::Teleport),
            (MEMORIZE_LOCATION, C::MemorizeLocation),
            (RECALL_TO_LOCATION, C::RecallToLocation),
            (CHANGE_EVENT_LOCATION, C::ChangeEventLocation),
            (TRADE_EVENT_LOCATIONS, C::TradeEventLocations),
            (STORE_TERRAIN_ID, C::StoreTerrainID),
            (TINT_SCREEN, C::TintScreen),
            (FLASH_SCREEN, C::FlashScreen),
            (SHAKE_SCREEN, C::ShakeScreen),
            (PAN_SCREEN, C::PanScreen),
            (WEATHER_EFFECTS, C::WeatherEffects),
            (SHOW_PICTURE, C::ShowPicture),
            (MOVE_PICTURE, C::MovePicture),
            (ERASE_PICTURE, C::ErasePicture),
            (SHOW_BATTLE_ANIMATION, C::ShowBattleAnimation),
            (FLASH_SPRITE, C::FlashSprite),
            (MOVE_EVENT, C::MoveEvent),
            (PROCEED_WITH_MOVEMENT, C::ProceedWithMovement),
            (HALT_ALL_MOVEMENT, C::HaltAllMovement),
            (WAIT, C::Wait),
            (PLAY_BGM, C::PlayBGM),
            (FADE_OUT_BGM, C::FadeOutBGM),
            (MEMORIZE_BGM, C::MemorizeBGM),
            (PLAY_MEMORIZED_BGM, C::PlayMemorizedBGM),
            (PLAY_SOUND, C::PlaySound),
            (KEY_INPUT_PROC, C::KeyInputProc),
            (CHANGE_PBG, C::ChangePBG),
            (CHANGE_ENCOUNTER_STEPS, C::ChangeEncounterSteps),
            (TILE_SUBSTITUTION, C::TileSubstitution),
            (CHANGE_ESCAPE_ACCESS, C::ChangeEscapeAccess),
            (OPEN_SAVE_MENU, C::OpenSaveMenu),
            (CHANGE_SAVE_ACCESS, C::ChangeSaveAccess),
            (CHANGE_MENU_ACCESS, C::ChangeMainMenuAccess),
            (COND_BRANCH, C::ConditionalBranch),
            (LABEL, C::Label),
            (JUMP_TO_LABEL, C::JumpToLabel),
            (LOOP, C::Loop),
            (BREAK_LOOP, C::BreakLoop),
            (END_EVENT_PROCESSING, C::EndEventProcessing),
            (CALL_EVENT, C::CallEvent),
            (COMMENT, C::Comment),
            (GAME_OVER, C::GameOver),
            (RETURN_TO_TITLE, C::ReturntoTitleScreen),
            (CHANGE_MONSTER_HP, C::ChangeMonsterHP),
            (CHANGE_MONSTER_MP, C::ChangeMonsterMP),
            (SHOW_HIDDEN_MONSTER, C::ShowHiddenMonster),
            (CHANGE_BATTLE_BG, C::ChangeBattleBG),
            (BATTLE_COND_BRANCH, C::ConditionalBranchB),
            (SHOW_MESSAGE_2, C::ShowMessage2),
            (SHOW_CHOICE_OPTION, C::ShowChoiceOption),
            (SHOW_CHOICE_END, C::ShowChoiceEnd),
            (VICTORY_HANDLER, C::VictoryHandler),
            (ESCAPE_HANDLER, C::EscapeHandler),
            (DEFEAT_HANDLER, C::DefeatHandler),
            (END_BATTLE, C::EndBattle),
            (INN_STAY, C::Stay),
            (INN_NO_STAY, C::NoStay),
            (INN_END, C::EndInn),
            (COND_ELSE, C::ElseBranch),
            (COND_END, C::EndBranch),
            (END_LOOP, C::EndLoop),
            (COMMENT_2, C::Comment2),
            (BATTLE_COND_ELSE, C::ElseBranchB),
            (BATTLE_COND_END, C::EndBranchB),
        ] {
            assert_eq!(ours, theirs.to_i32(), "{theirs:?}");
        }
    }

    #[test]
    fn every_route_code_is_the_one_liblcf_gives_its_name() {
        for (ours, theirs) in [
            (ROUTE_TOWARD_HERO, M::MoveTowardsHero),
            (ROUTE_FACE_HERO, M::FaceHero),
            (ROUTE_WAIT, M::Wait),
            (ROUTE_JUMP_START, M::BeginJump),
            (ROUTE_JUMP_END, M::EndJump),
            (ROUTE_LOCK_DIR, M::LockFacing),
            (ROUTE_UNLOCK_DIR, M::UnlockFacing),
            (ROUTE_SPEED_UP, M::IncreaseMovementSpeed),
            (ROUTE_SPEED_DOWN, M::DecreaseMovementSpeed),
            (ROUTE_FREQ_UP, M::IncreaseMovementFrequence),
            (ROUTE_FREQ_DOWN, M::DecreaseMovementFrequence),
            (ROUTE_SWITCH_ON, M::SwitchOn),
            (ROUTE_SWITCH_OFF, M::SwitchOff),
            (ROUTE_CHANGE_GRAPHIC, M::ChangeGraphic),
            (ROUTE_SOUND, M::PlaySoundEffect),
            (ROUTE_THROUGH_ON, M::WalkEverywhereOn),
            (ROUTE_THROUGH_OFF, M::WalkEverywhereOff),
            (ROUTE_ANIM_STOP, M::StopAnimation),
            (ROUTE_ANIM_RESUME, M::StartAnimation),
            (ROUTE_TRANSPARENCY[0], M::IncreaseTransp),
            (ROUTE_TRANSPARENCY[1], M::DecreaseTransp),
        ] {
            assert_eq!(ours, theirs.to_i32(), "{theirs:?}");
        }
    }
}
