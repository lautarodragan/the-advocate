//! El esquema de los archivos de RPG Maker 2000.
//!
//! **Generado por `cargo xtask generar`, y commiteado a propósito.**
//! No se edita a mano: lo que se edita es el generador o el CSV de
//! arriba. Ver `xtask/src/main.rs` para el porqué.
//!
//! Sale de las tablas de liblcf (/extras/ref/liblcf), que es de donde el ecosistema
//! entero saca los nombres: en el binario no hay ninguno, sólo
//! índices de campo.

#![allow(dead_code)]

use serde::{Deserialize, Serialize};

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AnimationPosition {
    #[serde(rename = "up")]
    Up = 0,
    #[serde(rename = "middle")]
    Middle = 1,
    #[serde(rename = "down")]
    Down = 2,
}

impl Default for AnimationPosition {
    fn default() -> Self { AnimationPosition::Up }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AnimationScope {
    #[serde(rename = "target")]
    Target = 0,
    #[serde(rename = "screen")]
    Screen = 1,
}

impl Default for AnimationScope {
    fn default() -> Self { AnimationScope::Target }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AnimationTimingFlashScope {
    #[serde(rename = "nothing")]
    Nothing = 0,
    #[serde(rename = "target")]
    Target = 1,
    #[serde(rename = "screen")]
    Screen = 2,
}

impl Default for AnimationTimingFlashScope {
    fn default() -> Self { AnimationTimingFlashScope::Nothing }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AnimationTimingScreenShake {
    #[serde(rename = "nothing")]
    Nothing = 0,
    #[serde(rename = "target")]
    Target = 1,
    #[serde(rename = "screen")]
    Screen = 2,
}

impl Default for AnimationTimingScreenShake {
    fn default() -> Self { AnimationTimingScreenShake::Nothing }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AttributeType {
    #[serde(rename = "physical")]
    Physical = 0,
    #[serde(rename = "magical")]
    Magical = 1,
}

impl Default for AttributeType {
    fn default() -> Self { AttributeType::Physical }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandType {
    #[serde(rename = "attack")]
    Attack = 0,
    #[serde(rename = "skill")]
    Skill = 1,
    #[serde(rename = "subskill")]
    Subskill = 2,
    #[serde(rename = "defense")]
    Defense = 3,
    #[serde(rename = "item")]
    Item = 4,
    #[serde(rename = "escape")]
    Escape = 5,
    #[serde(rename = "special")]
    Special = 6,
}

impl Default for BattleCommandType {
    fn default() -> Self { BattleCommandType::Attack }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandsBattleType {
    #[serde(rename = "traditional")]
    Traditional = 0,
    #[serde(rename = "alternative")]
    Alternative = 1,
    #[serde(rename = "gauge")]
    Gauge = 2,
}

impl Default for BattleCommandsBattleType {
    fn default() -> Self { BattleCommandsBattleType::Traditional }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandsFacing {
    #[serde(rename = "retain")]
    Retain = 0,
    #[serde(rename = "up")]
    Up = 1,
    #[serde(rename = "right")]
    Right = 2,
    #[serde(rename = "down")]
    Down = 3,
    #[serde(rename = "left")]
    Left = 4,
}

impl Default for BattleCommandsFacing {
    fn default() -> Self { BattleCommandsFacing::Retain }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandsPlacement {
    #[serde(rename = "manual")]
    Manual = 0,
    #[serde(rename = "automatic")]
    Automatic = 1,
}

impl Default for BattleCommandsPlacement {
    fn default() -> Self { BattleCommandsPlacement::Manual }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandsRowShown {
    #[serde(rename = "front")]
    Front = 0,
    #[serde(rename = "back")]
    Back = 1,
}

impl Default for BattleCommandsRowShown {
    fn default() -> Self { BattleCommandsRowShown::Front }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandsTransparency {
    #[serde(rename = "opaque")]
    Opaque = 0,
    #[serde(rename = "transparent")]
    Transparent = 1,
}

impl Default for BattleCommandsTransparency {
    fn default() -> Self { BattleCommandsTransparency::Opaque }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandsWindowSize {
    #[serde(rename = "large")]
    Large = 0,
    #[serde(rename = "small")]
    Small = 1,
}

impl Default for BattleCommandsWindowSize {
    fn default() -> Self { BattleCommandsWindowSize::Large }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationItemSkillAfterimage {
    #[serde(rename = "none")]
    None = 0,
    #[serde(rename = "add")]
    Add = 1,
}

impl Default for BattlerAnimationItemSkillAfterimage {
    fn default() -> Self { BattlerAnimationItemSkillAfterimage::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationItemSkillAnimType {
    #[serde(rename = "weapon")]
    Weapon = 0,
    #[serde(rename = "battle")]
    Battle = 1,
}

impl Default for BattlerAnimationItemSkillAnimType {
    fn default() -> Self { BattlerAnimationItemSkillAnimType::Weapon }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationItemSkillMovement {
    #[serde(rename = "none")]
    None = 0,
    #[serde(rename = "step")]
    Step = 1,
    #[serde(rename = "jump")]
    Jump = 2,
    #[serde(rename = "move")]
    Move = 3,
}

impl Default for BattlerAnimationItemSkillMovement {
    fn default() -> Self { BattlerAnimationItemSkillMovement::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationItemSkillSpeed {
    #[serde(rename = "fast")]
    Fast = 0,
    #[serde(rename = "medium")]
    Medium = 1,
    #[serde(rename = "slow")]
    Slow = 2,
}

impl Default for BattlerAnimationItemSkillSpeed {
    fn default() -> Self { BattlerAnimationItemSkillSpeed::Fast }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationPose {
    #[serde(rename = "Idle")]
    Idle = 0,
    #[serde(rename = "AttackRight")]
    AttackRight = 1,
    #[serde(rename = "AttackLeft")]
    AttackLeft = 2,
    #[serde(rename = "Skill")]
    Skill = 3,
    #[serde(rename = "Dead")]
    Dead = 4,
    #[serde(rename = "Damage")]
    Damage = 5,
    #[serde(rename = "Dazed")]
    Dazed = 6,
    #[serde(rename = "Defend")]
    Defend = 7,
    #[serde(rename = "WalkLeft")]
    WalkLeft = 8,
    #[serde(rename = "WalkRight")]
    WalkRight = 9,
    #[serde(rename = "Victory")]
    Victory = 10,
    #[serde(rename = "Item")]
    Item = 11,
}

impl Default for BattlerAnimationPose {
    fn default() -> Self { BattlerAnimationPose::Idle }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationPoseAnimType {
    #[serde(rename = "character")]
    Character = 0,
    #[serde(rename = "battle")]
    Battle = 1,
}

impl Default for BattlerAnimationPoseAnimType {
    fn default() -> Self { BattlerAnimationPoseAnimType::Character }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationSpeed {
    #[serde(rename = "slow")]
    Slow = 20,
    #[serde(rename = "medium")]
    Medium = 14,
    #[serde(rename = "fast")]
    Fast = 8,
}

impl Default for BattlerAnimationSpeed {
    fn default() -> Self { BattlerAnimationSpeed::Slow }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ChipsetAnimType {
    #[serde(rename = "reciprocating")]
    Reciprocating = 0,
    #[serde(rename = "cyclic")]
    Cyclic = 1,
}

impl Default for ChipsetAnimType {
    fn default() -> Self { ChipsetAnimType::Reciprocating }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CommonEventTrigger {
    #[serde(rename = "automatic")]
    Automatic = 3,
    #[serde(rename = "parallel")]
    Parallel = 4,
    #[serde(rename = "call")]
    Call = 5,
}

impl Default for CommonEventTrigger {
    fn default() -> Self { CommonEventTrigger::Automatic }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EnemyActionBasic {
    #[serde(rename = "attack")]
    Attack = 0,
    #[serde(rename = "dual_attack")]
    DualAttack = 1,
    #[serde(rename = "defense")]
    Defense = 2,
    #[serde(rename = "observe")]
    Observe = 3,
    #[serde(rename = "charge")]
    Charge = 4,
    #[serde(rename = "autodestruction")]
    Autodestruction = 5,
    #[serde(rename = "escape")]
    Escape = 6,
    #[serde(rename = "nothing")]
    Nothing = 7,
}

impl Default for EnemyActionBasic {
    fn default() -> Self { EnemyActionBasic::Attack }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EnemyActionConditionType {
    #[serde(rename = "always")]
    Always = 0,
    #[serde(rename = "switch")]
    Switch = 1,
    #[serde(rename = "turn")]
    Turn = 2,
    #[serde(rename = "actors")]
    Actors = 3,
    #[serde(rename = "hp")]
    Hp = 4,
    #[serde(rename = "sp")]
    Sp = 5,
    #[serde(rename = "party_lvl")]
    PartyLvl = 6,
    #[serde(rename = "party_fatigue")]
    PartyFatigue = 7,
}

impl Default for EnemyActionConditionType {
    fn default() -> Self { EnemyActionConditionType::Always }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EnemyActionKind {
    #[serde(rename = "basic")]
    Basic = 0,
    #[serde(rename = "skill")]
    Skill = 1,
    #[serde(rename = "transformation")]
    Transformation = 2,
}

impl Default for EnemyActionKind {
    fn default() -> Self { EnemyActionKind::Basic }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventCommandCode {
    #[serde(rename = "END")]
    END = 10,
    #[serde(rename = "CallCommonEvent")]
    CallCommonEvent = 1005,
    #[serde(rename = "ForceFlee")]
    ForceFlee = 1006,
    #[serde(rename = "EnableCombo")]
    EnableCombo = 1007,
    #[serde(rename = "ChangeClass")]
    ChangeClass = 1008,
    #[serde(rename = "ChangeBattleCommands")]
    ChangeBattleCommands = 1009,
    #[serde(rename = "OpenLoadMenu")]
    OpenLoadMenu = 5001,
    #[serde(rename = "ExitGame")]
    ExitGame = 5002,
    #[serde(rename = "ToggleAtbMode")]
    ToggleAtbMode = 5003,
    #[serde(rename = "ToggleFullscreen")]
    ToggleFullscreen = 5004,
    #[serde(rename = "OpenVideoOptions")]
    OpenVideoOptions = 5005,
    #[serde(rename = "ShowMessage")]
    ShowMessage = 10110,
    #[serde(rename = "MessageOptions")]
    MessageOptions = 10120,
    #[serde(rename = "ChangeFaceGraphic")]
    ChangeFaceGraphic = 10130,
    #[serde(rename = "ShowChoice")]
    ShowChoice = 10140,
    #[serde(rename = "InputNumber")]
    InputNumber = 10150,
    #[serde(rename = "ControlSwitches")]
    ControlSwitches = 10210,
    #[serde(rename = "ControlVars")]
    ControlVars = 10220,
    #[serde(rename = "TimerOperation")]
    TimerOperation = 10230,
    #[serde(rename = "ChangeGold")]
    ChangeGold = 10310,
    #[serde(rename = "ChangeItems")]
    ChangeItems = 10320,
    #[serde(rename = "ChangePartyMembers")]
    ChangePartyMembers = 10330,
    #[serde(rename = "ChangeExp")]
    ChangeExp = 10410,
    #[serde(rename = "ChangeLevel")]
    ChangeLevel = 10420,
    #[serde(rename = "ChangeParameters")]
    ChangeParameters = 10430,
    #[serde(rename = "ChangeSkills")]
    ChangeSkills = 10440,
    #[serde(rename = "ChangeEquipment")]
    ChangeEquipment = 10450,
    #[serde(rename = "ChangeHP")]
    ChangeHP = 10460,
    #[serde(rename = "ChangeSP")]
    ChangeSP = 10470,
    #[serde(rename = "ChangeCondition")]
    ChangeCondition = 10480,
    #[serde(rename = "FullHeal")]
    FullHeal = 10490,
    #[serde(rename = "SimulatedAttack")]
    SimulatedAttack = 10500,
    #[serde(rename = "ChangeHeroName")]
    ChangeHeroName = 10610,
    #[serde(rename = "ChangeHeroTitle")]
    ChangeHeroTitle = 10620,
    #[serde(rename = "ChangeSpriteAssociation")]
    ChangeSpriteAssociation = 10630,
    #[serde(rename = "ChangeActorFace")]
    ChangeActorFace = 10640,
    #[serde(rename = "ChangeVehicleGraphic")]
    ChangeVehicleGraphic = 10650,
    #[serde(rename = "ChangeSystemBGM")]
    ChangeSystemBGM = 10660,
    #[serde(rename = "ChangeSystemSFX")]
    ChangeSystemSFX = 10670,
    #[serde(rename = "ChangeSystemGraphics")]
    ChangeSystemGraphics = 10680,
    #[serde(rename = "ChangeScreenTransitions")]
    ChangeScreenTransitions = 10690,
    #[serde(rename = "EnemyEncounter")]
    EnemyEncounter = 10710,
    #[serde(rename = "OpenShop")]
    OpenShop = 10720,
    #[serde(rename = "ShowInn")]
    ShowInn = 10730,
    #[serde(rename = "EnterHeroName")]
    EnterHeroName = 10740,
    #[serde(rename = "Teleport")]
    Teleport = 10810,
    #[serde(rename = "MemorizeLocation")]
    MemorizeLocation = 10820,
    #[serde(rename = "RecallToLocation")]
    RecallToLocation = 10830,
    #[serde(rename = "EnterExitVehicle")]
    EnterExitVehicle = 10840,
    #[serde(rename = "SetVehicleLocation")]
    SetVehicleLocation = 10850,
    #[serde(rename = "ChangeEventLocation")]
    ChangeEventLocation = 10860,
    #[serde(rename = "TradeEventLocations")]
    TradeEventLocations = 10870,
    #[serde(rename = "StoreTerrainID")]
    StoreTerrainID = 10910,
    #[serde(rename = "StoreEventID")]
    StoreEventID = 10920,
    #[serde(rename = "EraseScreen")]
    EraseScreen = 11010,
    #[serde(rename = "ShowScreen")]
    ShowScreen = 11020,
    #[serde(rename = "TintScreen")]
    TintScreen = 11030,
    #[serde(rename = "FlashScreen")]
    FlashScreen = 11040,
    #[serde(rename = "ShakeScreen")]
    ShakeScreen = 11050,
    #[serde(rename = "PanScreen")]
    PanScreen = 11060,
    #[serde(rename = "WeatherEffects")]
    WeatherEffects = 11070,
    #[serde(rename = "ShowPicture")]
    ShowPicture = 11110,
    #[serde(rename = "MovePicture")]
    MovePicture = 11120,
    #[serde(rename = "ErasePicture")]
    ErasePicture = 11130,
    #[serde(rename = "ShowBattleAnimation")]
    ShowBattleAnimation = 11210,
    #[serde(rename = "PlayerVisibility")]
    PlayerVisibility = 11310,
    #[serde(rename = "FlashSprite")]
    FlashSprite = 11320,
    #[serde(rename = "MoveEvent")]
    MoveEvent = 11330,
    #[serde(rename = "ProceedWithMovement")]
    ProceedWithMovement = 11340,
    #[serde(rename = "HaltAllMovement")]
    HaltAllMovement = 11350,
    #[serde(rename = "Wait")]
    Wait = 11410,
    #[serde(rename = "PlayBGM")]
    PlayBGM = 11510,
    #[serde(rename = "FadeOutBGM")]
    FadeOutBGM = 11520,
    #[serde(rename = "MemorizeBGM")]
    MemorizeBGM = 11530,
    #[serde(rename = "PlayMemorizedBGM")]
    PlayMemorizedBGM = 11540,
    #[serde(rename = "PlaySound")]
    PlaySound = 11550,
    #[serde(rename = "PlayMovie")]
    PlayMovie = 11560,
    #[serde(rename = "KeyInputProc")]
    KeyInputProc = 11610,
    #[serde(rename = "ChangeMapTileset")]
    ChangeMapTileset = 11710,
    #[serde(rename = "ChangePBG")]
    ChangePBG = 11720,
    #[serde(rename = "ChangeEncounterSteps")]
    ChangeEncounterSteps = 11740,
    #[serde(rename = "TileSubstitution")]
    TileSubstitution = 11750,
    #[serde(rename = "TeleportTargets")]
    TeleportTargets = 11810,
    #[serde(rename = "ChangeTeleportAccess")]
    ChangeTeleportAccess = 11820,
    #[serde(rename = "EscapeTarget")]
    EscapeTarget = 11830,
    #[serde(rename = "ChangeEscapeAccess")]
    ChangeEscapeAccess = 11840,
    #[serde(rename = "OpenSaveMenu")]
    OpenSaveMenu = 11910,
    #[serde(rename = "ChangeSaveAccess")]
    ChangeSaveAccess = 11930,
    #[serde(rename = "OpenMainMenu")]
    OpenMainMenu = 11950,
    #[serde(rename = "ChangeMainMenuAccess")]
    ChangeMainMenuAccess = 11960,
    #[serde(rename = "ConditionalBranch")]
    ConditionalBranch = 12010,
    #[serde(rename = "Label")]
    Label = 12110,
    #[serde(rename = "JumpToLabel")]
    JumpToLabel = 12120,
    #[serde(rename = "Loop")]
    Loop = 12210,
    #[serde(rename = "BreakLoop")]
    BreakLoop = 12220,
    #[serde(rename = "EndEventProcessing")]
    EndEventProcessing = 12310,
    #[serde(rename = "EraseEvent")]
    EraseEvent = 12320,
    #[serde(rename = "CallEvent")]
    CallEvent = 12330,
    #[serde(rename = "Comment")]
    Comment = 12410,
    #[serde(rename = "GameOver")]
    GameOver = 12420,
    #[serde(rename = "ReturntoTitleScreen")]
    ReturntoTitleScreen = 12510,
    #[serde(rename = "ChangeMonsterHP")]
    ChangeMonsterHP = 13110,
    #[serde(rename = "ChangeMonsterMP")]
    ChangeMonsterMP = 13120,
    #[serde(rename = "ChangeMonsterCondition")]
    ChangeMonsterCondition = 13130,
    #[serde(rename = "ShowHiddenMonster")]
    ShowHiddenMonster = 13150,
    #[serde(rename = "ChangeBattleBG")]
    ChangeBattleBG = 13210,
    #[serde(rename = "ShowBattleAnimation_B")]
    ShowBattleAnimationB = 13260,
    #[serde(rename = "ConditionalBranch_B")]
    ConditionalBranchB = 13310,
    #[serde(rename = "TerminateBattle")]
    TerminateBattle = 13410,
    #[serde(rename = "ShowMessage_2")]
    ShowMessage2 = 20110,
    #[serde(rename = "ShowChoiceOption")]
    ShowChoiceOption = 20140,
    #[serde(rename = "ShowChoiceEnd")]
    ShowChoiceEnd = 20141,
    #[serde(rename = "VictoryHandler")]
    VictoryHandler = 20710,
    #[serde(rename = "EscapeHandler")]
    EscapeHandler = 20711,
    #[serde(rename = "DefeatHandler")]
    DefeatHandler = 20712,
    #[serde(rename = "EndBattle")]
    EndBattle = 20713,
    #[serde(rename = "Transaction")]
    Transaction = 20720,
    #[serde(rename = "NoTransaction")]
    NoTransaction = 20721,
    #[serde(rename = "EndShop")]
    EndShop = 20722,
    #[serde(rename = "Stay")]
    Stay = 20730,
    #[serde(rename = "NoStay")]
    NoStay = 20731,
    #[serde(rename = "EndInn")]
    EndInn = 20732,
    #[serde(rename = "ElseBranch")]
    ElseBranch = 22010,
    #[serde(rename = "EndBranch")]
    EndBranch = 22011,
    #[serde(rename = "EndLoop")]
    EndLoop = 22210,
    #[serde(rename = "Comment_2")]
    Comment2 = 22410,
    #[serde(rename = "ElseBranch_B")]
    ElseBranchB = 23310,
    #[serde(rename = "EndBranch_B")]
    EndBranchB = 23311,
}

impl Default for EventCommandCode {
    fn default() -> Self { EventCommandCode::END }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageAnimType {
    #[serde(rename = "non_continuous")]
    NonContinuous = 0,
    #[serde(rename = "continuous")]
    Continuous = 1,
    #[serde(rename = "fixed_non_continuous")]
    FixedNonContinuous = 2,
    #[serde(rename = "fixed_continuous")]
    FixedContinuous = 3,
    #[serde(rename = "fixed_graphic")]
    FixedGraphic = 4,
    #[serde(rename = "spin")]
    Spin = 5,
    #[serde(rename = "step_frame_fix")]
    StepFrameFix = 6,
}

impl Default for EventPageAnimType {
    fn default() -> Self { EventPageAnimType::NonContinuous }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageConditionComparison {
    #[serde(rename = "equal")]
    Equal = 0,
    #[serde(rename = "greater_equal")]
    GreaterEqual = 1,
    #[serde(rename = "less_equal")]
    LessEqual = 2,
    #[serde(rename = "greater")]
    Greater = 3,
    #[serde(rename = "less")]
    Less = 4,
    #[serde(rename = "not_equal")]
    NotEqual = 5,
}

impl Default for EventPageConditionComparison {
    fn default() -> Self { EventPageConditionComparison::Equal }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageDirection {
    #[serde(rename = "up")]
    Up = 0,
    #[serde(rename = "right")]
    Right = 1,
    #[serde(rename = "down")]
    Down = 2,
    #[serde(rename = "left")]
    Left = 3,
}

impl Default for EventPageDirection {
    fn default() -> Self { EventPageDirection::Up }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageFrame {
    #[serde(rename = "left")]
    Left = 0,
    #[serde(rename = "middle")]
    Middle = 1,
    #[serde(rename = "right")]
    Right = 2,
    #[serde(rename = "middle2")]
    Middle2 = 3,
}

impl Default for EventPageFrame {
    fn default() -> Self { EventPageFrame::Left }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageLayers {
    #[serde(rename = "below")]
    Below = 0,
    #[serde(rename = "same")]
    Same = 1,
    #[serde(rename = "above")]
    Above = 2,
}

impl Default for EventPageLayers {
    fn default() -> Self { EventPageLayers::Below }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageMoveSpeed {
    #[serde(rename = "eighth")]
    Eighth = 1,
    #[serde(rename = "quarter")]
    Quarter = 2,
    #[serde(rename = "half")]
    Half = 3,
    #[serde(rename = "normal")]
    Normal = 4,
    #[serde(rename = "double")]
    Double = 5,
    #[serde(rename = "fourfold")]
    Fourfold = 6,
}

impl Default for EventPageMoveSpeed {
    fn default() -> Self { EventPageMoveSpeed::Eighth }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageMoveType {
    #[serde(rename = "stationary")]
    Stationary = 0,
    #[serde(rename = "random")]
    Random = 1,
    #[serde(rename = "vertical")]
    Vertical = 2,
    #[serde(rename = "horizontal")]
    Horizontal = 3,
    #[serde(rename = "toward")]
    Toward = 4,
    #[serde(rename = "away")]
    Away = 5,
    #[serde(rename = "custom")]
    Custom = 6,
}

impl Default for EventPageMoveType {
    fn default() -> Self { EventPageMoveType::Stationary }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageTrigger {
    #[serde(rename = "action")]
    Action = 0,
    #[serde(rename = "touched")]
    Touched = 1,
    #[serde(rename = "collision")]
    Collision = 2,
    #[serde(rename = "auto_start")]
    AutoStart = 3,
    #[serde(rename = "parallel")]
    Parallel = 4,
}

impl Default for EventPageTrigger {
    fn default() -> Self { EventPageTrigger::Action }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ItemTarget {
    #[serde(rename = "single")]
    Single = 0,
    #[serde(rename = "center")]
    Center = 1,
    #[serde(rename = "simultaneous")]
    Simultaneous = 2,
    #[serde(rename = "sequential")]
    Sequential = 3,
}

impl Default for ItemTarget {
    fn default() -> Self { ItemTarget::Single }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ItemTrajectory {
    #[serde(rename = "straight")]
    Straight = 0,
    #[serde(rename = "return")]
    Return = 1,
}

impl Default for ItemTrajectory {
    fn default() -> Self { ItemTrajectory::Straight }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ItemType {
    #[serde(rename = "normal")]
    Normal = 0,
    #[serde(rename = "weapon")]
    Weapon = 1,
    #[serde(rename = "shield")]
    Shield = 2,
    #[serde(rename = "armor")]
    Armor = 3,
    #[serde(rename = "helmet")]
    Helmet = 4,
    #[serde(rename = "accessory")]
    Accessory = 5,
    #[serde(rename = "medicine")]
    Medicine = 6,
    #[serde(rename = "book")]
    Book = 7,
    #[serde(rename = "material")]
    Material = 8,
    #[serde(rename = "special")]
    Special = 9,
    #[serde(rename = "switch")]
    Switch = 10,
}

impl Default for ItemType {
    fn default() -> Self { ItemType::Normal }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MapGeneratorMode {
    #[serde(rename = "single_passage")]
    SinglePassage = 0,
    #[serde(rename = "linked_rooms")]
    LinkedRooms = 1,
    #[serde(rename = "maze_passage")]
    MazePassage = 2,
    #[serde(rename = "open_room")]
    OpenRoom = 3,
}

impl Default for MapGeneratorMode {
    fn default() -> Self { MapGeneratorMode::SinglePassage }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MapGeneratorTiles {
    #[serde(rename = "one")]
    One = 0,
    #[serde(rename = "two")]
    Two = 1,
}

impl Default for MapGeneratorTiles {
    fn default() -> Self { MapGeneratorTiles::One }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MapInfoBGMType {
    #[serde(rename = "parent")]
    Parent = 0,
    #[serde(rename = "terrain")]
    Terrain = 1,
    #[serde(rename = "specific")]
    Specific = 2,
}

impl Default for MapInfoBGMType {
    fn default() -> Self { MapInfoBGMType::Parent }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MapInfoMusicType {
    #[serde(rename = "parent")]
    Parent = 0,
    #[serde(rename = "event")]
    Event = 1,
    #[serde(rename = "specific")]
    Specific = 2,
}

impl Default for MapInfoMusicType {
    fn default() -> Self { MapInfoMusicType::Parent }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MapInfoTriState {
    #[serde(rename = "parent")]
    Parent = 0,
    #[serde(rename = "allow")]
    Allow = 1,
    #[serde(rename = "forbid")]
    Forbid = 2,
}

impl Default for MapInfoTriState {
    fn default() -> Self { MapInfoTriState::Parent }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MapScrollType {
    #[serde(rename = "none")]
    None = 0,
    #[serde(rename = "vertical")]
    Vertical = 1,
    #[serde(rename = "horizontal")]
    Horizontal = 2,
    #[serde(rename = "both")]
    Both = 3,
}

impl Default for MapScrollType {
    fn default() -> Self { MapScrollType::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MoveCommandCode {
    #[serde(rename = "move_up")]
    MoveUp = 0,
    #[serde(rename = "move_right")]
    MoveRight = 1,
    #[serde(rename = "move_down")]
    MoveDown = 2,
    #[serde(rename = "move_left")]
    MoveLeft = 3,
    #[serde(rename = "move_upright")]
    MoveUpright = 4,
    #[serde(rename = "move_downright")]
    MoveDownright = 5,
    #[serde(rename = "move_downleft")]
    MoveDownleft = 6,
    #[serde(rename = "move_upleft")]
    MoveUpleft = 7,
    #[serde(rename = "move_random")]
    MoveRandom = 8,
    #[serde(rename = "move_towards_hero")]
    MoveTowardsHero = 9,
    #[serde(rename = "move_away_from_hero")]
    MoveAwayFromHero = 10,
    #[serde(rename = "move_forward")]
    MoveForward = 11,
    #[serde(rename = "face_up")]
    FaceUp = 12,
    #[serde(rename = "face_right")]
    FaceRight = 13,
    #[serde(rename = "face_down")]
    FaceDown = 14,
    #[serde(rename = "face_left")]
    FaceLeft = 15,
    #[serde(rename = "turn_90_degree_right")]
    Turn90DegreeRight = 16,
    #[serde(rename = "turn_90_degree_left")]
    Turn90DegreeLeft = 17,
    #[serde(rename = "turn_180_degree")]
    Turn180Degree = 18,
    #[serde(rename = "turn_90_degree_random")]
    Turn90DegreeRandom = 19,
    #[serde(rename = "face_random_direction")]
    FaceRandomDirection = 20,
    #[serde(rename = "face_hero")]
    FaceHero = 21,
    #[serde(rename = "face_away_from_hero")]
    FaceAwayFromHero = 22,
    #[serde(rename = "wait")]
    Wait = 23,
    #[serde(rename = "begin_jump")]
    BeginJump = 24,
    #[serde(rename = "end_jump")]
    EndJump = 25,
    #[serde(rename = "lock_facing")]
    LockFacing = 26,
    #[serde(rename = "unlock_facing")]
    UnlockFacing = 27,
    #[serde(rename = "increase_movement_speed")]
    IncreaseMovementSpeed = 28,
    #[serde(rename = "decrease_movement_speed")]
    DecreaseMovementSpeed = 29,
    #[serde(rename = "increase_movement_frequence")]
    IncreaseMovementFrequence = 30,
    #[serde(rename = "decrease_movement_frequence")]
    DecreaseMovementFrequence = 31,
    #[serde(rename = "switch_on")]
    SwitchOn = 32,
    #[serde(rename = "switch_off")]
    SwitchOff = 33,
    #[serde(rename = "change_graphic")]
    ChangeGraphic = 34,
    #[serde(rename = "play_sound_effect")]
    PlaySoundEffect = 35,
    #[serde(rename = "walk_everywhere_on")]
    WalkEverywhereOn = 36,
    #[serde(rename = "walk_everywhere_off")]
    WalkEverywhereOff = 37,
    #[serde(rename = "stop_animation")]
    StopAnimation = 38,
    #[serde(rename = "start_animation")]
    StartAnimation = 39,
    #[serde(rename = "increase_transp")]
    IncreaseTransp = 40,
    #[serde(rename = "decrease_transp")]
    DecreaseTransp = 41,
}

impl Default for MoveCommandCode {
    fn default() -> Self { MoveCommandCode::MoveUp }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SaveActorRowType {
    #[serde(rename = "front")]
    Front = 0,
    #[serde(rename = "back")]
    Back = 1,
}

impl Default for SaveActorRowType {
    fn default() -> Self { SaveActorRowType::Front }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SavePartyLocationPanState {
    #[serde(rename = "fixed")]
    Fixed = 0,
    #[serde(rename = "follow")]
    Follow = 1,
}

impl Default for SavePartyLocationPanState {
    fn default() -> Self { SavePartyLocationPanState::Fixed }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SavePartyLocationVehicleType {
    #[serde(rename = "none")]
    None = 0,
    #[serde(rename = "skiff")]
    Skiff = 1,
    #[serde(rename = "ship")]
    Ship = 2,
    #[serde(rename = "airship")]
    Airship = 3,
}

impl Default for SavePartyLocationVehicleType {
    fn default() -> Self { SavePartyLocationVehicleType::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SavePictureBattleLayer {
    #[serde(rename = "none")]
    None = 0,
    #[serde(rename = "background")]
    Background = 1,
    #[serde(rename = "battlers_and_animations")]
    BattlersAndAnimations = 2,
    #[serde(rename = "weather")]
    Weather = 3,
    #[serde(rename = "windows_and_status")]
    WindowsAndStatus = 4,
    #[serde(rename = "timers")]
    Timers = 5,
}

impl Default for SavePictureBattleLayer {
    fn default() -> Self { SavePictureBattleLayer::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SavePictureEffect {
    #[serde(rename = "none")]
    None = 0,
    #[serde(rename = "rotation")]
    Rotation = 1,
    #[serde(rename = "wave")]
    Wave = 2,
    #[serde(rename = "maniac_fixed_angle")]
    ManiacFixedAngle = 3,
}

impl Default for SavePictureEffect {
    fn default() -> Self { SavePictureEffect::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SavePictureMapLayer {
    #[serde(rename = "none")]
    None = 0,
    #[serde(rename = "parallax")]
    Parallax = 1,
    #[serde(rename = "tilemap_below")]
    TilemapBelow = 2,
    #[serde(rename = "events_below")]
    EventsBelow = 3,
    #[serde(rename = "events_same_as_player")]
    EventsSameAsPlayer = 4,
    #[serde(rename = "tilemap_above")]
    TilemapAbove = 5,
    #[serde(rename = "events_above")]
    EventsAbove = 6,
    #[serde(rename = "weather")]
    Weather = 7,
    #[serde(rename = "animations")]
    Animations = 8,
    #[serde(rename = "windows")]
    Windows = 9,
    #[serde(rename = "timers")]
    Timers = 10,
}

impl Default for SavePictureMapLayer {
    fn default() -> Self { SavePictureMapLayer::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SaveSystemAtbMode {
    #[serde(rename = "atb_active")]
    AtbActive = 0,
    #[serde(rename = "atb_wait")]
    AtbWait = 1,
}

impl Default for SaveSystemAtbMode {
    fn default() -> Self { SaveSystemAtbMode::AtbActive }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SaveSystemScene {
    #[serde(rename = "map")]
    Map = 0,
    #[serde(rename = "menu")]
    Menu = 1,
    #[serde(rename = "battle")]
    Battle = 2,
    #[serde(rename = "shop")]
    Shop = 3,
    #[serde(rename = "name")]
    Name = 4,
    #[serde(rename = "file")]
    File = 5,
    #[serde(rename = "title")]
    Title = 6,
    #[serde(rename = "game_over")]
    GameOver = 7,
    #[serde(rename = "debug")]
    Debug = 8,
}

impl Default for SaveSystemScene {
    fn default() -> Self { SaveSystemScene::Map }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SaveVehicleLocationVehicleType {
    #[serde(rename = "none")]
    None = 0,
    #[serde(rename = "skiff")]
    Skiff = 1,
    #[serde(rename = "ship")]
    Ship = 2,
    #[serde(rename = "airship")]
    Airship = 3,
}

impl Default for SaveVehicleLocationVehicleType {
    fn default() -> Self { SaveVehicleLocationVehicleType::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SkillScope {
    #[serde(rename = "enemy")]
    Enemy = 0,
    #[serde(rename = "enemies")]
    Enemies = 1,
    #[serde(rename = "self")]
    Self_ = 2,
    #[serde(rename = "ally")]
    Ally = 3,
    #[serde(rename = "party")]
    Party = 4,
}

impl Default for SkillScope {
    fn default() -> Self { SkillScope::Enemy }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SkillSpType {
    #[serde(rename = "cost")]
    Cost = 0,
    #[serde(rename = "percent")]
    Percent = 1,
}

impl Default for SkillSpType {
    fn default() -> Self { SkillSpType::Cost }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SkillType {
    #[serde(rename = "normal")]
    Normal = 0,
    #[serde(rename = "teleport")]
    Teleport = 1,
    #[serde(rename = "escape")]
    Escape = 2,
    #[serde(rename = "switch")]
    Switch = 3,
    #[serde(rename = "subskill")]
    Subskill = 4,
}

impl Default for SkillType {
    fn default() -> Self { SkillType::Normal }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum StateAffectType {
    #[serde(rename = "half")]
    Half = 0,
    #[serde(rename = "double")]
    Double = 1,
    #[serde(rename = "nothing")]
    Nothing = 2,
}

impl Default for StateAffectType {
    fn default() -> Self { StateAffectType::Half }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum StateChangeType {
    #[serde(rename = "lose")]
    Lose = 0,
    #[serde(rename = "gain")]
    Gain = 1,
    #[serde(rename = "nothing")]
    Nothing = 2,
}

impl Default for StateChangeType {
    fn default() -> Self { StateChangeType::Lose }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum StatePersistence {
    #[serde(rename = "ends")]
    Ends = 0,
    #[serde(rename = "persists")]
    Persists = 1,
}

impl Default for StatePersistence {
    fn default() -> Self { StatePersistence::Ends }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum StateRestriction {
    #[serde(rename = "normal")]
    Normal = 0,
    #[serde(rename = "do_nothing")]
    DoNothing = 1,
    #[serde(rename = "attack_enemy")]
    AttackEnemy = 2,
    #[serde(rename = "attack_ally")]
    AttackAlly = 3,
}

impl Default for StateRestriction {
    fn default() -> Self { StateRestriction::Normal }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemBattleCondition {
    #[serde(rename = "none")]
    None = 0,
    #[serde(rename = "initiative")]
    Initiative = 1,
    #[serde(rename = "back")]
    Back = 2,
    #[serde(rename = "surround")]
    Surround = 3,
    #[serde(rename = "pincers")]
    Pincers = 4,
}

impl Default for SystemBattleCondition {
    fn default() -> Self { SystemBattleCondition::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemBattleFormation {
    #[serde(rename = "terrain")]
    Terrain = 0,
    #[serde(rename = "loose")]
    Loose = 1,
    #[serde(rename = "tight")]
    Tight = 2,
}

impl Default for SystemBattleFormation {
    fn default() -> Self { SystemBattleFormation::Terrain }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemEquipmentSetting {
    #[serde(rename = "actor")]
    Actor = 0,
    #[serde(rename = "class")]
    Class = 1,
}

impl Default for SystemEquipmentSetting {
    fn default() -> Self { SystemEquipmentSetting::Actor }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemFadeIn {
    #[serde(rename = "default")]
    Default = 0,
    #[serde(rename = "fade_in")]
    FadeIn = 1,
    #[serde(rename = "reconstitute_blocks")]
    ReconstituteBlocks = 2,
    #[serde(rename = "unwipe_downward")]
    UnwipeDownward = 3,
    #[serde(rename = "unwipe_upward")]
    UnwipeUpward = 4,
    #[serde(rename = "venetian_blinds")]
    VenetianBlinds = 5,
    #[serde(rename = "vertical_blinds")]
    VerticalBlinds = 6,
    #[serde(rename = "horizontal_blinds")]
    HorizontalBlinds = 7,
    #[serde(rename = "receding_square")]
    RecedingSquare = 8,
    #[serde(rename = "expanding_square")]
    ExpandingSquare = 9,
    #[serde(rename = "screen_moves_down")]
    ScreenMovesDown = 10,
    #[serde(rename = "screen_moves_up")]
    ScreenMovesUp = 11,
    #[serde(rename = "screen_moves_right")]
    ScreenMovesRight = 12,
    #[serde(rename = "screen_moves_left")]
    ScreenMovesLeft = 13,
    #[serde(rename = "vertical_unify")]
    VerticalUnify = 14,
    #[serde(rename = "horizontal_unify")]
    HorizontalUnify = 15,
    #[serde(rename = "unify_quadrants")]
    UnifyQuadrants = 16,
    #[serde(rename = "zoom_out")]
    ZoomOut = 17,
    #[serde(rename = "mosaic")]
    Mosaic = 18,
    #[serde(rename = "waver_screen")]
    WaverScreen = 19,
    #[serde(rename = "instantaneous")]
    Instantaneous = 20,
    #[serde(rename = "none")]
    None = 21,
}

impl Default for SystemFadeIn {
    fn default() -> Self { SystemFadeIn::Default }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemFadeOut {
    #[serde(rename = "default")]
    Default = 0,
    #[serde(rename = "fade_out")]
    FadeOut = 1,
    #[serde(rename = "remove_blocks")]
    RemoveBlocks = 2,
    #[serde(rename = "wipe_downward")]
    WipeDownward = 3,
    #[serde(rename = "wipe_upward")]
    WipeUpward = 4,
    #[serde(rename = "venetian_blinds")]
    VenetianBlinds = 5,
    #[serde(rename = "vertical_blinds")]
    VerticalBlinds = 6,
    #[serde(rename = "horizontal_blinds")]
    HorizontalBlinds = 7,
    #[serde(rename = "receding_square")]
    RecedingSquare = 8,
    #[serde(rename = "expanding_square")]
    ExpandingSquare = 9,
    #[serde(rename = "screen_moves_up")]
    ScreenMovesUp = 10,
    #[serde(rename = "screen_moves_down")]
    ScreenMovesDown = 11,
    #[serde(rename = "screen_moves_left")]
    ScreenMovesLeft = 12,
    #[serde(rename = "screen_moves_right")]
    ScreenMovesRight = 13,
    #[serde(rename = "vertical_div")]
    VerticalDiv = 14,
    #[serde(rename = "horizontal_div")]
    HorizontalDiv = 15,
    #[serde(rename = "quadrasection")]
    Quadrasection = 16,
    #[serde(rename = "zoom_in")]
    ZoomIn = 17,
    #[serde(rename = "mosaic")]
    Mosaic = 18,
    #[serde(rename = "waver_screen")]
    WaverScreen = 19,
    #[serde(rename = "instantaneous")]
    Instantaneous = 20,
    #[serde(rename = "none")]
    None = 21,
}

impl Default for SystemFadeOut {
    fn default() -> Self { SystemFadeOut::Default }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemFont {
    #[serde(rename = "gothic")]
    Gothic = 0,
    #[serde(rename = "mincho")]
    Mincho = 1,
}

impl Default for SystemFont {
    fn default() -> Self { SystemFont::Gothic }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemStretch {
    #[serde(rename = "stretch")]
    Stretch = 0,
    #[serde(rename = "tiled")]
    Tiled = 1,
    #[serde(rename = "easyrpg_none")]
    EasyrpgNone = 2,
}

impl Default for SystemStretch {
    fn default() -> Self { SystemStretch::Stretch }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TerrainBGAssociation {
    #[serde(rename = "background")]
    Background = 0,
    #[serde(rename = "frame")]
    Frame = 1,
}

impl Default for TerrainBGAssociation {
    fn default() -> Self { TerrainBGAssociation::Background }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TerrainBushDepth {
    #[serde(rename = "normal")]
    Normal = 0,
    #[serde(rename = "third")]
    Third = 1,
    #[serde(rename = "half")]
    Half = 2,
    #[serde(rename = "full")]
    Full = 3,
}

impl Default for TerrainBushDepth {
    fn default() -> Self { TerrainBushDepth::Normal }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TreeMapMapType {
    #[serde(rename = "root")]
    Root = 0,
    #[serde(rename = "map")]
    Map = 1,
    #[serde(rename = "area")]
    Area = 2,
}

impl Default for TreeMapMapType {
    fn default() -> Self { TreeMapMapType::Root }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Actor {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario
    pub title: String,
    /// campo 0x03 del binario
    pub character_name: String,
    /// campo 0x04 del binario
    /// default: 0
    pub character_index: i32,
    /// campo 0x05 del binario
    /// default: False
    pub transparent: bool,
    /// campo 0x07 del binario
    /// default: 1
    pub initial_level: i32,
    /// campo 0x08 del binario
    pub final_level: i32,
    /// campo 0x09 del binario
    /// default: True
    pub critical_hit: bool,
    /// campo 0x0A del binario
    /// default: 30
    pub critical_hit_chance: i32,
    /// campo 0x0F del binario
    pub face_name: String,
    /// campo 0x10 del binario
    /// default: 0
    pub face_index: i32,
    /// campo 0x15 del binario
    /// default: False
    pub two_weapon: bool,
    /// campo 0x16 del binario
    /// default: False
    pub lock_equipment: bool,
    /// campo 0x17 del binario
    /// default: False
    pub auto_battle: bool,
    /// campo 0x18 del binario
    /// default: False
    pub super_guard: bool,
    /// campo 0x1F del binario, se guarda aunque valga el default
    pub parameters: Parameters,
    /// campo 0x29 del binario
    pub exp_base: i32,
    /// campo 0x2A del binario
    pub exp_inflation: i32,
    /// campo 0x2B del binario
    /// default: 0
    pub exp_correction: i32,
    /// campo 0x33 del binario, se guarda aunque valga el default
    pub initial_equipment: Equipment,
    /// campo 0x38 del binario
    /// default: 1
    pub unarmed_animation: i32,
    /// campo 0x3F del binario, se guarda aunque valga el default
    pub skills: Vec<Learning>,
    /// campo 0x42 del binario
    /// default: False
    pub rename_skill: bool,
    /// campo 0x43 del binario
    pub skill_name: String,
    /// campo 0x48 del binario, se guarda aunque valga el default
    pub state_ranks: Vec<u8>,
    /// campo 0x4A del binario, se guarda aunque valga el default
    pub attribute_ranks: Vec<u8>,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Animation {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario
    pub animation_name: String,
    /// campo 0x03 del binario
    /// default: False
    pub large: bool,
    /// campo 0x06 del binario, se guarda aunque valga el default
    pub timings: Vec<AnimationTiming>,
    /// campo 0x09 del binario, se guarda aunque valga el default
    /// default: 0
    pub scope: AnimationScope,
    /// campo 0x0A del binario, se guarda aunque valga el default
    /// default: 2
    pub position: AnimationPosition,
    /// campo 0x0C del binario, se guarda aunque valga el default
    pub frames: Vec<AnimationFrame>,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct AnimationCellData {
    /// campo 0x01 del binario
    /// default: 1
    pub valid: i32,
    /// campo 0x02 del binario
    /// default: 0
    pub cell_id: i32,
    /// campo 0x03 del binario
    /// default: 0
    pub x: i32,
    /// campo 0x04 del binario
    /// default: 0
    pub y: i32,
    /// campo 0x05 del binario
    /// default: 100
    pub zoom: i32,
    /// campo 0x06 del binario
    /// default: 100
    pub tone_red: i32,
    /// campo 0x07 del binario
    /// default: 100
    pub tone_green: i32,
    /// campo 0x08 del binario
    /// default: 100
    pub tone_blue: i32,
    /// campo 0x09 del binario
    /// default: 100
    pub tone_gray: i32,
    /// campo 0x0A del binario
    /// default: 0
    pub transparency: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct AnimationFrame {
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub cells: Vec<AnimationCellData>,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct AnimationTiming {
    /// campo 0x01 del binario
    /// default: 0
    pub frame: i32,
    /// campo 0x02 del binario, se guarda aunque valga el default
    pub se: Sound,
    /// campo 0x03 del binario, se guarda aunque valga el default
    /// default: 0
    pub flash_scope: AnimationTimingFlashScope,
    /// campo 0x04 del binario
    /// default: 31
    pub flash_red: i32,
    /// campo 0x05 del binario
    /// default: 31
    pub flash_green: i32,
    /// campo 0x06 del binario
    /// default: 31
    pub flash_blue: i32,
    /// campo 0x07 del binario
    /// default: 31
    pub flash_power: i32,
    /// campo 0x08 del binario
    /// default: 0
    pub screen_shake: AnimationTimingScreenShake,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Attribute {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario, se guarda aunque valga el default
    /// default: 0
    pub r#type: AttributeType,
    /// campo 0x0B del binario
    /// default: 300
    pub a_rate: i32,
    /// campo 0x0C del binario
    /// default: 200
    pub b_rate: i32,
    /// campo 0x0D del binario
    /// default: 100
    pub c_rate: i32,
    /// campo 0x0E del binario
    /// default: 50
    pub d_rate: i32,
    /// campo 0x0F del binario
    /// default: 0
    pub e_rate: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct BattleCommand {
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub name: String,
    /// campo 0x02 del binario
    /// default: 0
    pub r#type: BattleCommandType,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct BattleCommands {
    /// campo 0x02 del binario
    /// default: 0
    pub placement: BattleCommandsPlacement,
    /// campo 0x06 del binario
    /// default: 0
    pub row: BattleCommandsRowShown,
    /// campo 0x07 del binario
    /// default: 0
    pub battle_type: BattleCommandsBattleType,
    /// campo 0x09 del binario
    /// default: True
    pub unused_display_normal_parameters: bool,
    /// campo 0x0A del binario, se guarda aunque valga el default
    pub commands: Vec<BattleCommand>,
    /// campo 0x10 del binario
    /// default: 1
    pub death_event: i32,
    /// campo 0x14 del binario
    /// default: 0
    pub window_size: BattleCommandsWindowSize,
    /// campo 0x18 del binario
    /// default: 0
    pub transparency: BattleCommandsTransparency,
    /// campo 0x19 del binario
    /// default: False
    pub death_teleport: bool,
    /// campo 0x1A del binario
    /// default: 1
    pub death_teleport_id: i32,
    /// campo 0x1B del binario
    /// default: 0
    pub death_teleport_x: i32,
    /// campo 0x1C del binario
    /// default: 0
    pub death_teleport_y: i32,
    /// campo 0x1D del binario
    /// default: 0
    pub death_teleport_face: BattleCommandsFacing,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Chipset {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario
    pub chipset_name: String,
    /// campo 0x03 del binario
    /// default: [1]*162
    pub terrain_data: Vec<i16>,
    /// campo 0x04 del binario
    /// default: [15]*162
    pub passable_data_lower: Vec<u8>,
    /// campo 0x05 del binario
    /// default: [31]+[15]*143
    pub passable_data_upper: Vec<u8>,
    /// campo 0x0B del binario
    /// default: 0
    pub animation_type: ChipsetAnimType,
    /// campo 0x0C del binario
    /// default: 0
    pub animation_speed: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Class {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x15 del binario
    /// default: False
    pub two_weapon: bool,
    /// campo 0x16 del binario
    /// default: False
    pub lock_equipment: bool,
    /// campo 0x17 del binario
    /// default: False
    pub auto_battle: bool,
    /// campo 0x18 del binario
    /// default: False
    pub super_guard: bool,
    /// campo 0x1F del binario
    pub parameters: Parameters,
    /// campo 0x29 del binario
    /// default: 300
    pub exp_base: i32,
    /// campo 0x2A del binario
    /// default: 300
    pub exp_inflation: i32,
    /// campo 0x2B del binario
    /// default: 0
    pub exp_correction: i32,
    /// campo 0x3E del binario
    /// default: 0
    pub battler_animation: i32,
    /// campo 0x3F del binario, se guarda aunque valga el default
    pub skills: Vec<Learning>,
    /// campo 0x48 del binario, se guarda aunque valga el default
    pub state_ranks: Vec<u8>,
    /// campo 0x4A del binario, se guarda aunque valga el default
    pub attribute_ranks: Vec<u8>,
    /// campo 0x50 del binario, se guarda aunque valga el default
    pub battle_commands: Vec<i32>,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct CommonEvent {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x0B del binario, se guarda aunque valga el default
    /// default: 5
    pub trigger: CommonEventTrigger,
    /// campo 0x0C del binario
    /// default: False
    pub switch_flag: bool,
    /// campo 0x0D del binario
    /// default: 1
    pub switch_id: i32,
    /// campo 0x16 del binario, se guarda aunque valga el default
    pub event_commands: Vec<EventCommand>,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Database {
    /// campo 0x0B del binario, se guarda aunque valga el default
    pub actors: Vec<Actor>,
    /// campo 0x0C del binario, se guarda aunque valga el default
    pub skills: Vec<Skill>,
    /// campo 0x0D del binario, se guarda aunque valga el default
    pub items: Vec<Item>,
    /// campo 0x0E del binario, se guarda aunque valga el default
    pub enemies: Vec<Enemy>,
    /// campo 0x0F del binario, se guarda aunque valga el default
    pub troops: Vec<Troop>,
    /// campo 0x10 del binario, se guarda aunque valga el default
    pub terrains: Vec<Terrain>,
    /// campo 0x11 del binario, se guarda aunque valga el default
    pub attributes: Vec<Attribute>,
    /// campo 0x12 del binario, se guarda aunque valga el default
    pub states: Vec<State>,
    /// campo 0x13 del binario, se guarda aunque valga el default
    pub animations: Vec<Animation>,
    /// campo 0x14 del binario, se guarda aunque valga el default
    pub chipsets: Vec<Chipset>,
    /// campo 0x15 del binario, se guarda aunque valga el default
    pub terms: Terms,
    /// campo 0x16 del binario, se guarda aunque valga el default
    pub system: System,
    /// campo 0x17 del binario, se guarda aunque valga el default
    pub switches: Vec<Switch>,
    /// campo 0x18 del binario, se guarda aunque valga el default
    pub variables: Vec<Variable>,
    /// campo 0x19 del binario, se guarda aunque valga el default
    pub commonevents: Vec<CommonEvent>,
    /// campo 0x1A del binario
    /// default: 0
    pub version: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Encounter {
    /// campo 0x01 del binario
    /// default: 0
    pub troop_id: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Enemy {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario
    pub battler_name: String,
    /// campo 0x03 del binario
    /// default: 0
    pub battler_hue: i32,
    /// campo 0x04 del binario
    /// default: 10
    pub max_hp: i32,
    /// campo 0x05 del binario
    /// default: 10
    pub max_sp: i32,
    /// campo 0x06 del binario
    /// default: 10
    pub attack: i32,
    /// campo 0x07 del binario
    /// default: 10
    pub defense: i32,
    /// campo 0x08 del binario
    /// default: 10
    pub spirit: i32,
    /// campo 0x09 del binario
    /// default: 10
    pub agility: i32,
    /// campo 0x0A del binario
    /// default: False
    pub transparent: bool,
    /// campo 0x0B del binario
    /// default: 0
    pub exp: i32,
    /// campo 0x0C del binario
    /// default: 0
    pub gold: i32,
    /// campo 0x0D del binario
    /// default: 0
    pub drop_id: i32,
    /// campo 0x0E del binario
    /// default: 100
    pub drop_prob: i32,
    /// campo 0x15 del binario
    /// default: False
    pub critical_hit: bool,
    /// campo 0x16 del binario
    /// default: 30
    pub critical_hit_chance: i32,
    /// campo 0x1A del binario
    /// default: False
    pub miss: bool,
    /// campo 0x1C del binario
    /// default: False
    pub levitate: bool,
    /// campo 0x20 del binario, se guarda aunque valga el default
    pub state_ranks: Vec<u8>,
    /// campo 0x22 del binario, se guarda aunque valga el default
    pub attribute_ranks: Vec<u8>,
    /// campo 0x2A del binario, se guarda aunque valga el default
    pub actions: Vec<EnemyAction>,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct EnemyAction {
    /// campo 0x01 del binario, se guarda aunque valga el default
    /// default: 0
    pub kind: EnemyActionKind,
    /// campo 0x02 del binario, se guarda aunque valga el default
    /// default: 1
    pub basic: EnemyActionBasic,
    /// campo 0x03 del binario
    /// default: 1
    pub skill_id: i32,
    /// campo 0x04 del binario
    /// default: 1
    pub enemy_id: i32,
    /// campo 0x05 del binario, se guarda aunque valga el default
    /// default: 0
    pub condition_type: EnemyActionConditionType,
    /// campo 0x06 del binario
    /// default: 0
    pub condition_param1: i32,
    /// campo 0x07 del binario
    /// default: 0
    pub condition_param2: i32,
    /// campo 0x08 del binario
    /// default: 1
    pub switch_id: i32,
    /// campo 0x09 del binario
    /// default: False
    pub switch_on: bool,
    /// campo 0x0A del binario
    /// default: 1
    pub switch_on_id: i32,
    /// campo 0x0B del binario
    /// default: False
    pub switch_off: bool,
    /// campo 0x0C del binario
    /// default: 1
    pub switch_off_id: i32,
    /// campo 0x0D del binario
    /// default: 50
    pub rating: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Equipment {
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Event {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario
    /// default: 0
    pub x: i32,
    /// campo 0x03 del binario
    /// default: 0
    pub y: i32,
    /// campo 0x05 del binario, se guarda aunque valga el default
    pub pages: Vec<EventPage>,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct EventCommand {
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct EventPage {
    /// campo 0x02 del binario, se guarda aunque valga el default
    pub condition: EventPageCondition,
    /// campo 0x15 del binario
    pub character_name: String,
    /// campo 0x16 del binario
    /// default: 0
    pub character_index: i32,
    /// campo 0x17 del binario, se guarda aunque valga el default
    /// default: 2
    pub character_direction: EventPageDirection,
    /// campo 0x18 del binario
    /// default: 1
    pub character_pattern: EventPageFrame,
    /// campo 0x19 del binario, se guarda aunque valga el default
    /// default: False
    pub translucent: bool,
    /// campo 0x1F del binario, se guarda aunque valga el default
    /// default: 1
    pub move_type: EventPageMoveType,
    /// campo 0x20 del binario
    /// default: 3
    pub move_frequency: i32,
    /// campo 0x21 del binario, se guarda aunque valga el default
    /// default: 0
    pub trigger: EventPageTrigger,
    /// campo 0x22 del binario, se guarda aunque valga el default
    /// default: 0
    pub layer: EventPageLayers,
    /// campo 0x23 del binario, se guarda aunque valga el default
    /// default: False
    pub overlap_forbidden: bool,
    /// campo 0x24 del binario, se guarda aunque valga el default
    /// default: 0
    pub animation_type: EventPageAnimType,
    /// campo 0x25 del binario
    /// default: 3
    pub move_speed: EventPageMoveSpeed,
    /// campo 0x29 del binario, se guarda aunque valga el default
    pub move_route: MoveRoute,
    /// campo 0x34 del binario, se guarda aunque valga el default
    pub event_commands: Vec<EventCommand>,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct EventPageCondition {
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub flags: u32,
    /// campo 0x02 del binario
    /// default: 1
    pub switch_a_id: i32,
    /// campo 0x03 del binario
    /// default: 1
    pub switch_b_id: i32,
    /// campo 0x04 del binario
    /// default: 1
    pub variable_id: i32,
    /// campo 0x05 del binario
    /// default: 0
    pub variable_value: i32,
    /// campo 0x06 del binario
    /// default: 1
    pub item_id: i32,
    /// campo 0x07 del binario, se guarda aunque valga el default
    /// default: 1
    pub actor_id: i32,
    /// campo 0x08 del binario
    /// default: 0
    pub timer_sec: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Item {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario
    pub description: String,
    /// campo 0x03 del binario, se guarda aunque valga el default
    /// default: 0
    pub r#type: ItemType,
    /// campo 0x05 del binario
    /// default: 0
    pub price: i32,
    /// campo 0x06 del binario
    /// default: 1
    pub uses: i32,
    /// campo 0x0B del binario
    /// default: 0
    pub atk_points1: i32,
    /// campo 0x0C del binario
    /// default: 0
    pub def_points1: i32,
    /// campo 0x0D del binario
    /// default: 0
    pub spi_points1: i32,
    /// campo 0x0E del binario
    /// default: 0
    pub agi_points1: i32,
    /// campo 0x0F del binario, se guarda aunque valga el default
    /// default: False
    pub two_handed: bool,
    /// campo 0x10 del binario
    /// default: 0
    pub sp_cost: i32,
    /// campo 0x11 del binario
    /// default: 90
    pub hit: i32,
    /// campo 0x12 del binario
    /// default: 0
    pub critical_hit: i32,
    /// campo 0x14 del binario
    /// default: 1
    pub animation_id: i32,
    /// campo 0x15 del binario
    /// default: False
    pub preemptive: bool,
    /// campo 0x16 del binario
    /// default: False
    pub dual_attack: bool,
    /// campo 0x17 del binario
    /// default: False
    pub attack_all: bool,
    /// campo 0x18 del binario
    /// default: False
    pub ignore_evasion: bool,
    /// campo 0x19 del binario
    /// default: False
    pub prevent_critical: bool,
    /// campo 0x1A del binario
    /// default: False
    pub raise_evasion: bool,
    /// campo 0x1B del binario
    /// default: False
    pub half_sp_cost: bool,
    /// campo 0x1C del binario
    /// default: False
    pub no_terrain_damage: bool,
    /// campo 0x1F del binario, se guarda aunque valga el default
    /// default: False
    pub entire_party: bool,
    /// campo 0x20 del binario
    /// default: 0
    pub recover_hp_rate: i32,
    /// campo 0x21 del binario
    /// default: 0
    pub recover_hp: i32,
    /// campo 0x22 del binario
    /// default: 0
    pub recover_sp_rate: i32,
    /// campo 0x23 del binario
    /// default: 0
    pub recover_sp: i32,
    /// campo 0x25 del binario
    /// default: False
    pub occasion_field1: bool,
    /// campo 0x26 del binario
    /// default: False
    pub ko_only: bool,
    /// campo 0x29 del binario
    /// default: 0
    pub max_hp_points: i32,
    /// campo 0x2A del binario
    /// default: 0
    pub max_sp_points: i32,
    /// campo 0x2B del binario
    /// default: 0
    pub atk_points2: i32,
    /// campo 0x2C del binario
    /// default: 0
    pub def_points2: i32,
    /// campo 0x2D del binario
    /// default: 0
    pub spi_points2: i32,
    /// campo 0x2E del binario
    /// default: 0
    pub agi_points2: i32,
    /// campo 0x33 del binario, se guarda aunque valga el default
    /// default: 0
    pub using_message: i32,
    /// campo 0x35 del binario
    /// default: 1
    pub skill_id: i32,
    /// campo 0x37 del binario
    /// default: 1
    pub switch_id: i32,
    /// campo 0x39 del binario
    /// default: True
    pub occasion_field2: bool,
    /// campo 0x3A del binario
    /// default: False
    pub occasion_battle: bool,
    /// campo 0x3E del binario, se guarda aunque valga el default
    pub actor_set: Vec<bool>,
    /// campo 0x40 del binario, se guarda aunque valga el default
    pub state_set: Vec<bool>,
    /// campo 0x42 del binario, se guarda aunque valga el default
    pub attribute_set: Vec<bool>,
    /// campo 0x43 del binario
    /// default: 0
    pub state_chance: i32,
    /// campo 0x44 del binario
    /// default: False
    pub reverse_state_effect: bool,
    /// campo 0x4B del binario
    /// default: 0
    pub ranged_trajectory: ItemTrajectory,
    /// campo 0x4C del binario
    /// default: 0
    pub ranged_target: ItemTarget,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Learning {
    /// campo 0x01 del binario
    /// default: 1
    pub level: i32,
    /// campo 0x02 del binario
    /// default: 1
    pub skill_id: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Map {
    /// campo 0x01 del binario
    /// default: 1
    pub chipset_id: i32,
    /// campo 0x02 del binario
    /// default: 20
    pub width: i32,
    /// campo 0x03 del binario
    /// default: 15
    pub height: i32,
    /// campo 0x0B del binario, se guarda aunque valga el default
    /// default: 0
    pub scroll_type: MapScrollType,
    /// campo 0x1F del binario
    /// default: False
    pub parallax_flag: bool,
    /// campo 0x20 del binario
    pub parallax_name: String,
    /// campo 0x21 del binario
    /// default: False
    pub parallax_loop_x: bool,
    /// campo 0x22 del binario
    /// default: False
    pub parallax_loop_y: bool,
    /// campo 0x23 del binario
    /// default: False
    pub parallax_auto_loop_x: bool,
    /// campo 0x24 del binario
    /// default: 0
    pub parallax_sx: i32,
    /// campo 0x25 del binario
    /// default: False
    pub parallax_auto_loop_y: bool,
    /// campo 0x26 del binario
    /// default: 0
    pub parallax_sy: i32,
    /// campo 0x28 del binario
    /// default: False
    pub generator_flag: bool,
    /// campo 0x29 del binario
    /// default: 0
    pub generator_mode: MapGeneratorMode,
    /// campo 0x2A del binario
    /// default: False
    pub top_level: bool,
    /// campo 0x30 del binario
    /// default: 0
    pub generator_tiles: MapGeneratorTiles,
    /// campo 0x31 del binario
    /// default: 4
    pub generator_width: i32,
    /// campo 0x32 del binario
    /// default: 1
    pub generator_height: i32,
    /// campo 0x33 del binario
    /// default: True
    pub generator_surround: bool,
    /// campo 0x34 del binario
    /// default: True
    pub generator_upper_wall: bool,
    /// campo 0x35 del binario
    /// default: True
    pub generator_floor_b: bool,
    /// campo 0x36 del binario
    /// default: True
    pub generator_floor_c: bool,
    /// campo 0x37 del binario
    /// default: True
    pub generator_extra_b: bool,
    /// campo 0x38 del binario
    /// default: True
    pub generator_extra_c: bool,
    /// campo 0x3C del binario
    pub generator_x: Vec<u32>,
    /// campo 0x3D del binario
    pub generator_y: Vec<u32>,
    /// campo 0x3E del binario
    pub generator_tile_ids: Vec<i16>,
    /// campo 0x47 del binario, se guarda aunque valga el default
    pub lower_layer: Vec<i16>,
    /// campo 0x48 del binario, se guarda aunque valga el default
    pub upper_layer: Vec<i16>,
    /// campo 0x51 del binario, se guarda aunque valga el default
    pub events: Vec<Event>,
    /// campo 0x5B del binario
    /// default: 0
    pub save_count: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct MapInfo {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario
    /// default: 0
    pub parent_map: i32,
    /// campo 0x03 del binario
    /// default: 0
    pub indentation: i32,
    /// campo 0x04 del binario
    /// default: -1
    pub r#type: TreeMapMapType,
    /// campo 0x05 del binario
    /// default: 0
    pub scrollbar_x: i32,
    /// campo 0x06 del binario
    /// default: 0
    pub scrollbar_y: i32,
    /// campo 0x07 del binario
    /// default: False
    pub expanded_node: bool,
    /// campo 0x0B del binario, se guarda aunque valga el default
    /// default: 0
    pub music_type: MapInfoMusicType,
    /// campo 0x0C del binario, se guarda aunque valga el default
    pub music: Music,
    /// campo 0x15 del binario, se guarda aunque valga el default
    /// default: 0
    pub background_type: MapInfoBGMType,
    /// campo 0x16 del binario
    pub background_name: String,
    /// campo 0x1F del binario, se guarda aunque valga el default
    /// default: 0
    pub teleport: MapInfoTriState,
    /// campo 0x20 del binario, se guarda aunque valga el default
    /// default: 0
    pub escape: MapInfoTriState,
    /// campo 0x21 del binario, se guarda aunque valga el default
    /// default: 0
    pub save: MapInfoTriState,
    /// campo 0x29 del binario, se guarda aunque valga el default
    pub encounters: Vec<Encounter>,
    /// campo 0x2C del binario
    /// default: 25
    pub encounter_steps: i32,
    /// campo 0x33 del binario, se guarda aunque valga el default
    pub area_rect: Rect,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct MoveCommand {
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct MoveRoute {
    /// campo 0x0C del binario, se guarda aunque valga el default
    pub move_commands: Vec<MoveCommand>,
    /// campo 0x15 del binario
    /// default: True
    pub repeat: bool,
    /// campo 0x16 del binario
    /// default: False
    pub skippable: bool,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Music {
    /// campo 0x01 del binario, se guarda aunque valga el default
    /// default: """(OFF)"""
    pub name: String,
    /// campo 0x02 del binario
    /// default: 0
    pub fadein: i32,
    /// campo 0x03 del binario
    /// default: 100
    pub volume: i32,
    /// campo 0x04 del binario
    /// default: 100
    pub tempo: i32,
    /// campo 0x05 del binario
    /// default: 50
    pub balance: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Parameters {
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Rect {
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Save {
    /// campo 0x64 del binario
    pub title: SaveTitle,
    /// campo 0x65 del binario, se guarda aunque valga el default
    pub system: SaveSystem,
    /// campo 0x66 del binario, se guarda aunque valga el default
    pub screen: SaveScreen,
    /// campo 0x67 del binario, se guarda aunque valga el default
    pub pictures: Vec<SavePicture>,
    /// campo 0x68 del binario, se guarda aunque valga el default
    pub party_location: SavePartyLocation,
    /// campo 0x69 del binario, se guarda aunque valga el default
    pub boat_location: SaveVehicleLocation,
    /// campo 0x6A del binario, se guarda aunque valga el default
    pub ship_location: SaveVehicleLocation,
    /// campo 0x6B del binario, se guarda aunque valga el default
    pub airship_location: SaveVehicleLocation,
    /// campo 0x6C del binario, se guarda aunque valga el default
    pub actors: Vec<SaveActor>,
    /// campo 0x6D del binario, se guarda aunque valga el default
    pub inventory: SaveInventory,
    /// campo 0x6E del binario, se guarda aunque valga el default
    pub targets: Vec<SaveTarget>,
    /// campo 0x6F del binario, se guarda aunque valga el default
    pub map_info: SaveMapInfo,
    /// campo 0x70 del binario, se guarda aunque valga el default
    pub panorama: SavePanorama,
    /// campo 0x71 del binario, se guarda aunque valga el default
    pub foreground_event_execstate: SaveEventExecState,
    /// campo 0x72 del binario, se guarda aunque valga el default
    pub common_events: Vec<SaveCommonEvent>,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveActor {
    /// campo 0x01 del binario, se guarda aunque valga el default
    /// default: kEmptyName
    pub name: String,
    /// campo 0x02 del binario, se guarda aunque valga el default
    /// default: kEmptyName
    pub title: String,
    /// campo 0x0B del binario
    pub sprite_name: String,
    /// campo 0x0C del binario
    /// default: 0
    pub sprite_id: i32,
    /// campo 0x0D del binario
    /// default: 0
    pub transparency: i32,
    /// campo 0x15 del binario
    pub face_name: String,
    /// campo 0x16 del binario
    /// default: 0
    pub face_id: i32,
    /// campo 0x1F del binario
    /// default: -1
    pub level: i32,
    /// campo 0x20 del binario
    /// default: -1
    pub exp: i32,
    /// campo 0x21 del binario
    /// default: -1
    pub hp_mod: i32,
    /// campo 0x22 del binario
    /// default: -1
    pub sp_mod: i32,
    /// campo 0x29 del binario
    /// default: 0
    pub attack_mod: i32,
    /// campo 0x2A del binario
    /// default: 0
    pub defense_mod: i32,
    /// campo 0x2B del binario
    /// default: 0
    pub spirit_mod: i32,
    /// campo 0x2C del binario
    /// default: 0
    pub agility_mod: i32,
    /// campo 0x34 del binario, se guarda aunque valga el default
    pub skills: Vec<i16>,
    /// campo 0x3D del binario, se guarda aunque valga el default
    /// default: "[0]*5"
    pub equipped: Vec<i16>,
    /// campo 0x47 del binario
    /// default: -1
    pub current_hp: i32,
    /// campo 0x48 del binario
    /// default: -1
    pub current_sp: i32,
    /// campo 0x52 del binario, se guarda aunque valga el default
    pub status: Vec<i16>,
    /// campo 0x53 del binario
    /// default: False
    pub changed_battle_commands: bool,
    /// campo 0x5A del binario
    /// default: -1
    pub class_id: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveCommonEvent {
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub parallel_event_execstate: SaveEventExecState,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveEventExecFrame {
    /// campo 0x02 del binario, se guarda aunque valga el default
    pub commands: Vec<EventCommand>,
    /// campo 0x0B del binario
    /// default: 0
    pub current_command: i32,
    /// campo 0x0C del binario
    /// default: 0
    pub event_id: i32,
    /// campo 0x0D del binario
    /// default: False
    pub triggered_by_decision_key: bool,
    /// campo 0x16 del binario, se guarda aunque valga el default
    pub subcommand_path: Vec<u8>,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveEventExecState {
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub stack: Vec<SaveEventExecFrame>,
    /// campo 0x04 del binario
    /// default: False
    pub show_message: bool,
    /// campo 0x0B del binario
    /// default: False
    pub abort_on_escape: bool,
    /// campo 0x0D del binario
    /// default: False
    pub wait_movement: bool,
    /// campo 0x15 del binario
    /// default: False
    pub keyinput_wait: bool,
    /// campo 0x16 del binario
    /// default: 0
    pub keyinput_variable: u8,
    /// campo 0x17 del binario
    /// default: False
    pub keyinput_all_directions: bool,
    /// campo 0x18 del binario
    /// default: 0
    pub keyinput_decision: i32,
    /// campo 0x19 del binario
    /// default: 0
    pub keyinput_cancel: i32,
    /// campo 0x1A del binario
    /// default: 0
    pub keyinput_2kshift_2k3numbers: i32,
    /// campo 0x1B del binario
    /// default: 0
    pub keyinput_2kdown_2k3operators: i32,
    /// campo 0x1C del binario
    /// default: 0
    pub keyinput_2kleft_2k3shift: i32,
    /// campo 0x1D del binario
    /// default: 0
    pub keyinput_2kright: i32,
    /// campo 0x1E del binario
    /// default: 0
    pub keyinput_2kup: i32,
    /// campo 0x1F del binario
    /// default: 0
    pub wait_time: i32,
    /// campo 0x20 del binario
    /// default: 0
    pub keyinput_time_variable: i32,
    /// campo 0x23 del binario
    /// default: 0
    pub keyinput_2k3down: i32,
    /// campo 0x24 del binario
    /// default: 0
    pub keyinput_2k3left: i32,
    /// campo 0x25 del binario
    /// default: 0
    pub keyinput_2k3right: i32,
    /// campo 0x26 del binario
    /// default: 0
    pub keyinput_2k3up: i32,
    /// campo 0x29 del binario
    /// default: False
    pub keyinput_timed: bool,
    /// campo 0x2a del binario
    /// default: False
    pub wait_key_enter: bool,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveInventory {
    /// campo 0x02 del binario, se guarda aunque valga el default
    pub party: Vec<i16>,
    /// campo 0x0C del binario, se guarda aunque valga el default
    pub item_ids: Vec<i16>,
    /// campo 0x0D del binario, se guarda aunque valga el default
    pub item_counts: Vec<u8>,
    /// campo 0x0E del binario, se guarda aunque valga el default
    pub item_usage: Vec<u8>,
    /// campo 0x15 del binario
    /// default: 0
    pub gold: i32,
    /// campo 0x17 del binario
    /// default: 0
    pub timer1_frames: i32,
    /// campo 0x18 del binario
    /// default: False
    pub timer1_active: bool,
    /// campo 0x19 del binario
    /// default: False
    pub timer1_visible: bool,
    /// campo 0x1A del binario
    /// default: False
    pub timer1_battle: bool,
    /// campo 0x1B del binario
    /// default: 0
    pub timer2_frames: i32,
    /// campo 0x1C del binario
    /// default: False
    pub timer2_active: bool,
    /// campo 0x1D del binario
    /// default: False
    pub timer2_visible: bool,
    /// campo 0x1E del binario
    /// default: False
    pub timer2_battle: bool,
    /// campo 0x20 del binario
    /// default: 0
    pub battles: i32,
    /// campo 0x21 del binario
    /// default: 0
    pub defeats: i32,
    /// campo 0x22 del binario
    /// default: 0
    pub escapes: i32,
    /// campo 0x23 del binario
    /// default: 0
    pub victories: i32,
    /// campo 0x29 del binario
    /// default: 0
    pub turns: i32,
    /// campo 0x2A del binario
    /// default: 0
    pub steps: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveMapEvent {
    /// campo 0x65 del binario
    /// default: False
    pub waiting_execution: bool,
    /// campo 0x66 del binario
    /// default: 0
    pub original_move_route_index: i32,
    /// campo 0x67 del binario
    /// default: False
    pub triggered_by_decision_key: bool,
    /// campo 0x6C del binario, se guarda aunque valga el default
    pub parallel_event_execstate: SaveEventExecState,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveMapEventBase {
    /// campo 0x01 del binario
    /// default: True
    pub active: bool,
    /// campo 0x0B del binario, se guarda aunque valga el default
    /// default: 0
    pub map_id: i32,
    /// campo 0x0C del binario, se guarda aunque valga el default
    /// default: 0
    pub position_x: i32,
    /// campo 0x0D del binario, se guarda aunque valga el default
    /// default: 0
    pub position_y: i32,
    /// campo 0x15 del binario, se guarda aunque valga el default
    /// default: 2
    pub direction: i32,
    /// campo 0x16 del binario, se guarda aunque valga el default
    /// default: 2
    pub facing: i32,
    /// campo 0x17 del binario
    /// default: 1
    pub anim_frame: i32,
    /// campo 0x18 del binario
    /// default: 0
    pub transparency: i32,
    /// campo 0x1F del binario
    /// default: 0
    pub remaining_step: i32,
    /// campo 0x20 del binario
    /// default: 2
    pub move_frequency: i32,
    /// campo 0x21 del binario, se guarda aunque valga el default
    /// default: 1
    pub layer: i32,
    /// campo 0x22 del binario
    /// default: False
    pub overlap_forbidden: bool,
    /// campo 0x23 del binario, se guarda aunque valga el default
    /// default: 0
    pub animation_type: EventPageAnimType,
    /// campo 0x24 del binario
    /// default: False
    pub lock_facing: bool,
    /// campo 0x25 del binario, se guarda aunque valga el default
    /// default: 4
    pub move_speed: i32,
    /// campo 0x29 del binario, se guarda aunque valga el default
    pub move_route: MoveRoute,
    /// campo 0x2A del binario
    /// default: False
    pub move_route_overwrite: bool,
    /// campo 0x2B del binario
    /// default: 0
    pub move_route_index: i32,
    /// campo 0x2C del binario
    /// default: False
    pub move_route_finished: bool,
    /// campo 0x2E del binario
    /// default: False
    pub sprite_hidden: bool,
    /// campo 0x2F del binario
    /// default: False
    pub move_route_through: bool,
    /// campo 0x30 del binario
    /// default: 0
    pub anim_paused: i32,
    /// campo 0x33 del binario
    /// default: False
    pub through: bool,
    /// campo 0x34 del binario
    /// default: 0
    pub stop_count: i32,
    /// campo 0x35 del binario
    /// default: 0
    pub anim_count: i32,
    /// campo 0x36 del binario
    /// default: 0
    pub max_stop_count: i32,
    /// campo 0x3D del binario
    /// default: False
    pub jumping: bool,
    /// campo 0x3E del binario
    /// default: 0
    pub begin_jump_x: i32,
    /// campo 0x3F del binario
    /// default: 0
    pub begin_jump_y: i32,
    /// campo 0x47 del binario
    /// default: False
    pub pause: bool,
    /// campo 0x48 del binario
    /// default: False
    pub flying: bool,
    /// campo 0x49 del binario
    pub sprite_name: String,
    /// campo 0x4A del binario
    /// default: 0
    pub sprite_id: i32,
    /// campo 0x4B del binario
    /// default: False
    pub processed: bool,
    /// campo 0x51 del binario
    /// default: -1
    pub flash_red: i32,
    /// campo 0x52 del binario
    /// default: -1
    pub flash_green: i32,
    /// campo 0x53 del binario
    /// default: -1
    pub flash_blue: i32,
    /// campo 0x54 del binario
    /// default: 0.0
    pub flash_current_level: f64,
    /// campo 0x55 del binario
    /// default: 0
    pub flash_time_left: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveMapInfo {
    /// campo 0x01 del binario
    /// default: 0
    pub position_x: i32,
    /// campo 0x02 del binario
    /// default: 0
    pub position_y: i32,
    /// campo 0x03 del binario
    /// default: -1
    pub encounter_steps: i32,
    /// campo 0x05 del binario
    /// default: 0
    pub chipset_id: i32,
    /// campo 0x0B del binario, se guarda aunque valga el default
    pub events: Vec<SaveMapEvent>,
    /// campo 0x20 del binario
    pub parallax_name: String,
    /// campo 0x21 del binario
    /// default: False
    pub parallax_horz: bool,
    /// campo 0x22 del binario
    /// default: False
    pub parallax_vert: bool,
    /// campo 0x23 del binario
    /// default: False
    pub parallax_horz_auto: bool,
    /// campo 0x24 del binario
    /// default: 0
    pub parallax_horz_speed: i32,
    /// campo 0x25 del binario
    /// default: False
    pub parallax_vert_auto: bool,
    /// campo 0x26 del binario
    /// default: 0
    pub parallax_vert_speed: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SavePanorama {
    /// campo 0x01 del binario
    /// default: 0
    pub pan_x: i32,
    /// campo 0x02 del binario
    /// default: 0
    pub pan_y: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SavePartyLocation {
    /// campo 0x65 del binario
    /// default: False
    pub boarding: bool,
    /// campo 0x66 del binario
    /// default: False
    pub aboard: bool,
    /// campo 0x67 del binario
    /// default: 0
    pub vehicle: SavePartyLocationVehicleType,
    /// campo 0x68 del binario
    /// default: False
    pub unboarding: bool,
    /// campo 0x69 del binario
    /// default: 4
    pub preboard_move_speed: i32,
    /// campo 0x6C del binario
    /// default: False
    pub menu_calling: bool,
    /// campo 0x6f del binario
    /// default: 1
    pub pan_state: SavePartyLocationPanState,
    /// campo 0x70 del binario
    /// default: kPanXDefault
    pub pan_current_x: i32,
    /// campo 0x71 del binario
    /// default: kPanYDefault
    pub pan_current_y: i32,
    /// campo 0x72 del binario
    /// default: kPanXDefault
    pub pan_finish_x: i32,
    /// campo 0x73 del binario
    /// default: kPanYDefault
    pub pan_finish_y: i32,
    /// campo 0x79 del binario
    /// default: kPanSpeedDefault
    pub pan_speed: i32,
    /// campo 0x7C del binario
    /// default: 0
    pub total_encounter_rate: i32,
    /// campo 0x7D del binario
    /// default: False
    pub encounter_calling: bool,
    /// campo 0x83 del binario
    /// default: 0
    pub map_save_count: i32,
    /// campo 0x84 del binario
    /// default: 0
    pub database_save_count: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SavePicture {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario
    /// default: 0.0
    pub start_x: f64,
    /// campo 0x03 del binario
    /// default: 0.0
    pub start_y: f64,
    /// campo 0x04 del binario
    /// default: 0.0
    pub current_x: f64,
    /// campo 0x05 del binario
    /// default: 0.0
    pub current_y: f64,
    /// campo 0x06 del binario
    /// default: False
    pub fixed_to_map: bool,
    /// campo 0x07 del binario
    /// default: 100.0
    pub current_magnify: f64,
    /// campo 0x08 del binario
    /// default: 0.0
    pub current_top_trans: f64,
    /// campo 0x09 del binario
    /// default: False
    pub use_transparent_color: bool,
    /// campo 0x0B del binario
    /// default: 100.0
    pub current_red: f64,
    /// campo 0x0C del binario
    /// default: 100.0
    pub current_green: f64,
    /// campo 0x0D del binario
    /// default: 100.0
    pub current_blue: f64,
    /// campo 0x0E del binario
    /// default: 100.0
    pub current_sat: f64,
    /// campo 0x0F del binario
    /// default: 0
    pub effect_mode: SavePictureEffect,
    /// campo 0x10 del binario
    /// default: 0.0
    pub current_effect_power: f64,
    /// campo 0x12 del binario
    /// default: 0.0
    pub current_bot_trans: f64,
    /// campo 0x19 del binario
    /// default: 7
    pub map_layer: SavePictureMapLayer,
    /// campo 0x1A del binario
    /// default: 0
    pub battle_layer: SavePictureBattleLayer,
    /// campo 0x1B del binario
    /// default: 97
    pub flags: u32,
    /// campo 0x1F del binario
    /// default: 0.0
    pub finish_x: f64,
    /// campo 0x20 del binario
    /// default: 0.0
    pub finish_y: f64,
    /// campo 0x21 del binario
    /// default: 100
    pub finish_magnify: i32,
    /// campo 0x22 del binario
    /// default: 0
    pub finish_top_trans: i32,
    /// campo 0x23 del binario
    /// default: 0
    pub finish_bot_trans: i32,
    /// campo 0x29 del binario
    /// default: 100
    pub finish_red: i32,
    /// campo 0x2A del binario
    /// default: 100
    pub finish_green: i32,
    /// campo 0x2B del binario
    /// default: 100
    pub finish_blue: i32,
    /// campo 0x2C del binario
    /// default: 100
    pub finish_sat: i32,
    /// campo 0x2E del binario
    /// default: 0
    pub finish_effect_power: i32,
    /// campo 0x33 del binario
    /// default: 0
    pub time_left: i32,
    /// campo 0x34 del binario
    /// default: 0.0
    pub current_rotation: f64,
    /// campo 0x35 del binario
    /// default: 0
    pub current_waver: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveScreen {
    /// campo 0x01 del binario
    /// default: 100
    pub tint_finish_red: i32,
    /// campo 0x02 del binario
    /// default: 100
    pub tint_finish_green: i32,
    /// campo 0x03 del binario
    /// default: 100
    pub tint_finish_blue: i32,
    /// campo 0x04 del binario
    /// default: 100
    pub tint_finish_sat: i32,
    /// campo 0x0B del binario
    /// default: 100.0
    pub tint_current_red: f64,
    /// campo 0x0C del binario
    /// default: 100.0
    pub tint_current_green: f64,
    /// campo 0x0D del binario
    /// default: 100.0
    pub tint_current_blue: f64,
    /// campo 0x0E del binario
    /// default: 100.0
    pub tint_current_sat: f64,
    /// campo 0x0F del binario
    /// default: 0
    pub tint_time_left: i32,
    /// campo 0x14 del binario
    /// default: False
    pub flash_continuous: bool,
    /// campo 0x15 del binario
    /// default: 0
    pub flash_red: i32,
    /// campo 0x16 del binario
    /// default: 0
    pub flash_green: i32,
    /// campo 0x17 del binario
    /// default: 0
    pub flash_blue: i32,
    /// campo 0x18 del binario
    /// default: 0.0
    pub flash_current_level: f64,
    /// campo 0x19 del binario
    /// default: 0
    pub flash_time_left: i32,
    /// campo 0x1E del binario
    /// default: False
    pub shake_continuous: bool,
    /// campo 0x1F del binario
    /// default: 0
    pub shake_strength: i32,
    /// campo 0x20 del binario
    /// default: 0
    pub shake_speed: i32,
    /// campo 0x21 del binario
    /// default: 0
    pub shake_position: i32,
    /// campo 0x22 del binario
    /// default: 0
    pub shake_position_y: i32,
    /// campo 0x23 del binario
    /// default: 0
    pub shake_time_left: i32,
    /// campo 0x29 del binario
    /// default: 0
    pub pan_x: i32,
    /// campo 0x2A del binario
    /// default: 0
    pub pan_y: i32,
    /// campo 0x2B del binario
    /// default: 0
    pub battleanim_id: i32,
    /// campo 0x2C del binario
    /// default: 0
    pub battleanim_target: i32,
    /// campo 0x2D del binario
    /// default: 0
    pub battleanim_frame: i32,
    /// campo 0x2E del binario
    /// default: False
    pub battleanim_active: bool,
    /// campo 0x2F del binario
    /// default: False
    pub battleanim_global: bool,
    /// campo 0x30 del binario
    /// default: 0
    pub weather: i32,
    /// campo 0x31 del binario
    /// default: 0
    pub weather_strength: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveSystem {
    /// campo 0x01 del binario, se guarda aunque valga el default
    /// default: 0
    pub scene: SaveSystemScene,
    /// campo 0x0B del binario
    /// default: 0
    pub frame_count: i32,
    /// campo 0x15 del binario
    pub graphics_name: String,
    /// campo 0x16 del binario
    /// default: 0
    pub message_stretch: SystemStretch,
    /// campo 0x17 del binario
    /// default: 0
    pub font_id: SystemFont,
    /// campo 0x20 del binario, se guarda aunque valga el default
    pub switches: Vec<bool>,
    /// campo 0x22 del binario, se guarda aunque valga el default
    pub variables: Vec<i32>,
    /// campo 0x29 del binario
    /// default: 0
    pub message_transparent: i32,
    /// campo 0x2A del binario
    /// default: 2
    pub message_position: i32,
    /// campo 0x2B del binario
    /// default: 1
    pub message_prevent_overlap: i32,
    /// campo 0x2C del binario
    /// default: 0
    pub message_continue_events: i32,
    /// campo 0x33 del binario
    pub face_name: String,
    /// campo 0x34 del binario
    /// default: 0
    pub face_id: i32,
    /// campo 0x35 del binario
    /// default: False
    pub face_right: bool,
    /// campo 0x36 del binario
    /// default: False
    pub face_flip: bool,
    /// campo 0x37 del binario
    /// default: False
    pub event_message_active: bool,
    /// campo 0x3D del binario
    /// default: False
    pub music_stopping: bool,
    /// campo 0x47 del binario, se guarda aunque valga el default
    /// default: "Music{ """" }"
    pub title_music: Music,
    /// campo 0x48 del binario, se guarda aunque valga el default
    /// default: "Music{ """" }"
    pub battle_music: Music,
    /// campo 0x49 del binario, se guarda aunque valga el default
    /// default: "Music{ """" }"
    pub battle_end_music: Music,
    /// campo 0x4A del binario, se guarda aunque valga el default
    /// default: "Music{ """" }"
    pub inn_music: Music,
    /// campo 0x4B del binario, se guarda aunque valga el default
    pub current_music: Music,
    /// campo 0x4C del binario, se guarda aunque valga el default
    pub before_vehicle_music: Music,
    /// campo 0x4D del binario, se guarda aunque valga el default
    pub before_battle_music: Music,
    /// campo 0x4E del binario, se guarda aunque valga el default
    pub stored_music: Music,
    /// campo 0x4F del binario, se guarda aunque valga el default
    /// default: "Music{ """" }"
    pub boat_music: Music,
    /// campo 0x50 del binario, se guarda aunque valga el default
    /// default: "Music{ """" }"
    pub ship_music: Music,
    /// campo 0x51 del binario, se guarda aunque valga el default
    /// default: "Music{ """" }"
    pub airship_music: Music,
    /// campo 0x52 del binario, se guarda aunque valga el default
    /// default: "Music{ """" }"
    pub gameover_music: Music,
    /// campo 0x5B del binario, se guarda aunque valga el default
    /// default: "Sound{ """" }"
    pub cursor_se: Sound,
    /// campo 0x5C del binario, se guarda aunque valga el default
    /// default: "Sound{ """" }"
    pub decision_se: Sound,
    /// campo 0x5D del binario, se guarda aunque valga el default
    /// default: "Sound{ """" }"
    pub cancel_se: Sound,
    /// campo 0x5E del binario, se guarda aunque valga el default
    /// default: "Sound{ """" }"
    pub buzzer_se: Sound,
    /// campo 0x5F del binario, se guarda aunque valga el default
    /// default: "Sound{ """" }"
    pub battle_se: Sound,
    /// campo 0x60 del binario, se guarda aunque valga el default
    /// default: "Sound{ """" }"
    pub escape_se: Sound,
    /// campo 0x61 del binario, se guarda aunque valga el default
    /// default: "Sound{ """" }"
    pub enemy_attack_se: Sound,
    /// campo 0x62 del binario, se guarda aunque valga el default
    /// default: "Sound{ """" }"
    pub enemy_damaged_se: Sound,
    /// campo 0x63 del binario, se guarda aunque valga el default
    /// default: "Sound{ """" }"
    pub actor_damaged_se: Sound,
    /// campo 0x64 del binario, se guarda aunque valga el default
    /// default: "Sound{ """" }"
    pub dodge_se: Sound,
    /// campo 0x65 del binario, se guarda aunque valga el default
    /// default: "Sound{ """" }"
    pub enemy_death_se: Sound,
    /// campo 0x66 del binario, se guarda aunque valga el default
    /// default: "Sound{ """" }"
    pub item_se: Sound,
    /// campo 0x6F del binario, se guarda aunque valga el default
    /// default: -1
    pub transition_out: i8,
    /// campo 0x70 del binario, se guarda aunque valga el default
    /// default: -1
    pub transition_in: i8,
    /// campo 0x71 del binario, se guarda aunque valga el default
    /// default: -1
    pub battle_start_fadeout: i8,
    /// campo 0x72 del binario, se guarda aunque valga el default
    /// default: -1
    pub battle_start_fadein: i8,
    /// campo 0x73 del binario, se guarda aunque valga el default
    /// default: -1
    pub battle_end_fadeout: i8,
    /// campo 0x74 del binario, se guarda aunque valga el default
    /// default: -1
    pub battle_end_fadein: i8,
    /// campo 0x79 del binario
    /// default: True
    pub teleport_allowed: bool,
    /// campo 0x7A del binario
    /// default: True
    pub escape_allowed: bool,
    /// campo 0x7B del binario
    /// default: True
    pub save_allowed: bool,
    /// campo 0x7C del binario
    /// default: True
    pub menu_allowed: bool,
    /// campo 0x7D del binario
    pub background: String,
    /// campo 0x83 del binario
    /// default: 0
    pub save_count: i32,
    /// campo 0x84 del binario
    /// default: 1
    pub save_slot: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveTarget {
    /// campo 0x01 del binario
    /// default: 0
    pub map_id: i32,
    /// campo 0x02 del binario
    /// default: 0
    pub map_x: i32,
    /// campo 0x03 del binario
    /// default: 0
    pub map_y: i32,
    /// campo 0x04 del binario
    /// default: False
    pub switch_on: bool,
    /// campo 0x05 del binario
    /// default: 0
    pub switch_id: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveTitle {
    /// campo 0x01 del binario
    /// default: 0.0
    pub timestamp: f64,
    /// campo 0x0B del binario
    pub hero_name: String,
    /// campo 0x0C del binario
    /// default: 0
    pub hero_level: i32,
    /// campo 0x0D del binario
    /// default: 0
    pub hero_hp: i32,
    /// campo 0x15 del binario
    pub face1_name: String,
    /// campo 0x16 del binario
    /// default: 0
    pub face1_id: i32,
    /// campo 0x17 del binario
    pub face2_name: String,
    /// campo 0x18 del binario
    /// default: 0
    pub face2_id: i32,
    /// campo 0x19 del binario
    pub face3_name: String,
    /// campo 0x1A del binario
    /// default: 0
    pub face3_id: i32,
    /// campo 0x1B del binario
    pub face4_name: String,
    /// campo 0x1C del binario
    /// default: 0
    pub face4_id: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SaveVehicleLocation {
    /// campo 0x65 del binario
    /// default: 0
    pub vehicle: SaveVehicleLocationVehicleType,
    /// campo 0x6A del binario
    /// default: 0
    pub remaining_ascent: i32,
    /// campo 0x6B del binario
    /// default: 0
    pub remaining_descent: i32,
    /// campo 0x6F del binario
    pub orig_sprite_name: String,
    /// campo 0x70 del binario
    /// default: 0
    pub orig_sprite_id: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Skill {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario
    pub description: String,
    /// campo 0x03 del binario
    pub using_message1: String,
    /// campo 0x04 del binario
    pub using_message2: String,
    /// campo 0x07 del binario
    /// default: 0
    pub failure_message: i32,
    /// campo 0x08 del binario, se guarda aunque valga el default
    /// default: 0
    pub r#type: SkillType,
    /// campo 0x0B del binario
    /// default: 0
    pub sp_cost: i32,
    /// campo 0x0C del binario, se guarda aunque valga el default
    /// default: 0
    pub scope: SkillScope,
    /// campo 0x0D del binario
    /// default: 1
    pub switch_id: i32,
    /// campo 0x0E del binario
    /// default: 1
    pub animation_id: i32,
    /// campo 0x10 del binario, se guarda aunque valga el default
    pub sound_effect: Sound,
    /// campo 0x12 del binario
    /// default: True
    pub occasion_field: bool,
    /// campo 0x13 del binario
    /// default: False
    pub occasion_battle: bool,
    /// campo 0x15 del binario
    /// default: 0
    pub physical_rate: i32,
    /// campo 0x16 del binario
    /// default: 3
    pub magical_rate: i32,
    /// campo 0x17 del binario
    /// default: 4
    pub variance: i32,
    /// campo 0x18 del binario
    /// default: 0
    pub power: i32,
    /// campo 0x19 del binario
    /// default: 100
    pub hit: i32,
    /// campo 0x1F del binario
    /// default: False
    pub affect_hp: bool,
    /// campo 0x20 del binario
    /// default: False
    pub affect_sp: bool,
    /// campo 0x21 del binario
    /// default: False
    pub affect_attack: bool,
    /// campo 0x22 del binario
    /// default: False
    pub affect_defense: bool,
    /// campo 0x23 del binario
    /// default: False
    pub affect_spirit: bool,
    /// campo 0x24 del binario
    /// default: False
    pub affect_agility: bool,
    /// campo 0x25 del binario
    /// default: False
    pub absorb_damage: bool,
    /// campo 0x26 del binario
    /// default: False
    pub ignore_defense: bool,
    /// campo 0x2A del binario, se guarda aunque valga el default
    pub state_effects: Vec<bool>,
    /// campo 0x2C del binario, se guarda aunque valga el default
    pub attribute_effects: Vec<bool>,
    /// campo 0x2D del binario
    /// default: False
    pub affect_attr_defence: bool,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Sound {
    /// campo 0x01 del binario, se guarda aunque valga el default
    /// default: """(OFF)"""
    pub name: String,
    /// campo 0x03 del binario
    /// default: 100
    pub volume: i32,
    /// campo 0x04 del binario
    /// default: 100
    pub tempo: i32,
    /// campo 0x05 del binario
    /// default: 50
    pub balance: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Start {
    /// campo 0x01 del binario
    /// default: 0
    pub party_map_id: i32,
    /// campo 0x02 del binario
    /// default: 0
    pub party_x: i32,
    /// campo 0x03 del binario
    /// default: 0
    pub party_y: i32,
    /// campo 0x0B del binario
    /// default: 0
    pub boat_map_id: i32,
    /// campo 0x0C del binario
    /// default: 0
    pub boat_x: i32,
    /// campo 0x0D del binario
    /// default: 0
    pub boat_y: i32,
    /// campo 0x15 del binario
    /// default: 0
    pub ship_map_id: i32,
    /// campo 0x16 del binario
    /// default: 0
    pub ship_x: i32,
    /// campo 0x17 del binario
    /// default: 0
    pub ship_y: i32,
    /// campo 0x1F del binario
    /// default: 0
    pub airship_map_id: i32,
    /// campo 0x20 del binario
    /// default: 0
    pub airship_x: i32,
    /// campo 0x21 del binario
    /// default: 0
    pub airship_y: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct State {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario, se guarda aunque valga el default
    /// default: 0
    pub r#type: StatePersistence,
    /// campo 0x03 del binario
    /// default: 6
    pub color: i32,
    /// campo 0x04 del binario
    /// default: 50
    pub priority: i32,
    /// campo 0x05 del binario, se guarda aunque valga el default
    /// default: 0
    pub restriction: StateRestriction,
    /// campo 0x0B del binario
    /// default: 100
    pub a_rate: i32,
    /// campo 0x0C del binario
    /// default: 80
    pub b_rate: i32,
    /// campo 0x0D del binario
    /// default: 60
    pub c_rate: i32,
    /// campo 0x0E del binario
    /// default: 30
    pub d_rate: i32,
    /// campo 0x0F del binario
    /// default: 0
    pub e_rate: i32,
    /// campo 0x15 del binario
    /// default: 0
    pub hold_turn: i32,
    /// campo 0x16 del binario
    /// default: 0
    pub auto_release_prob: i32,
    /// campo 0x17 del binario
    /// default: 0
    pub release_by_damage: i32,
    /// campo 0x1F del binario
    /// default: False
    pub affect_attack: bool,
    /// campo 0x20 del binario
    /// default: False
    pub affect_defense: bool,
    /// campo 0x21 del binario
    /// default: False
    pub affect_spirit: bool,
    /// campo 0x22 del binario
    /// default: False
    pub affect_agility: bool,
    /// campo 0x23 del binario
    /// default: 100
    pub reduce_hit_ratio: i32,
    /// campo 0x29 del binario
    /// default: False
    pub restrict_skill: bool,
    /// campo 0x2A del binario
    /// default: 0
    pub restrict_skill_level: i32,
    /// campo 0x2B del binario
    /// default: False
    pub restrict_magic: bool,
    /// campo 0x2C del binario
    /// default: 0
    pub restrict_magic_level: i32,
    /// campo 0x2D del binario
    /// default: 0
    pub hp_change_type: StateChangeType,
    /// campo 0x2E del binario
    /// default: 0
    pub sp_change_type: StateChangeType,
    /// campo 0x33 del binario
    pub message_actor: String,
    /// campo 0x34 del binario
    pub message_enemy: String,
    /// campo 0x35 del binario
    pub message_already: String,
    /// campo 0x36 del binario
    pub message_affected: String,
    /// campo 0x37 del binario
    pub message_recovery: String,
    /// campo 0x3D del binario
    /// default: 0
    pub hp_change_max: i32,
    /// campo 0x3E del binario
    /// default: 0
    pub hp_change_val: i32,
    /// campo 0x3F del binario
    /// default: 0
    pub hp_change_map_steps: i32,
    /// campo 0x40 del binario
    /// default: 0
    pub hp_change_map_val: i32,
    /// campo 0x41 del binario
    /// default: 0
    pub sp_change_max: i32,
    /// campo 0x42 del binario
    /// default: 0
    pub sp_change_val: i32,
    /// campo 0x43 del binario
    /// default: 0
    pub sp_change_map_steps: i32,
    /// campo 0x44 del binario
    /// default: 0
    pub sp_change_map_val: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Switch {
    /// campo 0x01 del binario
    pub name: String,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct System {
    /// campo 0x0A del binario
    /// default: 0
    pub ldb_id: i32,
    /// campo 0x0B del binario
    pub boat_name: String,
    /// campo 0x0C del binario
    pub ship_name: String,
    /// campo 0x0D del binario
    pub airship_name: String,
    /// campo 0x0E del binario
    /// default: 0
    pub boat_index: i32,
    /// campo 0x0F del binario
    /// default: 0
    pub ship_index: i32,
    /// campo 0x10 del binario
    /// default: 0
    pub airship_index: i32,
    /// campo 0x11 del binario
    pub title_name: String,
    /// campo 0x12 del binario
    pub gameover_name: String,
    /// campo 0x13 del binario
    pub system_name: String,
    /// campo 0x16 del binario, se guarda aunque valga el default
    /// default: "[1]"
    pub party: Vec<i16>,
    /// campo 0x1F del binario, se guarda aunque valga el default
    pub title_music: Music,
    /// campo 0x20 del binario, se guarda aunque valga el default
    pub battle_music: Music,
    /// campo 0x21 del binario, se guarda aunque valga el default
    pub battle_end_music: Music,
    /// campo 0x22 del binario, se guarda aunque valga el default
    pub inn_music: Music,
    /// campo 0x23 del binario, se guarda aunque valga el default
    pub boat_music: Music,
    /// campo 0x24 del binario, se guarda aunque valga el default
    pub ship_music: Music,
    /// campo 0x25 del binario, se guarda aunque valga el default
    pub airship_music: Music,
    /// campo 0x26 del binario, se guarda aunque valga el default
    pub gameover_music: Music,
    /// campo 0x29 del binario, se guarda aunque valga el default
    pub cursor_se: Sound,
    /// campo 0x2A del binario, se guarda aunque valga el default
    pub decision_se: Sound,
    /// campo 0x2B del binario, se guarda aunque valga el default
    pub cancel_se: Sound,
    /// campo 0x2C del binario, se guarda aunque valga el default
    pub buzzer_se: Sound,
    /// campo 0x2D del binario, se guarda aunque valga el default
    pub battle_se: Sound,
    /// campo 0x2E del binario, se guarda aunque valga el default
    pub escape_se: Sound,
    /// campo 0x2F del binario, se guarda aunque valga el default
    pub enemy_attack_se: Sound,
    /// campo 0x30 del binario, se guarda aunque valga el default
    pub enemy_damaged_se: Sound,
    /// campo 0x31 del binario, se guarda aunque valga el default
    pub actor_damaged_se: Sound,
    /// campo 0x32 del binario, se guarda aunque valga el default
    pub dodge_se: Sound,
    /// campo 0x33 del binario, se guarda aunque valga el default
    pub enemy_death_se: Sound,
    /// campo 0x34 del binario, se guarda aunque valga el default
    pub item_se: Sound,
    /// campo 0x3D del binario, se guarda aunque valga el default
    /// default: 0
    pub transition_out: SystemFadeOut,
    /// campo 0x3E del binario, se guarda aunque valga el default
    /// default: 0
    pub transition_in: SystemFadeIn,
    /// campo 0x3F del binario, se guarda aunque valga el default
    /// default: 0
    pub battle_start_fadeout: SystemFadeOut,
    /// campo 0x40 del binario, se guarda aunque valga el default
    /// default: 0
    pub battle_start_fadein: SystemFadeIn,
    /// campo 0x41 del binario, se guarda aunque valga el default
    /// default: 0
    pub battle_end_fadeout: SystemFadeOut,
    /// campo 0x42 del binario, se guarda aunque valga el default
    /// default: 0
    pub battle_end_fadein: SystemFadeIn,
    /// campo 0x47 del binario
    /// default: 0
    pub message_stretch: SystemStretch,
    /// campo 0x48 del binario
    /// default: 0
    pub font_id: SystemFont,
    /// campo 0x51 del binario
    /// default: 0
    pub selected_condition: i32,
    /// campo 0x52 del binario, se guarda aunque valga el default
    /// default: 0
    pub selected_hero: i32,
    /// campo 0x54 del binario
    pub battletest_background: String,
    /// campo 0x55 del binario, se guarda aunque valga el default
    pub battletest_data: Vec<TestBattler>,
    /// campo 0x5B del binario
    /// default: 0
    pub save_count: i32,
    /// campo 0x5E del binario
    /// default: 0
    pub battletest_terrain: i32,
    /// campo 0x5F del binario
    /// default: 0
    pub battletest_formation: SystemBattleFormation,
    /// campo 0x60 del binario
    /// default: 0
    pub battletest_condition: SystemBattleCondition,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Terms {
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub encounter: String,
    /// campo 0x02 del binario, se guarda aunque valga el default
    pub special_combat: String,
    /// campo 0x03 del binario, se guarda aunque valga el default
    pub escape_success: String,
    /// campo 0x04 del binario, se guarda aunque valga el default
    pub escape_failure: String,
    /// campo 0x05 del binario, se guarda aunque valga el default
    pub victory: String,
    /// campo 0x06 del binario, se guarda aunque valga el default
    pub defeat: String,
    /// campo 0x07 del binario, se guarda aunque valga el default
    pub exp_received: String,
    /// campo 0x08 del binario, se guarda aunque valga el default
    pub gold_recieved_a: String,
    /// campo 0x09 del binario, se guarda aunque valga el default
    pub gold_recieved_b: String,
    /// campo 0x0A del binario, se guarda aunque valga el default
    pub item_recieved: String,
    /// campo 0x0B del binario, se guarda aunque valga el default
    pub attacking: String,
    /// campo 0x0C del binario, se guarda aunque valga el default
    pub enemy_critical: String,
    /// campo 0x0D del binario, se guarda aunque valga el default
    pub actor_critical: String,
    /// campo 0x0E del binario, se guarda aunque valga el default
    pub defending: String,
    /// campo 0x0F del binario, se guarda aunque valga el default
    pub observing: String,
    /// campo 0x10 del binario, se guarda aunque valga el default
    pub focus: String,
    /// campo 0x11 del binario, se guarda aunque valga el default
    pub autodestruction: String,
    /// campo 0x12 del binario, se guarda aunque valga el default
    pub enemy_escape: String,
    /// campo 0x13 del binario, se guarda aunque valga el default
    pub enemy_transform: String,
    /// campo 0x14 del binario, se guarda aunque valga el default
    pub enemy_damaged: String,
    /// campo 0x15 del binario, se guarda aunque valga el default
    pub enemy_undamaged: String,
    /// campo 0x16 del binario, se guarda aunque valga el default
    pub actor_damaged: String,
    /// campo 0x17 del binario, se guarda aunque valga el default
    pub actor_undamaged: String,
    /// campo 0x18 del binario, se guarda aunque valga el default
    pub skill_failure_a: String,
    /// campo 0x19 del binario, se guarda aunque valga el default
    pub skill_failure_b: String,
    /// campo 0x1A del binario, se guarda aunque valga el default
    pub skill_failure_c: String,
    /// campo 0x1B del binario, se guarda aunque valga el default
    pub dodge: String,
    /// campo 0x1C del binario, se guarda aunque valga el default
    pub use_item: String,
    /// campo 0x1D del binario, se guarda aunque valga el default
    pub hp_recovery: String,
    /// campo 0x1E del binario, se guarda aunque valga el default
    pub parameter_increase: String,
    /// campo 0x1F del binario, se guarda aunque valga el default
    pub parameter_decrease: String,
    /// campo 0x20 del binario, se guarda aunque valga el default
    pub enemy_hp_absorbed: String,
    /// campo 0x21 del binario, se guarda aunque valga el default
    pub actor_hp_absorbed: String,
    /// campo 0x22 del binario, se guarda aunque valga el default
    pub resistance_increase: String,
    /// campo 0x23 del binario, se guarda aunque valga el default
    pub resistance_decrease: String,
    /// campo 0x24 del binario, se guarda aunque valga el default
    pub level_up: String,
    /// campo 0x25 del binario, se guarda aunque valga el default
    pub skill_learned: String,
    /// campo 0x29 del binario, se guarda aunque valga el default
    pub shop_greeting1: String,
    /// campo 0x2A del binario, se guarda aunque valga el default
    pub shop_regreeting1: String,
    /// campo 0x2B del binario, se guarda aunque valga el default
    pub shop_buy1: String,
    /// campo 0x2C del binario, se guarda aunque valga el default
    pub shop_sell1: String,
    /// campo 0x2D del binario, se guarda aunque valga el default
    pub shop_leave1: String,
    /// campo 0x2E del binario, se guarda aunque valga el default
    pub shop_buy_select1: String,
    /// campo 0x2F del binario, se guarda aunque valga el default
    pub shop_buy_number1: String,
    /// campo 0x30 del binario, se guarda aunque valga el default
    pub shop_purchased1: String,
    /// campo 0x31 del binario, se guarda aunque valga el default
    pub shop_sell_select1: String,
    /// campo 0x32 del binario, se guarda aunque valga el default
    pub shop_sell_number1: String,
    /// campo 0x33 del binario, se guarda aunque valga el default
    pub shop_sold1: String,
    /// campo 0x36 del binario, se guarda aunque valga el default
    pub shop_greeting2: String,
    /// campo 0x37 del binario, se guarda aunque valga el default
    pub shop_regreeting2: String,
    /// campo 0x38 del binario, se guarda aunque valga el default
    pub shop_buy2: String,
    /// campo 0x39 del binario, se guarda aunque valga el default
    pub shop_sell2: String,
    /// campo 0x3A del binario, se guarda aunque valga el default
    pub shop_leave2: String,
    /// campo 0x3B del binario, se guarda aunque valga el default
    pub shop_buy_select2: String,
    /// campo 0x3C del binario, se guarda aunque valga el default
    pub shop_buy_number2: String,
    /// campo 0x3D del binario, se guarda aunque valga el default
    pub shop_purchased2: String,
    /// campo 0x3E del binario, se guarda aunque valga el default
    pub shop_sell_select2: String,
    /// campo 0x3F del binario, se guarda aunque valga el default
    pub shop_sell_number2: String,
    /// campo 0x40 del binario, se guarda aunque valga el default
    pub shop_sold2: String,
    /// campo 0x43 del binario, se guarda aunque valga el default
    pub shop_greeting3: String,
    /// campo 0x44 del binario, se guarda aunque valga el default
    pub shop_regreeting3: String,
    /// campo 0x45 del binario, se guarda aunque valga el default
    pub shop_buy3: String,
    /// campo 0x46 del binario, se guarda aunque valga el default
    pub shop_sell3: String,
    /// campo 0x47 del binario, se guarda aunque valga el default
    pub shop_leave3: String,
    /// campo 0x48 del binario, se guarda aunque valga el default
    pub shop_buy_select3: String,
    /// campo 0x49 del binario, se guarda aunque valga el default
    pub shop_buy_number3: String,
    /// campo 0x4A del binario, se guarda aunque valga el default
    pub shop_purchased3: String,
    /// campo 0x4B del binario, se guarda aunque valga el default
    pub shop_sell_select3: String,
    /// campo 0x4C del binario, se guarda aunque valga el default
    pub shop_sell_number3: String,
    /// campo 0x4D del binario, se guarda aunque valga el default
    pub shop_sold3: String,
    /// campo 0x50 del binario, se guarda aunque valga el default
    pub inn_a_greeting_1: String,
    /// campo 0x51 del binario, se guarda aunque valga el default
    pub inn_a_greeting_2: String,
    /// campo 0x52 del binario, se guarda aunque valga el default
    pub inn_a_greeting_3: String,
    /// campo 0x53 del binario, se guarda aunque valga el default
    pub inn_a_accept: String,
    /// campo 0x54 del binario, se guarda aunque valga el default
    pub inn_a_cancel: String,
    /// campo 0x55 del binario, se guarda aunque valga el default
    pub inn_b_greeting_1: String,
    /// campo 0x56 del binario, se guarda aunque valga el default
    pub inn_b_greeting_2: String,
    /// campo 0x57 del binario, se guarda aunque valga el default
    pub inn_b_greeting_3: String,
    /// campo 0x58 del binario, se guarda aunque valga el default
    pub inn_b_accept: String,
    /// campo 0x59 del binario, se guarda aunque valga el default
    pub inn_b_cancel: String,
    /// campo 0x5C del binario, se guarda aunque valga el default
    pub possessed_items: String,
    /// campo 0x5D del binario, se guarda aunque valga el default
    pub equipped_items: String,
    /// campo 0x5F del binario, se guarda aunque valga el default
    pub gold: String,
    /// campo 0x65 del binario, se guarda aunque valga el default
    pub battle_fight: String,
    /// campo 0x66 del binario, se guarda aunque valga el default
    pub battle_auto: String,
    /// campo 0x67 del binario, se guarda aunque valga el default
    pub battle_escape: String,
    /// campo 0x68 del binario, se guarda aunque valga el default
    pub command_attack: String,
    /// campo 0x69 del binario, se guarda aunque valga el default
    pub command_defend: String,
    /// campo 0x6A del binario, se guarda aunque valga el default
    pub command_item: String,
    /// campo 0x6B del binario, se guarda aunque valga el default
    pub command_skill: String,
    /// campo 0x6C del binario, se guarda aunque valga el default
    pub menu_equipment: String,
    /// campo 0x6E del binario, se guarda aunque valga el default
    pub menu_save: String,
    /// campo 0x70 del binario, se guarda aunque valga el default
    pub menu_quit: String,
    /// campo 0x72 del binario, se guarda aunque valga el default
    pub new_game: String,
    /// campo 0x73 del binario, se guarda aunque valga el default
    pub load_game: String,
    /// campo 0x75 del binario, se guarda aunque valga el default
    pub exit_game: String,
    /// campo 0x7B del binario, se guarda aunque valga el default
    pub level: String,
    /// campo 0x7C del binario, se guarda aunque valga el default
    pub health_points: String,
    /// campo 0x7D del binario, se guarda aunque valga el default
    pub spirit_points: String,
    /// campo 0x7E del binario, se guarda aunque valga el default
    pub normal_status: String,
    /// campo 0x7F del binario, se guarda aunque valga el default
    pub exp_short: String,
    /// campo 0x80 del binario, se guarda aunque valga el default
    pub lvl_short: String,
    /// campo 0x81 del binario, se guarda aunque valga el default
    pub hp_short: String,
    /// campo 0x82 del binario, se guarda aunque valga el default
    pub sp_short: String,
    /// campo 0x83 del binario, se guarda aunque valga el default
    pub sp_cost: String,
    /// campo 0x84 del binario, se guarda aunque valga el default
    pub attack: String,
    /// campo 0x85 del binario, se guarda aunque valga el default
    pub defense: String,
    /// campo 0x86 del binario, se guarda aunque valga el default
    pub spirit: String,
    /// campo 0x87 del binario, se guarda aunque valga el default
    pub agility: String,
    /// campo 0x88 del binario, se guarda aunque valga el default
    pub weapon: String,
    /// campo 0x89 del binario, se guarda aunque valga el default
    pub shield: String,
    /// campo 0x8A del binario, se guarda aunque valga el default
    pub armor: String,
    /// campo 0x8B del binario, se guarda aunque valga el default
    pub helmet: String,
    /// campo 0x8C del binario, se guarda aunque valga el default
    pub accessory: String,
    /// campo 0x92 del binario, se guarda aunque valga el default
    pub save_game_message: String,
    /// campo 0x93 del binario, se guarda aunque valga el default
    pub load_game_message: String,
    /// campo 0x94 del binario, se guarda aunque valga el default
    pub file: String,
    /// campo 0x97 del binario, se guarda aunque valga el default
    pub exit_game_message: String,
    /// campo 0x98 del binario, se guarda aunque valga el default
    pub yes: String,
    /// campo 0x99 del binario, se guarda aunque valga el default
    pub no: String,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Terrain {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario
    /// default: 0
    pub damage: i32,
    /// campo 0x03 del binario
    /// default: 100
    pub encounter_rate: i32,
    /// campo 0x04 del binario
    pub background_name: String,
    /// campo 0x05 del binario
    /// default: False
    pub boat_pass: bool,
    /// campo 0x06 del binario
    /// default: False
    pub ship_pass: bool,
    /// campo 0x07 del binario
    /// default: True
    pub airship_pass: bool,
    /// campo 0x09 del binario
    /// default: True
    pub airship_land: bool,
    /// campo 0x0B del binario, se guarda aunque valga el default
    /// default: 0
    pub bush_depth: TerrainBushDepth,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct TestBattler {
    /// campo 0x01 del binario
    /// default: 1
    pub actor_id: i32,
    /// campo 0x02 del binario
    /// default: 1
    pub level: i32,
    /// campo 0x0B del binario
    /// default: 0
    pub weapon_id: i32,
    /// campo 0x0C del binario
    /// default: 0
    pub shield_id: i32,
    /// campo 0x0D del binario
    /// default: 0
    pub armor_id: i32,
    /// campo 0x0E del binario
    /// default: 0
    pub helmet_id: i32,
    /// campo 0x0F del binario
    /// default: 0
    pub accessory_id: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct TreeMap {
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Troop {
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario, se guarda aunque valga el default
    pub members: Vec<TroopMember>,
    /// campo 0x05 del binario, se guarda aunque valga el default
    pub terrain_set: Vec<bool>,
    /// campo 0x0B del binario, se guarda aunque valga el default
    pub pages: Vec<TroopPage>,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct TroopMember {
    /// campo 0x01 del binario
    /// default: 1
    pub enemy_id: i32,
    /// campo 0x02 del binario
    /// default: 0
    pub x: i32,
    /// campo 0x03 del binario
    /// default: 0
    pub y: i32,
    /// campo 0x04 del binario
    /// default: False
    pub invisible: bool,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct TroopPage {
    /// campo 0x02 del binario, se guarda aunque valga el default
    pub condition: TroopPageCondition,
    /// campo 0x0C del binario, se guarda aunque valga el default
    pub event_commands: Vec<EventCommand>,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct TroopPageCondition {
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub flags: u32,
    /// campo 0x02 del binario
    /// default: 1
    pub switch_a_id: i32,
    /// campo 0x03 del binario
    /// default: 1
    pub switch_b_id: i32,
    /// campo 0x04 del binario
    /// default: 1
    pub variable_id: i32,
    /// campo 0x05 del binario
    /// default: 0
    pub variable_value: i32,
    /// campo 0x06 del binario
    /// default: 0
    pub turn_a: i32,
    /// campo 0x07 del binario
    /// default: 0
    pub turn_b: i32,
    /// campo 0x08 del binario
    /// default: 0
    pub fatigue_min: i32,
    /// campo 0x09 del binario
    /// default: 100
    pub fatigue_max: i32,
    /// campo 0x0A del binario
    /// default: 0
    pub enemy_id: i32,
    /// campo 0x0B del binario
    /// default: 0
    pub enemy_hp_min: i32,
    /// campo 0x0C del binario
    /// default: 100
    pub enemy_hp_max: i32,
    /// campo 0x0D del binario
    /// default: 1
    pub actor_id: i32,
    /// campo 0x0E del binario
    /// default: 0
    pub actor_hp_min: i32,
    /// campo 0x0F del binario
    /// default: 100
    pub actor_hp_max: i32,
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Variable {
    /// campo 0x01 del binario
    pub name: String,
}

