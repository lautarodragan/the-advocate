//! El esquema de los archivos de RPG Maker 2000, y su códec.
//!
//! **Generado por `cargo xtask generar`, y commiteado a propósito.**
//! No se edita a mano: lo que se edita es el generador o el CSV de
//! arriba. Ver `xtask/src/main.rs` para el porqué.
//!
//! Sale de las tablas de liblcf (/extras/ref/liblcf), que es de donde el ecosistema
//! entero saca los nombres: en el binario no hay ninguno, sólo
//! índices de campo.

#![allow(dead_code, unused_variables, clippy::all)]

use crate::lcf::*;
use serde::{Deserialize, Serialize};

/// Generado desde `constants.csv`.
#[allow(non_upper_case_globals)]
pub const kDeathID: i32 = 1;

/// Generado desde `constants.csv`.
#[allow(non_upper_case_globals)]
pub const kPanXDefault: i32 = 9 * 256;

/// Generado desde `constants.csv`.
#[allow(non_upper_case_globals)]
pub const kPanYDefault: i32 = 7 * 256;

/// Generado desde `constants.csv`.
#[allow(non_upper_case_globals)]
pub const kPanSpeedDefault: i32 = 2 << 3;

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AnimationPosition {
    #[serde(rename = "up")]
    Up,
    #[serde(rename = "middle")]
    Middle,
    #[serde(rename = "down")]
    Down,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl AnimationPosition {
    pub fn a_i32(self) -> i32 {
        match self {
            AnimationPosition::Up => 0,
            AnimationPosition::Middle => 1,
            AnimationPosition::Down => 2,
            AnimationPosition::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => AnimationPosition::Up,
            1 => AnimationPosition::Middle,
            2 => AnimationPosition::Down,
            v => AnimationPosition::Otro(v),
        }
    }
}

impl Default for AnimationPosition {
    fn default() -> Self { AnimationPosition::Up }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AnimationScope {
    #[serde(rename = "target")]
    Target,
    #[serde(rename = "screen")]
    Screen,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl AnimationScope {
    pub fn a_i32(self) -> i32 {
        match self {
            AnimationScope::Target => 0,
            AnimationScope::Screen => 1,
            AnimationScope::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => AnimationScope::Target,
            1 => AnimationScope::Screen,
            v => AnimationScope::Otro(v),
        }
    }
}

impl Default for AnimationScope {
    fn default() -> Self { AnimationScope::Target }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AnimationTimingFlashScope {
    #[serde(rename = "nothing")]
    Nothing,
    #[serde(rename = "target")]
    Target,
    #[serde(rename = "screen")]
    Screen,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl AnimationTimingFlashScope {
    pub fn a_i32(self) -> i32 {
        match self {
            AnimationTimingFlashScope::Nothing => 0,
            AnimationTimingFlashScope::Target => 1,
            AnimationTimingFlashScope::Screen => 2,
            AnimationTimingFlashScope::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => AnimationTimingFlashScope::Nothing,
            1 => AnimationTimingFlashScope::Target,
            2 => AnimationTimingFlashScope::Screen,
            v => AnimationTimingFlashScope::Otro(v),
        }
    }
}

impl Default for AnimationTimingFlashScope {
    fn default() -> Self { AnimationTimingFlashScope::Nothing }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AnimationTimingScreenShake {
    #[serde(rename = "nothing")]
    Nothing,
    #[serde(rename = "target")]
    Target,
    #[serde(rename = "screen")]
    Screen,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl AnimationTimingScreenShake {
    pub fn a_i32(self) -> i32 {
        match self {
            AnimationTimingScreenShake::Nothing => 0,
            AnimationTimingScreenShake::Target => 1,
            AnimationTimingScreenShake::Screen => 2,
            AnimationTimingScreenShake::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => AnimationTimingScreenShake::Nothing,
            1 => AnimationTimingScreenShake::Target,
            2 => AnimationTimingScreenShake::Screen,
            v => AnimationTimingScreenShake::Otro(v),
        }
    }
}

impl Default for AnimationTimingScreenShake {
    fn default() -> Self { AnimationTimingScreenShake::Nothing }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AttributeType {
    #[serde(rename = "physical")]
    Physical,
    #[serde(rename = "magical")]
    Magical,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl AttributeType {
    pub fn a_i32(self) -> i32 {
        match self {
            AttributeType::Physical => 0,
            AttributeType::Magical => 1,
            AttributeType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => AttributeType::Physical,
            1 => AttributeType::Magical,
            v => AttributeType::Otro(v),
        }
    }
}

impl Default for AttributeType {
    fn default() -> Self { AttributeType::Physical }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandType {
    #[serde(rename = "attack")]
    Attack,
    #[serde(rename = "skill")]
    Skill,
    #[serde(rename = "subskill")]
    Subskill,
    #[serde(rename = "defense")]
    Defense,
    #[serde(rename = "item")]
    Item,
    #[serde(rename = "escape")]
    Escape,
    #[serde(rename = "special")]
    Special,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattleCommandType {
    pub fn a_i32(self) -> i32 {
        match self {
            BattleCommandType::Attack => 0,
            BattleCommandType::Skill => 1,
            BattleCommandType::Subskill => 2,
            BattleCommandType::Defense => 3,
            BattleCommandType::Item => 4,
            BattleCommandType::Escape => 5,
            BattleCommandType::Special => 6,
            BattleCommandType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattleCommandType::Attack,
            1 => BattleCommandType::Skill,
            2 => BattleCommandType::Subskill,
            3 => BattleCommandType::Defense,
            4 => BattleCommandType::Item,
            5 => BattleCommandType::Escape,
            6 => BattleCommandType::Special,
            v => BattleCommandType::Otro(v),
        }
    }
}

impl Default for BattleCommandType {
    fn default() -> Self { BattleCommandType::Attack }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandsBattleType {
    #[serde(rename = "traditional")]
    Traditional,
    #[serde(rename = "alternative")]
    Alternative,
    #[serde(rename = "gauge")]
    Gauge,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattleCommandsBattleType {
    pub fn a_i32(self) -> i32 {
        match self {
            BattleCommandsBattleType::Traditional => 0,
            BattleCommandsBattleType::Alternative => 1,
            BattleCommandsBattleType::Gauge => 2,
            BattleCommandsBattleType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattleCommandsBattleType::Traditional,
            1 => BattleCommandsBattleType::Alternative,
            2 => BattleCommandsBattleType::Gauge,
            v => BattleCommandsBattleType::Otro(v),
        }
    }
}

impl Default for BattleCommandsBattleType {
    fn default() -> Self { BattleCommandsBattleType::Traditional }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandsFacing {
    #[serde(rename = "retain")]
    Retain,
    #[serde(rename = "up")]
    Up,
    #[serde(rename = "right")]
    Right,
    #[serde(rename = "down")]
    Down,
    #[serde(rename = "left")]
    Left,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattleCommandsFacing {
    pub fn a_i32(self) -> i32 {
        match self {
            BattleCommandsFacing::Retain => 0,
            BattleCommandsFacing::Up => 1,
            BattleCommandsFacing::Right => 2,
            BattleCommandsFacing::Down => 3,
            BattleCommandsFacing::Left => 4,
            BattleCommandsFacing::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattleCommandsFacing::Retain,
            1 => BattleCommandsFacing::Up,
            2 => BattleCommandsFacing::Right,
            3 => BattleCommandsFacing::Down,
            4 => BattleCommandsFacing::Left,
            v => BattleCommandsFacing::Otro(v),
        }
    }
}

impl Default for BattleCommandsFacing {
    fn default() -> Self { BattleCommandsFacing::Retain }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandsPlacement {
    #[serde(rename = "manual")]
    Manual,
    #[serde(rename = "automatic")]
    Automatic,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattleCommandsPlacement {
    pub fn a_i32(self) -> i32 {
        match self {
            BattleCommandsPlacement::Manual => 0,
            BattleCommandsPlacement::Automatic => 1,
            BattleCommandsPlacement::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattleCommandsPlacement::Manual,
            1 => BattleCommandsPlacement::Automatic,
            v => BattleCommandsPlacement::Otro(v),
        }
    }
}

impl Default for BattleCommandsPlacement {
    fn default() -> Self { BattleCommandsPlacement::Manual }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandsRowShown {
    #[serde(rename = "front")]
    Front,
    #[serde(rename = "back")]
    Back,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattleCommandsRowShown {
    pub fn a_i32(self) -> i32 {
        match self {
            BattleCommandsRowShown::Front => 0,
            BattleCommandsRowShown::Back => 1,
            BattleCommandsRowShown::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattleCommandsRowShown::Front,
            1 => BattleCommandsRowShown::Back,
            v => BattleCommandsRowShown::Otro(v),
        }
    }
}

impl Default for BattleCommandsRowShown {
    fn default() -> Self { BattleCommandsRowShown::Front }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandsTransparency {
    #[serde(rename = "opaque")]
    Opaque,
    #[serde(rename = "transparent")]
    Transparent,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattleCommandsTransparency {
    pub fn a_i32(self) -> i32 {
        match self {
            BattleCommandsTransparency::Opaque => 0,
            BattleCommandsTransparency::Transparent => 1,
            BattleCommandsTransparency::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattleCommandsTransparency::Opaque,
            1 => BattleCommandsTransparency::Transparent,
            v => BattleCommandsTransparency::Otro(v),
        }
    }
}

impl Default for BattleCommandsTransparency {
    fn default() -> Self { BattleCommandsTransparency::Opaque }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattleCommandsWindowSize {
    #[serde(rename = "large")]
    Large,
    #[serde(rename = "small")]
    Small,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattleCommandsWindowSize {
    pub fn a_i32(self) -> i32 {
        match self {
            BattleCommandsWindowSize::Large => 0,
            BattleCommandsWindowSize::Small => 1,
            BattleCommandsWindowSize::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattleCommandsWindowSize::Large,
            1 => BattleCommandsWindowSize::Small,
            v => BattleCommandsWindowSize::Otro(v),
        }
    }
}

impl Default for BattleCommandsWindowSize {
    fn default() -> Self { BattleCommandsWindowSize::Large }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationItemSkillAfterimage {
    #[serde(rename = "none")]
    None,
    #[serde(rename = "add")]
    Add,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattlerAnimationItemSkillAfterimage {
    pub fn a_i32(self) -> i32 {
        match self {
            BattlerAnimationItemSkillAfterimage::None => 0,
            BattlerAnimationItemSkillAfterimage::Add => 1,
            BattlerAnimationItemSkillAfterimage::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattlerAnimationItemSkillAfterimage::None,
            1 => BattlerAnimationItemSkillAfterimage::Add,
            v => BattlerAnimationItemSkillAfterimage::Otro(v),
        }
    }
}

impl Default for BattlerAnimationItemSkillAfterimage {
    fn default() -> Self { BattlerAnimationItemSkillAfterimage::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationItemSkillAnimType {
    #[serde(rename = "weapon")]
    Weapon,
    #[serde(rename = "battle")]
    Battle,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattlerAnimationItemSkillAnimType {
    pub fn a_i32(self) -> i32 {
        match self {
            BattlerAnimationItemSkillAnimType::Weapon => 0,
            BattlerAnimationItemSkillAnimType::Battle => 1,
            BattlerAnimationItemSkillAnimType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattlerAnimationItemSkillAnimType::Weapon,
            1 => BattlerAnimationItemSkillAnimType::Battle,
            v => BattlerAnimationItemSkillAnimType::Otro(v),
        }
    }
}

impl Default for BattlerAnimationItemSkillAnimType {
    fn default() -> Self { BattlerAnimationItemSkillAnimType::Weapon }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationItemSkillMovement {
    #[serde(rename = "none")]
    None,
    #[serde(rename = "step")]
    Step,
    #[serde(rename = "jump")]
    Jump,
    #[serde(rename = "move")]
    Move,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattlerAnimationItemSkillMovement {
    pub fn a_i32(self) -> i32 {
        match self {
            BattlerAnimationItemSkillMovement::None => 0,
            BattlerAnimationItemSkillMovement::Step => 1,
            BattlerAnimationItemSkillMovement::Jump => 2,
            BattlerAnimationItemSkillMovement::Move => 3,
            BattlerAnimationItemSkillMovement::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattlerAnimationItemSkillMovement::None,
            1 => BattlerAnimationItemSkillMovement::Step,
            2 => BattlerAnimationItemSkillMovement::Jump,
            3 => BattlerAnimationItemSkillMovement::Move,
            v => BattlerAnimationItemSkillMovement::Otro(v),
        }
    }
}

impl Default for BattlerAnimationItemSkillMovement {
    fn default() -> Self { BattlerAnimationItemSkillMovement::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationItemSkillSpeed {
    #[serde(rename = "fast")]
    Fast,
    #[serde(rename = "medium")]
    Medium,
    #[serde(rename = "slow")]
    Slow,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattlerAnimationItemSkillSpeed {
    pub fn a_i32(self) -> i32 {
        match self {
            BattlerAnimationItemSkillSpeed::Fast => 0,
            BattlerAnimationItemSkillSpeed::Medium => 1,
            BattlerAnimationItemSkillSpeed::Slow => 2,
            BattlerAnimationItemSkillSpeed::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattlerAnimationItemSkillSpeed::Fast,
            1 => BattlerAnimationItemSkillSpeed::Medium,
            2 => BattlerAnimationItemSkillSpeed::Slow,
            v => BattlerAnimationItemSkillSpeed::Otro(v),
        }
    }
}

impl Default for BattlerAnimationItemSkillSpeed {
    fn default() -> Self { BattlerAnimationItemSkillSpeed::Fast }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationPose {
    #[serde(rename = "Idle")]
    Idle,
    #[serde(rename = "AttackRight")]
    AttackRight,
    #[serde(rename = "AttackLeft")]
    AttackLeft,
    #[serde(rename = "Skill")]
    Skill,
    #[serde(rename = "Dead")]
    Dead,
    #[serde(rename = "Damage")]
    Damage,
    #[serde(rename = "Dazed")]
    Dazed,
    #[serde(rename = "Defend")]
    Defend,
    #[serde(rename = "WalkLeft")]
    WalkLeft,
    #[serde(rename = "WalkRight")]
    WalkRight,
    #[serde(rename = "Victory")]
    Victory,
    #[serde(rename = "Item")]
    Item,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattlerAnimationPose {
    pub fn a_i32(self) -> i32 {
        match self {
            BattlerAnimationPose::Idle => 0,
            BattlerAnimationPose::AttackRight => 1,
            BattlerAnimationPose::AttackLeft => 2,
            BattlerAnimationPose::Skill => 3,
            BattlerAnimationPose::Dead => 4,
            BattlerAnimationPose::Damage => 5,
            BattlerAnimationPose::Dazed => 6,
            BattlerAnimationPose::Defend => 7,
            BattlerAnimationPose::WalkLeft => 8,
            BattlerAnimationPose::WalkRight => 9,
            BattlerAnimationPose::Victory => 10,
            BattlerAnimationPose::Item => 11,
            BattlerAnimationPose::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattlerAnimationPose::Idle,
            1 => BattlerAnimationPose::AttackRight,
            2 => BattlerAnimationPose::AttackLeft,
            3 => BattlerAnimationPose::Skill,
            4 => BattlerAnimationPose::Dead,
            5 => BattlerAnimationPose::Damage,
            6 => BattlerAnimationPose::Dazed,
            7 => BattlerAnimationPose::Defend,
            8 => BattlerAnimationPose::WalkLeft,
            9 => BattlerAnimationPose::WalkRight,
            10 => BattlerAnimationPose::Victory,
            11 => BattlerAnimationPose::Item,
            v => BattlerAnimationPose::Otro(v),
        }
    }
}

impl Default for BattlerAnimationPose {
    fn default() -> Self { BattlerAnimationPose::Idle }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationPoseAnimType {
    #[serde(rename = "character")]
    Character,
    #[serde(rename = "battle")]
    Battle,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattlerAnimationPoseAnimType {
    pub fn a_i32(self) -> i32 {
        match self {
            BattlerAnimationPoseAnimType::Character => 0,
            BattlerAnimationPoseAnimType::Battle => 1,
            BattlerAnimationPoseAnimType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => BattlerAnimationPoseAnimType::Character,
            1 => BattlerAnimationPoseAnimType::Battle,
            v => BattlerAnimationPoseAnimType::Otro(v),
        }
    }
}

impl Default for BattlerAnimationPoseAnimType {
    fn default() -> Self { BattlerAnimationPoseAnimType::Character }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BattlerAnimationSpeed {
    #[serde(rename = "slow")]
    Slow,
    #[serde(rename = "medium")]
    Medium,
    #[serde(rename = "fast")]
    Fast,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl BattlerAnimationSpeed {
    pub fn a_i32(self) -> i32 {
        match self {
            BattlerAnimationSpeed::Slow => 20,
            BattlerAnimationSpeed::Medium => 14,
            BattlerAnimationSpeed::Fast => 8,
            BattlerAnimationSpeed::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            20 => BattlerAnimationSpeed::Slow,
            14 => BattlerAnimationSpeed::Medium,
            8 => BattlerAnimationSpeed::Fast,
            v => BattlerAnimationSpeed::Otro(v),
        }
    }
}

impl Default for BattlerAnimationSpeed {
    fn default() -> Self { BattlerAnimationSpeed::Slow }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ChipsetAnimType {
    #[serde(rename = "reciprocating")]
    Reciprocating,
    #[serde(rename = "cyclic")]
    Cyclic,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl ChipsetAnimType {
    pub fn a_i32(self) -> i32 {
        match self {
            ChipsetAnimType::Reciprocating => 0,
            ChipsetAnimType::Cyclic => 1,
            ChipsetAnimType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => ChipsetAnimType::Reciprocating,
            1 => ChipsetAnimType::Cyclic,
            v => ChipsetAnimType::Otro(v),
        }
    }
}

impl Default for ChipsetAnimType {
    fn default() -> Self { ChipsetAnimType::Reciprocating }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CommonEventTrigger {
    #[serde(rename = "automatic")]
    Automatic,
    #[serde(rename = "parallel")]
    Parallel,
    #[serde(rename = "call")]
    Call,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl CommonEventTrigger {
    pub fn a_i32(self) -> i32 {
        match self {
            CommonEventTrigger::Automatic => 3,
            CommonEventTrigger::Parallel => 4,
            CommonEventTrigger::Call => 5,
            CommonEventTrigger::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            3 => CommonEventTrigger::Automatic,
            4 => CommonEventTrigger::Parallel,
            5 => CommonEventTrigger::Call,
            v => CommonEventTrigger::Otro(v),
        }
    }
}

impl Default for CommonEventTrigger {
    fn default() -> Self { CommonEventTrigger::Automatic }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EnemyActionBasic {
    #[serde(rename = "attack")]
    Attack,
    #[serde(rename = "dual_attack")]
    DualAttack,
    #[serde(rename = "defense")]
    Defense,
    #[serde(rename = "observe")]
    Observe,
    #[serde(rename = "charge")]
    Charge,
    #[serde(rename = "autodestruction")]
    Autodestruction,
    #[serde(rename = "escape")]
    Escape,
    #[serde(rename = "nothing")]
    Nothing,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl EnemyActionBasic {
    pub fn a_i32(self) -> i32 {
        match self {
            EnemyActionBasic::Attack => 0,
            EnemyActionBasic::DualAttack => 1,
            EnemyActionBasic::Defense => 2,
            EnemyActionBasic::Observe => 3,
            EnemyActionBasic::Charge => 4,
            EnemyActionBasic::Autodestruction => 5,
            EnemyActionBasic::Escape => 6,
            EnemyActionBasic::Nothing => 7,
            EnemyActionBasic::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => EnemyActionBasic::Attack,
            1 => EnemyActionBasic::DualAttack,
            2 => EnemyActionBasic::Defense,
            3 => EnemyActionBasic::Observe,
            4 => EnemyActionBasic::Charge,
            5 => EnemyActionBasic::Autodestruction,
            6 => EnemyActionBasic::Escape,
            7 => EnemyActionBasic::Nothing,
            v => EnemyActionBasic::Otro(v),
        }
    }
}

impl Default for EnemyActionBasic {
    fn default() -> Self { EnemyActionBasic::Attack }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EnemyActionConditionType {
    #[serde(rename = "always")]
    Always,
    #[serde(rename = "switch")]
    Switch,
    #[serde(rename = "turn")]
    Turn,
    #[serde(rename = "actors")]
    Actors,
    #[serde(rename = "hp")]
    Hp,
    #[serde(rename = "sp")]
    Sp,
    #[serde(rename = "party_lvl")]
    PartyLvl,
    #[serde(rename = "party_fatigue")]
    PartyFatigue,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl EnemyActionConditionType {
    pub fn a_i32(self) -> i32 {
        match self {
            EnemyActionConditionType::Always => 0,
            EnemyActionConditionType::Switch => 1,
            EnemyActionConditionType::Turn => 2,
            EnemyActionConditionType::Actors => 3,
            EnemyActionConditionType::Hp => 4,
            EnemyActionConditionType::Sp => 5,
            EnemyActionConditionType::PartyLvl => 6,
            EnemyActionConditionType::PartyFatigue => 7,
            EnemyActionConditionType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => EnemyActionConditionType::Always,
            1 => EnemyActionConditionType::Switch,
            2 => EnemyActionConditionType::Turn,
            3 => EnemyActionConditionType::Actors,
            4 => EnemyActionConditionType::Hp,
            5 => EnemyActionConditionType::Sp,
            6 => EnemyActionConditionType::PartyLvl,
            7 => EnemyActionConditionType::PartyFatigue,
            v => EnemyActionConditionType::Otro(v),
        }
    }
}

impl Default for EnemyActionConditionType {
    fn default() -> Self { EnemyActionConditionType::Always }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EnemyActionKind {
    #[serde(rename = "basic")]
    Basic,
    #[serde(rename = "skill")]
    Skill,
    #[serde(rename = "transformation")]
    Transformation,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl EnemyActionKind {
    pub fn a_i32(self) -> i32 {
        match self {
            EnemyActionKind::Basic => 0,
            EnemyActionKind::Skill => 1,
            EnemyActionKind::Transformation => 2,
            EnemyActionKind::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => EnemyActionKind::Basic,
            1 => EnemyActionKind::Skill,
            2 => EnemyActionKind::Transformation,
            v => EnemyActionKind::Otro(v),
        }
    }
}

impl Default for EnemyActionKind {
    fn default() -> Self { EnemyActionKind::Basic }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventCommandCode {
    #[serde(rename = "END")]
    END,
    #[serde(rename = "CallCommonEvent")]
    CallCommonEvent,
    #[serde(rename = "ForceFlee")]
    ForceFlee,
    #[serde(rename = "EnableCombo")]
    EnableCombo,
    #[serde(rename = "ChangeClass")]
    ChangeClass,
    #[serde(rename = "ChangeBattleCommands")]
    ChangeBattleCommands,
    #[serde(rename = "OpenLoadMenu")]
    OpenLoadMenu,
    #[serde(rename = "ExitGame")]
    ExitGame,
    #[serde(rename = "ToggleAtbMode")]
    ToggleAtbMode,
    #[serde(rename = "ToggleFullscreen")]
    ToggleFullscreen,
    #[serde(rename = "OpenVideoOptions")]
    OpenVideoOptions,
    #[serde(rename = "ShowMessage")]
    ShowMessage,
    #[serde(rename = "MessageOptions")]
    MessageOptions,
    #[serde(rename = "ChangeFaceGraphic")]
    ChangeFaceGraphic,
    #[serde(rename = "ShowChoice")]
    ShowChoice,
    #[serde(rename = "InputNumber")]
    InputNumber,
    #[serde(rename = "ControlSwitches")]
    ControlSwitches,
    #[serde(rename = "ControlVars")]
    ControlVars,
    #[serde(rename = "TimerOperation")]
    TimerOperation,
    #[serde(rename = "ChangeGold")]
    ChangeGold,
    #[serde(rename = "ChangeItems")]
    ChangeItems,
    #[serde(rename = "ChangePartyMembers")]
    ChangePartyMembers,
    #[serde(rename = "ChangeExp")]
    ChangeExp,
    #[serde(rename = "ChangeLevel")]
    ChangeLevel,
    #[serde(rename = "ChangeParameters")]
    ChangeParameters,
    #[serde(rename = "ChangeSkills")]
    ChangeSkills,
    #[serde(rename = "ChangeEquipment")]
    ChangeEquipment,
    #[serde(rename = "ChangeHP")]
    ChangeHP,
    #[serde(rename = "ChangeSP")]
    ChangeSP,
    #[serde(rename = "ChangeCondition")]
    ChangeCondition,
    #[serde(rename = "FullHeal")]
    FullHeal,
    #[serde(rename = "SimulatedAttack")]
    SimulatedAttack,
    #[serde(rename = "ChangeHeroName")]
    ChangeHeroName,
    #[serde(rename = "ChangeHeroTitle")]
    ChangeHeroTitle,
    #[serde(rename = "ChangeSpriteAssociation")]
    ChangeSpriteAssociation,
    #[serde(rename = "ChangeActorFace")]
    ChangeActorFace,
    #[serde(rename = "ChangeVehicleGraphic")]
    ChangeVehicleGraphic,
    #[serde(rename = "ChangeSystemBGM")]
    ChangeSystemBGM,
    #[serde(rename = "ChangeSystemSFX")]
    ChangeSystemSFX,
    #[serde(rename = "ChangeSystemGraphics")]
    ChangeSystemGraphics,
    #[serde(rename = "ChangeScreenTransitions")]
    ChangeScreenTransitions,
    #[serde(rename = "EnemyEncounter")]
    EnemyEncounter,
    #[serde(rename = "OpenShop")]
    OpenShop,
    #[serde(rename = "ShowInn")]
    ShowInn,
    #[serde(rename = "EnterHeroName")]
    EnterHeroName,
    #[serde(rename = "Teleport")]
    Teleport,
    #[serde(rename = "MemorizeLocation")]
    MemorizeLocation,
    #[serde(rename = "RecallToLocation")]
    RecallToLocation,
    #[serde(rename = "EnterExitVehicle")]
    EnterExitVehicle,
    #[serde(rename = "SetVehicleLocation")]
    SetVehicleLocation,
    #[serde(rename = "ChangeEventLocation")]
    ChangeEventLocation,
    #[serde(rename = "TradeEventLocations")]
    TradeEventLocations,
    #[serde(rename = "StoreTerrainID")]
    StoreTerrainID,
    #[serde(rename = "StoreEventID")]
    StoreEventID,
    #[serde(rename = "EraseScreen")]
    EraseScreen,
    #[serde(rename = "ShowScreen")]
    ShowScreen,
    #[serde(rename = "TintScreen")]
    TintScreen,
    #[serde(rename = "FlashScreen")]
    FlashScreen,
    #[serde(rename = "ShakeScreen")]
    ShakeScreen,
    #[serde(rename = "PanScreen")]
    PanScreen,
    #[serde(rename = "WeatherEffects")]
    WeatherEffects,
    #[serde(rename = "ShowPicture")]
    ShowPicture,
    #[serde(rename = "MovePicture")]
    MovePicture,
    #[serde(rename = "ErasePicture")]
    ErasePicture,
    #[serde(rename = "ShowBattleAnimation")]
    ShowBattleAnimation,
    #[serde(rename = "PlayerVisibility")]
    PlayerVisibility,
    #[serde(rename = "FlashSprite")]
    FlashSprite,
    #[serde(rename = "MoveEvent")]
    MoveEvent,
    #[serde(rename = "ProceedWithMovement")]
    ProceedWithMovement,
    #[serde(rename = "HaltAllMovement")]
    HaltAllMovement,
    #[serde(rename = "Wait")]
    Wait,
    #[serde(rename = "PlayBGM")]
    PlayBGM,
    #[serde(rename = "FadeOutBGM")]
    FadeOutBGM,
    #[serde(rename = "MemorizeBGM")]
    MemorizeBGM,
    #[serde(rename = "PlayMemorizedBGM")]
    PlayMemorizedBGM,
    #[serde(rename = "PlaySound")]
    PlaySound,
    #[serde(rename = "PlayMovie")]
    PlayMovie,
    #[serde(rename = "KeyInputProc")]
    KeyInputProc,
    #[serde(rename = "ChangeMapTileset")]
    ChangeMapTileset,
    #[serde(rename = "ChangePBG")]
    ChangePBG,
    #[serde(rename = "ChangeEncounterSteps")]
    ChangeEncounterSteps,
    #[serde(rename = "TileSubstitution")]
    TileSubstitution,
    #[serde(rename = "TeleportTargets")]
    TeleportTargets,
    #[serde(rename = "ChangeTeleportAccess")]
    ChangeTeleportAccess,
    #[serde(rename = "EscapeTarget")]
    EscapeTarget,
    #[serde(rename = "ChangeEscapeAccess")]
    ChangeEscapeAccess,
    #[serde(rename = "OpenSaveMenu")]
    OpenSaveMenu,
    #[serde(rename = "ChangeSaveAccess")]
    ChangeSaveAccess,
    #[serde(rename = "OpenMainMenu")]
    OpenMainMenu,
    #[serde(rename = "ChangeMainMenuAccess")]
    ChangeMainMenuAccess,
    #[serde(rename = "ConditionalBranch")]
    ConditionalBranch,
    #[serde(rename = "Label")]
    Label,
    #[serde(rename = "JumpToLabel")]
    JumpToLabel,
    #[serde(rename = "Loop")]
    Loop,
    #[serde(rename = "BreakLoop")]
    BreakLoop,
    #[serde(rename = "EndEventProcessing")]
    EndEventProcessing,
    #[serde(rename = "EraseEvent")]
    EraseEvent,
    #[serde(rename = "CallEvent")]
    CallEvent,
    #[serde(rename = "Comment")]
    Comment,
    #[serde(rename = "GameOver")]
    GameOver,
    #[serde(rename = "ReturntoTitleScreen")]
    ReturntoTitleScreen,
    #[serde(rename = "ChangeMonsterHP")]
    ChangeMonsterHP,
    #[serde(rename = "ChangeMonsterMP")]
    ChangeMonsterMP,
    #[serde(rename = "ChangeMonsterCondition")]
    ChangeMonsterCondition,
    #[serde(rename = "ShowHiddenMonster")]
    ShowHiddenMonster,
    #[serde(rename = "ChangeBattleBG")]
    ChangeBattleBG,
    #[serde(rename = "ShowBattleAnimation_B")]
    ShowBattleAnimationB,
    #[serde(rename = "ConditionalBranch_B")]
    ConditionalBranchB,
    #[serde(rename = "TerminateBattle")]
    TerminateBattle,
    #[serde(rename = "ShowMessage_2")]
    ShowMessage2,
    #[serde(rename = "ShowChoiceOption")]
    ShowChoiceOption,
    #[serde(rename = "ShowChoiceEnd")]
    ShowChoiceEnd,
    #[serde(rename = "VictoryHandler")]
    VictoryHandler,
    #[serde(rename = "EscapeHandler")]
    EscapeHandler,
    #[serde(rename = "DefeatHandler")]
    DefeatHandler,
    #[serde(rename = "EndBattle")]
    EndBattle,
    #[serde(rename = "Transaction")]
    Transaction,
    #[serde(rename = "NoTransaction")]
    NoTransaction,
    #[serde(rename = "EndShop")]
    EndShop,
    #[serde(rename = "Stay")]
    Stay,
    #[serde(rename = "NoStay")]
    NoStay,
    #[serde(rename = "EndInn")]
    EndInn,
    #[serde(rename = "ElseBranch")]
    ElseBranch,
    #[serde(rename = "EndBranch")]
    EndBranch,
    #[serde(rename = "EndLoop")]
    EndLoop,
    #[serde(rename = "Comment_2")]
    Comment2,
    #[serde(rename = "ElseBranch_B")]
    ElseBranchB,
    #[serde(rename = "EndBranch_B")]
    EndBranchB,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl EventCommandCode {
    pub fn a_i32(self) -> i32 {
        match self {
            EventCommandCode::END => 10,
            EventCommandCode::CallCommonEvent => 1005,
            EventCommandCode::ForceFlee => 1006,
            EventCommandCode::EnableCombo => 1007,
            EventCommandCode::ChangeClass => 1008,
            EventCommandCode::ChangeBattleCommands => 1009,
            EventCommandCode::OpenLoadMenu => 5001,
            EventCommandCode::ExitGame => 5002,
            EventCommandCode::ToggleAtbMode => 5003,
            EventCommandCode::ToggleFullscreen => 5004,
            EventCommandCode::OpenVideoOptions => 5005,
            EventCommandCode::ShowMessage => 10110,
            EventCommandCode::MessageOptions => 10120,
            EventCommandCode::ChangeFaceGraphic => 10130,
            EventCommandCode::ShowChoice => 10140,
            EventCommandCode::InputNumber => 10150,
            EventCommandCode::ControlSwitches => 10210,
            EventCommandCode::ControlVars => 10220,
            EventCommandCode::TimerOperation => 10230,
            EventCommandCode::ChangeGold => 10310,
            EventCommandCode::ChangeItems => 10320,
            EventCommandCode::ChangePartyMembers => 10330,
            EventCommandCode::ChangeExp => 10410,
            EventCommandCode::ChangeLevel => 10420,
            EventCommandCode::ChangeParameters => 10430,
            EventCommandCode::ChangeSkills => 10440,
            EventCommandCode::ChangeEquipment => 10450,
            EventCommandCode::ChangeHP => 10460,
            EventCommandCode::ChangeSP => 10470,
            EventCommandCode::ChangeCondition => 10480,
            EventCommandCode::FullHeal => 10490,
            EventCommandCode::SimulatedAttack => 10500,
            EventCommandCode::ChangeHeroName => 10610,
            EventCommandCode::ChangeHeroTitle => 10620,
            EventCommandCode::ChangeSpriteAssociation => 10630,
            EventCommandCode::ChangeActorFace => 10640,
            EventCommandCode::ChangeVehicleGraphic => 10650,
            EventCommandCode::ChangeSystemBGM => 10660,
            EventCommandCode::ChangeSystemSFX => 10670,
            EventCommandCode::ChangeSystemGraphics => 10680,
            EventCommandCode::ChangeScreenTransitions => 10690,
            EventCommandCode::EnemyEncounter => 10710,
            EventCommandCode::OpenShop => 10720,
            EventCommandCode::ShowInn => 10730,
            EventCommandCode::EnterHeroName => 10740,
            EventCommandCode::Teleport => 10810,
            EventCommandCode::MemorizeLocation => 10820,
            EventCommandCode::RecallToLocation => 10830,
            EventCommandCode::EnterExitVehicle => 10840,
            EventCommandCode::SetVehicleLocation => 10850,
            EventCommandCode::ChangeEventLocation => 10860,
            EventCommandCode::TradeEventLocations => 10870,
            EventCommandCode::StoreTerrainID => 10910,
            EventCommandCode::StoreEventID => 10920,
            EventCommandCode::EraseScreen => 11010,
            EventCommandCode::ShowScreen => 11020,
            EventCommandCode::TintScreen => 11030,
            EventCommandCode::FlashScreen => 11040,
            EventCommandCode::ShakeScreen => 11050,
            EventCommandCode::PanScreen => 11060,
            EventCommandCode::WeatherEffects => 11070,
            EventCommandCode::ShowPicture => 11110,
            EventCommandCode::MovePicture => 11120,
            EventCommandCode::ErasePicture => 11130,
            EventCommandCode::ShowBattleAnimation => 11210,
            EventCommandCode::PlayerVisibility => 11310,
            EventCommandCode::FlashSprite => 11320,
            EventCommandCode::MoveEvent => 11330,
            EventCommandCode::ProceedWithMovement => 11340,
            EventCommandCode::HaltAllMovement => 11350,
            EventCommandCode::Wait => 11410,
            EventCommandCode::PlayBGM => 11510,
            EventCommandCode::FadeOutBGM => 11520,
            EventCommandCode::MemorizeBGM => 11530,
            EventCommandCode::PlayMemorizedBGM => 11540,
            EventCommandCode::PlaySound => 11550,
            EventCommandCode::PlayMovie => 11560,
            EventCommandCode::KeyInputProc => 11610,
            EventCommandCode::ChangeMapTileset => 11710,
            EventCommandCode::ChangePBG => 11720,
            EventCommandCode::ChangeEncounterSteps => 11740,
            EventCommandCode::TileSubstitution => 11750,
            EventCommandCode::TeleportTargets => 11810,
            EventCommandCode::ChangeTeleportAccess => 11820,
            EventCommandCode::EscapeTarget => 11830,
            EventCommandCode::ChangeEscapeAccess => 11840,
            EventCommandCode::OpenSaveMenu => 11910,
            EventCommandCode::ChangeSaveAccess => 11930,
            EventCommandCode::OpenMainMenu => 11950,
            EventCommandCode::ChangeMainMenuAccess => 11960,
            EventCommandCode::ConditionalBranch => 12010,
            EventCommandCode::Label => 12110,
            EventCommandCode::JumpToLabel => 12120,
            EventCommandCode::Loop => 12210,
            EventCommandCode::BreakLoop => 12220,
            EventCommandCode::EndEventProcessing => 12310,
            EventCommandCode::EraseEvent => 12320,
            EventCommandCode::CallEvent => 12330,
            EventCommandCode::Comment => 12410,
            EventCommandCode::GameOver => 12420,
            EventCommandCode::ReturntoTitleScreen => 12510,
            EventCommandCode::ChangeMonsterHP => 13110,
            EventCommandCode::ChangeMonsterMP => 13120,
            EventCommandCode::ChangeMonsterCondition => 13130,
            EventCommandCode::ShowHiddenMonster => 13150,
            EventCommandCode::ChangeBattleBG => 13210,
            EventCommandCode::ShowBattleAnimationB => 13260,
            EventCommandCode::ConditionalBranchB => 13310,
            EventCommandCode::TerminateBattle => 13410,
            EventCommandCode::ShowMessage2 => 20110,
            EventCommandCode::ShowChoiceOption => 20140,
            EventCommandCode::ShowChoiceEnd => 20141,
            EventCommandCode::VictoryHandler => 20710,
            EventCommandCode::EscapeHandler => 20711,
            EventCommandCode::DefeatHandler => 20712,
            EventCommandCode::EndBattle => 20713,
            EventCommandCode::Transaction => 20720,
            EventCommandCode::NoTransaction => 20721,
            EventCommandCode::EndShop => 20722,
            EventCommandCode::Stay => 20730,
            EventCommandCode::NoStay => 20731,
            EventCommandCode::EndInn => 20732,
            EventCommandCode::ElseBranch => 22010,
            EventCommandCode::EndBranch => 22011,
            EventCommandCode::EndLoop => 22210,
            EventCommandCode::Comment2 => 22410,
            EventCommandCode::ElseBranchB => 23310,
            EventCommandCode::EndBranchB => 23311,
            EventCommandCode::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            10 => EventCommandCode::END,
            1005 => EventCommandCode::CallCommonEvent,
            1006 => EventCommandCode::ForceFlee,
            1007 => EventCommandCode::EnableCombo,
            1008 => EventCommandCode::ChangeClass,
            1009 => EventCommandCode::ChangeBattleCommands,
            5001 => EventCommandCode::OpenLoadMenu,
            5002 => EventCommandCode::ExitGame,
            5003 => EventCommandCode::ToggleAtbMode,
            5004 => EventCommandCode::ToggleFullscreen,
            5005 => EventCommandCode::OpenVideoOptions,
            10110 => EventCommandCode::ShowMessage,
            10120 => EventCommandCode::MessageOptions,
            10130 => EventCommandCode::ChangeFaceGraphic,
            10140 => EventCommandCode::ShowChoice,
            10150 => EventCommandCode::InputNumber,
            10210 => EventCommandCode::ControlSwitches,
            10220 => EventCommandCode::ControlVars,
            10230 => EventCommandCode::TimerOperation,
            10310 => EventCommandCode::ChangeGold,
            10320 => EventCommandCode::ChangeItems,
            10330 => EventCommandCode::ChangePartyMembers,
            10410 => EventCommandCode::ChangeExp,
            10420 => EventCommandCode::ChangeLevel,
            10430 => EventCommandCode::ChangeParameters,
            10440 => EventCommandCode::ChangeSkills,
            10450 => EventCommandCode::ChangeEquipment,
            10460 => EventCommandCode::ChangeHP,
            10470 => EventCommandCode::ChangeSP,
            10480 => EventCommandCode::ChangeCondition,
            10490 => EventCommandCode::FullHeal,
            10500 => EventCommandCode::SimulatedAttack,
            10610 => EventCommandCode::ChangeHeroName,
            10620 => EventCommandCode::ChangeHeroTitle,
            10630 => EventCommandCode::ChangeSpriteAssociation,
            10640 => EventCommandCode::ChangeActorFace,
            10650 => EventCommandCode::ChangeVehicleGraphic,
            10660 => EventCommandCode::ChangeSystemBGM,
            10670 => EventCommandCode::ChangeSystemSFX,
            10680 => EventCommandCode::ChangeSystemGraphics,
            10690 => EventCommandCode::ChangeScreenTransitions,
            10710 => EventCommandCode::EnemyEncounter,
            10720 => EventCommandCode::OpenShop,
            10730 => EventCommandCode::ShowInn,
            10740 => EventCommandCode::EnterHeroName,
            10810 => EventCommandCode::Teleport,
            10820 => EventCommandCode::MemorizeLocation,
            10830 => EventCommandCode::RecallToLocation,
            10840 => EventCommandCode::EnterExitVehicle,
            10850 => EventCommandCode::SetVehicleLocation,
            10860 => EventCommandCode::ChangeEventLocation,
            10870 => EventCommandCode::TradeEventLocations,
            10910 => EventCommandCode::StoreTerrainID,
            10920 => EventCommandCode::StoreEventID,
            11010 => EventCommandCode::EraseScreen,
            11020 => EventCommandCode::ShowScreen,
            11030 => EventCommandCode::TintScreen,
            11040 => EventCommandCode::FlashScreen,
            11050 => EventCommandCode::ShakeScreen,
            11060 => EventCommandCode::PanScreen,
            11070 => EventCommandCode::WeatherEffects,
            11110 => EventCommandCode::ShowPicture,
            11120 => EventCommandCode::MovePicture,
            11130 => EventCommandCode::ErasePicture,
            11210 => EventCommandCode::ShowBattleAnimation,
            11310 => EventCommandCode::PlayerVisibility,
            11320 => EventCommandCode::FlashSprite,
            11330 => EventCommandCode::MoveEvent,
            11340 => EventCommandCode::ProceedWithMovement,
            11350 => EventCommandCode::HaltAllMovement,
            11410 => EventCommandCode::Wait,
            11510 => EventCommandCode::PlayBGM,
            11520 => EventCommandCode::FadeOutBGM,
            11530 => EventCommandCode::MemorizeBGM,
            11540 => EventCommandCode::PlayMemorizedBGM,
            11550 => EventCommandCode::PlaySound,
            11560 => EventCommandCode::PlayMovie,
            11610 => EventCommandCode::KeyInputProc,
            11710 => EventCommandCode::ChangeMapTileset,
            11720 => EventCommandCode::ChangePBG,
            11740 => EventCommandCode::ChangeEncounterSteps,
            11750 => EventCommandCode::TileSubstitution,
            11810 => EventCommandCode::TeleportTargets,
            11820 => EventCommandCode::ChangeTeleportAccess,
            11830 => EventCommandCode::EscapeTarget,
            11840 => EventCommandCode::ChangeEscapeAccess,
            11910 => EventCommandCode::OpenSaveMenu,
            11930 => EventCommandCode::ChangeSaveAccess,
            11950 => EventCommandCode::OpenMainMenu,
            11960 => EventCommandCode::ChangeMainMenuAccess,
            12010 => EventCommandCode::ConditionalBranch,
            12110 => EventCommandCode::Label,
            12120 => EventCommandCode::JumpToLabel,
            12210 => EventCommandCode::Loop,
            12220 => EventCommandCode::BreakLoop,
            12310 => EventCommandCode::EndEventProcessing,
            12320 => EventCommandCode::EraseEvent,
            12330 => EventCommandCode::CallEvent,
            12410 => EventCommandCode::Comment,
            12420 => EventCommandCode::GameOver,
            12510 => EventCommandCode::ReturntoTitleScreen,
            13110 => EventCommandCode::ChangeMonsterHP,
            13120 => EventCommandCode::ChangeMonsterMP,
            13130 => EventCommandCode::ChangeMonsterCondition,
            13150 => EventCommandCode::ShowHiddenMonster,
            13210 => EventCommandCode::ChangeBattleBG,
            13260 => EventCommandCode::ShowBattleAnimationB,
            13310 => EventCommandCode::ConditionalBranchB,
            13410 => EventCommandCode::TerminateBattle,
            20110 => EventCommandCode::ShowMessage2,
            20140 => EventCommandCode::ShowChoiceOption,
            20141 => EventCommandCode::ShowChoiceEnd,
            20710 => EventCommandCode::VictoryHandler,
            20711 => EventCommandCode::EscapeHandler,
            20712 => EventCommandCode::DefeatHandler,
            20713 => EventCommandCode::EndBattle,
            20720 => EventCommandCode::Transaction,
            20721 => EventCommandCode::NoTransaction,
            20722 => EventCommandCode::EndShop,
            20730 => EventCommandCode::Stay,
            20731 => EventCommandCode::NoStay,
            20732 => EventCommandCode::EndInn,
            22010 => EventCommandCode::ElseBranch,
            22011 => EventCommandCode::EndBranch,
            22210 => EventCommandCode::EndLoop,
            22410 => EventCommandCode::Comment2,
            23310 => EventCommandCode::ElseBranchB,
            23311 => EventCommandCode::EndBranchB,
            v => EventCommandCode::Otro(v),
        }
    }
}

impl Default for EventCommandCode {
    fn default() -> Self { EventCommandCode::END }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageAnimType {
    #[serde(rename = "non_continuous")]
    NonContinuous,
    #[serde(rename = "continuous")]
    Continuous,
    #[serde(rename = "fixed_non_continuous")]
    FixedNonContinuous,
    #[serde(rename = "fixed_continuous")]
    FixedContinuous,
    #[serde(rename = "fixed_graphic")]
    FixedGraphic,
    #[serde(rename = "spin")]
    Spin,
    #[serde(rename = "step_frame_fix")]
    StepFrameFix,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl EventPageAnimType {
    pub fn a_i32(self) -> i32 {
        match self {
            EventPageAnimType::NonContinuous => 0,
            EventPageAnimType::Continuous => 1,
            EventPageAnimType::FixedNonContinuous => 2,
            EventPageAnimType::FixedContinuous => 3,
            EventPageAnimType::FixedGraphic => 4,
            EventPageAnimType::Spin => 5,
            EventPageAnimType::StepFrameFix => 6,
            EventPageAnimType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => EventPageAnimType::NonContinuous,
            1 => EventPageAnimType::Continuous,
            2 => EventPageAnimType::FixedNonContinuous,
            3 => EventPageAnimType::FixedContinuous,
            4 => EventPageAnimType::FixedGraphic,
            5 => EventPageAnimType::Spin,
            6 => EventPageAnimType::StepFrameFix,
            v => EventPageAnimType::Otro(v),
        }
    }
}

impl Default for EventPageAnimType {
    fn default() -> Self { EventPageAnimType::NonContinuous }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageConditionComparison {
    #[serde(rename = "equal")]
    Equal,
    #[serde(rename = "greater_equal")]
    GreaterEqual,
    #[serde(rename = "less_equal")]
    LessEqual,
    #[serde(rename = "greater")]
    Greater,
    #[serde(rename = "less")]
    Less,
    #[serde(rename = "not_equal")]
    NotEqual,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl EventPageConditionComparison {
    pub fn a_i32(self) -> i32 {
        match self {
            EventPageConditionComparison::Equal => 0,
            EventPageConditionComparison::GreaterEqual => 1,
            EventPageConditionComparison::LessEqual => 2,
            EventPageConditionComparison::Greater => 3,
            EventPageConditionComparison::Less => 4,
            EventPageConditionComparison::NotEqual => 5,
            EventPageConditionComparison::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => EventPageConditionComparison::Equal,
            1 => EventPageConditionComparison::GreaterEqual,
            2 => EventPageConditionComparison::LessEqual,
            3 => EventPageConditionComparison::Greater,
            4 => EventPageConditionComparison::Less,
            5 => EventPageConditionComparison::NotEqual,
            v => EventPageConditionComparison::Otro(v),
        }
    }
}

impl Default for EventPageConditionComparison {
    fn default() -> Self { EventPageConditionComparison::Equal }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageDirection {
    #[serde(rename = "up")]
    Up,
    #[serde(rename = "right")]
    Right,
    #[serde(rename = "down")]
    Down,
    #[serde(rename = "left")]
    Left,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl EventPageDirection {
    pub fn a_i32(self) -> i32 {
        match self {
            EventPageDirection::Up => 0,
            EventPageDirection::Right => 1,
            EventPageDirection::Down => 2,
            EventPageDirection::Left => 3,
            EventPageDirection::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => EventPageDirection::Up,
            1 => EventPageDirection::Right,
            2 => EventPageDirection::Down,
            3 => EventPageDirection::Left,
            v => EventPageDirection::Otro(v),
        }
    }
}

impl Default for EventPageDirection {
    fn default() -> Self { EventPageDirection::Up }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageFrame {
    #[serde(rename = "left")]
    Left,
    #[serde(rename = "middle")]
    Middle,
    #[serde(rename = "right")]
    Right,
    #[serde(rename = "middle2")]
    Middle2,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl EventPageFrame {
    pub fn a_i32(self) -> i32 {
        match self {
            EventPageFrame::Left => 0,
            EventPageFrame::Middle => 1,
            EventPageFrame::Right => 2,
            EventPageFrame::Middle2 => 3,
            EventPageFrame::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => EventPageFrame::Left,
            1 => EventPageFrame::Middle,
            2 => EventPageFrame::Right,
            3 => EventPageFrame::Middle2,
            v => EventPageFrame::Otro(v),
        }
    }
}

impl Default for EventPageFrame {
    fn default() -> Self { EventPageFrame::Left }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageLayers {
    #[serde(rename = "below")]
    Below,
    #[serde(rename = "same")]
    Same,
    #[serde(rename = "above")]
    Above,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl EventPageLayers {
    pub fn a_i32(self) -> i32 {
        match self {
            EventPageLayers::Below => 0,
            EventPageLayers::Same => 1,
            EventPageLayers::Above => 2,
            EventPageLayers::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => EventPageLayers::Below,
            1 => EventPageLayers::Same,
            2 => EventPageLayers::Above,
            v => EventPageLayers::Otro(v),
        }
    }
}

impl Default for EventPageLayers {
    fn default() -> Self { EventPageLayers::Below }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageMoveSpeed {
    #[serde(rename = "eighth")]
    Eighth,
    #[serde(rename = "quarter")]
    Quarter,
    #[serde(rename = "half")]
    Half,
    #[serde(rename = "normal")]
    Normal,
    #[serde(rename = "double")]
    Double,
    #[serde(rename = "fourfold")]
    Fourfold,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl EventPageMoveSpeed {
    pub fn a_i32(self) -> i32 {
        match self {
            EventPageMoveSpeed::Eighth => 1,
            EventPageMoveSpeed::Quarter => 2,
            EventPageMoveSpeed::Half => 3,
            EventPageMoveSpeed::Normal => 4,
            EventPageMoveSpeed::Double => 5,
            EventPageMoveSpeed::Fourfold => 6,
            EventPageMoveSpeed::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            1 => EventPageMoveSpeed::Eighth,
            2 => EventPageMoveSpeed::Quarter,
            3 => EventPageMoveSpeed::Half,
            4 => EventPageMoveSpeed::Normal,
            5 => EventPageMoveSpeed::Double,
            6 => EventPageMoveSpeed::Fourfold,
            v => EventPageMoveSpeed::Otro(v),
        }
    }
}

impl Default for EventPageMoveSpeed {
    fn default() -> Self { EventPageMoveSpeed::Eighth }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageMoveType {
    #[serde(rename = "stationary")]
    Stationary,
    #[serde(rename = "random")]
    Random,
    #[serde(rename = "vertical")]
    Vertical,
    #[serde(rename = "horizontal")]
    Horizontal,
    #[serde(rename = "toward")]
    Toward,
    #[serde(rename = "away")]
    Away,
    #[serde(rename = "custom")]
    Custom,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl EventPageMoveType {
    pub fn a_i32(self) -> i32 {
        match self {
            EventPageMoveType::Stationary => 0,
            EventPageMoveType::Random => 1,
            EventPageMoveType::Vertical => 2,
            EventPageMoveType::Horizontal => 3,
            EventPageMoveType::Toward => 4,
            EventPageMoveType::Away => 5,
            EventPageMoveType::Custom => 6,
            EventPageMoveType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => EventPageMoveType::Stationary,
            1 => EventPageMoveType::Random,
            2 => EventPageMoveType::Vertical,
            3 => EventPageMoveType::Horizontal,
            4 => EventPageMoveType::Toward,
            5 => EventPageMoveType::Away,
            6 => EventPageMoveType::Custom,
            v => EventPageMoveType::Otro(v),
        }
    }
}

impl Default for EventPageMoveType {
    fn default() -> Self { EventPageMoveType::Stationary }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPageTrigger {
    #[serde(rename = "action")]
    Action,
    #[serde(rename = "touched")]
    Touched,
    #[serde(rename = "collision")]
    Collision,
    #[serde(rename = "auto_start")]
    AutoStart,
    #[serde(rename = "parallel")]
    Parallel,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl EventPageTrigger {
    pub fn a_i32(self) -> i32 {
        match self {
            EventPageTrigger::Action => 0,
            EventPageTrigger::Touched => 1,
            EventPageTrigger::Collision => 2,
            EventPageTrigger::AutoStart => 3,
            EventPageTrigger::Parallel => 4,
            EventPageTrigger::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => EventPageTrigger::Action,
            1 => EventPageTrigger::Touched,
            2 => EventPageTrigger::Collision,
            3 => EventPageTrigger::AutoStart,
            4 => EventPageTrigger::Parallel,
            v => EventPageTrigger::Otro(v),
        }
    }
}

impl Default for EventPageTrigger {
    fn default() -> Self { EventPageTrigger::Action }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ItemTarget {
    #[serde(rename = "single")]
    Single,
    #[serde(rename = "center")]
    Center,
    #[serde(rename = "simultaneous")]
    Simultaneous,
    #[serde(rename = "sequential")]
    Sequential,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl ItemTarget {
    pub fn a_i32(self) -> i32 {
        match self {
            ItemTarget::Single => 0,
            ItemTarget::Center => 1,
            ItemTarget::Simultaneous => 2,
            ItemTarget::Sequential => 3,
            ItemTarget::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => ItemTarget::Single,
            1 => ItemTarget::Center,
            2 => ItemTarget::Simultaneous,
            3 => ItemTarget::Sequential,
            v => ItemTarget::Otro(v),
        }
    }
}

impl Default for ItemTarget {
    fn default() -> Self { ItemTarget::Single }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ItemTrajectory {
    #[serde(rename = "straight")]
    Straight,
    #[serde(rename = "return")]
    Return,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl ItemTrajectory {
    pub fn a_i32(self) -> i32 {
        match self {
            ItemTrajectory::Straight => 0,
            ItemTrajectory::Return => 1,
            ItemTrajectory::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => ItemTrajectory::Straight,
            1 => ItemTrajectory::Return,
            v => ItemTrajectory::Otro(v),
        }
    }
}

impl Default for ItemTrajectory {
    fn default() -> Self { ItemTrajectory::Straight }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ItemType {
    #[serde(rename = "normal")]
    Normal,
    #[serde(rename = "weapon")]
    Weapon,
    #[serde(rename = "shield")]
    Shield,
    #[serde(rename = "armor")]
    Armor,
    #[serde(rename = "helmet")]
    Helmet,
    #[serde(rename = "accessory")]
    Accessory,
    #[serde(rename = "medicine")]
    Medicine,
    #[serde(rename = "book")]
    Book,
    #[serde(rename = "material")]
    Material,
    #[serde(rename = "special")]
    Special,
    #[serde(rename = "switch")]
    Switch,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl ItemType {
    pub fn a_i32(self) -> i32 {
        match self {
            ItemType::Normal => 0,
            ItemType::Weapon => 1,
            ItemType::Shield => 2,
            ItemType::Armor => 3,
            ItemType::Helmet => 4,
            ItemType::Accessory => 5,
            ItemType::Medicine => 6,
            ItemType::Book => 7,
            ItemType::Material => 8,
            ItemType::Special => 9,
            ItemType::Switch => 10,
            ItemType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => ItemType::Normal,
            1 => ItemType::Weapon,
            2 => ItemType::Shield,
            3 => ItemType::Armor,
            4 => ItemType::Helmet,
            5 => ItemType::Accessory,
            6 => ItemType::Medicine,
            7 => ItemType::Book,
            8 => ItemType::Material,
            9 => ItemType::Special,
            10 => ItemType::Switch,
            v => ItemType::Otro(v),
        }
    }
}

impl Default for ItemType {
    fn default() -> Self { ItemType::Normal }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MapGeneratorMode {
    #[serde(rename = "single_passage")]
    SinglePassage,
    #[serde(rename = "linked_rooms")]
    LinkedRooms,
    #[serde(rename = "maze_passage")]
    MazePassage,
    #[serde(rename = "open_room")]
    OpenRoom,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl MapGeneratorMode {
    pub fn a_i32(self) -> i32 {
        match self {
            MapGeneratorMode::SinglePassage => 0,
            MapGeneratorMode::LinkedRooms => 1,
            MapGeneratorMode::MazePassage => 2,
            MapGeneratorMode::OpenRoom => 3,
            MapGeneratorMode::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => MapGeneratorMode::SinglePassage,
            1 => MapGeneratorMode::LinkedRooms,
            2 => MapGeneratorMode::MazePassage,
            3 => MapGeneratorMode::OpenRoom,
            v => MapGeneratorMode::Otro(v),
        }
    }
}

impl Default for MapGeneratorMode {
    fn default() -> Self { MapGeneratorMode::SinglePassage }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MapGeneratorTiles {
    #[serde(rename = "one")]
    One,
    #[serde(rename = "two")]
    Two,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl MapGeneratorTiles {
    pub fn a_i32(self) -> i32 {
        match self {
            MapGeneratorTiles::One => 0,
            MapGeneratorTiles::Two => 1,
            MapGeneratorTiles::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => MapGeneratorTiles::One,
            1 => MapGeneratorTiles::Two,
            v => MapGeneratorTiles::Otro(v),
        }
    }
}

impl Default for MapGeneratorTiles {
    fn default() -> Self { MapGeneratorTiles::One }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MapInfoBGMType {
    #[serde(rename = "parent")]
    Parent,
    #[serde(rename = "terrain")]
    Terrain,
    #[serde(rename = "specific")]
    Specific,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl MapInfoBGMType {
    pub fn a_i32(self) -> i32 {
        match self {
            MapInfoBGMType::Parent => 0,
            MapInfoBGMType::Terrain => 1,
            MapInfoBGMType::Specific => 2,
            MapInfoBGMType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => MapInfoBGMType::Parent,
            1 => MapInfoBGMType::Terrain,
            2 => MapInfoBGMType::Specific,
            v => MapInfoBGMType::Otro(v),
        }
    }
}

impl Default for MapInfoBGMType {
    fn default() -> Self { MapInfoBGMType::Parent }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MapInfoMusicType {
    #[serde(rename = "parent")]
    Parent,
    #[serde(rename = "event")]
    Event,
    #[serde(rename = "specific")]
    Specific,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl MapInfoMusicType {
    pub fn a_i32(self) -> i32 {
        match self {
            MapInfoMusicType::Parent => 0,
            MapInfoMusicType::Event => 1,
            MapInfoMusicType::Specific => 2,
            MapInfoMusicType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => MapInfoMusicType::Parent,
            1 => MapInfoMusicType::Event,
            2 => MapInfoMusicType::Specific,
            v => MapInfoMusicType::Otro(v),
        }
    }
}

impl Default for MapInfoMusicType {
    fn default() -> Self { MapInfoMusicType::Parent }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MapInfoTriState {
    #[serde(rename = "parent")]
    Parent,
    #[serde(rename = "allow")]
    Allow,
    #[serde(rename = "forbid")]
    Forbid,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl MapInfoTriState {
    pub fn a_i32(self) -> i32 {
        match self {
            MapInfoTriState::Parent => 0,
            MapInfoTriState::Allow => 1,
            MapInfoTriState::Forbid => 2,
            MapInfoTriState::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => MapInfoTriState::Parent,
            1 => MapInfoTriState::Allow,
            2 => MapInfoTriState::Forbid,
            v => MapInfoTriState::Otro(v),
        }
    }
}

impl Default for MapInfoTriState {
    fn default() -> Self { MapInfoTriState::Parent }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MapScrollType {
    #[serde(rename = "none")]
    None,
    #[serde(rename = "vertical")]
    Vertical,
    #[serde(rename = "horizontal")]
    Horizontal,
    #[serde(rename = "both")]
    Both,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl MapScrollType {
    pub fn a_i32(self) -> i32 {
        match self {
            MapScrollType::None => 0,
            MapScrollType::Vertical => 1,
            MapScrollType::Horizontal => 2,
            MapScrollType::Both => 3,
            MapScrollType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => MapScrollType::None,
            1 => MapScrollType::Vertical,
            2 => MapScrollType::Horizontal,
            3 => MapScrollType::Both,
            v => MapScrollType::Otro(v),
        }
    }
}

impl Default for MapScrollType {
    fn default() -> Self { MapScrollType::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MoveCommandCode {
    #[serde(rename = "move_up")]
    MoveUp,
    #[serde(rename = "move_right")]
    MoveRight,
    #[serde(rename = "move_down")]
    MoveDown,
    #[serde(rename = "move_left")]
    MoveLeft,
    #[serde(rename = "move_upright")]
    MoveUpright,
    #[serde(rename = "move_downright")]
    MoveDownright,
    #[serde(rename = "move_downleft")]
    MoveDownleft,
    #[serde(rename = "move_upleft")]
    MoveUpleft,
    #[serde(rename = "move_random")]
    MoveRandom,
    #[serde(rename = "move_towards_hero")]
    MoveTowardsHero,
    #[serde(rename = "move_away_from_hero")]
    MoveAwayFromHero,
    #[serde(rename = "move_forward")]
    MoveForward,
    #[serde(rename = "face_up")]
    FaceUp,
    #[serde(rename = "face_right")]
    FaceRight,
    #[serde(rename = "face_down")]
    FaceDown,
    #[serde(rename = "face_left")]
    FaceLeft,
    #[serde(rename = "turn_90_degree_right")]
    Turn90DegreeRight,
    #[serde(rename = "turn_90_degree_left")]
    Turn90DegreeLeft,
    #[serde(rename = "turn_180_degree")]
    Turn180Degree,
    #[serde(rename = "turn_90_degree_random")]
    Turn90DegreeRandom,
    #[serde(rename = "face_random_direction")]
    FaceRandomDirection,
    #[serde(rename = "face_hero")]
    FaceHero,
    #[serde(rename = "face_away_from_hero")]
    FaceAwayFromHero,
    #[serde(rename = "wait")]
    Wait,
    #[serde(rename = "begin_jump")]
    BeginJump,
    #[serde(rename = "end_jump")]
    EndJump,
    #[serde(rename = "lock_facing")]
    LockFacing,
    #[serde(rename = "unlock_facing")]
    UnlockFacing,
    #[serde(rename = "increase_movement_speed")]
    IncreaseMovementSpeed,
    #[serde(rename = "decrease_movement_speed")]
    DecreaseMovementSpeed,
    #[serde(rename = "increase_movement_frequence")]
    IncreaseMovementFrequence,
    #[serde(rename = "decrease_movement_frequence")]
    DecreaseMovementFrequence,
    #[serde(rename = "switch_on")]
    SwitchOn,
    #[serde(rename = "switch_off")]
    SwitchOff,
    #[serde(rename = "change_graphic")]
    ChangeGraphic,
    #[serde(rename = "play_sound_effect")]
    PlaySoundEffect,
    #[serde(rename = "walk_everywhere_on")]
    WalkEverywhereOn,
    #[serde(rename = "walk_everywhere_off")]
    WalkEverywhereOff,
    #[serde(rename = "stop_animation")]
    StopAnimation,
    #[serde(rename = "start_animation")]
    StartAnimation,
    #[serde(rename = "increase_transp")]
    IncreaseTransp,
    #[serde(rename = "decrease_transp")]
    DecreaseTransp,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl MoveCommandCode {
    pub fn a_i32(self) -> i32 {
        match self {
            MoveCommandCode::MoveUp => 0,
            MoveCommandCode::MoveRight => 1,
            MoveCommandCode::MoveDown => 2,
            MoveCommandCode::MoveLeft => 3,
            MoveCommandCode::MoveUpright => 4,
            MoveCommandCode::MoveDownright => 5,
            MoveCommandCode::MoveDownleft => 6,
            MoveCommandCode::MoveUpleft => 7,
            MoveCommandCode::MoveRandom => 8,
            MoveCommandCode::MoveTowardsHero => 9,
            MoveCommandCode::MoveAwayFromHero => 10,
            MoveCommandCode::MoveForward => 11,
            MoveCommandCode::FaceUp => 12,
            MoveCommandCode::FaceRight => 13,
            MoveCommandCode::FaceDown => 14,
            MoveCommandCode::FaceLeft => 15,
            MoveCommandCode::Turn90DegreeRight => 16,
            MoveCommandCode::Turn90DegreeLeft => 17,
            MoveCommandCode::Turn180Degree => 18,
            MoveCommandCode::Turn90DegreeRandom => 19,
            MoveCommandCode::FaceRandomDirection => 20,
            MoveCommandCode::FaceHero => 21,
            MoveCommandCode::FaceAwayFromHero => 22,
            MoveCommandCode::Wait => 23,
            MoveCommandCode::BeginJump => 24,
            MoveCommandCode::EndJump => 25,
            MoveCommandCode::LockFacing => 26,
            MoveCommandCode::UnlockFacing => 27,
            MoveCommandCode::IncreaseMovementSpeed => 28,
            MoveCommandCode::DecreaseMovementSpeed => 29,
            MoveCommandCode::IncreaseMovementFrequence => 30,
            MoveCommandCode::DecreaseMovementFrequence => 31,
            MoveCommandCode::SwitchOn => 32,
            MoveCommandCode::SwitchOff => 33,
            MoveCommandCode::ChangeGraphic => 34,
            MoveCommandCode::PlaySoundEffect => 35,
            MoveCommandCode::WalkEverywhereOn => 36,
            MoveCommandCode::WalkEverywhereOff => 37,
            MoveCommandCode::StopAnimation => 38,
            MoveCommandCode::StartAnimation => 39,
            MoveCommandCode::IncreaseTransp => 40,
            MoveCommandCode::DecreaseTransp => 41,
            MoveCommandCode::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => MoveCommandCode::MoveUp,
            1 => MoveCommandCode::MoveRight,
            2 => MoveCommandCode::MoveDown,
            3 => MoveCommandCode::MoveLeft,
            4 => MoveCommandCode::MoveUpright,
            5 => MoveCommandCode::MoveDownright,
            6 => MoveCommandCode::MoveDownleft,
            7 => MoveCommandCode::MoveUpleft,
            8 => MoveCommandCode::MoveRandom,
            9 => MoveCommandCode::MoveTowardsHero,
            10 => MoveCommandCode::MoveAwayFromHero,
            11 => MoveCommandCode::MoveForward,
            12 => MoveCommandCode::FaceUp,
            13 => MoveCommandCode::FaceRight,
            14 => MoveCommandCode::FaceDown,
            15 => MoveCommandCode::FaceLeft,
            16 => MoveCommandCode::Turn90DegreeRight,
            17 => MoveCommandCode::Turn90DegreeLeft,
            18 => MoveCommandCode::Turn180Degree,
            19 => MoveCommandCode::Turn90DegreeRandom,
            20 => MoveCommandCode::FaceRandomDirection,
            21 => MoveCommandCode::FaceHero,
            22 => MoveCommandCode::FaceAwayFromHero,
            23 => MoveCommandCode::Wait,
            24 => MoveCommandCode::BeginJump,
            25 => MoveCommandCode::EndJump,
            26 => MoveCommandCode::LockFacing,
            27 => MoveCommandCode::UnlockFacing,
            28 => MoveCommandCode::IncreaseMovementSpeed,
            29 => MoveCommandCode::DecreaseMovementSpeed,
            30 => MoveCommandCode::IncreaseMovementFrequence,
            31 => MoveCommandCode::DecreaseMovementFrequence,
            32 => MoveCommandCode::SwitchOn,
            33 => MoveCommandCode::SwitchOff,
            34 => MoveCommandCode::ChangeGraphic,
            35 => MoveCommandCode::PlaySoundEffect,
            36 => MoveCommandCode::WalkEverywhereOn,
            37 => MoveCommandCode::WalkEverywhereOff,
            38 => MoveCommandCode::StopAnimation,
            39 => MoveCommandCode::StartAnimation,
            40 => MoveCommandCode::IncreaseTransp,
            41 => MoveCommandCode::DecreaseTransp,
            v => MoveCommandCode::Otro(v),
        }
    }
}

impl Default for MoveCommandCode {
    fn default() -> Self { MoveCommandCode::MoveUp }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SaveActorRowType {
    #[serde(rename = "front")]
    Front,
    #[serde(rename = "back")]
    Back,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SaveActorRowType {
    pub fn a_i32(self) -> i32 {
        match self {
            SaveActorRowType::Front => 0,
            SaveActorRowType::Back => 1,
            SaveActorRowType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SaveActorRowType::Front,
            1 => SaveActorRowType::Back,
            v => SaveActorRowType::Otro(v),
        }
    }
}

impl Default for SaveActorRowType {
    fn default() -> Self { SaveActorRowType::Front }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SavePartyLocationPanState {
    #[serde(rename = "fixed")]
    Fixed,
    #[serde(rename = "follow")]
    Follow,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SavePartyLocationPanState {
    pub fn a_i32(self) -> i32 {
        match self {
            SavePartyLocationPanState::Fixed => 0,
            SavePartyLocationPanState::Follow => 1,
            SavePartyLocationPanState::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SavePartyLocationPanState::Fixed,
            1 => SavePartyLocationPanState::Follow,
            v => SavePartyLocationPanState::Otro(v),
        }
    }
}

impl Default for SavePartyLocationPanState {
    fn default() -> Self { SavePartyLocationPanState::Fixed }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SavePartyLocationVehicleType {
    #[serde(rename = "none")]
    None,
    #[serde(rename = "skiff")]
    Skiff,
    #[serde(rename = "ship")]
    Ship,
    #[serde(rename = "airship")]
    Airship,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SavePartyLocationVehicleType {
    pub fn a_i32(self) -> i32 {
        match self {
            SavePartyLocationVehicleType::None => 0,
            SavePartyLocationVehicleType::Skiff => 1,
            SavePartyLocationVehicleType::Ship => 2,
            SavePartyLocationVehicleType::Airship => 3,
            SavePartyLocationVehicleType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SavePartyLocationVehicleType::None,
            1 => SavePartyLocationVehicleType::Skiff,
            2 => SavePartyLocationVehicleType::Ship,
            3 => SavePartyLocationVehicleType::Airship,
            v => SavePartyLocationVehicleType::Otro(v),
        }
    }
}

impl Default for SavePartyLocationVehicleType {
    fn default() -> Self { SavePartyLocationVehicleType::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SavePictureBattleLayer {
    #[serde(rename = "none")]
    None,
    #[serde(rename = "background")]
    Background,
    #[serde(rename = "battlers_and_animations")]
    BattlersAndAnimations,
    #[serde(rename = "weather")]
    Weather,
    #[serde(rename = "windows_and_status")]
    WindowsAndStatus,
    #[serde(rename = "timers")]
    Timers,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SavePictureBattleLayer {
    pub fn a_i32(self) -> i32 {
        match self {
            SavePictureBattleLayer::None => 0,
            SavePictureBattleLayer::Background => 1,
            SavePictureBattleLayer::BattlersAndAnimations => 2,
            SavePictureBattleLayer::Weather => 3,
            SavePictureBattleLayer::WindowsAndStatus => 4,
            SavePictureBattleLayer::Timers => 5,
            SavePictureBattleLayer::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SavePictureBattleLayer::None,
            1 => SavePictureBattleLayer::Background,
            2 => SavePictureBattleLayer::BattlersAndAnimations,
            3 => SavePictureBattleLayer::Weather,
            4 => SavePictureBattleLayer::WindowsAndStatus,
            5 => SavePictureBattleLayer::Timers,
            v => SavePictureBattleLayer::Otro(v),
        }
    }
}

impl Default for SavePictureBattleLayer {
    fn default() -> Self { SavePictureBattleLayer::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SavePictureEffect {
    #[serde(rename = "none")]
    None,
    #[serde(rename = "rotation")]
    Rotation,
    #[serde(rename = "wave")]
    Wave,
    #[serde(rename = "maniac_fixed_angle")]
    ManiacFixedAngle,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SavePictureEffect {
    pub fn a_i32(self) -> i32 {
        match self {
            SavePictureEffect::None => 0,
            SavePictureEffect::Rotation => 1,
            SavePictureEffect::Wave => 2,
            SavePictureEffect::ManiacFixedAngle => 3,
            SavePictureEffect::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SavePictureEffect::None,
            1 => SavePictureEffect::Rotation,
            2 => SavePictureEffect::Wave,
            3 => SavePictureEffect::ManiacFixedAngle,
            v => SavePictureEffect::Otro(v),
        }
    }
}

impl Default for SavePictureEffect {
    fn default() -> Self { SavePictureEffect::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SavePictureMapLayer {
    #[serde(rename = "none")]
    None,
    #[serde(rename = "parallax")]
    Parallax,
    #[serde(rename = "tilemap_below")]
    TilemapBelow,
    #[serde(rename = "events_below")]
    EventsBelow,
    #[serde(rename = "events_same_as_player")]
    EventsSameAsPlayer,
    #[serde(rename = "tilemap_above")]
    TilemapAbove,
    #[serde(rename = "events_above")]
    EventsAbove,
    #[serde(rename = "weather")]
    Weather,
    #[serde(rename = "animations")]
    Animations,
    #[serde(rename = "windows")]
    Windows,
    #[serde(rename = "timers")]
    Timers,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SavePictureMapLayer {
    pub fn a_i32(self) -> i32 {
        match self {
            SavePictureMapLayer::None => 0,
            SavePictureMapLayer::Parallax => 1,
            SavePictureMapLayer::TilemapBelow => 2,
            SavePictureMapLayer::EventsBelow => 3,
            SavePictureMapLayer::EventsSameAsPlayer => 4,
            SavePictureMapLayer::TilemapAbove => 5,
            SavePictureMapLayer::EventsAbove => 6,
            SavePictureMapLayer::Weather => 7,
            SavePictureMapLayer::Animations => 8,
            SavePictureMapLayer::Windows => 9,
            SavePictureMapLayer::Timers => 10,
            SavePictureMapLayer::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SavePictureMapLayer::None,
            1 => SavePictureMapLayer::Parallax,
            2 => SavePictureMapLayer::TilemapBelow,
            3 => SavePictureMapLayer::EventsBelow,
            4 => SavePictureMapLayer::EventsSameAsPlayer,
            5 => SavePictureMapLayer::TilemapAbove,
            6 => SavePictureMapLayer::EventsAbove,
            7 => SavePictureMapLayer::Weather,
            8 => SavePictureMapLayer::Animations,
            9 => SavePictureMapLayer::Windows,
            10 => SavePictureMapLayer::Timers,
            v => SavePictureMapLayer::Otro(v),
        }
    }
}

impl Default for SavePictureMapLayer {
    fn default() -> Self { SavePictureMapLayer::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SaveSystemAtbMode {
    #[serde(rename = "atb_active")]
    AtbActive,
    #[serde(rename = "atb_wait")]
    AtbWait,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SaveSystemAtbMode {
    pub fn a_i32(self) -> i32 {
        match self {
            SaveSystemAtbMode::AtbActive => 0,
            SaveSystemAtbMode::AtbWait => 1,
            SaveSystemAtbMode::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SaveSystemAtbMode::AtbActive,
            1 => SaveSystemAtbMode::AtbWait,
            v => SaveSystemAtbMode::Otro(v),
        }
    }
}

impl Default for SaveSystemAtbMode {
    fn default() -> Self { SaveSystemAtbMode::AtbActive }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SaveSystemScene {
    #[serde(rename = "map")]
    Map,
    #[serde(rename = "menu")]
    Menu,
    #[serde(rename = "battle")]
    Battle,
    #[serde(rename = "shop")]
    Shop,
    #[serde(rename = "name")]
    Name,
    #[serde(rename = "file")]
    File,
    #[serde(rename = "title")]
    Title,
    #[serde(rename = "game_over")]
    GameOver,
    #[serde(rename = "debug")]
    Debug,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SaveSystemScene {
    pub fn a_i32(self) -> i32 {
        match self {
            SaveSystemScene::Map => 0,
            SaveSystemScene::Menu => 1,
            SaveSystemScene::Battle => 2,
            SaveSystemScene::Shop => 3,
            SaveSystemScene::Name => 4,
            SaveSystemScene::File => 5,
            SaveSystemScene::Title => 6,
            SaveSystemScene::GameOver => 7,
            SaveSystemScene::Debug => 8,
            SaveSystemScene::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SaveSystemScene::Map,
            1 => SaveSystemScene::Menu,
            2 => SaveSystemScene::Battle,
            3 => SaveSystemScene::Shop,
            4 => SaveSystemScene::Name,
            5 => SaveSystemScene::File,
            6 => SaveSystemScene::Title,
            7 => SaveSystemScene::GameOver,
            8 => SaveSystemScene::Debug,
            v => SaveSystemScene::Otro(v),
        }
    }
}

impl Default for SaveSystemScene {
    fn default() -> Self { SaveSystemScene::Map }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SaveVehicleLocationVehicleType {
    #[serde(rename = "none")]
    None,
    #[serde(rename = "skiff")]
    Skiff,
    #[serde(rename = "ship")]
    Ship,
    #[serde(rename = "airship")]
    Airship,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SaveVehicleLocationVehicleType {
    pub fn a_i32(self) -> i32 {
        match self {
            SaveVehicleLocationVehicleType::None => 0,
            SaveVehicleLocationVehicleType::Skiff => 1,
            SaveVehicleLocationVehicleType::Ship => 2,
            SaveVehicleLocationVehicleType::Airship => 3,
            SaveVehicleLocationVehicleType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SaveVehicleLocationVehicleType::None,
            1 => SaveVehicleLocationVehicleType::Skiff,
            2 => SaveVehicleLocationVehicleType::Ship,
            3 => SaveVehicleLocationVehicleType::Airship,
            v => SaveVehicleLocationVehicleType::Otro(v),
        }
    }
}

impl Default for SaveVehicleLocationVehicleType {
    fn default() -> Self { SaveVehicleLocationVehicleType::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SkillScope {
    #[serde(rename = "enemy")]
    Enemy,
    #[serde(rename = "enemies")]
    Enemies,
    #[serde(rename = "self")]
    Self_,
    #[serde(rename = "ally")]
    Ally,
    #[serde(rename = "party")]
    Party,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SkillScope {
    pub fn a_i32(self) -> i32 {
        match self {
            SkillScope::Enemy => 0,
            SkillScope::Enemies => 1,
            SkillScope::Self_ => 2,
            SkillScope::Ally => 3,
            SkillScope::Party => 4,
            SkillScope::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SkillScope::Enemy,
            1 => SkillScope::Enemies,
            2 => SkillScope::Self_,
            3 => SkillScope::Ally,
            4 => SkillScope::Party,
            v => SkillScope::Otro(v),
        }
    }
}

impl Default for SkillScope {
    fn default() -> Self { SkillScope::Enemy }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SkillSpType {
    #[serde(rename = "cost")]
    Cost,
    #[serde(rename = "percent")]
    Percent,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SkillSpType {
    pub fn a_i32(self) -> i32 {
        match self {
            SkillSpType::Cost => 0,
            SkillSpType::Percent => 1,
            SkillSpType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SkillSpType::Cost,
            1 => SkillSpType::Percent,
            v => SkillSpType::Otro(v),
        }
    }
}

impl Default for SkillSpType {
    fn default() -> Self { SkillSpType::Cost }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SkillType {
    #[serde(rename = "normal")]
    Normal,
    #[serde(rename = "teleport")]
    Teleport,
    #[serde(rename = "escape")]
    Escape,
    #[serde(rename = "switch")]
    Switch,
    #[serde(rename = "subskill")]
    Subskill,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SkillType {
    pub fn a_i32(self) -> i32 {
        match self {
            SkillType::Normal => 0,
            SkillType::Teleport => 1,
            SkillType::Escape => 2,
            SkillType::Switch => 3,
            SkillType::Subskill => 4,
            SkillType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SkillType::Normal,
            1 => SkillType::Teleport,
            2 => SkillType::Escape,
            3 => SkillType::Switch,
            4 => SkillType::Subskill,
            v => SkillType::Otro(v),
        }
    }
}

impl Default for SkillType {
    fn default() -> Self { SkillType::Normal }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum StateAffectType {
    #[serde(rename = "half")]
    Half,
    #[serde(rename = "double")]
    Double,
    #[serde(rename = "nothing")]
    Nothing,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl StateAffectType {
    pub fn a_i32(self) -> i32 {
        match self {
            StateAffectType::Half => 0,
            StateAffectType::Double => 1,
            StateAffectType::Nothing => 2,
            StateAffectType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => StateAffectType::Half,
            1 => StateAffectType::Double,
            2 => StateAffectType::Nothing,
            v => StateAffectType::Otro(v),
        }
    }
}

impl Default for StateAffectType {
    fn default() -> Self { StateAffectType::Half }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum StateChangeType {
    #[serde(rename = "lose")]
    Lose,
    #[serde(rename = "gain")]
    Gain,
    #[serde(rename = "nothing")]
    Nothing,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl StateChangeType {
    pub fn a_i32(self) -> i32 {
        match self {
            StateChangeType::Lose => 0,
            StateChangeType::Gain => 1,
            StateChangeType::Nothing => 2,
            StateChangeType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => StateChangeType::Lose,
            1 => StateChangeType::Gain,
            2 => StateChangeType::Nothing,
            v => StateChangeType::Otro(v),
        }
    }
}

impl Default for StateChangeType {
    fn default() -> Self { StateChangeType::Lose }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum StatePersistence {
    #[serde(rename = "ends")]
    Ends,
    #[serde(rename = "persists")]
    Persists,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl StatePersistence {
    pub fn a_i32(self) -> i32 {
        match self {
            StatePersistence::Ends => 0,
            StatePersistence::Persists => 1,
            StatePersistence::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => StatePersistence::Ends,
            1 => StatePersistence::Persists,
            v => StatePersistence::Otro(v),
        }
    }
}

impl Default for StatePersistence {
    fn default() -> Self { StatePersistence::Ends }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum StateRestriction {
    #[serde(rename = "normal")]
    Normal,
    #[serde(rename = "do_nothing")]
    DoNothing,
    #[serde(rename = "attack_enemy")]
    AttackEnemy,
    #[serde(rename = "attack_ally")]
    AttackAlly,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl StateRestriction {
    pub fn a_i32(self) -> i32 {
        match self {
            StateRestriction::Normal => 0,
            StateRestriction::DoNothing => 1,
            StateRestriction::AttackEnemy => 2,
            StateRestriction::AttackAlly => 3,
            StateRestriction::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => StateRestriction::Normal,
            1 => StateRestriction::DoNothing,
            2 => StateRestriction::AttackEnemy,
            3 => StateRestriction::AttackAlly,
            v => StateRestriction::Otro(v),
        }
    }
}

impl Default for StateRestriction {
    fn default() -> Self { StateRestriction::Normal }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemBattleCondition {
    #[serde(rename = "none")]
    None,
    #[serde(rename = "initiative")]
    Initiative,
    #[serde(rename = "back")]
    Back,
    #[serde(rename = "surround")]
    Surround,
    #[serde(rename = "pincers")]
    Pincers,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SystemBattleCondition {
    pub fn a_i32(self) -> i32 {
        match self {
            SystemBattleCondition::None => 0,
            SystemBattleCondition::Initiative => 1,
            SystemBattleCondition::Back => 2,
            SystemBattleCondition::Surround => 3,
            SystemBattleCondition::Pincers => 4,
            SystemBattleCondition::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SystemBattleCondition::None,
            1 => SystemBattleCondition::Initiative,
            2 => SystemBattleCondition::Back,
            3 => SystemBattleCondition::Surround,
            4 => SystemBattleCondition::Pincers,
            v => SystemBattleCondition::Otro(v),
        }
    }
}

impl Default for SystemBattleCondition {
    fn default() -> Self { SystemBattleCondition::None }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemBattleFormation {
    #[serde(rename = "terrain")]
    Terrain,
    #[serde(rename = "loose")]
    Loose,
    #[serde(rename = "tight")]
    Tight,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SystemBattleFormation {
    pub fn a_i32(self) -> i32 {
        match self {
            SystemBattleFormation::Terrain => 0,
            SystemBattleFormation::Loose => 1,
            SystemBattleFormation::Tight => 2,
            SystemBattleFormation::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SystemBattleFormation::Terrain,
            1 => SystemBattleFormation::Loose,
            2 => SystemBattleFormation::Tight,
            v => SystemBattleFormation::Otro(v),
        }
    }
}

impl Default for SystemBattleFormation {
    fn default() -> Self { SystemBattleFormation::Terrain }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemEquipmentSetting {
    #[serde(rename = "actor")]
    Actor,
    #[serde(rename = "class")]
    Class,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SystemEquipmentSetting {
    pub fn a_i32(self) -> i32 {
        match self {
            SystemEquipmentSetting::Actor => 0,
            SystemEquipmentSetting::Class => 1,
            SystemEquipmentSetting::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SystemEquipmentSetting::Actor,
            1 => SystemEquipmentSetting::Class,
            v => SystemEquipmentSetting::Otro(v),
        }
    }
}

impl Default for SystemEquipmentSetting {
    fn default() -> Self { SystemEquipmentSetting::Actor }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemFadeIn {
    #[serde(rename = "default")]
    Default,
    #[serde(rename = "fade_in")]
    FadeIn,
    #[serde(rename = "reconstitute_blocks")]
    ReconstituteBlocks,
    #[serde(rename = "unwipe_downward")]
    UnwipeDownward,
    #[serde(rename = "unwipe_upward")]
    UnwipeUpward,
    #[serde(rename = "venetian_blinds")]
    VenetianBlinds,
    #[serde(rename = "vertical_blinds")]
    VerticalBlinds,
    #[serde(rename = "horizontal_blinds")]
    HorizontalBlinds,
    #[serde(rename = "receding_square")]
    RecedingSquare,
    #[serde(rename = "expanding_square")]
    ExpandingSquare,
    #[serde(rename = "screen_moves_down")]
    ScreenMovesDown,
    #[serde(rename = "screen_moves_up")]
    ScreenMovesUp,
    #[serde(rename = "screen_moves_right")]
    ScreenMovesRight,
    #[serde(rename = "screen_moves_left")]
    ScreenMovesLeft,
    #[serde(rename = "vertical_unify")]
    VerticalUnify,
    #[serde(rename = "horizontal_unify")]
    HorizontalUnify,
    #[serde(rename = "unify_quadrants")]
    UnifyQuadrants,
    #[serde(rename = "zoom_out")]
    ZoomOut,
    #[serde(rename = "mosaic")]
    Mosaic,
    #[serde(rename = "waver_screen")]
    WaverScreen,
    #[serde(rename = "instantaneous")]
    Instantaneous,
    #[serde(rename = "none")]
    None,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SystemFadeIn {
    pub fn a_i32(self) -> i32 {
        match self {
            SystemFadeIn::Default => 0,
            SystemFadeIn::FadeIn => 1,
            SystemFadeIn::ReconstituteBlocks => 2,
            SystemFadeIn::UnwipeDownward => 3,
            SystemFadeIn::UnwipeUpward => 4,
            SystemFadeIn::VenetianBlinds => 5,
            SystemFadeIn::VerticalBlinds => 6,
            SystemFadeIn::HorizontalBlinds => 7,
            SystemFadeIn::RecedingSquare => 8,
            SystemFadeIn::ExpandingSquare => 9,
            SystemFadeIn::ScreenMovesDown => 10,
            SystemFadeIn::ScreenMovesUp => 11,
            SystemFadeIn::ScreenMovesRight => 12,
            SystemFadeIn::ScreenMovesLeft => 13,
            SystemFadeIn::VerticalUnify => 14,
            SystemFadeIn::HorizontalUnify => 15,
            SystemFadeIn::UnifyQuadrants => 16,
            SystemFadeIn::ZoomOut => 17,
            SystemFadeIn::Mosaic => 18,
            SystemFadeIn::WaverScreen => 19,
            SystemFadeIn::Instantaneous => 20,
            SystemFadeIn::None => 21,
            SystemFadeIn::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SystemFadeIn::Default,
            1 => SystemFadeIn::FadeIn,
            2 => SystemFadeIn::ReconstituteBlocks,
            3 => SystemFadeIn::UnwipeDownward,
            4 => SystemFadeIn::UnwipeUpward,
            5 => SystemFadeIn::VenetianBlinds,
            6 => SystemFadeIn::VerticalBlinds,
            7 => SystemFadeIn::HorizontalBlinds,
            8 => SystemFadeIn::RecedingSquare,
            9 => SystemFadeIn::ExpandingSquare,
            10 => SystemFadeIn::ScreenMovesDown,
            11 => SystemFadeIn::ScreenMovesUp,
            12 => SystemFadeIn::ScreenMovesRight,
            13 => SystemFadeIn::ScreenMovesLeft,
            14 => SystemFadeIn::VerticalUnify,
            15 => SystemFadeIn::HorizontalUnify,
            16 => SystemFadeIn::UnifyQuadrants,
            17 => SystemFadeIn::ZoomOut,
            18 => SystemFadeIn::Mosaic,
            19 => SystemFadeIn::WaverScreen,
            20 => SystemFadeIn::Instantaneous,
            21 => SystemFadeIn::None,
            v => SystemFadeIn::Otro(v),
        }
    }
}

impl Default for SystemFadeIn {
    fn default() -> Self { SystemFadeIn::Default }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemFadeOut {
    #[serde(rename = "default")]
    Default,
    #[serde(rename = "fade_out")]
    FadeOut,
    #[serde(rename = "remove_blocks")]
    RemoveBlocks,
    #[serde(rename = "wipe_downward")]
    WipeDownward,
    #[serde(rename = "wipe_upward")]
    WipeUpward,
    #[serde(rename = "venetian_blinds")]
    VenetianBlinds,
    #[serde(rename = "vertical_blinds")]
    VerticalBlinds,
    #[serde(rename = "horizontal_blinds")]
    HorizontalBlinds,
    #[serde(rename = "receding_square")]
    RecedingSquare,
    #[serde(rename = "expanding_square")]
    ExpandingSquare,
    #[serde(rename = "screen_moves_up")]
    ScreenMovesUp,
    #[serde(rename = "screen_moves_down")]
    ScreenMovesDown,
    #[serde(rename = "screen_moves_left")]
    ScreenMovesLeft,
    #[serde(rename = "screen_moves_right")]
    ScreenMovesRight,
    #[serde(rename = "vertical_div")]
    VerticalDiv,
    #[serde(rename = "horizontal_div")]
    HorizontalDiv,
    #[serde(rename = "quadrasection")]
    Quadrasection,
    #[serde(rename = "zoom_in")]
    ZoomIn,
    #[serde(rename = "mosaic")]
    Mosaic,
    #[serde(rename = "waver_screen")]
    WaverScreen,
    #[serde(rename = "instantaneous")]
    Instantaneous,
    #[serde(rename = "none")]
    None,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SystemFadeOut {
    pub fn a_i32(self) -> i32 {
        match self {
            SystemFadeOut::Default => 0,
            SystemFadeOut::FadeOut => 1,
            SystemFadeOut::RemoveBlocks => 2,
            SystemFadeOut::WipeDownward => 3,
            SystemFadeOut::WipeUpward => 4,
            SystemFadeOut::VenetianBlinds => 5,
            SystemFadeOut::VerticalBlinds => 6,
            SystemFadeOut::HorizontalBlinds => 7,
            SystemFadeOut::RecedingSquare => 8,
            SystemFadeOut::ExpandingSquare => 9,
            SystemFadeOut::ScreenMovesUp => 10,
            SystemFadeOut::ScreenMovesDown => 11,
            SystemFadeOut::ScreenMovesLeft => 12,
            SystemFadeOut::ScreenMovesRight => 13,
            SystemFadeOut::VerticalDiv => 14,
            SystemFadeOut::HorizontalDiv => 15,
            SystemFadeOut::Quadrasection => 16,
            SystemFadeOut::ZoomIn => 17,
            SystemFadeOut::Mosaic => 18,
            SystemFadeOut::WaverScreen => 19,
            SystemFadeOut::Instantaneous => 20,
            SystemFadeOut::None => 21,
            SystemFadeOut::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SystemFadeOut::Default,
            1 => SystemFadeOut::FadeOut,
            2 => SystemFadeOut::RemoveBlocks,
            3 => SystemFadeOut::WipeDownward,
            4 => SystemFadeOut::WipeUpward,
            5 => SystemFadeOut::VenetianBlinds,
            6 => SystemFadeOut::VerticalBlinds,
            7 => SystemFadeOut::HorizontalBlinds,
            8 => SystemFadeOut::RecedingSquare,
            9 => SystemFadeOut::ExpandingSquare,
            10 => SystemFadeOut::ScreenMovesUp,
            11 => SystemFadeOut::ScreenMovesDown,
            12 => SystemFadeOut::ScreenMovesLeft,
            13 => SystemFadeOut::ScreenMovesRight,
            14 => SystemFadeOut::VerticalDiv,
            15 => SystemFadeOut::HorizontalDiv,
            16 => SystemFadeOut::Quadrasection,
            17 => SystemFadeOut::ZoomIn,
            18 => SystemFadeOut::Mosaic,
            19 => SystemFadeOut::WaverScreen,
            20 => SystemFadeOut::Instantaneous,
            21 => SystemFadeOut::None,
            v => SystemFadeOut::Otro(v),
        }
    }
}

impl Default for SystemFadeOut {
    fn default() -> Self { SystemFadeOut::Default }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemFont {
    #[serde(rename = "gothic")]
    Gothic,
    #[serde(rename = "mincho")]
    Mincho,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SystemFont {
    pub fn a_i32(self) -> i32 {
        match self {
            SystemFont::Gothic => 0,
            SystemFont::Mincho => 1,
            SystemFont::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SystemFont::Gothic,
            1 => SystemFont::Mincho,
            v => SystemFont::Otro(v),
        }
    }
}

impl Default for SystemFont {
    fn default() -> Self { SystemFont::Gothic }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemStretch {
    #[serde(rename = "stretch")]
    Stretch,
    #[serde(rename = "tiled")]
    Tiled,
    #[serde(rename = "easyrpg_none")]
    EasyrpgNone,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl SystemStretch {
    pub fn a_i32(self) -> i32 {
        match self {
            SystemStretch::Stretch => 0,
            SystemStretch::Tiled => 1,
            SystemStretch::EasyrpgNone => 2,
            SystemStretch::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => SystemStretch::Stretch,
            1 => SystemStretch::Tiled,
            2 => SystemStretch::EasyrpgNone,
            v => SystemStretch::Otro(v),
        }
    }
}

impl Default for SystemStretch {
    fn default() -> Self { SystemStretch::Stretch }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TerrainBGAssociation {
    #[serde(rename = "background")]
    Background,
    #[serde(rename = "frame")]
    Frame,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl TerrainBGAssociation {
    pub fn a_i32(self) -> i32 {
        match self {
            TerrainBGAssociation::Background => 0,
            TerrainBGAssociation::Frame => 1,
            TerrainBGAssociation::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => TerrainBGAssociation::Background,
            1 => TerrainBGAssociation::Frame,
            v => TerrainBGAssociation::Otro(v),
        }
    }
}

impl Default for TerrainBGAssociation {
    fn default() -> Self { TerrainBGAssociation::Background }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TerrainBushDepth {
    #[serde(rename = "normal")]
    Normal,
    #[serde(rename = "third")]
    Third,
    #[serde(rename = "half")]
    Half,
    #[serde(rename = "full")]
    Full,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl TerrainBushDepth {
    pub fn a_i32(self) -> i32 {
        match self {
            TerrainBushDepth::Normal => 0,
            TerrainBushDepth::Third => 1,
            TerrainBushDepth::Half => 2,
            TerrainBushDepth::Full => 3,
            TerrainBushDepth::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => TerrainBushDepth::Normal,
            1 => TerrainBushDepth::Third,
            2 => TerrainBushDepth::Half,
            3 => TerrainBushDepth::Full,
            v => TerrainBushDepth::Otro(v),
        }
    }
}

impl Default for TerrainBushDepth {
    fn default() -> Self { TerrainBushDepth::Normal }
}

/// Generado desde `enums.csv`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TreeMapMapType {
    #[serde(rename = "root")]
    Root,
    #[serde(rename = "map")]
    Map,
    #[serde(rename = "area")]
    Area,
    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.
    Otro(i32),
}

impl TreeMapMapType {
    pub fn a_i32(self) -> i32 {
        match self {
            TreeMapMapType::Root => 0,
            TreeMapMapType::Map => 1,
            TreeMapMapType::Area => 2,
            TreeMapMapType::Otro(v) => v,
        }
    }
    pub fn de_i32(v: i32) -> Self {
        match v {
            0 => TreeMapMapType::Root,
            1 => TreeMapMapType::Map,
            2 => TreeMapMapType::Area,
            v => TreeMapMapType::Otro(v),
        }
    }
}

impl Default for TreeMapMapType {
    fn default() -> Self { TreeMapMapType::Root }
}

/// Generado desde `flags.csv`: el orden de los campos **es** el orden
/// de los bits, del menos significativo para arriba.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct EventPageConditionFlags {
    pub switch_a: bool,
    pub switch_b: bool,
    pub variable: bool,
    pub item: bool,
    pub actor: bool,
    pub timer: bool,
}

impl EventPageConditionFlags {
    pub fn leer(d: &[u8]) -> Self {
        let mut f = Self::default();
        f.switch_a = bit(d, 0);
        f.switch_b = bit(d, 1);
        f.variable = bit(d, 2);
        f.item = bit(d, 3);
        f.actor = bit(d, 4);
        f.timer = bit(d, 5);
        f
    }
    pub fn escribir(&self) -> Vec<u8> {
        let mut b = vec![0u8; 1];
        if self.switch_a { b[0] |= 1 << 0; }
        if self.switch_b { b[0] |= 1 << 1; }
        if self.variable { b[0] |= 1 << 2; }
        if self.item { b[0] |= 1 << 3; }
        if self.actor { b[0] |= 1 << 4; }
        if self.timer { b[0] |= 1 << 5; }
        b
    }
}

/// Generado desde `flags.csv`: el orden de los campos **es** el orden
/// de los bits, del menos significativo para arriba.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SavePictureFlags {
}

impl SavePictureFlags {
    pub fn leer(d: &[u8]) -> Self {
        let f = Self::default();
        f
    }
    pub fn escribir(&self) -> Vec<u8> {
        let b = vec![0u8; 0];
        b
    }
}

/// Generado desde `flags.csv`: el orden de los campos **es** el orden
/// de los bits, del menos significativo para arriba.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct TerrainFlags {
}

impl TerrainFlags {
    pub fn leer(d: &[u8]) -> Self {
        let f = Self::default();
        f
    }
    pub fn escribir(&self) -> Vec<u8> {
        let b = vec![0u8; 0];
        b
    }
}

/// Generado desde `flags.csv`: el orden de los campos **es** el orden
/// de los bits, del menos significativo para arriba.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct TroopPageConditionFlags {
    pub switch_a: bool,
    pub switch_b: bool,
    pub variable: bool,
    pub turn: bool,
    pub fatigue: bool,
    pub enemy_hp: bool,
    pub actor_hp: bool,
}

impl TroopPageConditionFlags {
    pub fn leer(d: &[u8]) -> Self {
        let mut f = Self::default();
        f.switch_a = bit(d, 0);
        f.switch_b = bit(d, 1);
        f.variable = bit(d, 2);
        f.turn = bit(d, 3);
        f.fatigue = bit(d, 4);
        f.enemy_hp = bit(d, 5);
        f.actor_hp = bit(d, 6);
        f
    }
    pub fn escribir(&self) -> Vec<u8> {
        let mut b = vec![0u8; 1];
        if self.switch_a { b[0] |= 1 << 0; }
        if self.switch_b { b[0] |= 1 << 1; }
        if self.variable { b[0] |= 1 << 2; }
        if self.turn { b[0] |= 1 << 3; }
        if self.fatigue { b[0] |= 1 << 4; }
        if self.enemy_hp { b[0] |= 1 << 5; }
        if self.actor_hp { b[0] |= 1 << 6; }
        b
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Actor {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// default: 50|99
    pub final_level: i32,
    /// campo 0x09 del binario
    /// default: True
    pub critical_hit: bool,
    /// campo 0x0a del binario
    /// default: 30
    pub critical_hit_chance: i32,
    /// campo 0x0f del binario
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
    /// campo 0x1f del binario, se guarda aunque valga el default
    pub parameters: Parameters,
    /// campo 0x29 del binario
    /// default: 30|300
    pub exp_base: i32,
    /// campo 0x2a del binario
    /// default: 30|300
    pub exp_inflation: i32,
    /// campo 0x2b del binario
    /// default: 0
    pub exp_correction: i32,
    /// campo 0x33 del binario, se guarda aunque valga el default
    pub initial_equipment: Equipment,
    /// campo 0x38 del binario
    /// default: 1
    pub unarmed_animation: i32,
    /// campo 0x3f del binario, se guarda aunque valga el default
    pub skills: Vec<Learning>,
    /// campo 0x42 del binario
    /// default: False
    pub rename_skill: bool,
    /// campo 0x43 del binario
    pub skill_name: String,
    /// campo 0x48 del binario, se guarda aunque valga el default
    pub state_ranks: Vec<u8>,
    /// campo 0x4a del binario, se guarda aunque valga el default
    pub attribute_ranks: Vec<u8>,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Actor {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            title: "".to_string(),
            character_name: "".to_string(),
            character_index: 0,
            transparent: false,
            initial_level: 1,
            final_level: 50,
            critical_hit: true,
            critical_hit_chance: 30,
            face_name: "".to_string(),
            face_index: 0,
            two_weapon: false,
            lock_equipment: false,
            auto_battle: false,
            super_guard: false,
            parameters: Default::default(),
            exp_base: 30,
            exp_inflation: 30,
            exp_correction: 0,
            initial_equipment: Default::default(),
            unarmed_animation: 1,
            skills: Default::default(),
            rename_skill: false,
            skill_name: "".to_string(),
            state_ranks: Vec::new(),
            attribute_ranks: Vec::new(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Animation {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x0a del binario, se guarda aunque valga el default
    /// default: 2
    pub position: AnimationPosition,
    /// campo 0x0c del binario, se guarda aunque valga el default
    pub frames: Vec<AnimationFrame>,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Animation {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            animation_name: "".to_string(),
            large: false,
            timings: Default::default(),
            scope: AnimationScope::de_i32(0),
            position: AnimationPosition::de_i32(2),
            frames: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct AnimationCellData {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x0a del binario
    /// default: 0
    pub transparency: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for AnimationCellData {
    fn default() -> Self {
        Self {
            id: 0,
            valid: 1,
            cell_id: 0,
            x: 0,
            y: 0,
            zoom: 100,
            tone_red: 100,
            tone_green: 100,
            tone_blue: 100,
            tone_gray: 100,
            transparency: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct AnimationFrame {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub cells: Vec<AnimationCellData>,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for AnimationFrame {
    fn default() -> Self {
        Self {
            id: 0,
            cells: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct AnimationTiming {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for AnimationTiming {
    fn default() -> Self {
        Self {
            id: 0,
            frame: 0,
            se: Default::default(),
            flash_scope: AnimationTimingFlashScope::de_i32(0),
            flash_red: 31,
            flash_green: 31,
            flash_blue: 31,
            flash_power: 31,
            screen_shake: AnimationTimingScreenShake::de_i32(0),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Attribute {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario, se guarda aunque valga el default
    /// default: 0
    pub r#type: AttributeType,
    /// campo 0x0b del binario
    /// default: 300
    pub a_rate: i32,
    /// campo 0x0c del binario
    /// default: 200
    pub b_rate: i32,
    /// campo 0x0d del binario
    /// default: 100
    pub c_rate: i32,
    /// campo 0x0e del binario
    /// default: 50
    pub d_rate: i32,
    /// campo 0x0f del binario
    /// default: 0
    pub e_rate: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Attribute {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            r#type: AttributeType::de_i32(0),
            a_rate: 300,
            b_rate: 200,
            c_rate: 100,
            d_rate: 50,
            e_rate: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct BattleCommand {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub name: String,
    /// campo 0x02 del binario
    /// default: 0
    pub r#type: BattleCommandType,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for BattleCommand {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            r#type: BattleCommandType::de_i32(0),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
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
    /// campo 0x0a del binario, se guarda aunque valga el default
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
    /// campo 0x1a del binario
    /// default: 1
    pub death_teleport_id: i32,
    /// campo 0x1b del binario
    /// default: 0
    pub death_teleport_x: i32,
    /// campo 0x1c del binario
    /// default: 0
    pub death_teleport_y: i32,
    /// campo 0x1d del binario
    /// default: 0
    pub death_teleport_face: BattleCommandsFacing,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for BattleCommands {
    fn default() -> Self {
        Self {
            placement: BattleCommandsPlacement::de_i32(0),
            row: BattleCommandsRowShown::de_i32(0),
            battle_type: BattleCommandsBattleType::de_i32(0),
            unused_display_normal_parameters: true,
            commands: Default::default(),
            death_event: 1,
            window_size: BattleCommandsWindowSize::de_i32(0),
            transparency: BattleCommandsTransparency::de_i32(0),
            death_teleport: false,
            death_teleport_id: 1,
            death_teleport_x: 0,
            death_teleport_y: 0,
            death_teleport_face: BattleCommandsFacing::de_i32(0),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Chipset {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x0b del binario
    /// default: 0
    pub animation_type: ChipsetAnimType,
    /// campo 0x0c del binario
    /// default: 0
    pub animation_speed: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Chipset {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            chipset_name: "".to_string(),
            terrain_data: vec![1; 162],
            passable_data_lower: vec![15; 162],
            passable_data_upper: [vec![31; 1], vec![15; 143]].concat(),
            animation_type: ChipsetAnimType::de_i32(0),
            animation_speed: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Class {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x1f del binario
    pub parameters: Parameters,
    /// campo 0x29 del binario
    /// default: 300
    pub exp_base: i32,
    /// campo 0x2a del binario
    /// default: 300
    pub exp_inflation: i32,
    /// campo 0x2b del binario
    /// default: 0
    pub exp_correction: i32,
    /// campo 0x3e del binario
    /// default: 0
    pub battler_animation: i32,
    /// campo 0x3f del binario, se guarda aunque valga el default
    pub skills: Vec<Learning>,
    /// campo 0x48 del binario, se guarda aunque valga el default
    pub state_ranks: Vec<u8>,
    /// campo 0x4a del binario, se guarda aunque valga el default
    pub attribute_ranks: Vec<u8>,
    /// campo 0x50 del binario, se guarda aunque valga el default
    pub battle_commands: Vec<i32>,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Class {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            two_weapon: false,
            lock_equipment: false,
            auto_battle: false,
            super_guard: false,
            parameters: Default::default(),
            exp_base: 300,
            exp_inflation: 300,
            exp_correction: 0,
            battler_animation: 0,
            skills: Default::default(),
            state_ranks: Vec::new(),
            attribute_ranks: Vec::new(),
            battle_commands: Vec::new(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct CommonEvent {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x0b del binario, se guarda aunque valga el default
    /// default: 5
    pub trigger: CommonEventTrigger,
    /// campo 0x0c del binario
    /// default: False
    pub switch_flag: bool,
    /// campo 0x0d del binario
    /// default: 1
    pub switch_id: i32,
    /// campo 0x16 del binario, se guarda aunque valga el default
    pub event_commands: Vec<EventCommand>,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for CommonEvent {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            trigger: CommonEventTrigger::de_i32(5),
            switch_flag: false,
            switch_id: 1,
            event_commands: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Database {
    /// campo 0x0b del binario, se guarda aunque valga el default
    pub actors: Vec<Actor>,
    /// campo 0x0c del binario, se guarda aunque valga el default
    pub skills: Vec<Skill>,
    /// campo 0x0d del binario, se guarda aunque valga el default
    pub items: Vec<Item>,
    /// campo 0x0e del binario, se guarda aunque valga el default
    pub enemies: Vec<Enemy>,
    /// campo 0x0f del binario, se guarda aunque valga el default
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
    /// campo 0x1a del binario
    /// default: 0
    pub version: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Database {
    fn default() -> Self {
        Self {
            actors: Default::default(),
            skills: Default::default(),
            items: Default::default(),
            enemies: Default::default(),
            troops: Default::default(),
            terrains: Default::default(),
            attributes: Default::default(),
            states: Default::default(),
            animations: Default::default(),
            chipsets: Default::default(),
            terms: Default::default(),
            system: Default::default(),
            switches: Default::default(),
            variables: Default::default(),
            commonevents: Default::default(),
            version: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Encounter {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x01 del binario
    /// default: 0
    pub troop_id: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Encounter {
    fn default() -> Self {
        Self {
            id: 0,
            troop_id: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Enemy {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x0a del binario
    /// default: False
    pub transparent: bool,
    /// campo 0x0b del binario
    /// default: 0
    pub exp: i32,
    /// campo 0x0c del binario
    /// default: 0
    pub gold: i32,
    /// campo 0x0d del binario
    /// default: 0
    pub drop_id: i32,
    /// campo 0x0e del binario
    /// default: 100
    pub drop_prob: i32,
    /// campo 0x15 del binario
    /// default: False
    pub critical_hit: bool,
    /// campo 0x16 del binario
    /// default: 30
    pub critical_hit_chance: i32,
    /// campo 0x1a del binario
    /// default: False
    pub miss: bool,
    /// campo 0x1c del binario
    /// default: False
    pub levitate: bool,
    /// campo 0x20 del binario, se guarda aunque valga el default
    pub state_ranks: Vec<u8>,
    /// campo 0x22 del binario, se guarda aunque valga el default
    pub attribute_ranks: Vec<u8>,
    /// campo 0x2a del binario, se guarda aunque valga el default
    pub actions: Vec<EnemyAction>,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Enemy {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            battler_name: "".to_string(),
            battler_hue: 0,
            max_hp: 10,
            max_sp: 10,
            attack: 10,
            defense: 10,
            spirit: 10,
            agility: 10,
            transparent: false,
            exp: 0,
            gold: 0,
            drop_id: 0,
            drop_prob: 100,
            critical_hit: false,
            critical_hit_chance: 30,
            miss: false,
            levitate: false,
            state_ranks: Vec::new(),
            attribute_ranks: Vec::new(),
            actions: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct EnemyAction {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x0a del binario
    /// default: 1
    pub switch_on_id: i32,
    /// campo 0x0b del binario
    /// default: False
    pub switch_off: bool,
    /// campo 0x0c del binario
    /// default: 1
    pub switch_off_id: i32,
    /// campo 0x0d del binario
    /// default: 50
    pub rating: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for EnemyAction {
    fn default() -> Self {
        Self {
            id: 0,
            kind: EnemyActionKind::de_i32(0),
            basic: EnemyActionBasic::de_i32(1),
            skill_id: 1,
            enemy_id: 1,
            condition_type: EnemyActionConditionType::de_i32(0),
            condition_param1: 0,
            condition_param2: 0,
            switch_id: 1,
            switch_on: false,
            switch_on_id: 1,
            switch_off: false,
            switch_off_id: 1,
            rating: 50,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Equipment {
    /// campo 0x00 del binario
    /// default: 0
    pub weapon_id: i32,
    /// campo 0x00 del binario
    /// default: 0
    pub shield_id: i32,
    /// campo 0x00 del binario
    /// default: 0
    pub armor_id: i32,
    /// campo 0x00 del binario
    /// default: 0
    pub helmet_id: i32,
    /// campo 0x00 del binario
    /// default: 0
    pub accessory_id: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Equipment {
    fn default() -> Self {
        Self {
            weapon_id: 0,
            shield_id: 0,
            armor_id: 0,
            helmet_id: 0,
            accessory_id: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Event {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Event {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            x: 0,
            y: 0,
            pages: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct EventCommand {
    /// campo 0x00 del binario
    /// default: 0
    pub code: EventCommandCode,
    /// campo 0x00 del binario
    /// default: 0
    pub indent: i32,
    /// campo 0x00 del binario
    pub string: String,
    /// campo 0x00 del binario
    pub parameters: Vec<i32>,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for EventCommand {
    fn default() -> Self {
        Self {
            code: EventCommandCode::de_i32(0),
            indent: 0,
            string: "".to_string(),
            parameters: Vec::new(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct EventPage {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x1f del binario, se guarda aunque valga el default
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for EventPage {
    fn default() -> Self {
        Self {
            id: 0,
            condition: Default::default(),
            character_name: "".to_string(),
            character_index: 0,
            character_direction: EventPageDirection::de_i32(2),
            character_pattern: EventPageFrame::de_i32(1),
            translucent: false,
            move_type: EventPageMoveType::de_i32(1),
            move_frequency: 3,
            trigger: EventPageTrigger::de_i32(0),
            layer: EventPageLayers::de_i32(0),
            overlap_forbidden: false,
            animation_type: EventPageAnimType::de_i32(0),
            move_speed: EventPageMoveSpeed::de_i32(3),
            move_route: Default::default(),
            event_commands: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct EventPageCondition {
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub flags: EventPageConditionFlags,
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for EventPageCondition {
    fn default() -> Self {
        Self {
            flags: Default::default(),
            switch_a_id: 1,
            switch_b_id: 1,
            variable_id: 1,
            variable_value: 0,
            item_id: 1,
            actor_id: 1,
            timer_sec: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Item {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x0b del binario
    /// default: 0
    pub atk_points1: i32,
    /// campo 0x0c del binario
    /// default: 0
    pub def_points1: i32,
    /// campo 0x0d del binario
    /// default: 0
    pub spi_points1: i32,
    /// campo 0x0e del binario
    /// default: 0
    pub agi_points1: i32,
    /// campo 0x0f del binario, se guarda aunque valga el default
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
    /// campo 0x1a del binario
    /// default: False
    pub raise_evasion: bool,
    /// campo 0x1b del binario
    /// default: False
    pub half_sp_cost: bool,
    /// campo 0x1c del binario
    /// default: False
    pub no_terrain_damage: bool,
    /// campo 0x1f del binario, se guarda aunque valga el default
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
    /// campo 0x2a del binario
    /// default: 0
    pub max_sp_points: i32,
    /// campo 0x2b del binario
    /// default: 0
    pub atk_points2: i32,
    /// campo 0x2c del binario
    /// default: 0
    pub def_points2: i32,
    /// campo 0x2d del binario
    /// default: 0
    pub spi_points2: i32,
    /// campo 0x2e del binario
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
    /// campo 0x3a del binario
    /// default: False
    pub occasion_battle: bool,
    /// campo 0x3e del binario, se guarda aunque valga el default
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
    /// campo 0x4b del binario
    /// default: 0
    pub ranged_trajectory: ItemTrajectory,
    /// campo 0x4c del binario
    /// default: 0
    pub ranged_target: ItemTarget,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Item {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            description: "".to_string(),
            r#type: ItemType::de_i32(0),
            price: 0,
            uses: 1,
            atk_points1: 0,
            def_points1: 0,
            spi_points1: 0,
            agi_points1: 0,
            two_handed: false,
            sp_cost: 0,
            hit: 90,
            critical_hit: 0,
            animation_id: 1,
            preemptive: false,
            dual_attack: false,
            attack_all: false,
            ignore_evasion: false,
            prevent_critical: false,
            raise_evasion: false,
            half_sp_cost: false,
            no_terrain_damage: false,
            entire_party: false,
            recover_hp_rate: 0,
            recover_hp: 0,
            recover_sp_rate: 0,
            recover_sp: 0,
            occasion_field1: false,
            ko_only: false,
            max_hp_points: 0,
            max_sp_points: 0,
            atk_points2: 0,
            def_points2: 0,
            spi_points2: 0,
            agi_points2: 0,
            using_message: 0,
            skill_id: 1,
            switch_id: 1,
            occasion_field2: true,
            occasion_battle: false,
            actor_set: Vec::new(),
            state_set: Vec::new(),
            attribute_set: Vec::new(),
            state_chance: 0,
            reverse_state_effect: false,
            ranged_trajectory: ItemTrajectory::de_i32(0),
            ranged_target: ItemTarget::de_i32(0),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Learning {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x01 del binario
    /// default: 1
    pub level: i32,
    /// campo 0x02 del binario
    /// default: 1
    pub skill_id: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Learning {
    fn default() -> Self {
        Self {
            id: 0,
            level: 1,
            skill_id: 1,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
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
    /// campo 0x0b del binario, se guarda aunque valga el default
    /// default: 0
    pub scroll_type: MapScrollType,
    /// campo 0x1f del binario
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
    /// campo 0x2a del binario
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
    /// campo 0x3c del binario
    pub generator_x: Vec<u32>,
    /// campo 0x3d del binario
    pub generator_y: Vec<u32>,
    /// campo 0x3e del binario
    pub generator_tile_ids: Vec<i16>,
    /// campo 0x47 del binario, se guarda aunque valga el default
    pub lower_layer: Vec<i16>,
    /// campo 0x48 del binario, se guarda aunque valga el default
    pub upper_layer: Vec<i16>,
    /// campo 0x51 del binario, se guarda aunque valga el default
    pub events: Vec<Event>,
    /// campo 0x5b del binario
    /// default: 0
    pub save_count: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Map {
    fn default() -> Self {
        Self {
            chipset_id: 1,
            width: 20,
            height: 15,
            scroll_type: MapScrollType::de_i32(0),
            parallax_flag: false,
            parallax_name: "".to_string(),
            parallax_loop_x: false,
            parallax_loop_y: false,
            parallax_auto_loop_x: false,
            parallax_sx: 0,
            parallax_auto_loop_y: false,
            parallax_sy: 0,
            generator_flag: false,
            generator_mode: MapGeneratorMode::de_i32(0),
            top_level: false,
            generator_tiles: MapGeneratorTiles::de_i32(0),
            generator_width: 4,
            generator_height: 1,
            generator_surround: true,
            generator_upper_wall: true,
            generator_floor_b: true,
            generator_floor_c: true,
            generator_extra_b: true,
            generator_extra_c: true,
            generator_x: Vec::new(),
            generator_y: Vec::new(),
            generator_tile_ids: Vec::new(),
            lower_layer: Vec::new(),
            upper_layer: Vec::new(),
            events: Default::default(),
            save_count: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct MapInfo {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x0b del binario, se guarda aunque valga el default
    /// default: 0
    pub music_type: MapInfoMusicType,
    /// campo 0x0c del binario, se guarda aunque valga el default
    pub music: Music,
    /// campo 0x15 del binario, se guarda aunque valga el default
    /// default: 0
    pub background_type: MapInfoBGMType,
    /// campo 0x16 del binario
    pub background_name: String,
    /// campo 0x1f del binario, se guarda aunque valga el default
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
    /// campo 0x2c del binario
    /// default: 25
    pub encounter_steps: i32,
    /// campo 0x33 del binario, se guarda aunque valga el default
    pub area_rect: Rect,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for MapInfo {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            parent_map: 0,
            indentation: 0,
            r#type: TreeMapMapType::de_i32(-1),
            scrollbar_x: 0,
            scrollbar_y: 0,
            expanded_node: false,
            music_type: MapInfoMusicType::de_i32(0),
            music: Default::default(),
            background_type: MapInfoBGMType::de_i32(0),
            background_name: "".to_string(),
            teleport: MapInfoTriState::de_i32(0),
            escape: MapInfoTriState::de_i32(0),
            save: MapInfoTriState::de_i32(0),
            encounters: Default::default(),
            encounter_steps: 25,
            area_rect: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct MoveCommand {
    /// campo 0x00 del binario
    /// default: 0
    pub command_id: MoveCommandCode,
    /// campo 0x00 del binario
    pub parameter_string: String,
    /// campo 0x00 del binario
    /// default: 0
    pub parameter_a: i32,
    /// campo 0x00 del binario
    /// default: 0
    pub parameter_b: i32,
    /// campo 0x00 del binario
    /// default: 0
    pub parameter_c: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for MoveCommand {
    fn default() -> Self {
        Self {
            command_id: MoveCommandCode::de_i32(0),
            parameter_string: "".to_string(),
            parameter_a: 0,
            parameter_b: 0,
            parameter_c: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct MoveRoute {
    /// campo 0x0c del binario, se guarda aunque valga el default
    pub move_commands: Vec<MoveCommand>,
    /// campo 0x15 del binario
    /// default: True
    pub repeat: bool,
    /// campo 0x16 del binario
    /// default: False
    pub skippable: bool,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for MoveRoute {
    fn default() -> Self {
        Self {
            move_commands: Default::default(),
            repeat: true,
            skippable: false,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Music {
    /// campo 0x01 del binario, se guarda aunque valga el default
    /// default: "(OFF)"
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Music {
    fn default() -> Self {
        Self {
            name: "\"(OFF)\"".to_string(),
            fadein: 0,
            volume: 100,
            tempo: 100,
            balance: 50,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Parameters {
    /// campo 0x00 del binario, se guarda aunque valga el default
    pub maxhp: Vec<i16>,
    /// campo 0x00 del binario, se guarda aunque valga el default
    pub maxsp: Vec<i16>,
    /// campo 0x00 del binario, se guarda aunque valga el default
    pub attack: Vec<i16>,
    /// campo 0x00 del binario, se guarda aunque valga el default
    pub defense: Vec<i16>,
    /// campo 0x00 del binario, se guarda aunque valga el default
    pub spirit: Vec<i16>,
    /// campo 0x00 del binario, se guarda aunque valga el default
    pub agility: Vec<i16>,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Parameters {
    fn default() -> Self {
        Self {
            maxhp: Vec::new(),
            maxsp: Vec::new(),
            attack: Vec::new(),
            defense: Vec::new(),
            spirit: Vec::new(),
            agility: Vec::new(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Rect {
    /// campo 0x00 del binario
    /// default: 0
    pub l: u32,
    /// campo 0x00 del binario
    /// default: 0
    pub t: u32,
    /// campo 0x00 del binario
    /// default: 0
    pub r: u32,
    /// campo 0x00 del binario
    /// default: 0
    pub b: u32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Rect {
    fn default() -> Self {
        Self {
            l: 0,
            t: 0,
            r: 0,
            b: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
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
    /// campo 0x6a del binario, se guarda aunque valga el default
    pub ship_location: SaveVehicleLocation,
    /// campo 0x6b del binario, se guarda aunque valga el default
    pub airship_location: SaveVehicleLocation,
    /// campo 0x6c del binario, se guarda aunque valga el default
    pub actors: Vec<SaveActor>,
    /// campo 0x6d del binario, se guarda aunque valga el default
    pub inventory: SaveInventory,
    /// campo 0x6e del binario, se guarda aunque valga el default
    pub targets: Vec<SaveTarget>,
    /// campo 0x6f del binario, se guarda aunque valga el default
    pub map_info: SaveMapInfo,
    /// campo 0x70 del binario, se guarda aunque valga el default
    pub panorama: SavePanorama,
    /// campo 0x71 del binario, se guarda aunque valga el default
    pub foreground_event_execstate: SaveEventExecState,
    /// campo 0x72 del binario, se guarda aunque valga el default
    pub common_events: Vec<SaveCommonEvent>,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Save {
    fn default() -> Self {
        Self {
            title: Default::default(),
            system: Default::default(),
            screen: Default::default(),
            pictures: Default::default(),
            party_location: Default::default(),
            boat_location: Default::default(),
            ship_location: Default::default(),
            airship_location: Default::default(),
            actors: Default::default(),
            inventory: Default::default(),
            targets: Default::default(),
            map_info: Default::default(),
            panorama: Default::default(),
            foreground_event_execstate: Default::default(),
            common_events: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SaveActor {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x01 del binario, se guarda aunque valga el default
    /// default: kEmptyName
    pub name: String,
    /// campo 0x02 del binario, se guarda aunque valga el default
    /// default: kEmptyName
    pub title: String,
    /// campo 0x0b del binario
    pub sprite_name: String,
    /// campo 0x0c del binario
    /// default: 0
    pub sprite_id: i32,
    /// campo 0x0d del binario
    /// default: 0
    pub transparency: i32,
    /// campo 0x15 del binario
    pub face_name: String,
    /// campo 0x16 del binario
    /// default: 0
    pub face_id: i32,
    /// campo 0x1f del binario
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
    /// campo 0x2a del binario
    /// default: 0
    pub defense_mod: i32,
    /// campo 0x2b del binario
    /// default: 0
    pub spirit_mod: i32,
    /// campo 0x2c del binario
    /// default: 0
    pub agility_mod: i32,
    /// campo 0x34 del binario, se guarda aunque valga el default
    pub skills: Vec<i16>,
    /// campo 0x3d del binario, se guarda aunque valga el default
    /// default: [0]*5
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
    /// campo 0x5a del binario
    /// default: -1
    pub class_id: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveActor {
    fn default() -> Self {
        Self {
            id: 0,
            name: "\u{1}".to_string(),
            title: "\u{1}".to_string(),
            sprite_name: "".to_string(),
            sprite_id: 0,
            transparency: 0,
            face_name: "".to_string(),
            face_id: 0,
            level: -1,
            exp: -1,
            hp_mod: -1,
            sp_mod: -1,
            attack_mod: 0,
            defense_mod: 0,
            spirit_mod: 0,
            agility_mod: 0,
            skills: Vec::new(),
            equipped: vec![0; 5],
            current_hp: -1,
            current_sp: -1,
            status: Vec::new(),
            changed_battle_commands: false,
            class_id: -1,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SaveCommonEvent {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub parallel_event_execstate: SaveEventExecState,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveCommonEvent {
    fn default() -> Self {
        Self {
            id: 0,
            parallel_event_execstate: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SaveEventExecFrame {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x02 del binario, se guarda aunque valga el default
    pub commands: Vec<EventCommand>,
    /// campo 0x0b del binario
    /// default: 0
    pub current_command: i32,
    /// campo 0x0c del binario
    /// default: 0
    pub event_id: i32,
    /// campo 0x0d del binario
    /// default: False
    pub triggered_by_decision_key: bool,
    /// campo 0x16 del binario, se guarda aunque valga el default
    pub subcommand_path: Vec<u8>,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveEventExecFrame {
    fn default() -> Self {
        Self {
            id: 0,
            commands: Default::default(),
            current_command: 0,
            event_id: 0,
            triggered_by_decision_key: false,
            subcommand_path: Vec::new(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SaveEventExecState {
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub stack: Vec<SaveEventExecFrame>,
    /// campo 0x04 del binario
    /// default: False
    pub show_message: bool,
    /// campo 0x0b del binario
    /// default: False
    pub abort_on_escape: bool,
    /// campo 0x0d del binario
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
    /// campo 0x1a del binario
    /// default: 0
    pub keyinput_2kshift_2k3numbers: i32,
    /// campo 0x1b del binario
    /// default: 0
    pub keyinput_2kdown_2k3operators: i32,
    /// campo 0x1c del binario
    /// default: 0
    pub keyinput_2kleft_2k3shift: i32,
    /// campo 0x1d del binario
    /// default: 0
    pub keyinput_2kright: i32,
    /// campo 0x1e del binario
    /// default: 0
    pub keyinput_2kup: i32,
    /// campo 0x1f del binario
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveEventExecState {
    fn default() -> Self {
        Self {
            stack: Default::default(),
            show_message: false,
            abort_on_escape: false,
            wait_movement: false,
            keyinput_wait: false,
            keyinput_variable: 0,
            keyinput_all_directions: false,
            keyinput_decision: 0,
            keyinput_cancel: 0,
            keyinput_2kshift_2k3numbers: 0,
            keyinput_2kdown_2k3operators: 0,
            keyinput_2kleft_2k3shift: 0,
            keyinput_2kright: 0,
            keyinput_2kup: 0,
            wait_time: 0,
            keyinput_time_variable: 0,
            keyinput_2k3down: 0,
            keyinput_2k3left: 0,
            keyinput_2k3right: 0,
            keyinput_2k3up: 0,
            keyinput_timed: false,
            wait_key_enter: false,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SaveInventory {
    /// campo 0x02 del binario, se guarda aunque valga el default
    pub party: Vec<i16>,
    /// campo 0x0c del binario, se guarda aunque valga el default
    pub item_ids: Vec<i16>,
    /// campo 0x0d del binario, se guarda aunque valga el default
    pub item_counts: Vec<u8>,
    /// campo 0x0e del binario, se guarda aunque valga el default
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
    /// campo 0x1a del binario
    /// default: False
    pub timer1_battle: bool,
    /// campo 0x1b del binario
    /// default: 0
    pub timer2_frames: i32,
    /// campo 0x1c del binario
    /// default: False
    pub timer2_active: bool,
    /// campo 0x1d del binario
    /// default: False
    pub timer2_visible: bool,
    /// campo 0x1e del binario
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
    /// campo 0x2a del binario
    /// default: 0
    pub steps: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveInventory {
    fn default() -> Self {
        Self {
            party: Vec::new(),
            item_ids: Vec::new(),
            item_counts: Vec::new(),
            item_usage: Vec::new(),
            gold: 0,
            timer1_frames: 0,
            timer1_active: false,
            timer1_visible: false,
            timer1_battle: false,
            timer2_frames: 0,
            timer2_active: false,
            timer2_visible: false,
            timer2_battle: false,
            battles: 0,
            defeats: 0,
            escapes: 0,
            victories: 0,
            turns: 0,
            steps: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SaveMapEvent {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x65 del binario
    /// default: False
    pub waiting_execution: bool,
    /// campo 0x66 del binario
    /// default: 0
    pub original_move_route_index: i32,
    /// campo 0x67 del binario
    /// default: False
    pub triggered_by_decision_key: bool,
    /// campo 0x6c del binario, se guarda aunque valga el default
    pub parallel_event_execstate: SaveEventExecState,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveMapEvent {
    fn default() -> Self {
        Self {
            id: 0,
            waiting_execution: false,
            original_move_route_index: 0,
            triggered_by_decision_key: false,
            parallel_event_execstate: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SaveMapEventBase {
    /// campo 0x01 del binario
    /// default: True
    pub active: bool,
    /// campo 0x0b del binario, se guarda aunque valga el default
    /// default: 0
    pub map_id: i32,
    /// campo 0x0c del binario, se guarda aunque valga el default
    /// default: 0
    pub position_x: i32,
    /// campo 0x0d del binario, se guarda aunque valga el default
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
    /// campo 0x1f del binario
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
    /// campo 0x2a del binario
    /// default: False
    pub move_route_overwrite: bool,
    /// campo 0x2b del binario
    /// default: 0
    pub move_route_index: i32,
    /// campo 0x2c del binario
    /// default: False
    pub move_route_finished: bool,
    /// campo 0x2e del binario
    /// default: False
    pub sprite_hidden: bool,
    /// campo 0x2f del binario
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
    /// campo 0x3d del binario
    /// default: False
    pub jumping: bool,
    /// campo 0x3e del binario
    /// default: 0
    pub begin_jump_x: i32,
    /// campo 0x3f del binario
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
    /// campo 0x4a del binario
    /// default: 0
    pub sprite_id: i32,
    /// campo 0x4b del binario
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveMapEventBase {
    fn default() -> Self {
        Self {
            active: true,
            map_id: 0,
            position_x: 0,
            position_y: 0,
            direction: 2,
            facing: 2,
            anim_frame: 1,
            transparency: 0,
            remaining_step: 0,
            move_frequency: 2,
            layer: 1,
            overlap_forbidden: false,
            animation_type: EventPageAnimType::de_i32(0),
            lock_facing: false,
            move_speed: 4,
            move_route: Default::default(),
            move_route_overwrite: false,
            move_route_index: 0,
            move_route_finished: false,
            sprite_hidden: false,
            move_route_through: false,
            anim_paused: 0,
            through: false,
            stop_count: 0,
            anim_count: 0,
            max_stop_count: 0,
            jumping: false,
            begin_jump_x: 0,
            begin_jump_y: 0,
            pause: false,
            flying: false,
            sprite_name: "".to_string(),
            sprite_id: 0,
            processed: false,
            flash_red: -1,
            flash_green: -1,
            flash_blue: -1,
            flash_current_level: 0.0,
            flash_time_left: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
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
    /// campo 0x0b del binario, se guarda aunque valga el default
    pub events: Vec<SaveMapEvent>,
    /// campo 0x15 del binario, se guarda aunque valga el default
    /// default: [x for x in range(0, 144)]
    pub lower_tiles: Vec<u8>,
    /// campo 0x16 del binario, se guarda aunque valga el default
    /// default: [x for x in range(0, 144)]
    pub upper_tiles: Vec<u8>,
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveMapInfo {
    fn default() -> Self {
        Self {
            position_x: 0,
            position_y: 0,
            encounter_steps: -1,
            chipset_id: 0,
            events: Default::default(),
            lower_tiles: (0..144).collect(),
            upper_tiles: (0..144).collect(),
            parallax_name: "".to_string(),
            parallax_horz: false,
            parallax_vert: false,
            parallax_horz_auto: false,
            parallax_horz_speed: 0,
            parallax_vert_auto: false,
            parallax_vert_speed: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SavePanorama {
    /// campo 0x01 del binario
    /// default: 0
    pub pan_x: i32,
    /// campo 0x02 del binario
    /// default: 0
    pub pan_y: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SavePanorama {
    fn default() -> Self {
        Self {
            pan_x: 0,
            pan_y: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
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
    /// campo 0x6c del binario
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
    /// campo 0x7c del binario
    /// default: 0
    pub total_encounter_rate: i32,
    /// campo 0x7d del binario
    /// default: False
    pub encounter_calling: bool,
    /// campo 0x83 del binario
    /// default: 0
    pub map_save_count: i32,
    /// campo 0x84 del binario
    /// default: 0
    pub database_save_count: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SavePartyLocation {
    fn default() -> Self {
        Self {
            boarding: false,
            aboard: false,
            vehicle: SavePartyLocationVehicleType::de_i32(0),
            unboarding: false,
            preboard_move_speed: 4,
            menu_calling: false,
            pan_state: SavePartyLocationPanState::de_i32(1),
            pan_current_x: kPanXDefault,
            pan_current_y: kPanYDefault,
            pan_finish_x: kPanXDefault,
            pan_finish_y: kPanYDefault,
            pan_speed: kPanSpeedDefault,
            total_encounter_rate: 0,
            encounter_calling: false,
            map_save_count: 0,
            database_save_count: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SavePicture {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x0b del binario
    /// default: 100.0
    pub current_red: f64,
    /// campo 0x0c del binario
    /// default: 100.0
    pub current_green: f64,
    /// campo 0x0d del binario
    /// default: 100.0
    pub current_blue: f64,
    /// campo 0x0e del binario
    /// default: 100.0
    pub current_sat: f64,
    /// campo 0x0f del binario
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
    /// campo 0x1a del binario
    /// default: 0
    pub battle_layer: SavePictureBattleLayer,
    /// campo 0x1b del binario
    /// default: 97
    pub flags: SavePictureFlags,
    /// campo 0x1f del binario
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
    /// campo 0x2a del binario
    /// default: 100
    pub finish_green: i32,
    /// campo 0x2b del binario
    /// default: 100
    pub finish_blue: i32,
    /// campo 0x2c del binario
    /// default: 100
    pub finish_sat: i32,
    /// campo 0x2e del binario
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SavePicture {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            start_x: 0.0,
            start_y: 0.0,
            current_x: 0.0,
            current_y: 0.0,
            fixed_to_map: false,
            current_magnify: 100.0,
            current_top_trans: 0.0,
            use_transparent_color: false,
            current_red: 100.0,
            current_green: 100.0,
            current_blue: 100.0,
            current_sat: 100.0,
            effect_mode: SavePictureEffect::de_i32(0),
            current_effect_power: 0.0,
            current_bot_trans: 0.0,
            map_layer: SavePictureMapLayer::de_i32(7),
            battle_layer: SavePictureBattleLayer::de_i32(0),
            flags: Default::default(),
            finish_x: 0.0,
            finish_y: 0.0,
            finish_magnify: 100,
            finish_top_trans: 0,
            finish_bot_trans: 0,
            finish_red: 100,
            finish_green: 100,
            finish_blue: 100,
            finish_sat: 100,
            finish_effect_power: 0,
            time_left: 0,
            current_rotation: 0.0,
            current_waver: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
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
    /// campo 0x0b del binario
    /// default: 100.0
    pub tint_current_red: f64,
    /// campo 0x0c del binario
    /// default: 100.0
    pub tint_current_green: f64,
    /// campo 0x0d del binario
    /// default: 100.0
    pub tint_current_blue: f64,
    /// campo 0x0e del binario
    /// default: 100.0
    pub tint_current_sat: f64,
    /// campo 0x0f del binario
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
    /// campo 0x1e del binario
    /// default: False
    pub shake_continuous: bool,
    /// campo 0x1f del binario
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
    /// campo 0x2a del binario
    /// default: 0
    pub pan_y: i32,
    /// campo 0x2b del binario
    /// default: 0
    pub battleanim_id: i32,
    /// campo 0x2c del binario
    /// default: 0
    pub battleanim_target: i32,
    /// campo 0x2d del binario
    /// default: 0
    pub battleanim_frame: i32,
    /// campo 0x2e del binario
    /// default: False
    pub battleanim_active: bool,
    /// campo 0x2f del binario
    /// default: False
    pub battleanim_global: bool,
    /// campo 0x30 del binario
    /// default: 0
    pub weather: i32,
    /// campo 0x31 del binario
    /// default: 0
    pub weather_strength: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveScreen {
    fn default() -> Self {
        Self {
            tint_finish_red: 100,
            tint_finish_green: 100,
            tint_finish_blue: 100,
            tint_finish_sat: 100,
            tint_current_red: 100.0,
            tint_current_green: 100.0,
            tint_current_blue: 100.0,
            tint_current_sat: 100.0,
            tint_time_left: 0,
            flash_continuous: false,
            flash_red: 0,
            flash_green: 0,
            flash_blue: 0,
            flash_current_level: 0.0,
            flash_time_left: 0,
            shake_continuous: false,
            shake_strength: 0,
            shake_speed: 0,
            shake_position: 0,
            shake_position_y: 0,
            shake_time_left: 0,
            pan_x: 0,
            pan_y: 0,
            battleanim_id: 0,
            battleanim_target: 0,
            battleanim_frame: 0,
            battleanim_active: false,
            battleanim_global: false,
            weather: 0,
            weather_strength: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SaveSystem {
    /// campo 0x01 del binario, se guarda aunque valga el default
    /// default: 0
    pub scene: SaveSystemScene,
    /// campo 0x0b del binario
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
    /// campo 0x2a del binario
    /// default: 2
    pub message_position: i32,
    /// campo 0x2b del binario
    /// default: 1
    pub message_prevent_overlap: i32,
    /// campo 0x2c del binario
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
    /// campo 0x3d del binario
    /// default: False
    pub music_stopping: bool,
    /// campo 0x47 del binario, se guarda aunque valga el default
    /// default: Music{ "" }
    pub title_music: Music,
    /// campo 0x48 del binario, se guarda aunque valga el default
    /// default: Music{ "" }
    pub battle_music: Music,
    /// campo 0x49 del binario, se guarda aunque valga el default
    /// default: Music{ "" }
    pub battle_end_music: Music,
    /// campo 0x4a del binario, se guarda aunque valga el default
    /// default: Music{ "" }
    pub inn_music: Music,
    /// campo 0x4b del binario, se guarda aunque valga el default
    pub current_music: Music,
    /// campo 0x4c del binario, se guarda aunque valga el default
    pub before_vehicle_music: Music,
    /// campo 0x4d del binario, se guarda aunque valga el default
    pub before_battle_music: Music,
    /// campo 0x4e del binario, se guarda aunque valga el default
    pub stored_music: Music,
    /// campo 0x4f del binario, se guarda aunque valga el default
    /// default: Music{ "" }
    pub boat_music: Music,
    /// campo 0x50 del binario, se guarda aunque valga el default
    /// default: Music{ "" }
    pub ship_music: Music,
    /// campo 0x51 del binario, se guarda aunque valga el default
    /// default: Music{ "" }
    pub airship_music: Music,
    /// campo 0x52 del binario, se guarda aunque valga el default
    /// default: Music{ "" }
    pub gameover_music: Music,
    /// campo 0x5b del binario, se guarda aunque valga el default
    /// default: Sound{ "" }
    pub cursor_se: Sound,
    /// campo 0x5c del binario, se guarda aunque valga el default
    /// default: Sound{ "" }
    pub decision_se: Sound,
    /// campo 0x5d del binario, se guarda aunque valga el default
    /// default: Sound{ "" }
    pub cancel_se: Sound,
    /// campo 0x5e del binario, se guarda aunque valga el default
    /// default: Sound{ "" }
    pub buzzer_se: Sound,
    /// campo 0x5f del binario, se guarda aunque valga el default
    /// default: Sound{ "" }
    pub battle_se: Sound,
    /// campo 0x60 del binario, se guarda aunque valga el default
    /// default: Sound{ "" }
    pub escape_se: Sound,
    /// campo 0x61 del binario, se guarda aunque valga el default
    /// default: Sound{ "" }
    pub enemy_attack_se: Sound,
    /// campo 0x62 del binario, se guarda aunque valga el default
    /// default: Sound{ "" }
    pub enemy_damaged_se: Sound,
    /// campo 0x63 del binario, se guarda aunque valga el default
    /// default: Sound{ "" }
    pub actor_damaged_se: Sound,
    /// campo 0x64 del binario, se guarda aunque valga el default
    /// default: Sound{ "" }
    pub dodge_se: Sound,
    /// campo 0x65 del binario, se guarda aunque valga el default
    /// default: Sound{ "" }
    pub enemy_death_se: Sound,
    /// campo 0x66 del binario, se guarda aunque valga el default
    /// default: Sound{ "" }
    pub item_se: Sound,
    /// campo 0x6f del binario, se guarda aunque valga el default
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
    /// campo 0x7a del binario
    /// default: True
    pub escape_allowed: bool,
    /// campo 0x7b del binario
    /// default: True
    pub save_allowed: bool,
    /// campo 0x7c del binario
    /// default: True
    pub menu_allowed: bool,
    /// campo 0x7d del binario
    pub background: String,
    /// campo 0x83 del binario
    /// default: 0
    pub save_count: i32,
    /// campo 0x84 del binario
    /// default: 1
    pub save_slot: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveSystem {
    fn default() -> Self {
        Self {
            scene: SaveSystemScene::de_i32(0),
            frame_count: 0,
            graphics_name: "".to_string(),
            message_stretch: SystemStretch::de_i32(0),
            font_id: SystemFont::de_i32(0),
            switches: Vec::new(),
            variables: Vec::new(),
            message_transparent: 0,
            message_position: 2,
            message_prevent_overlap: 1,
            message_continue_events: 0,
            face_name: "".to_string(),
            face_id: 0,
            face_right: false,
            face_flip: false,
            event_message_active: false,
            music_stopping: false,
            title_music: Default::default(),
            battle_music: Default::default(),
            battle_end_music: Default::default(),
            inn_music: Default::default(),
            current_music: Default::default(),
            before_vehicle_music: Default::default(),
            before_battle_music: Default::default(),
            stored_music: Default::default(),
            boat_music: Default::default(),
            ship_music: Default::default(),
            airship_music: Default::default(),
            gameover_music: Default::default(),
            cursor_se: Default::default(),
            decision_se: Default::default(),
            cancel_se: Default::default(),
            buzzer_se: Default::default(),
            battle_se: Default::default(),
            escape_se: Default::default(),
            enemy_attack_se: Default::default(),
            enemy_damaged_se: Default::default(),
            actor_damaged_se: Default::default(),
            dodge_se: Default::default(),
            enemy_death_se: Default::default(),
            item_se: Default::default(),
            transition_out: -1,
            transition_in: -1,
            battle_start_fadeout: -1,
            battle_start_fadein: -1,
            battle_end_fadeout: -1,
            battle_end_fadein: -1,
            teleport_allowed: true,
            escape_allowed: true,
            save_allowed: true,
            menu_allowed: true,
            background: "".to_string(),
            save_count: 0,
            save_slot: 1,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SaveTarget {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveTarget {
    fn default() -> Self {
        Self {
            id: 0,
            map_id: 0,
            map_x: 0,
            map_y: 0,
            switch_on: false,
            switch_id: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SaveTitle {
    /// campo 0x01 del binario
    /// default: 0.0
    pub timestamp: f64,
    /// campo 0x0b del binario
    pub hero_name: String,
    /// campo 0x0c del binario
    /// default: 0
    pub hero_level: i32,
    /// campo 0x0d del binario
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
    /// campo 0x1a del binario
    /// default: 0
    pub face3_id: i32,
    /// campo 0x1b del binario
    pub face4_name: String,
    /// campo 0x1c del binario
    /// default: 0
    pub face4_id: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveTitle {
    fn default() -> Self {
        Self {
            timestamp: 0.0,
            hero_name: "".to_string(),
            hero_level: 0,
            hero_hp: 0,
            face1_name: "".to_string(),
            face1_id: 0,
            face2_name: "".to_string(),
            face2_id: 0,
            face3_name: "".to_string(),
            face3_id: 0,
            face4_name: "".to_string(),
            face4_id: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SaveVehicleLocation {
    /// campo 0x65 del binario
    /// default: 0
    pub vehicle: SaveVehicleLocationVehicleType,
    /// campo 0x6a del binario
    /// default: 0
    pub remaining_ascent: i32,
    /// campo 0x6b del binario
    /// default: 0
    pub remaining_descent: i32,
    /// campo 0x6f del binario
    pub orig_sprite_name: String,
    /// campo 0x70 del binario
    /// default: 0
    pub orig_sprite_id: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for SaveVehicleLocation {
    fn default() -> Self {
        Self {
            vehicle: SaveVehicleLocationVehicleType::de_i32(0),
            remaining_ascent: 0,
            remaining_descent: 0,
            orig_sprite_name: "".to_string(),
            orig_sprite_id: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Skill {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x0b del binario
    /// default: 0
    pub sp_cost: i32,
    /// campo 0x0c del binario, se guarda aunque valga el default
    /// default: 0
    pub scope: SkillScope,
    /// campo 0x0d del binario
    /// default: 1
    pub switch_id: i32,
    /// campo 0x0e del binario
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
    /// campo 0x1f del binario
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
    /// campo 0x2a del binario, se guarda aunque valga el default
    pub state_effects: Vec<bool>,
    /// campo 0x2c del binario, se guarda aunque valga el default
    pub attribute_effects: Vec<bool>,
    /// campo 0x2d del binario
    /// default: False
    pub affect_attr_defence: bool,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Skill {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            description: "".to_string(),
            using_message1: "".to_string(),
            using_message2: "".to_string(),
            failure_message: 0,
            r#type: SkillType::de_i32(0),
            sp_cost: 0,
            scope: SkillScope::de_i32(0),
            switch_id: 1,
            animation_id: 1,
            sound_effect: Default::default(),
            occasion_field: true,
            occasion_battle: false,
            physical_rate: 0,
            magical_rate: 3,
            variance: 4,
            power: 0,
            hit: 100,
            affect_hp: false,
            affect_sp: false,
            affect_attack: false,
            affect_defense: false,
            affect_spirit: false,
            affect_agility: false,
            absorb_damage: false,
            ignore_defense: false,
            state_effects: Vec::new(),
            attribute_effects: Vec::new(),
            affect_attr_defence: false,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Sound {
    /// campo 0x01 del binario, se guarda aunque valga el default
    /// default: "(OFF)"
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Sound {
    fn default() -> Self {
        Self {
            name: "\"(OFF)\"".to_string(),
            volume: 100,
            tempo: 100,
            balance: 50,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
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
    /// campo 0x0b del binario
    /// default: 0
    pub boat_map_id: i32,
    /// campo 0x0c del binario
    /// default: 0
    pub boat_x: i32,
    /// campo 0x0d del binario
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
    /// campo 0x1f del binario
    /// default: 0
    pub airship_map_id: i32,
    /// campo 0x20 del binario
    /// default: 0
    pub airship_x: i32,
    /// campo 0x21 del binario
    /// default: 0
    pub airship_y: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Start {
    fn default() -> Self {
        Self {
            party_map_id: 0,
            party_x: 0,
            party_y: 0,
            boat_map_id: 0,
            boat_x: 0,
            boat_y: 0,
            ship_map_id: 0,
            ship_x: 0,
            ship_y: 0,
            airship_map_id: 0,
            airship_x: 0,
            airship_y: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct State {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x0b del binario
    /// default: 100
    pub a_rate: i32,
    /// campo 0x0c del binario
    /// default: 80
    pub b_rate: i32,
    /// campo 0x0d del binario
    /// default: 60
    pub c_rate: i32,
    /// campo 0x0e del binario
    /// default: 30
    pub d_rate: i32,
    /// campo 0x0f del binario
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
    /// campo 0x1f del binario
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
    /// campo 0x2a del binario
    /// default: 0
    pub restrict_skill_level: i32,
    /// campo 0x2b del binario
    /// default: False
    pub restrict_magic: bool,
    /// campo 0x2c del binario
    /// default: 0
    pub restrict_magic_level: i32,
    /// campo 0x2d del binario
    /// default: 0
    pub hp_change_type: StateChangeType,
    /// campo 0x2e del binario
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
    /// campo 0x3d del binario
    /// default: 0
    pub hp_change_max: i32,
    /// campo 0x3e del binario
    /// default: 0
    pub hp_change_val: i32,
    /// campo 0x3f del binario
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for State {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            r#type: StatePersistence::de_i32(0),
            color: 6,
            priority: 50,
            restriction: StateRestriction::de_i32(0),
            a_rate: 100,
            b_rate: 80,
            c_rate: 60,
            d_rate: 30,
            e_rate: 0,
            hold_turn: 0,
            auto_release_prob: 0,
            release_by_damage: 0,
            affect_attack: false,
            affect_defense: false,
            affect_spirit: false,
            affect_agility: false,
            reduce_hit_ratio: 100,
            restrict_skill: false,
            restrict_skill_level: 0,
            restrict_magic: false,
            restrict_magic_level: 0,
            hp_change_type: StateChangeType::de_i32(0),
            sp_change_type: StateChangeType::de_i32(0),
            message_actor: "".to_string(),
            message_enemy: "".to_string(),
            message_already: "".to_string(),
            message_affected: "".to_string(),
            message_recovery: "".to_string(),
            hp_change_max: 0,
            hp_change_val: 0,
            hp_change_map_steps: 0,
            hp_change_map_val: 0,
            sp_change_max: 0,
            sp_change_val: 0,
            sp_change_map_steps: 0,
            sp_change_map_val: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Switch {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x01 del binario
    pub name: String,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Switch {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct System {
    /// campo 0x0a del binario
    /// default: 0
    pub ldb_id: i32,
    /// campo 0x0b del binario
    pub boat_name: String,
    /// campo 0x0c del binario
    pub ship_name: String,
    /// campo 0x0d del binario
    pub airship_name: String,
    /// campo 0x0e del binario
    /// default: 0
    pub boat_index: i32,
    /// campo 0x0f del binario
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
    /// default: [1]
    pub party: Vec<i16>,
    /// campo 0x1f del binario, se guarda aunque valga el default
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
    /// campo 0x2a del binario, se guarda aunque valga el default
    pub decision_se: Sound,
    /// campo 0x2b del binario, se guarda aunque valga el default
    pub cancel_se: Sound,
    /// campo 0x2c del binario, se guarda aunque valga el default
    pub buzzer_se: Sound,
    /// campo 0x2d del binario, se guarda aunque valga el default
    pub battle_se: Sound,
    /// campo 0x2e del binario, se guarda aunque valga el default
    pub escape_se: Sound,
    /// campo 0x2f del binario, se guarda aunque valga el default
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
    /// campo 0x3d del binario, se guarda aunque valga el default
    /// default: 0
    pub transition_out: SystemFadeOut,
    /// campo 0x3e del binario, se guarda aunque valga el default
    /// default: 0
    pub transition_in: SystemFadeIn,
    /// campo 0x3f del binario, se guarda aunque valga el default
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
    /// campo 0x5b del binario
    /// default: 0
    pub save_count: i32,
    /// campo 0x5e del binario
    /// default: 0
    pub battletest_terrain: i32,
    /// campo 0x5f del binario
    /// default: 0
    pub battletest_formation: SystemBattleFormation,
    /// campo 0x60 del binario
    /// default: 0
    pub battletest_condition: SystemBattleCondition,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for System {
    fn default() -> Self {
        Self {
            ldb_id: 0,
            boat_name: "".to_string(),
            ship_name: "".to_string(),
            airship_name: "".to_string(),
            boat_index: 0,
            ship_index: 0,
            airship_index: 0,
            title_name: "".to_string(),
            gameover_name: "".to_string(),
            system_name: "".to_string(),
            party: vec![1; 1],
            title_music: Default::default(),
            battle_music: Default::default(),
            battle_end_music: Default::default(),
            inn_music: Default::default(),
            boat_music: Default::default(),
            ship_music: Default::default(),
            airship_music: Default::default(),
            gameover_music: Default::default(),
            cursor_se: Default::default(),
            decision_se: Default::default(),
            cancel_se: Default::default(),
            buzzer_se: Default::default(),
            battle_se: Default::default(),
            escape_se: Default::default(),
            enemy_attack_se: Default::default(),
            enemy_damaged_se: Default::default(),
            actor_damaged_se: Default::default(),
            dodge_se: Default::default(),
            enemy_death_se: Default::default(),
            item_se: Default::default(),
            transition_out: SystemFadeOut::de_i32(0),
            transition_in: SystemFadeIn::de_i32(0),
            battle_start_fadeout: SystemFadeOut::de_i32(0),
            battle_start_fadein: SystemFadeIn::de_i32(0),
            battle_end_fadeout: SystemFadeOut::de_i32(0),
            battle_end_fadein: SystemFadeIn::de_i32(0),
            message_stretch: SystemStretch::de_i32(0),
            font_id: SystemFont::de_i32(0),
            selected_condition: 0,
            selected_hero: 0,
            battletest_background: "".to_string(),
            battletest_data: Default::default(),
            save_count: 0,
            battletest_terrain: 0,
            battletest_formation: SystemBattleFormation::de_i32(0),
            battletest_condition: SystemBattleCondition::de_i32(0),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
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
    /// campo 0x0a del binario, se guarda aunque valga el default
    pub item_recieved: String,
    /// campo 0x0b del binario, se guarda aunque valga el default
    pub attacking: String,
    /// campo 0x0c del binario, se guarda aunque valga el default
    pub enemy_critical: String,
    /// campo 0x0d del binario, se guarda aunque valga el default
    pub actor_critical: String,
    /// campo 0x0e del binario, se guarda aunque valga el default
    pub defending: String,
    /// campo 0x0f del binario, se guarda aunque valga el default
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
    /// campo 0x1a del binario, se guarda aunque valga el default
    pub skill_failure_c: String,
    /// campo 0x1b del binario, se guarda aunque valga el default
    pub dodge: String,
    /// campo 0x1c del binario, se guarda aunque valga el default
    pub use_item: String,
    /// campo 0x1d del binario, se guarda aunque valga el default
    pub hp_recovery: String,
    /// campo 0x1e del binario, se guarda aunque valga el default
    pub parameter_increase: String,
    /// campo 0x1f del binario, se guarda aunque valga el default
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
    /// campo 0x2a del binario, se guarda aunque valga el default
    pub shop_regreeting1: String,
    /// campo 0x2b del binario, se guarda aunque valga el default
    pub shop_buy1: String,
    /// campo 0x2c del binario, se guarda aunque valga el default
    pub shop_sell1: String,
    /// campo 0x2d del binario, se guarda aunque valga el default
    pub shop_leave1: String,
    /// campo 0x2e del binario, se guarda aunque valga el default
    pub shop_buy_select1: String,
    /// campo 0x2f del binario, se guarda aunque valga el default
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
    /// campo 0x3a del binario, se guarda aunque valga el default
    pub shop_leave2: String,
    /// campo 0x3b del binario, se guarda aunque valga el default
    pub shop_buy_select2: String,
    /// campo 0x3c del binario, se guarda aunque valga el default
    pub shop_buy_number2: String,
    /// campo 0x3d del binario, se guarda aunque valga el default
    pub shop_purchased2: String,
    /// campo 0x3e del binario, se guarda aunque valga el default
    pub shop_sell_select2: String,
    /// campo 0x3f del binario, se guarda aunque valga el default
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
    /// campo 0x4a del binario, se guarda aunque valga el default
    pub shop_purchased3: String,
    /// campo 0x4b del binario, se guarda aunque valga el default
    pub shop_sell_select3: String,
    /// campo 0x4c del binario, se guarda aunque valga el default
    pub shop_sell_number3: String,
    /// campo 0x4d del binario, se guarda aunque valga el default
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
    /// campo 0x5c del binario, se guarda aunque valga el default
    pub possessed_items: String,
    /// campo 0x5d del binario, se guarda aunque valga el default
    pub equipped_items: String,
    /// campo 0x5f del binario, se guarda aunque valga el default
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
    /// campo 0x6a del binario, se guarda aunque valga el default
    pub command_item: String,
    /// campo 0x6b del binario, se guarda aunque valga el default
    pub command_skill: String,
    /// campo 0x6c del binario, se guarda aunque valga el default
    pub menu_equipment: String,
    /// campo 0x6e del binario, se guarda aunque valga el default
    pub menu_save: String,
    /// campo 0x70 del binario, se guarda aunque valga el default
    pub menu_quit: String,
    /// campo 0x72 del binario, se guarda aunque valga el default
    pub new_game: String,
    /// campo 0x73 del binario, se guarda aunque valga el default
    pub load_game: String,
    /// campo 0x75 del binario, se guarda aunque valga el default
    pub exit_game: String,
    /// campo 0x7b del binario, se guarda aunque valga el default
    pub level: String,
    /// campo 0x7c del binario, se guarda aunque valga el default
    pub health_points: String,
    /// campo 0x7d del binario, se guarda aunque valga el default
    pub spirit_points: String,
    /// campo 0x7e del binario, se guarda aunque valga el default
    pub normal_status: String,
    /// campo 0x7f del binario, se guarda aunque valga el default
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
    /// campo 0x8a del binario, se guarda aunque valga el default
    pub armor: String,
    /// campo 0x8b del binario, se guarda aunque valga el default
    pub helmet: String,
    /// campo 0x8c del binario, se guarda aunque valga el default
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Terms {
    fn default() -> Self {
        Self {
            encounter: "".to_string(),
            special_combat: "".to_string(),
            escape_success: "".to_string(),
            escape_failure: "".to_string(),
            victory: "".to_string(),
            defeat: "".to_string(),
            exp_received: "".to_string(),
            gold_recieved_a: "".to_string(),
            gold_recieved_b: "".to_string(),
            item_recieved: "".to_string(),
            attacking: "".to_string(),
            enemy_critical: "".to_string(),
            actor_critical: "".to_string(),
            defending: "".to_string(),
            observing: "".to_string(),
            focus: "".to_string(),
            autodestruction: "".to_string(),
            enemy_escape: "".to_string(),
            enemy_transform: "".to_string(),
            enemy_damaged: "".to_string(),
            enemy_undamaged: "".to_string(),
            actor_damaged: "".to_string(),
            actor_undamaged: "".to_string(),
            skill_failure_a: "".to_string(),
            skill_failure_b: "".to_string(),
            skill_failure_c: "".to_string(),
            dodge: "".to_string(),
            use_item: "".to_string(),
            hp_recovery: "".to_string(),
            parameter_increase: "".to_string(),
            parameter_decrease: "".to_string(),
            enemy_hp_absorbed: "".to_string(),
            actor_hp_absorbed: "".to_string(),
            resistance_increase: "".to_string(),
            resistance_decrease: "".to_string(),
            level_up: "".to_string(),
            skill_learned: "".to_string(),
            shop_greeting1: "".to_string(),
            shop_regreeting1: "".to_string(),
            shop_buy1: "".to_string(),
            shop_sell1: "".to_string(),
            shop_leave1: "".to_string(),
            shop_buy_select1: "".to_string(),
            shop_buy_number1: "".to_string(),
            shop_purchased1: "".to_string(),
            shop_sell_select1: "".to_string(),
            shop_sell_number1: "".to_string(),
            shop_sold1: "".to_string(),
            shop_greeting2: "".to_string(),
            shop_regreeting2: "".to_string(),
            shop_buy2: "".to_string(),
            shop_sell2: "".to_string(),
            shop_leave2: "".to_string(),
            shop_buy_select2: "".to_string(),
            shop_buy_number2: "".to_string(),
            shop_purchased2: "".to_string(),
            shop_sell_select2: "".to_string(),
            shop_sell_number2: "".to_string(),
            shop_sold2: "".to_string(),
            shop_greeting3: "".to_string(),
            shop_regreeting3: "".to_string(),
            shop_buy3: "".to_string(),
            shop_sell3: "".to_string(),
            shop_leave3: "".to_string(),
            shop_buy_select3: "".to_string(),
            shop_buy_number3: "".to_string(),
            shop_purchased3: "".to_string(),
            shop_sell_select3: "".to_string(),
            shop_sell_number3: "".to_string(),
            shop_sold3: "".to_string(),
            inn_a_greeting_1: "".to_string(),
            inn_a_greeting_2: "".to_string(),
            inn_a_greeting_3: "".to_string(),
            inn_a_accept: "".to_string(),
            inn_a_cancel: "".to_string(),
            inn_b_greeting_1: "".to_string(),
            inn_b_greeting_2: "".to_string(),
            inn_b_greeting_3: "".to_string(),
            inn_b_accept: "".to_string(),
            inn_b_cancel: "".to_string(),
            possessed_items: "".to_string(),
            equipped_items: "".to_string(),
            gold: "".to_string(),
            battle_fight: "".to_string(),
            battle_auto: "".to_string(),
            battle_escape: "".to_string(),
            command_attack: "".to_string(),
            command_defend: "".to_string(),
            command_item: "".to_string(),
            command_skill: "".to_string(),
            menu_equipment: "".to_string(),
            menu_save: "".to_string(),
            menu_quit: "".to_string(),
            new_game: "".to_string(),
            load_game: "".to_string(),
            exit_game: "".to_string(),
            level: "".to_string(),
            health_points: "".to_string(),
            spirit_points: "".to_string(),
            normal_status: "".to_string(),
            exp_short: "".to_string(),
            lvl_short: "".to_string(),
            hp_short: "".to_string(),
            sp_short: "".to_string(),
            sp_cost: "".to_string(),
            attack: "".to_string(),
            defense: "".to_string(),
            spirit: "".to_string(),
            agility: "".to_string(),
            weapon: "".to_string(),
            shield: "".to_string(),
            armor: "".to_string(),
            helmet: "".to_string(),
            accessory: "".to_string(),
            save_game_message: "".to_string(),
            load_game_message: "".to_string(),
            file: "".to_string(),
            exit_game_message: "".to_string(),
            yes: "".to_string(),
            no: "".to_string(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Terrain {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// campo 0x0b del binario, se guarda aunque valga el default
    /// default: 0
    pub bush_depth: TerrainBushDepth,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Terrain {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            damage: 0,
            encounter_rate: 100,
            background_name: "".to_string(),
            boat_pass: false,
            ship_pass: false,
            airship_pass: true,
            airship_land: true,
            bush_depth: TerrainBushDepth::de_i32(0),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct TestBattler {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x01 del binario
    /// default: 1
    pub actor_id: i32,
    /// campo 0x02 del binario
    /// default: 1
    pub level: i32,
    /// campo 0x0b del binario
    /// default: 0
    pub weapon_id: i32,
    /// campo 0x0c del binario
    /// default: 0
    pub shield_id: i32,
    /// campo 0x0d del binario
    /// default: 0
    pub armor_id: i32,
    /// campo 0x0e del binario
    /// default: 0
    pub helmet_id: i32,
    /// campo 0x0f del binario
    /// default: 0
    pub accessory_id: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for TestBattler {
    fn default() -> Self {
        Self {
            id: 0,
            actor_id: 1,
            level: 1,
            weapon_id: 0,
            shield_id: 0,
            armor_id: 0,
            helmet_id: 0,
            accessory_id: 0,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct TreeMap {
    /// campo 0x00 del binario, se guarda aunque valga el default
    pub maps: Vec<MapInfo>,
    /// campo 0x00 del binario, se guarda aunque valga el default
    pub tree_order: Vec<i32>,
    /// campo 0x00 del binario
    /// default: 0
    pub active_node: i32,
    /// campo 0x00 del binario
    pub start: Start,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for TreeMap {
    fn default() -> Self {
        Self {
            maps: Default::default(),
            tree_order: Vec::new(),
            active_node: 0,
            start: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Troop {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x01 del binario
    pub name: String,
    /// campo 0x02 del binario, se guarda aunque valga el default
    pub members: Vec<TroopMember>,
    /// campo 0x05 del binario, se guarda aunque valga el default
    pub terrain_set: Vec<bool>,
    /// campo 0x0b del binario, se guarda aunque valga el default
    pub pages: Vec<TroopPage>,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Troop {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            members: Default::default(),
            terrain_set: Vec::new(),
            pages: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct TroopMember {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
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
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for TroopMember {
    fn default() -> Self {
        Self {
            id: 0,
            enemy_id: 1,
            x: 0,
            y: 0,
            invisible: false,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct TroopPage {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x02 del binario, se guarda aunque valga el default
    pub condition: TroopPageCondition,
    /// campo 0x0c del binario, se guarda aunque valga el default
    pub event_commands: Vec<EventCommand>,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for TroopPage {
    fn default() -> Self {
        Self {
            id: 0,
            condition: Default::default(),
            event_commands: Default::default(),
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct TroopPageCondition {
    /// campo 0x01 del binario, se guarda aunque valga el default
    pub flags: TroopPageConditionFlags,
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
    /// campo 0x0a del binario
    /// default: 0
    pub enemy_id: i32,
    /// campo 0x0b del binario
    /// default: 0
    pub enemy_hp_min: i32,
    /// campo 0x0c del binario
    /// default: 100
    pub enemy_hp_max: i32,
    /// campo 0x0d del binario
    /// default: 1
    pub actor_id: i32,
    /// campo 0x0e del binario
    /// default: 0
    pub actor_hp_min: i32,
    /// campo 0x0f del binario
    /// default: 100
    pub actor_hp_max: i32,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for TroopPageCondition {
    fn default() -> Self {
        Self {
            flags: Default::default(),
            switch_a_id: 1,
            switch_b_id: 1,
            variable_id: 1,
            variable_value: 0,
            turn_a: 0,
            turn_b: 0,
            fatigue_min: 0,
            fatigue_max: 100,
            enemy_id: 0,
            enemy_hp_min: 0,
            enemy_hp_max: 100,
            actor_id: 1,
            actor_hp_min: 0,
            actor_hp_max: 100,
            desconocidos: Vec::new(),
        }
    }
}

/// Generado desde `fields.csv`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Variable {
    /// El número con el que el array nombra a este elemento.
    pub id: i32,
    /// campo 0x01 del binario
    pub name: String,
    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub desconocidos: Vec<ChunkCrudo>,
}

impl Default for Variable {
    fn default() -> Self {
        Self {
            id: 0,
            name: "".to_string(),
            desconocidos: Vec::new(),
        }
    }
}

impl Chunked for Learning {
    const NOMBRE: &'static str = "Learning";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.level = dec_ber(d),
            0x02 => self.skill_id = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Learning::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.level != p.level { c.push((0x01, cod_ber(self.level))); }
        if self.skill_id != p.skill_id { c.push((0x02, cod_ber(self.skill_id))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Actor {
    const NOMBRE: &'static str = "Actor";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.title = dec_texto(d),
            0x03 => self.character_name = dec_texto(d),
            0x04 => self.character_index = dec_ber(d),
            0x05 => self.transparent = dec_bool(d),
            0x07 => self.initial_level = dec_ber(d),
            0x08 => self.final_level = dec_ber(d),
            0x09 => self.critical_hit = dec_bool(d),
            0x0a => self.critical_hit_chance = dec_ber(d),
            0x0f => self.face_name = dec_texto(d),
            0x10 => self.face_index = dec_ber(d),
            0x15 => self.two_weapon = dec_bool(d),
            0x16 => self.lock_equipment = dec_bool(d),
            0x17 => self.auto_battle = dec_bool(d),
            0x18 => self.super_guard = dec_bool(d),
            0x1f => self.parameters = Parameters::leer_crudo(d)?,
            0x29 => self.exp_base = dec_ber(d),
            0x2a => self.exp_inflation = dec_ber(d),
            0x2b => self.exp_correction = dec_ber(d),
            0x33 => self.initial_equipment = Equipment::leer_crudo(d)?,
            0x38 => self.unarmed_animation = dec_ber(d),
            0x3f => self.skills = dec_array::<Learning>(d)?,
            0x42 => self.rename_skill = dec_bool(d),
            0x43 => self.skill_name = dec_texto(d),
            0x47 => {} // largo de `state_ranks`, se recalcula al escribir
            0x48 => self.state_ranks = d.to_vec(),
            0x49 => {} // largo de `attribute_ranks`, se recalcula al escribir
            0x4a => self.attribute_ranks = d.to_vec(),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Actor::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        if self.title != p.title { c.push((0x02, cod_texto(&self.title))); }
        if self.character_name != p.character_name { c.push((0x03, cod_texto(&self.character_name))); }
        if self.character_index != p.character_index { c.push((0x04, cod_ber(self.character_index))); }
        if self.transparent != p.transparent { c.push((0x05, cod_bool(self.transparent))); }
        if self.initial_level != p.initial_level { c.push((0x07, cod_ber(self.initial_level))); }
        if self.final_level != p.final_level { c.push((0x08, cod_ber(self.final_level))); }
        if self.critical_hit != p.critical_hit { c.push((0x09, cod_bool(self.critical_hit))); }
        if self.critical_hit_chance != p.critical_hit_chance { c.push((0x0a, cod_ber(self.critical_hit_chance))); }
        if self.face_name != p.face_name { c.push((0x0f, cod_texto(&self.face_name))); }
        if self.face_index != p.face_index { c.push((0x10, cod_ber(self.face_index))); }
        if self.two_weapon != p.two_weapon { c.push((0x15, cod_bool(self.two_weapon))); }
        if self.lock_equipment != p.lock_equipment { c.push((0x16, cod_bool(self.lock_equipment))); }
        if self.auto_battle != p.auto_battle { c.push((0x17, cod_bool(self.auto_battle))); }
        if self.super_guard != p.super_guard { c.push((0x18, cod_bool(self.super_guard))); }
        c.push((0x1f, self.parameters.escribir_crudo()));
        if self.exp_base != p.exp_base { c.push((0x29, cod_ber(self.exp_base))); }
        if self.exp_inflation != p.exp_inflation { c.push((0x2a, cod_ber(self.exp_inflation))); }
        if self.exp_correction != p.exp_correction { c.push((0x2b, cod_ber(self.exp_correction))); }
        c.push((0x33, self.initial_equipment.escribir_crudo()));
        if self.unarmed_animation != p.unarmed_animation { c.push((0x38, cod_ber(self.unarmed_animation))); }
        c.push((0x3f, cod_array(&self.skills)?));
        if self.rename_skill != p.rename_skill { c.push((0x42, cod_bool(self.rename_skill))); }
        if self.skill_name != p.skill_name { c.push((0x43, cod_texto(&self.skill_name))); }
        let v_state_ranks = self.state_ranks.clone();
        if v_state_ranks.len() != p.state_ranks.clone().len() { c.push((0x47, cod_ber(v_state_ranks.len() as i32))); }
        c.push((0x48, v_state_ranks));
        let v_attribute_ranks = self.attribute_ranks.clone();
        if v_attribute_ranks.len() != p.attribute_ranks.clone().len() { c.push((0x49, cod_ber(v_attribute_ranks.len() as i32))); }
        c.push((0x4a, v_attribute_ranks));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Sound {
    const NOMBRE: &'static str = "Sound";
    const TERMINADOR: bool = true;
    const CON_ID: bool = false;
    fn id(&self) -> i32 { 0 }
    fn poner_id(&mut self, v: i32) { let _ = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x03 => self.volume = dec_ber(d),
            0x04 => self.tempo = dec_ber(d),
            0x05 => self.balance = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Sound::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        c.push((0x01, cod_texto(&self.name)));
        if self.volume != p.volume { c.push((0x03, cod_ber(self.volume))); }
        if self.tempo != p.tempo { c.push((0x04, cod_ber(self.tempo))); }
        if self.balance != p.balance { c.push((0x05, cod_ber(self.balance))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for AnimationTiming {
    const NOMBRE: &'static str = "AnimationTiming";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.frame = dec_ber(d),
            0x02 => self.se = dec_struct::<Sound>(d)?,
            0x03 => self.flash_scope = AnimationTimingFlashScope::de_i32(dec_ber(d)),
            0x04 => self.flash_red = dec_ber(d),
            0x05 => self.flash_green = dec_ber(d),
            0x06 => self.flash_blue = dec_ber(d),
            0x07 => self.flash_power = dec_ber(d),
            0x08 => self.screen_shake = AnimationTimingScreenShake::de_i32(dec_ber(d)),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = AnimationTiming::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.frame != p.frame { c.push((0x01, cod_ber(self.frame))); }
        c.push((0x02, cod_struct(&self.se)?));
        c.push((0x03, cod_ber(self.flash_scope.a_i32())));
        if self.flash_red != p.flash_red { c.push((0x04, cod_ber(self.flash_red))); }
        if self.flash_green != p.flash_green { c.push((0x05, cod_ber(self.flash_green))); }
        if self.flash_blue != p.flash_blue { c.push((0x06, cod_ber(self.flash_blue))); }
        if self.flash_power != p.flash_power { c.push((0x07, cod_ber(self.flash_power))); }
        if self.screen_shake != p.screen_shake { c.push((0x08, cod_ber(self.screen_shake.a_i32()))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for AnimationCellData {
    const NOMBRE: &'static str = "AnimationCellData";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.valid = dec_ber(d),
            0x02 => self.cell_id = dec_ber(d),
            0x03 => self.x = dec_ber(d),
            0x04 => self.y = dec_ber(d),
            0x05 => self.zoom = dec_ber(d),
            0x06 => self.tone_red = dec_ber(d),
            0x07 => self.tone_green = dec_ber(d),
            0x08 => self.tone_blue = dec_ber(d),
            0x09 => self.tone_gray = dec_ber(d),
            0x0a => self.transparency = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = AnimationCellData::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.valid != p.valid { c.push((0x01, cod_ber(self.valid))); }
        if self.cell_id != p.cell_id { c.push((0x02, cod_ber(self.cell_id))); }
        if self.x != p.x { c.push((0x03, cod_ber(self.x))); }
        if self.y != p.y { c.push((0x04, cod_ber(self.y))); }
        if self.zoom != p.zoom { c.push((0x05, cod_ber(self.zoom))); }
        if self.tone_red != p.tone_red { c.push((0x06, cod_ber(self.tone_red))); }
        if self.tone_green != p.tone_green { c.push((0x07, cod_ber(self.tone_green))); }
        if self.tone_blue != p.tone_blue { c.push((0x08, cod_ber(self.tone_blue))); }
        if self.tone_gray != p.tone_gray { c.push((0x09, cod_ber(self.tone_gray))); }
        if self.transparency != p.transparency { c.push((0x0a, cod_ber(self.transparency))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for AnimationFrame {
    const NOMBRE: &'static str = "AnimationFrame";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.cells = dec_array::<AnimationCellData>(d)?,
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = AnimationFrame::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        c.push((0x01, cod_array(&self.cells)?));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Animation {
    const NOMBRE: &'static str = "Animation";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.animation_name = dec_texto(d),
            0x03 => self.large = dec_bool(d),
            0x06 => self.timings = dec_array::<AnimationTiming>(d)?,
            0x09 => self.scope = AnimationScope::de_i32(dec_ber(d)),
            0x0a => self.position = AnimationPosition::de_i32(dec_ber(d)),
            0x0c => self.frames = dec_array::<AnimationFrame>(d)?,
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Animation::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        if self.animation_name != p.animation_name { c.push((0x02, cod_texto(&self.animation_name))); }
        if self.large != p.large { c.push((0x03, cod_bool(self.large))); }
        c.push((0x06, cod_array(&self.timings)?));
        c.push((0x09, cod_ber(self.scope.a_i32())));
        c.push((0x0a, cod_ber(self.position.a_i32())));
        c.push((0x0c, cod_array(&self.frames)?));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Attribute {
    const NOMBRE: &'static str = "Attribute";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.r#type = AttributeType::de_i32(dec_ber(d)),
            0x0b => self.a_rate = dec_ber(d),
            0x0c => self.b_rate = dec_ber(d),
            0x0d => self.c_rate = dec_ber(d),
            0x0e => self.d_rate = dec_ber(d),
            0x0f => self.e_rate = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Attribute::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        c.push((0x02, cod_ber(self.r#type.a_i32())));
        if self.a_rate != p.a_rate { c.push((0x0b, cod_ber(self.a_rate))); }
        if self.b_rate != p.b_rate { c.push((0x0c, cod_ber(self.b_rate))); }
        if self.c_rate != p.c_rate { c.push((0x0d, cod_ber(self.c_rate))); }
        if self.d_rate != p.d_rate { c.push((0x0e, cod_ber(self.d_rate))); }
        if self.e_rate != p.e_rate { c.push((0x0f, cod_ber(self.e_rate))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for BattleCommand {
    const NOMBRE: &'static str = "BattleCommand";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.r#type = BattleCommandType::de_i32(dec_ber(d)),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = BattleCommand::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        c.push((0x01, cod_texto(&self.name)));
        if self.r#type != p.r#type { c.push((0x02, cod_ber(self.r#type.a_i32()))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for BattleCommands {
    const NOMBRE: &'static str = "BattleCommands";
    const TERMINADOR: bool = true;
    const CON_ID: bool = false;
    fn id(&self) -> i32 { 0 }
    fn poner_id(&mut self, v: i32) { let _ = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x02 => self.placement = BattleCommandsPlacement::de_i32(dec_ber(d)),
            0x06 => self.row = BattleCommandsRowShown::de_i32(dec_ber(d)),
            0x07 => self.battle_type = BattleCommandsBattleType::de_i32(dec_ber(d)),
            0x09 => self.unused_display_normal_parameters = dec_bool(d),
            0x0a => self.commands = dec_array::<BattleCommand>(d)?,
            0x10 => self.death_event = dec_ber(d),
            0x14 => self.window_size = BattleCommandsWindowSize::de_i32(dec_ber(d)),
            0x18 => self.transparency = BattleCommandsTransparency::de_i32(dec_ber(d)),
            0x19 => self.death_teleport = dec_bool(d),
            0x1a => self.death_teleport_id = dec_ber(d),
            0x1b => self.death_teleport_x = dec_ber(d),
            0x1c => self.death_teleport_y = dec_ber(d),
            0x1d => self.death_teleport_face = BattleCommandsFacing::de_i32(dec_ber(d)),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = BattleCommands::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.placement != p.placement { c.push((0x02, cod_ber(self.placement.a_i32()))); }
        if self.row != p.row { c.push((0x06, cod_ber(self.row.a_i32()))); }
        if self.battle_type != p.battle_type { c.push((0x07, cod_ber(self.battle_type.a_i32()))); }
        if self.unused_display_normal_parameters != p.unused_display_normal_parameters { c.push((0x09, cod_bool(self.unused_display_normal_parameters))); }
        c.push((0x0a, cod_array(&self.commands)?));
        if self.death_event != p.death_event { c.push((0x10, cod_ber(self.death_event))); }
        if self.window_size != p.window_size { c.push((0x14, cod_ber(self.window_size.a_i32()))); }
        if self.transparency != p.transparency { c.push((0x18, cod_ber(self.transparency.a_i32()))); }
        if self.death_teleport != p.death_teleport { c.push((0x19, cod_bool(self.death_teleport))); }
        if self.death_teleport_id != p.death_teleport_id { c.push((0x1a, cod_ber(self.death_teleport_id))); }
        if self.death_teleport_x != p.death_teleport_x { c.push((0x1b, cod_ber(self.death_teleport_x))); }
        if self.death_teleport_y != p.death_teleport_y { c.push((0x1c, cod_ber(self.death_teleport_y))); }
        if self.death_teleport_face != p.death_teleport_face { c.push((0x1d, cod_ber(self.death_teleport_face.a_i32()))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Chipset {
    const NOMBRE: &'static str = "Chipset";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.chipset_name = dec_texto(d),
            0x03 => self.terrain_data = dec_vec_i16(d),
            0x04 => self.passable_data_lower = d.to_vec(),
            0x05 => self.passable_data_upper = d.to_vec(),
            0x0b => self.animation_type = ChipsetAnimType::de_i32(dec_ber(d)),
            0x0c => self.animation_speed = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Chipset::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        if self.chipset_name != p.chipset_name { c.push((0x02, cod_texto(&self.chipset_name))); }
        if self.terrain_data != p.terrain_data { c.push((0x03, cod_vec_i16(&self.terrain_data))); }
        if self.passable_data_lower != p.passable_data_lower { c.push((0x04, self.passable_data_lower.clone())); }
        if self.passable_data_upper != p.passable_data_upper { c.push((0x05, self.passable_data_upper.clone())); }
        if self.animation_type != p.animation_type { c.push((0x0b, cod_ber(self.animation_type.a_i32()))); }
        if self.animation_speed != p.animation_speed { c.push((0x0c, cod_ber(self.animation_speed))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Class {
    const NOMBRE: &'static str = "Class";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x15 => self.two_weapon = dec_bool(d),
            0x16 => self.lock_equipment = dec_bool(d),
            0x17 => self.auto_battle = dec_bool(d),
            0x18 => self.super_guard = dec_bool(d),
            0x1f => self.parameters = Parameters::leer_crudo(d)?,
            0x29 => self.exp_base = dec_ber(d),
            0x2a => self.exp_inflation = dec_ber(d),
            0x2b => self.exp_correction = dec_ber(d),
            0x3e => self.battler_animation = dec_ber(d),
            0x3f => self.skills = dec_array::<Learning>(d)?,
            0x47 => {} // largo de `state_ranks`, se recalcula al escribir
            0x48 => self.state_ranks = d.to_vec(),
            0x49 => {} // largo de `attribute_ranks`, se recalcula al escribir
            0x4a => self.attribute_ranks = d.to_vec(),
            0x50 => self.battle_commands = dec_vec_i32(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Class::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        if self.two_weapon != p.two_weapon { c.push((0x15, cod_bool(self.two_weapon))); }
        if self.lock_equipment != p.lock_equipment { c.push((0x16, cod_bool(self.lock_equipment))); }
        if self.auto_battle != p.auto_battle { c.push((0x17, cod_bool(self.auto_battle))); }
        if self.super_guard != p.super_guard { c.push((0x18, cod_bool(self.super_guard))); }
        if self.parameters != p.parameters { c.push((0x1f, self.parameters.escribir_crudo())); }
        if self.exp_base != p.exp_base { c.push((0x29, cod_ber(self.exp_base))); }
        if self.exp_inflation != p.exp_inflation { c.push((0x2a, cod_ber(self.exp_inflation))); }
        if self.exp_correction != p.exp_correction { c.push((0x2b, cod_ber(self.exp_correction))); }
        if self.battler_animation != p.battler_animation { c.push((0x3e, cod_ber(self.battler_animation))); }
        c.push((0x3f, cod_array(&self.skills)?));
        let v_state_ranks = self.state_ranks.clone();
        if v_state_ranks.len() != p.state_ranks.clone().len() { c.push((0x47, cod_ber(v_state_ranks.len() as i32))); }
        c.push((0x48, v_state_ranks));
        let v_attribute_ranks = self.attribute_ranks.clone();
        if v_attribute_ranks.len() != p.attribute_ranks.clone().len() { c.push((0x49, cod_ber(v_attribute_ranks.len() as i32))); }
        c.push((0x4a, v_attribute_ranks));
        c.push((0x50, cod_vec_i32(&self.battle_commands)));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for CommonEvent {
    const NOMBRE: &'static str = "CommonEvent";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x0b => self.trigger = CommonEventTrigger::de_i32(dec_ber(d)),
            0x0c => self.switch_flag = dec_bool(d),
            0x0d => self.switch_id = dec_ber(d),
            0x15 => {} // largo de `event_commands`, se recalcula al escribir
            0x16 => self.event_commands = dec_comandos_evento(d)?,
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = CommonEvent::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        c.push((0x0b, cod_ber(self.trigger.a_i32())));
        if self.switch_flag != p.switch_flag { c.push((0x0c, cod_bool(self.switch_flag))); }
        if self.switch_id != p.switch_id { c.push((0x0d, cod_ber(self.switch_id))); }
        let v_event_commands = cod_comandos_evento(&self.event_commands);
        c.push((0x15, cod_ber(v_event_commands.len() as i32)));
        c.push((0x16, v_event_commands));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Skill {
    const NOMBRE: &'static str = "Skill";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.description = dec_texto(d),
            0x03 => self.using_message1 = dec_texto(d),
            0x04 => self.using_message2 = dec_texto(d),
            0x07 => self.failure_message = dec_ber(d),
            0x08 => self.r#type = SkillType::de_i32(dec_ber(d)),
            0x0b => self.sp_cost = dec_ber(d),
            0x0c => self.scope = SkillScope::de_i32(dec_ber(d)),
            0x0d => self.switch_id = dec_ber(d),
            0x0e => self.animation_id = dec_ber(d),
            0x10 => self.sound_effect = dec_struct::<Sound>(d)?,
            0x12 => self.occasion_field = dec_bool(d),
            0x13 => self.occasion_battle = dec_bool(d),
            0x15 => self.physical_rate = dec_ber(d),
            0x16 => self.magical_rate = dec_ber(d),
            0x17 => self.variance = dec_ber(d),
            0x18 => self.power = dec_ber(d),
            0x19 => self.hit = dec_ber(d),
            0x1f => self.affect_hp = dec_bool(d),
            0x20 => self.affect_sp = dec_bool(d),
            0x21 => self.affect_attack = dec_bool(d),
            0x22 => self.affect_defense = dec_bool(d),
            0x23 => self.affect_spirit = dec_bool(d),
            0x24 => self.affect_agility = dec_bool(d),
            0x25 => self.absorb_damage = dec_bool(d),
            0x26 => self.ignore_defense = dec_bool(d),
            0x29 => {} // largo de `state_effects`, se recalcula al escribir
            0x2a => self.state_effects = dec_vec_bool(d),
            0x2b => {} // largo de `attribute_effects`, se recalcula al escribir
            0x2c => self.attribute_effects = dec_vec_bool(d),
            0x2d => self.affect_attr_defence = dec_bool(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Skill::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        if self.description != p.description { c.push((0x02, cod_texto(&self.description))); }
        if self.using_message1 != p.using_message1 { c.push((0x03, cod_texto(&self.using_message1))); }
        if self.using_message2 != p.using_message2 { c.push((0x04, cod_texto(&self.using_message2))); }
        if self.failure_message != p.failure_message { c.push((0x07, cod_ber(self.failure_message))); }
        c.push((0x08, cod_ber(self.r#type.a_i32())));
        if self.sp_cost != p.sp_cost { c.push((0x0b, cod_ber(self.sp_cost))); }
        c.push((0x0c, cod_ber(self.scope.a_i32())));
        if self.switch_id != p.switch_id { c.push((0x0d, cod_ber(self.switch_id))); }
        if self.animation_id != p.animation_id { c.push((0x0e, cod_ber(self.animation_id))); }
        c.push((0x10, cod_struct(&self.sound_effect)?));
        if self.occasion_field != p.occasion_field { c.push((0x12, cod_bool(self.occasion_field))); }
        if self.occasion_battle != p.occasion_battle { c.push((0x13, cod_bool(self.occasion_battle))); }
        if self.physical_rate != p.physical_rate { c.push((0x15, cod_ber(self.physical_rate))); }
        if self.magical_rate != p.magical_rate { c.push((0x16, cod_ber(self.magical_rate))); }
        if self.variance != p.variance { c.push((0x17, cod_ber(self.variance))); }
        if self.power != p.power { c.push((0x18, cod_ber(self.power))); }
        if self.hit != p.hit { c.push((0x19, cod_ber(self.hit))); }
        if self.affect_hp != p.affect_hp { c.push((0x1f, cod_bool(self.affect_hp))); }
        if self.affect_sp != p.affect_sp { c.push((0x20, cod_bool(self.affect_sp))); }
        if self.affect_attack != p.affect_attack { c.push((0x21, cod_bool(self.affect_attack))); }
        if self.affect_defense != p.affect_defense { c.push((0x22, cod_bool(self.affect_defense))); }
        if self.affect_spirit != p.affect_spirit { c.push((0x23, cod_bool(self.affect_spirit))); }
        if self.affect_agility != p.affect_agility { c.push((0x24, cod_bool(self.affect_agility))); }
        if self.absorb_damage != p.absorb_damage { c.push((0x25, cod_bool(self.absorb_damage))); }
        if self.ignore_defense != p.ignore_defense { c.push((0x26, cod_bool(self.ignore_defense))); }
        let v_state_effects = cod_vec_bool(&self.state_effects);
        if v_state_effects.len() != cod_vec_bool(&p.state_effects).len() { c.push((0x29, cod_ber(v_state_effects.len() as i32))); }
        c.push((0x2a, v_state_effects));
        let v_attribute_effects = cod_vec_bool(&self.attribute_effects);
        if v_attribute_effects.len() != cod_vec_bool(&p.attribute_effects).len() { c.push((0x2b, cod_ber(v_attribute_effects.len() as i32))); }
        c.push((0x2c, v_attribute_effects));
        if self.affect_attr_defence != p.affect_attr_defence { c.push((0x2d, cod_bool(self.affect_attr_defence))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Item {
    const NOMBRE: &'static str = "Item";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.description = dec_texto(d),
            0x03 => self.r#type = ItemType::de_i32(dec_ber(d)),
            0x05 => self.price = dec_ber(d),
            0x06 => self.uses = dec_ber(d),
            0x0b => self.atk_points1 = dec_ber(d),
            0x0c => self.def_points1 = dec_ber(d),
            0x0d => self.spi_points1 = dec_ber(d),
            0x0e => self.agi_points1 = dec_ber(d),
            0x0f => self.two_handed = dec_bool(d),
            0x10 => self.sp_cost = dec_ber(d),
            0x11 => self.hit = dec_ber(d),
            0x12 => self.critical_hit = dec_ber(d),
            0x14 => self.animation_id = dec_ber(d),
            0x15 => self.preemptive = dec_bool(d),
            0x16 => self.dual_attack = dec_bool(d),
            0x17 => self.attack_all = dec_bool(d),
            0x18 => self.ignore_evasion = dec_bool(d),
            0x19 => self.prevent_critical = dec_bool(d),
            0x1a => self.raise_evasion = dec_bool(d),
            0x1b => self.half_sp_cost = dec_bool(d),
            0x1c => self.no_terrain_damage = dec_bool(d),
            0x1f => self.entire_party = dec_bool(d),
            0x20 => self.recover_hp_rate = dec_ber(d),
            0x21 => self.recover_hp = dec_ber(d),
            0x22 => self.recover_sp_rate = dec_ber(d),
            0x23 => self.recover_sp = dec_ber(d),
            0x25 => self.occasion_field1 = dec_bool(d),
            0x26 => self.ko_only = dec_bool(d),
            0x29 => self.max_hp_points = dec_ber(d),
            0x2a => self.max_sp_points = dec_ber(d),
            0x2b => self.atk_points2 = dec_ber(d),
            0x2c => self.def_points2 = dec_ber(d),
            0x2d => self.spi_points2 = dec_ber(d),
            0x2e => self.agi_points2 = dec_ber(d),
            0x33 => self.using_message = dec_ber(d),
            0x35 => self.skill_id = dec_ber(d),
            0x37 => self.switch_id = dec_ber(d),
            0x39 => self.occasion_field2 = dec_bool(d),
            0x3a => self.occasion_battle = dec_bool(d),
            0x3d => {} // largo de `actor_set`, se recalcula al escribir
            0x3e => self.actor_set = dec_vec_bool(d),
            0x3f => {} // largo de `state_set`, se recalcula al escribir
            0x40 => self.state_set = dec_vec_bool(d),
            0x41 => {} // largo de `attribute_set`, se recalcula al escribir
            0x42 => self.attribute_set = dec_vec_bool(d),
            0x43 => self.state_chance = dec_ber(d),
            0x44 => self.reverse_state_effect = dec_bool(d),
            0x4b => self.ranged_trajectory = ItemTrajectory::de_i32(dec_ber(d)),
            0x4c => self.ranged_target = ItemTarget::de_i32(dec_ber(d)),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Item::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        if self.description != p.description { c.push((0x02, cod_texto(&self.description))); }
        c.push((0x03, cod_ber(self.r#type.a_i32())));
        if self.price != p.price { c.push((0x05, cod_ber(self.price))); }
        if self.uses != p.uses { c.push((0x06, cod_ber(self.uses))); }
        if self.atk_points1 != p.atk_points1 { c.push((0x0b, cod_ber(self.atk_points1))); }
        if self.def_points1 != p.def_points1 { c.push((0x0c, cod_ber(self.def_points1))); }
        if self.spi_points1 != p.spi_points1 { c.push((0x0d, cod_ber(self.spi_points1))); }
        if self.agi_points1 != p.agi_points1 { c.push((0x0e, cod_ber(self.agi_points1))); }
        c.push((0x0f, cod_bool(self.two_handed)));
        if self.sp_cost != p.sp_cost { c.push((0x10, cod_ber(self.sp_cost))); }
        if self.hit != p.hit { c.push((0x11, cod_ber(self.hit))); }
        if self.critical_hit != p.critical_hit { c.push((0x12, cod_ber(self.critical_hit))); }
        if self.animation_id != p.animation_id { c.push((0x14, cod_ber(self.animation_id))); }
        if self.preemptive != p.preemptive { c.push((0x15, cod_bool(self.preemptive))); }
        if self.dual_attack != p.dual_attack { c.push((0x16, cod_bool(self.dual_attack))); }
        if self.attack_all != p.attack_all { c.push((0x17, cod_bool(self.attack_all))); }
        if self.ignore_evasion != p.ignore_evasion { c.push((0x18, cod_bool(self.ignore_evasion))); }
        if self.prevent_critical != p.prevent_critical { c.push((0x19, cod_bool(self.prevent_critical))); }
        if self.raise_evasion != p.raise_evasion { c.push((0x1a, cod_bool(self.raise_evasion))); }
        if self.half_sp_cost != p.half_sp_cost { c.push((0x1b, cod_bool(self.half_sp_cost))); }
        if self.no_terrain_damage != p.no_terrain_damage { c.push((0x1c, cod_bool(self.no_terrain_damage))); }
        c.push((0x1f, cod_bool(self.entire_party)));
        if self.recover_hp_rate != p.recover_hp_rate { c.push((0x20, cod_ber(self.recover_hp_rate))); }
        if self.recover_hp != p.recover_hp { c.push((0x21, cod_ber(self.recover_hp))); }
        if self.recover_sp_rate != p.recover_sp_rate { c.push((0x22, cod_ber(self.recover_sp_rate))); }
        if self.recover_sp != p.recover_sp { c.push((0x23, cod_ber(self.recover_sp))); }
        if self.occasion_field1 != p.occasion_field1 { c.push((0x25, cod_bool(self.occasion_field1))); }
        if self.ko_only != p.ko_only { c.push((0x26, cod_bool(self.ko_only))); }
        if self.max_hp_points != p.max_hp_points { c.push((0x29, cod_ber(self.max_hp_points))); }
        if self.max_sp_points != p.max_sp_points { c.push((0x2a, cod_ber(self.max_sp_points))); }
        if self.atk_points2 != p.atk_points2 { c.push((0x2b, cod_ber(self.atk_points2))); }
        if self.def_points2 != p.def_points2 { c.push((0x2c, cod_ber(self.def_points2))); }
        if self.spi_points2 != p.spi_points2 { c.push((0x2d, cod_ber(self.spi_points2))); }
        if self.agi_points2 != p.agi_points2 { c.push((0x2e, cod_ber(self.agi_points2))); }
        c.push((0x33, cod_ber(self.using_message)));
        if self.skill_id != p.skill_id { c.push((0x35, cod_ber(self.skill_id))); }
        if self.switch_id != p.switch_id { c.push((0x37, cod_ber(self.switch_id))); }
        if self.occasion_field2 != p.occasion_field2 { c.push((0x39, cod_bool(self.occasion_field2))); }
        if self.occasion_battle != p.occasion_battle { c.push((0x3a, cod_bool(self.occasion_battle))); }
        let v_actor_set = cod_vec_bool(&self.actor_set);
        if v_actor_set.len() != cod_vec_bool(&p.actor_set).len() { c.push((0x3d, cod_ber(v_actor_set.len() as i32))); }
        c.push((0x3e, v_actor_set));
        let v_state_set = cod_vec_bool(&self.state_set);
        if v_state_set.len() != cod_vec_bool(&p.state_set).len() { c.push((0x3f, cod_ber(v_state_set.len() as i32))); }
        c.push((0x40, v_state_set));
        let v_attribute_set = cod_vec_bool(&self.attribute_set);
        if v_attribute_set.len() != cod_vec_bool(&p.attribute_set).len() { c.push((0x41, cod_ber(v_attribute_set.len() as i32))); }
        c.push((0x42, v_attribute_set));
        if self.state_chance != p.state_chance { c.push((0x43, cod_ber(self.state_chance))); }
        if self.reverse_state_effect != p.reverse_state_effect { c.push((0x44, cod_bool(self.reverse_state_effect))); }
        if self.ranged_trajectory != p.ranged_trajectory { c.push((0x4b, cod_ber(self.ranged_trajectory.a_i32()))); }
        if self.ranged_target != p.ranged_target { c.push((0x4c, cod_ber(self.ranged_target.a_i32()))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for EnemyAction {
    const NOMBRE: &'static str = "EnemyAction";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.kind = EnemyActionKind::de_i32(dec_ber(d)),
            0x02 => self.basic = EnemyActionBasic::de_i32(dec_ber(d)),
            0x03 => self.skill_id = dec_ber(d),
            0x04 => self.enemy_id = dec_ber(d),
            0x05 => self.condition_type = EnemyActionConditionType::de_i32(dec_ber(d)),
            0x06 => self.condition_param1 = dec_ber(d),
            0x07 => self.condition_param2 = dec_ber(d),
            0x08 => self.switch_id = dec_ber(d),
            0x09 => self.switch_on = dec_bool(d),
            0x0a => self.switch_on_id = dec_ber(d),
            0x0b => self.switch_off = dec_bool(d),
            0x0c => self.switch_off_id = dec_ber(d),
            0x0d => self.rating = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = EnemyAction::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        c.push((0x01, cod_ber(self.kind.a_i32())));
        c.push((0x02, cod_ber(self.basic.a_i32())));
        if self.skill_id != p.skill_id { c.push((0x03, cod_ber(self.skill_id))); }
        if self.enemy_id != p.enemy_id { c.push((0x04, cod_ber(self.enemy_id))); }
        c.push((0x05, cod_ber(self.condition_type.a_i32())));
        if self.condition_param1 != p.condition_param1 { c.push((0x06, cod_ber(self.condition_param1))); }
        if self.condition_param2 != p.condition_param2 { c.push((0x07, cod_ber(self.condition_param2))); }
        if self.switch_id != p.switch_id { c.push((0x08, cod_ber(self.switch_id))); }
        if self.switch_on != p.switch_on { c.push((0x09, cod_bool(self.switch_on))); }
        if self.switch_on_id != p.switch_on_id { c.push((0x0a, cod_ber(self.switch_on_id))); }
        if self.switch_off != p.switch_off { c.push((0x0b, cod_bool(self.switch_off))); }
        if self.switch_off_id != p.switch_off_id { c.push((0x0c, cod_ber(self.switch_off_id))); }
        if self.rating != p.rating { c.push((0x0d, cod_ber(self.rating))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Enemy {
    const NOMBRE: &'static str = "Enemy";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.battler_name = dec_texto(d),
            0x03 => self.battler_hue = dec_ber(d),
            0x04 => self.max_hp = dec_ber(d),
            0x05 => self.max_sp = dec_ber(d),
            0x06 => self.attack = dec_ber(d),
            0x07 => self.defense = dec_ber(d),
            0x08 => self.spirit = dec_ber(d),
            0x09 => self.agility = dec_ber(d),
            0x0a => self.transparent = dec_bool(d),
            0x0b => self.exp = dec_ber(d),
            0x0c => self.gold = dec_ber(d),
            0x0d => self.drop_id = dec_ber(d),
            0x0e => self.drop_prob = dec_ber(d),
            0x15 => self.critical_hit = dec_bool(d),
            0x16 => self.critical_hit_chance = dec_ber(d),
            0x1a => self.miss = dec_bool(d),
            0x1c => self.levitate = dec_bool(d),
            0x1f => {} // largo de `state_ranks`, se recalcula al escribir
            0x20 => self.state_ranks = d.to_vec(),
            0x21 => {} // largo de `attribute_ranks`, se recalcula al escribir
            0x22 => self.attribute_ranks = d.to_vec(),
            0x2a => self.actions = dec_array::<EnemyAction>(d)?,
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Enemy::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        if self.battler_name != p.battler_name { c.push((0x02, cod_texto(&self.battler_name))); }
        if self.battler_hue != p.battler_hue { c.push((0x03, cod_ber(self.battler_hue))); }
        if self.max_hp != p.max_hp { c.push((0x04, cod_ber(self.max_hp))); }
        if self.max_sp != p.max_sp { c.push((0x05, cod_ber(self.max_sp))); }
        if self.attack != p.attack { c.push((0x06, cod_ber(self.attack))); }
        if self.defense != p.defense { c.push((0x07, cod_ber(self.defense))); }
        if self.spirit != p.spirit { c.push((0x08, cod_ber(self.spirit))); }
        if self.agility != p.agility { c.push((0x09, cod_ber(self.agility))); }
        if self.transparent != p.transparent { c.push((0x0a, cod_bool(self.transparent))); }
        if self.exp != p.exp { c.push((0x0b, cod_ber(self.exp))); }
        if self.gold != p.gold { c.push((0x0c, cod_ber(self.gold))); }
        if self.drop_id != p.drop_id { c.push((0x0d, cod_ber(self.drop_id))); }
        if self.drop_prob != p.drop_prob { c.push((0x0e, cod_ber(self.drop_prob))); }
        if self.critical_hit != p.critical_hit { c.push((0x15, cod_bool(self.critical_hit))); }
        if self.critical_hit_chance != p.critical_hit_chance { c.push((0x16, cod_ber(self.critical_hit_chance))); }
        if self.miss != p.miss { c.push((0x1a, cod_bool(self.miss))); }
        if self.levitate != p.levitate { c.push((0x1c, cod_bool(self.levitate))); }
        let v_state_ranks = self.state_ranks.clone();
        if v_state_ranks.len() != p.state_ranks.clone().len() { c.push((0x1f, cod_ber(v_state_ranks.len() as i32))); }
        c.push((0x20, v_state_ranks));
        let v_attribute_ranks = self.attribute_ranks.clone();
        if v_attribute_ranks.len() != p.attribute_ranks.clone().len() { c.push((0x21, cod_ber(v_attribute_ranks.len() as i32))); }
        c.push((0x22, v_attribute_ranks));
        c.push((0x2a, cod_array(&self.actions)?));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for TroopMember {
    const NOMBRE: &'static str = "TroopMember";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.enemy_id = dec_ber(d),
            0x02 => self.x = dec_ber(d),
            0x03 => self.y = dec_ber(d),
            0x04 => self.invisible = dec_bool(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = TroopMember::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.enemy_id != p.enemy_id { c.push((0x01, cod_ber(self.enemy_id))); }
        if self.x != p.x { c.push((0x02, cod_ber(self.x))); }
        if self.y != p.y { c.push((0x03, cod_ber(self.y))); }
        if self.invisible != p.invisible { c.push((0x04, cod_bool(self.invisible))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for TroopPageCondition {
    const NOMBRE: &'static str = "TroopPageCondition";
    const TERMINADOR: bool = true;
    const CON_ID: bool = false;
    fn id(&self) -> i32 { 0 }
    fn poner_id(&mut self, v: i32) { let _ = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.flags = TroopPageConditionFlags::leer(d),
            0x02 => self.switch_a_id = dec_ber(d),
            0x03 => self.switch_b_id = dec_ber(d),
            0x04 => self.variable_id = dec_ber(d),
            0x05 => self.variable_value = dec_ber(d),
            0x06 => self.turn_a = dec_ber(d),
            0x07 => self.turn_b = dec_ber(d),
            0x08 => self.fatigue_min = dec_ber(d),
            0x09 => self.fatigue_max = dec_ber(d),
            0x0a => self.enemy_id = dec_ber(d),
            0x0b => self.enemy_hp_min = dec_ber(d),
            0x0c => self.enemy_hp_max = dec_ber(d),
            0x0d => self.actor_id = dec_ber(d),
            0x0e => self.actor_hp_min = dec_ber(d),
            0x0f => self.actor_hp_max = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = TroopPageCondition::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        c.push((0x01, self.flags.escribir()));
        if self.switch_a_id != p.switch_a_id { c.push((0x02, cod_ber(self.switch_a_id))); }
        if self.switch_b_id != p.switch_b_id { c.push((0x03, cod_ber(self.switch_b_id))); }
        if self.variable_id != p.variable_id { c.push((0x04, cod_ber(self.variable_id))); }
        if self.variable_value != p.variable_value { c.push((0x05, cod_ber(self.variable_value))); }
        if self.turn_a != p.turn_a { c.push((0x06, cod_ber(self.turn_a))); }
        if self.turn_b != p.turn_b { c.push((0x07, cod_ber(self.turn_b))); }
        if self.fatigue_min != p.fatigue_min { c.push((0x08, cod_ber(self.fatigue_min))); }
        if self.fatigue_max != p.fatigue_max { c.push((0x09, cod_ber(self.fatigue_max))); }
        if self.enemy_id != p.enemy_id { c.push((0x0a, cod_ber(self.enemy_id))); }
        if self.enemy_hp_min != p.enemy_hp_min { c.push((0x0b, cod_ber(self.enemy_hp_min))); }
        if self.enemy_hp_max != p.enemy_hp_max { c.push((0x0c, cod_ber(self.enemy_hp_max))); }
        if self.actor_id != p.actor_id { c.push((0x0d, cod_ber(self.actor_id))); }
        if self.actor_hp_min != p.actor_hp_min { c.push((0x0e, cod_ber(self.actor_hp_min))); }
        if self.actor_hp_max != p.actor_hp_max { c.push((0x0f, cod_ber(self.actor_hp_max))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for TroopPage {
    const NOMBRE: &'static str = "TroopPage";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x02 => self.condition = dec_struct::<TroopPageCondition>(d)?,
            0x0b => {} // largo de `event_commands`, se recalcula al escribir
            0x0c => self.event_commands = dec_comandos_evento(d)?,
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = TroopPage::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        c.push((0x02, cod_struct(&self.condition)?));
        let v_event_commands = cod_comandos_evento(&self.event_commands);
        c.push((0x0b, cod_ber(v_event_commands.len() as i32)));
        c.push((0x0c, v_event_commands));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Troop {
    const NOMBRE: &'static str = "Troop";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.members = dec_array::<TroopMember>(d)?,
            0x04 => {} // largo de `terrain_set`, se recalcula al escribir
            0x05 => self.terrain_set = dec_vec_bool(d),
            0x0b => self.pages = dec_array::<TroopPage>(d)?,
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Troop::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        c.push((0x02, cod_array(&self.members)?));
        let v_terrain_set = cod_vec_bool(&self.terrain_set);
        if v_terrain_set.len() != cod_vec_bool(&p.terrain_set).len() { c.push((0x04, cod_ber(v_terrain_set.len() as i32))); }
        c.push((0x05, v_terrain_set));
        c.push((0x0b, cod_array(&self.pages)?));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Terrain {
    const NOMBRE: &'static str = "Terrain";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.damage = dec_ber(d),
            0x03 => self.encounter_rate = dec_ber(d),
            0x04 => self.background_name = dec_texto(d),
            0x05 => self.boat_pass = dec_bool(d),
            0x06 => self.ship_pass = dec_bool(d),
            0x07 => self.airship_pass = dec_bool(d),
            0x09 => self.airship_land = dec_bool(d),
            0x0b => self.bush_depth = TerrainBushDepth::de_i32(dec_ber(d)),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Terrain::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        if self.damage != p.damage { c.push((0x02, cod_ber(self.damage))); }
        if self.encounter_rate != p.encounter_rate { c.push((0x03, cod_ber(self.encounter_rate))); }
        if self.background_name != p.background_name { c.push((0x04, cod_texto(&self.background_name))); }
        if self.boat_pass != p.boat_pass { c.push((0x05, cod_bool(self.boat_pass))); }
        if self.ship_pass != p.ship_pass { c.push((0x06, cod_bool(self.ship_pass))); }
        if self.airship_pass != p.airship_pass { c.push((0x07, cod_bool(self.airship_pass))); }
        if self.airship_land != p.airship_land { c.push((0x09, cod_bool(self.airship_land))); }
        c.push((0x0b, cod_ber(self.bush_depth.a_i32())));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for State {
    const NOMBRE: &'static str = "State";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.r#type = StatePersistence::de_i32(dec_ber(d)),
            0x03 => self.color = dec_ber(d),
            0x04 => self.priority = dec_ber(d),
            0x05 => self.restriction = StateRestriction::de_i32(dec_ber(d)),
            0x0b => self.a_rate = dec_ber(d),
            0x0c => self.b_rate = dec_ber(d),
            0x0d => self.c_rate = dec_ber(d),
            0x0e => self.d_rate = dec_ber(d),
            0x0f => self.e_rate = dec_ber(d),
            0x15 => self.hold_turn = dec_ber(d),
            0x16 => self.auto_release_prob = dec_ber(d),
            0x17 => self.release_by_damage = dec_ber(d),
            0x1f => self.affect_attack = dec_bool(d),
            0x20 => self.affect_defense = dec_bool(d),
            0x21 => self.affect_spirit = dec_bool(d),
            0x22 => self.affect_agility = dec_bool(d),
            0x23 => self.reduce_hit_ratio = dec_ber(d),
            0x29 => self.restrict_skill = dec_bool(d),
            0x2a => self.restrict_skill_level = dec_ber(d),
            0x2b => self.restrict_magic = dec_bool(d),
            0x2c => self.restrict_magic_level = dec_ber(d),
            0x2d => self.hp_change_type = StateChangeType::de_i32(dec_ber(d)),
            0x2e => self.sp_change_type = StateChangeType::de_i32(dec_ber(d)),
            0x33 => self.message_actor = dec_texto(d),
            0x34 => self.message_enemy = dec_texto(d),
            0x35 => self.message_already = dec_texto(d),
            0x36 => self.message_affected = dec_texto(d),
            0x37 => self.message_recovery = dec_texto(d),
            0x3d => self.hp_change_max = dec_ber(d),
            0x3e => self.hp_change_val = dec_ber(d),
            0x3f => self.hp_change_map_steps = dec_ber(d),
            0x40 => self.hp_change_map_val = dec_ber(d),
            0x41 => self.sp_change_max = dec_ber(d),
            0x42 => self.sp_change_val = dec_ber(d),
            0x43 => self.sp_change_map_steps = dec_ber(d),
            0x44 => self.sp_change_map_val = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = State::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        c.push((0x02, cod_ber(self.r#type.a_i32())));
        if self.color != p.color { c.push((0x03, cod_ber(self.color))); }
        if self.priority != p.priority { c.push((0x04, cod_ber(self.priority))); }
        c.push((0x05, cod_ber(self.restriction.a_i32())));
        if self.a_rate != p.a_rate { c.push((0x0b, cod_ber(self.a_rate))); }
        if self.b_rate != p.b_rate { c.push((0x0c, cod_ber(self.b_rate))); }
        if self.c_rate != p.c_rate { c.push((0x0d, cod_ber(self.c_rate))); }
        if self.d_rate != p.d_rate { c.push((0x0e, cod_ber(self.d_rate))); }
        if self.e_rate != p.e_rate { c.push((0x0f, cod_ber(self.e_rate))); }
        if self.hold_turn != p.hold_turn { c.push((0x15, cod_ber(self.hold_turn))); }
        if self.auto_release_prob != p.auto_release_prob { c.push((0x16, cod_ber(self.auto_release_prob))); }
        if self.release_by_damage != p.release_by_damage { c.push((0x17, cod_ber(self.release_by_damage))); }
        if self.affect_attack != p.affect_attack { c.push((0x1f, cod_bool(self.affect_attack))); }
        if self.affect_defense != p.affect_defense { c.push((0x20, cod_bool(self.affect_defense))); }
        if self.affect_spirit != p.affect_spirit { c.push((0x21, cod_bool(self.affect_spirit))); }
        if self.affect_agility != p.affect_agility { c.push((0x22, cod_bool(self.affect_agility))); }
        if self.reduce_hit_ratio != p.reduce_hit_ratio { c.push((0x23, cod_ber(self.reduce_hit_ratio))); }
        if self.restrict_skill != p.restrict_skill { c.push((0x29, cod_bool(self.restrict_skill))); }
        if self.restrict_skill_level != p.restrict_skill_level { c.push((0x2a, cod_ber(self.restrict_skill_level))); }
        if self.restrict_magic != p.restrict_magic { c.push((0x2b, cod_bool(self.restrict_magic))); }
        if self.restrict_magic_level != p.restrict_magic_level { c.push((0x2c, cod_ber(self.restrict_magic_level))); }
        if self.hp_change_type != p.hp_change_type { c.push((0x2d, cod_ber(self.hp_change_type.a_i32()))); }
        if self.sp_change_type != p.sp_change_type { c.push((0x2e, cod_ber(self.sp_change_type.a_i32()))); }
        if self.message_actor != p.message_actor { c.push((0x33, cod_texto(&self.message_actor))); }
        if self.message_enemy != p.message_enemy { c.push((0x34, cod_texto(&self.message_enemy))); }
        if self.message_already != p.message_already { c.push((0x35, cod_texto(&self.message_already))); }
        if self.message_affected != p.message_affected { c.push((0x36, cod_texto(&self.message_affected))); }
        if self.message_recovery != p.message_recovery { c.push((0x37, cod_texto(&self.message_recovery))); }
        if self.hp_change_max != p.hp_change_max { c.push((0x3d, cod_ber(self.hp_change_max))); }
        if self.hp_change_val != p.hp_change_val { c.push((0x3e, cod_ber(self.hp_change_val))); }
        if self.hp_change_map_steps != p.hp_change_map_steps { c.push((0x3f, cod_ber(self.hp_change_map_steps))); }
        if self.hp_change_map_val != p.hp_change_map_val { c.push((0x40, cod_ber(self.hp_change_map_val))); }
        if self.sp_change_max != p.sp_change_max { c.push((0x41, cod_ber(self.sp_change_max))); }
        if self.sp_change_val != p.sp_change_val { c.push((0x42, cod_ber(self.sp_change_val))); }
        if self.sp_change_map_steps != p.sp_change_map_steps { c.push((0x43, cod_ber(self.sp_change_map_steps))); }
        if self.sp_change_map_val != p.sp_change_map_val { c.push((0x44, cod_ber(self.sp_change_map_val))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Terms {
    const NOMBRE: &'static str = "Terms";
    const TERMINADOR: bool = true;
    const CON_ID: bool = false;
    fn id(&self) -> i32 { 0 }
    fn poner_id(&mut self, v: i32) { let _ = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.encounter = dec_texto(d),
            0x02 => self.special_combat = dec_texto(d),
            0x03 => self.escape_success = dec_texto(d),
            0x04 => self.escape_failure = dec_texto(d),
            0x05 => self.victory = dec_texto(d),
            0x06 => self.defeat = dec_texto(d),
            0x07 => self.exp_received = dec_texto(d),
            0x08 => self.gold_recieved_a = dec_texto(d),
            0x09 => self.gold_recieved_b = dec_texto(d),
            0x0a => self.item_recieved = dec_texto(d),
            0x0b => self.attacking = dec_texto(d),
            0x0c => self.enemy_critical = dec_texto(d),
            0x0d => self.actor_critical = dec_texto(d),
            0x0e => self.defending = dec_texto(d),
            0x0f => self.observing = dec_texto(d),
            0x10 => self.focus = dec_texto(d),
            0x11 => self.autodestruction = dec_texto(d),
            0x12 => self.enemy_escape = dec_texto(d),
            0x13 => self.enemy_transform = dec_texto(d),
            0x14 => self.enemy_damaged = dec_texto(d),
            0x15 => self.enemy_undamaged = dec_texto(d),
            0x16 => self.actor_damaged = dec_texto(d),
            0x17 => self.actor_undamaged = dec_texto(d),
            0x18 => self.skill_failure_a = dec_texto(d),
            0x19 => self.skill_failure_b = dec_texto(d),
            0x1a => self.skill_failure_c = dec_texto(d),
            0x1b => self.dodge = dec_texto(d),
            0x1c => self.use_item = dec_texto(d),
            0x1d => self.hp_recovery = dec_texto(d),
            0x1e => self.parameter_increase = dec_texto(d),
            0x1f => self.parameter_decrease = dec_texto(d),
            0x20 => self.enemy_hp_absorbed = dec_texto(d),
            0x21 => self.actor_hp_absorbed = dec_texto(d),
            0x22 => self.resistance_increase = dec_texto(d),
            0x23 => self.resistance_decrease = dec_texto(d),
            0x24 => self.level_up = dec_texto(d),
            0x25 => self.skill_learned = dec_texto(d),
            0x29 => self.shop_greeting1 = dec_texto(d),
            0x2a => self.shop_regreeting1 = dec_texto(d),
            0x2b => self.shop_buy1 = dec_texto(d),
            0x2c => self.shop_sell1 = dec_texto(d),
            0x2d => self.shop_leave1 = dec_texto(d),
            0x2e => self.shop_buy_select1 = dec_texto(d),
            0x2f => self.shop_buy_number1 = dec_texto(d),
            0x30 => self.shop_purchased1 = dec_texto(d),
            0x31 => self.shop_sell_select1 = dec_texto(d),
            0x32 => self.shop_sell_number1 = dec_texto(d),
            0x33 => self.shop_sold1 = dec_texto(d),
            0x36 => self.shop_greeting2 = dec_texto(d),
            0x37 => self.shop_regreeting2 = dec_texto(d),
            0x38 => self.shop_buy2 = dec_texto(d),
            0x39 => self.shop_sell2 = dec_texto(d),
            0x3a => self.shop_leave2 = dec_texto(d),
            0x3b => self.shop_buy_select2 = dec_texto(d),
            0x3c => self.shop_buy_number2 = dec_texto(d),
            0x3d => self.shop_purchased2 = dec_texto(d),
            0x3e => self.shop_sell_select2 = dec_texto(d),
            0x3f => self.shop_sell_number2 = dec_texto(d),
            0x40 => self.shop_sold2 = dec_texto(d),
            0x43 => self.shop_greeting3 = dec_texto(d),
            0x44 => self.shop_regreeting3 = dec_texto(d),
            0x45 => self.shop_buy3 = dec_texto(d),
            0x46 => self.shop_sell3 = dec_texto(d),
            0x47 => self.shop_leave3 = dec_texto(d),
            0x48 => self.shop_buy_select3 = dec_texto(d),
            0x49 => self.shop_buy_number3 = dec_texto(d),
            0x4a => self.shop_purchased3 = dec_texto(d),
            0x4b => self.shop_sell_select3 = dec_texto(d),
            0x4c => self.shop_sell_number3 = dec_texto(d),
            0x4d => self.shop_sold3 = dec_texto(d),
            0x50 => self.inn_a_greeting_1 = dec_texto(d),
            0x51 => self.inn_a_greeting_2 = dec_texto(d),
            0x52 => self.inn_a_greeting_3 = dec_texto(d),
            0x53 => self.inn_a_accept = dec_texto(d),
            0x54 => self.inn_a_cancel = dec_texto(d),
            0x55 => self.inn_b_greeting_1 = dec_texto(d),
            0x56 => self.inn_b_greeting_2 = dec_texto(d),
            0x57 => self.inn_b_greeting_3 = dec_texto(d),
            0x58 => self.inn_b_accept = dec_texto(d),
            0x59 => self.inn_b_cancel = dec_texto(d),
            0x5c => self.possessed_items = dec_texto(d),
            0x5d => self.equipped_items = dec_texto(d),
            0x5f => self.gold = dec_texto(d),
            0x65 => self.battle_fight = dec_texto(d),
            0x66 => self.battle_auto = dec_texto(d),
            0x67 => self.battle_escape = dec_texto(d),
            0x68 => self.command_attack = dec_texto(d),
            0x69 => self.command_defend = dec_texto(d),
            0x6a => self.command_item = dec_texto(d),
            0x6b => self.command_skill = dec_texto(d),
            0x6c => self.menu_equipment = dec_texto(d),
            0x6e => self.menu_save = dec_texto(d),
            0x70 => self.menu_quit = dec_texto(d),
            0x72 => self.new_game = dec_texto(d),
            0x73 => self.load_game = dec_texto(d),
            0x75 => self.exit_game = dec_texto(d),
            0x7b => self.level = dec_texto(d),
            0x7c => self.health_points = dec_texto(d),
            0x7d => self.spirit_points = dec_texto(d),
            0x7e => self.normal_status = dec_texto(d),
            0x7f => self.exp_short = dec_texto(d),
            0x80 => self.lvl_short = dec_texto(d),
            0x81 => self.hp_short = dec_texto(d),
            0x82 => self.sp_short = dec_texto(d),
            0x83 => self.sp_cost = dec_texto(d),
            0x84 => self.attack = dec_texto(d),
            0x85 => self.defense = dec_texto(d),
            0x86 => self.spirit = dec_texto(d),
            0x87 => self.agility = dec_texto(d),
            0x88 => self.weapon = dec_texto(d),
            0x89 => self.shield = dec_texto(d),
            0x8a => self.armor = dec_texto(d),
            0x8b => self.helmet = dec_texto(d),
            0x8c => self.accessory = dec_texto(d),
            0x92 => self.save_game_message = dec_texto(d),
            0x93 => self.load_game_message = dec_texto(d),
            0x94 => self.file = dec_texto(d),
            0x97 => self.exit_game_message = dec_texto(d),
            0x98 => self.yes = dec_texto(d),
            0x99 => self.no = dec_texto(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Terms::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        c.push((0x01, cod_texto(&self.encounter)));
        c.push((0x02, cod_texto(&self.special_combat)));
        c.push((0x03, cod_texto(&self.escape_success)));
        c.push((0x04, cod_texto(&self.escape_failure)));
        c.push((0x05, cod_texto(&self.victory)));
        c.push((0x06, cod_texto(&self.defeat)));
        c.push((0x07, cod_texto(&self.exp_received)));
        c.push((0x08, cod_texto(&self.gold_recieved_a)));
        c.push((0x09, cod_texto(&self.gold_recieved_b)));
        c.push((0x0a, cod_texto(&self.item_recieved)));
        c.push((0x0b, cod_texto(&self.attacking)));
        c.push((0x0c, cod_texto(&self.enemy_critical)));
        c.push((0x0d, cod_texto(&self.actor_critical)));
        c.push((0x0e, cod_texto(&self.defending)));
        c.push((0x0f, cod_texto(&self.observing)));
        c.push((0x10, cod_texto(&self.focus)));
        c.push((0x11, cod_texto(&self.autodestruction)));
        c.push((0x12, cod_texto(&self.enemy_escape)));
        c.push((0x13, cod_texto(&self.enemy_transform)));
        c.push((0x14, cod_texto(&self.enemy_damaged)));
        c.push((0x15, cod_texto(&self.enemy_undamaged)));
        c.push((0x16, cod_texto(&self.actor_damaged)));
        c.push((0x17, cod_texto(&self.actor_undamaged)));
        c.push((0x18, cod_texto(&self.skill_failure_a)));
        c.push((0x19, cod_texto(&self.skill_failure_b)));
        c.push((0x1a, cod_texto(&self.skill_failure_c)));
        c.push((0x1b, cod_texto(&self.dodge)));
        c.push((0x1c, cod_texto(&self.use_item)));
        c.push((0x1d, cod_texto(&self.hp_recovery)));
        c.push((0x1e, cod_texto(&self.parameter_increase)));
        c.push((0x1f, cod_texto(&self.parameter_decrease)));
        c.push((0x20, cod_texto(&self.enemy_hp_absorbed)));
        c.push((0x21, cod_texto(&self.actor_hp_absorbed)));
        c.push((0x22, cod_texto(&self.resistance_increase)));
        c.push((0x23, cod_texto(&self.resistance_decrease)));
        c.push((0x24, cod_texto(&self.level_up)));
        c.push((0x25, cod_texto(&self.skill_learned)));
        c.push((0x29, cod_texto(&self.shop_greeting1)));
        c.push((0x2a, cod_texto(&self.shop_regreeting1)));
        c.push((0x2b, cod_texto(&self.shop_buy1)));
        c.push((0x2c, cod_texto(&self.shop_sell1)));
        c.push((0x2d, cod_texto(&self.shop_leave1)));
        c.push((0x2e, cod_texto(&self.shop_buy_select1)));
        c.push((0x2f, cod_texto(&self.shop_buy_number1)));
        c.push((0x30, cod_texto(&self.shop_purchased1)));
        c.push((0x31, cod_texto(&self.shop_sell_select1)));
        c.push((0x32, cod_texto(&self.shop_sell_number1)));
        c.push((0x33, cod_texto(&self.shop_sold1)));
        c.push((0x36, cod_texto(&self.shop_greeting2)));
        c.push((0x37, cod_texto(&self.shop_regreeting2)));
        c.push((0x38, cod_texto(&self.shop_buy2)));
        c.push((0x39, cod_texto(&self.shop_sell2)));
        c.push((0x3a, cod_texto(&self.shop_leave2)));
        c.push((0x3b, cod_texto(&self.shop_buy_select2)));
        c.push((0x3c, cod_texto(&self.shop_buy_number2)));
        c.push((0x3d, cod_texto(&self.shop_purchased2)));
        c.push((0x3e, cod_texto(&self.shop_sell_select2)));
        c.push((0x3f, cod_texto(&self.shop_sell_number2)));
        c.push((0x40, cod_texto(&self.shop_sold2)));
        c.push((0x43, cod_texto(&self.shop_greeting3)));
        c.push((0x44, cod_texto(&self.shop_regreeting3)));
        c.push((0x45, cod_texto(&self.shop_buy3)));
        c.push((0x46, cod_texto(&self.shop_sell3)));
        c.push((0x47, cod_texto(&self.shop_leave3)));
        c.push((0x48, cod_texto(&self.shop_buy_select3)));
        c.push((0x49, cod_texto(&self.shop_buy_number3)));
        c.push((0x4a, cod_texto(&self.shop_purchased3)));
        c.push((0x4b, cod_texto(&self.shop_sell_select3)));
        c.push((0x4c, cod_texto(&self.shop_sell_number3)));
        c.push((0x4d, cod_texto(&self.shop_sold3)));
        c.push((0x50, cod_texto(&self.inn_a_greeting_1)));
        c.push((0x51, cod_texto(&self.inn_a_greeting_2)));
        c.push((0x52, cod_texto(&self.inn_a_greeting_3)));
        c.push((0x53, cod_texto(&self.inn_a_accept)));
        c.push((0x54, cod_texto(&self.inn_a_cancel)));
        c.push((0x55, cod_texto(&self.inn_b_greeting_1)));
        c.push((0x56, cod_texto(&self.inn_b_greeting_2)));
        c.push((0x57, cod_texto(&self.inn_b_greeting_3)));
        c.push((0x58, cod_texto(&self.inn_b_accept)));
        c.push((0x59, cod_texto(&self.inn_b_cancel)));
        c.push((0x5c, cod_texto(&self.possessed_items)));
        c.push((0x5d, cod_texto(&self.equipped_items)));
        c.push((0x5f, cod_texto(&self.gold)));
        c.push((0x65, cod_texto(&self.battle_fight)));
        c.push((0x66, cod_texto(&self.battle_auto)));
        c.push((0x67, cod_texto(&self.battle_escape)));
        c.push((0x68, cod_texto(&self.command_attack)));
        c.push((0x69, cod_texto(&self.command_defend)));
        c.push((0x6a, cod_texto(&self.command_item)));
        c.push((0x6b, cod_texto(&self.command_skill)));
        c.push((0x6c, cod_texto(&self.menu_equipment)));
        c.push((0x6e, cod_texto(&self.menu_save)));
        c.push((0x70, cod_texto(&self.menu_quit)));
        c.push((0x72, cod_texto(&self.new_game)));
        c.push((0x73, cod_texto(&self.load_game)));
        c.push((0x75, cod_texto(&self.exit_game)));
        c.push((0x7b, cod_texto(&self.level)));
        c.push((0x7c, cod_texto(&self.health_points)));
        c.push((0x7d, cod_texto(&self.spirit_points)));
        c.push((0x7e, cod_texto(&self.normal_status)));
        c.push((0x7f, cod_texto(&self.exp_short)));
        c.push((0x80, cod_texto(&self.lvl_short)));
        c.push((0x81, cod_texto(&self.hp_short)));
        c.push((0x82, cod_texto(&self.sp_short)));
        c.push((0x83, cod_texto(&self.sp_cost)));
        c.push((0x84, cod_texto(&self.attack)));
        c.push((0x85, cod_texto(&self.defense)));
        c.push((0x86, cod_texto(&self.spirit)));
        c.push((0x87, cod_texto(&self.agility)));
        c.push((0x88, cod_texto(&self.weapon)));
        c.push((0x89, cod_texto(&self.shield)));
        c.push((0x8a, cod_texto(&self.armor)));
        c.push((0x8b, cod_texto(&self.helmet)));
        c.push((0x8c, cod_texto(&self.accessory)));
        c.push((0x92, cod_texto(&self.save_game_message)));
        c.push((0x93, cod_texto(&self.load_game_message)));
        c.push((0x94, cod_texto(&self.file)));
        c.push((0x97, cod_texto(&self.exit_game_message)));
        c.push((0x98, cod_texto(&self.yes)));
        c.push((0x99, cod_texto(&self.no)));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Music {
    const NOMBRE: &'static str = "Music";
    const TERMINADOR: bool = true;
    const CON_ID: bool = false;
    fn id(&self) -> i32 { 0 }
    fn poner_id(&mut self, v: i32) { let _ = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.fadein = dec_ber(d),
            0x03 => self.volume = dec_ber(d),
            0x04 => self.tempo = dec_ber(d),
            0x05 => self.balance = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Music::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        c.push((0x01, cod_texto(&self.name)));
        if self.fadein != p.fadein { c.push((0x02, cod_ber(self.fadein))); }
        if self.volume != p.volume { c.push((0x03, cod_ber(self.volume))); }
        if self.tempo != p.tempo { c.push((0x04, cod_ber(self.tempo))); }
        if self.balance != p.balance { c.push((0x05, cod_ber(self.balance))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for TestBattler {
    const NOMBRE: &'static str = "TestBattler";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.actor_id = dec_ber(d),
            0x02 => self.level = dec_ber(d),
            0x0b => self.weapon_id = dec_ber(d),
            0x0c => self.shield_id = dec_ber(d),
            0x0d => self.armor_id = dec_ber(d),
            0x0e => self.helmet_id = dec_ber(d),
            0x0f => self.accessory_id = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = TestBattler::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.actor_id != p.actor_id { c.push((0x01, cod_ber(self.actor_id))); }
        if self.level != p.level { c.push((0x02, cod_ber(self.level))); }
        if self.weapon_id != p.weapon_id { c.push((0x0b, cod_ber(self.weapon_id))); }
        if self.shield_id != p.shield_id { c.push((0x0c, cod_ber(self.shield_id))); }
        if self.armor_id != p.armor_id { c.push((0x0d, cod_ber(self.armor_id))); }
        if self.helmet_id != p.helmet_id { c.push((0x0e, cod_ber(self.helmet_id))); }
        if self.accessory_id != p.accessory_id { c.push((0x0f, cod_ber(self.accessory_id))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for System {
    const NOMBRE: &'static str = "System";
    const TERMINADOR: bool = true;
    const CON_ID: bool = false;
    fn id(&self) -> i32 { 0 }
    fn poner_id(&mut self, v: i32) { let _ = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x0a => self.ldb_id = dec_ber(d),
            0x0b => self.boat_name = dec_texto(d),
            0x0c => self.ship_name = dec_texto(d),
            0x0d => self.airship_name = dec_texto(d),
            0x0e => self.boat_index = dec_ber(d),
            0x0f => self.ship_index = dec_ber(d),
            0x10 => self.airship_index = dec_ber(d),
            0x11 => self.title_name = dec_texto(d),
            0x12 => self.gameover_name = dec_texto(d),
            0x13 => self.system_name = dec_texto(d),
            0x15 => {} // largo de `party`, se recalcula al escribir
            0x16 => self.party = dec_vec_i16(d),
            0x1f => self.title_music = dec_struct::<Music>(d)?,
            0x20 => self.battle_music = dec_struct::<Music>(d)?,
            0x21 => self.battle_end_music = dec_struct::<Music>(d)?,
            0x22 => self.inn_music = dec_struct::<Music>(d)?,
            0x23 => self.boat_music = dec_struct::<Music>(d)?,
            0x24 => self.ship_music = dec_struct::<Music>(d)?,
            0x25 => self.airship_music = dec_struct::<Music>(d)?,
            0x26 => self.gameover_music = dec_struct::<Music>(d)?,
            0x29 => self.cursor_se = dec_struct::<Sound>(d)?,
            0x2a => self.decision_se = dec_struct::<Sound>(d)?,
            0x2b => self.cancel_se = dec_struct::<Sound>(d)?,
            0x2c => self.buzzer_se = dec_struct::<Sound>(d)?,
            0x2d => self.battle_se = dec_struct::<Sound>(d)?,
            0x2e => self.escape_se = dec_struct::<Sound>(d)?,
            0x2f => self.enemy_attack_se = dec_struct::<Sound>(d)?,
            0x30 => self.enemy_damaged_se = dec_struct::<Sound>(d)?,
            0x31 => self.actor_damaged_se = dec_struct::<Sound>(d)?,
            0x32 => self.dodge_se = dec_struct::<Sound>(d)?,
            0x33 => self.enemy_death_se = dec_struct::<Sound>(d)?,
            0x34 => self.item_se = dec_struct::<Sound>(d)?,
            0x3d => self.transition_out = SystemFadeOut::de_i32(dec_ber(d)),
            0x3e => self.transition_in = SystemFadeIn::de_i32(dec_ber(d)),
            0x3f => self.battle_start_fadeout = SystemFadeOut::de_i32(dec_ber(d)),
            0x40 => self.battle_start_fadein = SystemFadeIn::de_i32(dec_ber(d)),
            0x41 => self.battle_end_fadeout = SystemFadeOut::de_i32(dec_ber(d)),
            0x42 => self.battle_end_fadein = SystemFadeIn::de_i32(dec_ber(d)),
            0x47 => self.message_stretch = SystemStretch::de_i32(dec_ber(d)),
            0x48 => self.font_id = SystemFont::de_i32(dec_ber(d)),
            0x51 => self.selected_condition = dec_ber(d),
            0x52 => self.selected_hero = dec_ber(d),
            0x54 => self.battletest_background = dec_texto(d),
            0x55 => self.battletest_data = dec_array::<TestBattler>(d)?,
            0x5b => self.save_count = dec_ber(d),
            0x5e => self.battletest_terrain = dec_ber(d),
            0x5f => self.battletest_formation = SystemBattleFormation::de_i32(dec_ber(d)),
            0x60 => self.battletest_condition = SystemBattleCondition::de_i32(dec_ber(d)),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = System::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.ldb_id != p.ldb_id { c.push((0x0a, cod_ber(self.ldb_id))); }
        if self.boat_name != p.boat_name { c.push((0x0b, cod_texto(&self.boat_name))); }
        if self.ship_name != p.ship_name { c.push((0x0c, cod_texto(&self.ship_name))); }
        if self.airship_name != p.airship_name { c.push((0x0d, cod_texto(&self.airship_name))); }
        if self.boat_index != p.boat_index { c.push((0x0e, cod_ber(self.boat_index))); }
        if self.ship_index != p.ship_index { c.push((0x0f, cod_ber(self.ship_index))); }
        if self.airship_index != p.airship_index { c.push((0x10, cod_ber(self.airship_index))); }
        if self.title_name != p.title_name { c.push((0x11, cod_texto(&self.title_name))); }
        if self.gameover_name != p.gameover_name { c.push((0x12, cod_texto(&self.gameover_name))); }
        if self.system_name != p.system_name { c.push((0x13, cod_texto(&self.system_name))); }
        let v_party = cod_vec_i16(&self.party);
        if self.party.len() != p.party.len() { c.push((0x15, cod_ber(self.party.len() as i32))); }
        c.push((0x16, v_party));
        c.push((0x1f, cod_struct(&self.title_music)?));
        c.push((0x20, cod_struct(&self.battle_music)?));
        c.push((0x21, cod_struct(&self.battle_end_music)?));
        c.push((0x22, cod_struct(&self.inn_music)?));
        c.push((0x23, cod_struct(&self.boat_music)?));
        c.push((0x24, cod_struct(&self.ship_music)?));
        c.push((0x25, cod_struct(&self.airship_music)?));
        c.push((0x26, cod_struct(&self.gameover_music)?));
        c.push((0x29, cod_struct(&self.cursor_se)?));
        c.push((0x2a, cod_struct(&self.decision_se)?));
        c.push((0x2b, cod_struct(&self.cancel_se)?));
        c.push((0x2c, cod_struct(&self.buzzer_se)?));
        c.push((0x2d, cod_struct(&self.battle_se)?));
        c.push((0x2e, cod_struct(&self.escape_se)?));
        c.push((0x2f, cod_struct(&self.enemy_attack_se)?));
        c.push((0x30, cod_struct(&self.enemy_damaged_se)?));
        c.push((0x31, cod_struct(&self.actor_damaged_se)?));
        c.push((0x32, cod_struct(&self.dodge_se)?));
        c.push((0x33, cod_struct(&self.enemy_death_se)?));
        c.push((0x34, cod_struct(&self.item_se)?));
        c.push((0x3d, cod_ber(self.transition_out.a_i32())));
        c.push((0x3e, cod_ber(self.transition_in.a_i32())));
        c.push((0x3f, cod_ber(self.battle_start_fadeout.a_i32())));
        c.push((0x40, cod_ber(self.battle_start_fadein.a_i32())));
        c.push((0x41, cod_ber(self.battle_end_fadeout.a_i32())));
        c.push((0x42, cod_ber(self.battle_end_fadein.a_i32())));
        if self.message_stretch != p.message_stretch { c.push((0x47, cod_ber(self.message_stretch.a_i32()))); }
        if self.font_id != p.font_id { c.push((0x48, cod_ber(self.font_id.a_i32()))); }
        if self.selected_condition != p.selected_condition { c.push((0x51, cod_ber(self.selected_condition))); }
        c.push((0x52, cod_ber(self.selected_hero)));
        if self.battletest_background != p.battletest_background { c.push((0x54, cod_texto(&self.battletest_background))); }
        c.push((0x55, cod_array(&self.battletest_data)?));
        if self.save_count != p.save_count { c.push((0x5b, cod_ber(self.save_count))); }
        if self.battletest_terrain != p.battletest_terrain { c.push((0x5e, cod_ber(self.battletest_terrain))); }
        if self.battletest_formation != p.battletest_formation { c.push((0x5f, cod_ber(self.battletest_formation.a_i32()))); }
        if self.battletest_condition != p.battletest_condition { c.push((0x60, cod_ber(self.battletest_condition.a_i32()))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Switch {
    const NOMBRE: &'static str = "Switch";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Switch::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Variable {
    const NOMBRE: &'static str = "Variable";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Variable::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Database {
    const NOMBRE: &'static str = "Database";
    const TERMINADOR: bool = false;
    const CON_ID: bool = false;
    fn id(&self) -> i32 { 0 }
    fn poner_id(&mut self, v: i32) { let _ = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x0b => self.actors = dec_array::<Actor>(d)?,
            0x0c => self.skills = dec_array::<Skill>(d)?,
            0x0d => self.items = dec_array::<Item>(d)?,
            0x0e => self.enemies = dec_array::<Enemy>(d)?,
            0x0f => self.troops = dec_array::<Troop>(d)?,
            0x10 => self.terrains = dec_array::<Terrain>(d)?,
            0x11 => self.attributes = dec_array::<Attribute>(d)?,
            0x12 => self.states = dec_array::<State>(d)?,
            0x13 => self.animations = dec_array::<Animation>(d)?,
            0x14 => self.chipsets = dec_array::<Chipset>(d)?,
            0x15 => self.terms = dec_struct::<Terms>(d)?,
            0x16 => self.system = dec_struct::<System>(d)?,
            0x17 => self.switches = dec_array::<Switch>(d)?,
            0x18 => self.variables = dec_array::<Variable>(d)?,
            0x19 => self.commonevents = dec_array::<CommonEvent>(d)?,
            0x1a => self.version = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Database::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        c.push((0x0b, cod_array(&self.actors)?));
        c.push((0x0c, cod_array(&self.skills)?));
        c.push((0x0d, cod_array(&self.items)?));
        c.push((0x0e, cod_array(&self.enemies)?));
        c.push((0x0f, cod_array(&self.troops)?));
        c.push((0x10, cod_array(&self.terrains)?));
        c.push((0x11, cod_array(&self.attributes)?));
        c.push((0x12, cod_array(&self.states)?));
        c.push((0x13, cod_array(&self.animations)?));
        c.push((0x14, cod_array(&self.chipsets)?));
        c.push((0x15, cod_struct(&self.terms)?));
        c.push((0x16, cod_struct(&self.system)?));
        c.push((0x17, cod_array(&self.switches)?));
        c.push((0x18, cod_array(&self.variables)?));
        c.push((0x19, cod_array(&self.commonevents)?));
        if self.version != p.version { c.push((0x1a, cod_ber(self.version))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for EventPageCondition {
    const NOMBRE: &'static str = "EventPageCondition";
    const TERMINADOR: bool = true;
    const CON_ID: bool = false;
    fn id(&self) -> i32 { 0 }
    fn poner_id(&mut self, v: i32) { let _ = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.flags = EventPageConditionFlags::leer(d),
            0x02 => self.switch_a_id = dec_ber(d),
            0x03 => self.switch_b_id = dec_ber(d),
            0x04 => self.variable_id = dec_ber(d),
            0x05 => self.variable_value = dec_ber(d),
            0x06 => self.item_id = dec_ber(d),
            0x07 => self.actor_id = dec_ber(d),
            0x08 => self.timer_sec = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = EventPageCondition::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        c.push((0x01, self.flags.escribir()));
        if self.switch_a_id != p.switch_a_id { c.push((0x02, cod_ber(self.switch_a_id))); }
        if self.switch_b_id != p.switch_b_id { c.push((0x03, cod_ber(self.switch_b_id))); }
        if self.variable_id != p.variable_id { c.push((0x04, cod_ber(self.variable_id))); }
        if self.variable_value != p.variable_value { c.push((0x05, cod_ber(self.variable_value))); }
        if self.item_id != p.item_id { c.push((0x06, cod_ber(self.item_id))); }
        c.push((0x07, cod_ber(self.actor_id)));
        if self.timer_sec != p.timer_sec { c.push((0x08, cod_ber(self.timer_sec))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for MoveRoute {
    const NOMBRE: &'static str = "MoveRoute";
    const TERMINADOR: bool = true;
    const CON_ID: bool = false;
    fn id(&self) -> i32 { 0 }
    fn poner_id(&mut self, v: i32) { let _ = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x0b => {} // largo de `move_commands`, se recalcula al escribir
            0x0c => self.move_commands = dec_comandos_ruta(d)?,
            0x15 => self.repeat = dec_bool(d),
            0x16 => self.skippable = dec_bool(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = MoveRoute::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        let v_move_commands = cod_comandos_ruta(&self.move_commands);
        if v_move_commands.len() != cod_comandos_ruta(&p.move_commands).len() { c.push((0x0b, cod_ber(v_move_commands.len() as i32))); }
        c.push((0x0c, v_move_commands));
        if self.repeat != p.repeat { c.push((0x15, cod_bool(self.repeat))); }
        if self.skippable != p.skippable { c.push((0x16, cod_bool(self.skippable))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for EventPage {
    const NOMBRE: &'static str = "EventPage";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x02 => self.condition = dec_struct::<EventPageCondition>(d)?,
            0x15 => self.character_name = dec_texto(d),
            0x16 => self.character_index = dec_ber(d),
            0x17 => self.character_direction = EventPageDirection::de_i32(dec_ber(d)),
            0x18 => self.character_pattern = EventPageFrame::de_i32(dec_ber(d)),
            0x19 => self.translucent = dec_bool(d),
            0x1f => self.move_type = EventPageMoveType::de_i32(dec_ber(d)),
            0x20 => self.move_frequency = dec_ber(d),
            0x21 => self.trigger = EventPageTrigger::de_i32(dec_ber(d)),
            0x22 => self.layer = EventPageLayers::de_i32(dec_ber(d)),
            0x23 => self.overlap_forbidden = dec_bool(d),
            0x24 => self.animation_type = EventPageAnimType::de_i32(dec_ber(d)),
            0x25 => self.move_speed = EventPageMoveSpeed::de_i32(dec_ber(d)),
            0x29 => self.move_route = dec_struct::<MoveRoute>(d)?,
            0x33 => {} // largo de `event_commands`, se recalcula al escribir
            0x34 => self.event_commands = dec_comandos_evento(d)?,
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = EventPage::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        c.push((0x02, cod_struct(&self.condition)?));
        if self.character_name != p.character_name { c.push((0x15, cod_texto(&self.character_name))); }
        if self.character_index != p.character_index { c.push((0x16, cod_ber(self.character_index))); }
        c.push((0x17, cod_ber(self.character_direction.a_i32())));
        if self.character_pattern != p.character_pattern { c.push((0x18, cod_ber(self.character_pattern.a_i32()))); }
        c.push((0x19, cod_bool(self.translucent)));
        c.push((0x1f, cod_ber(self.move_type.a_i32())));
        if self.move_frequency != p.move_frequency { c.push((0x20, cod_ber(self.move_frequency))); }
        c.push((0x21, cod_ber(self.trigger.a_i32())));
        c.push((0x22, cod_ber(self.layer.a_i32())));
        c.push((0x23, cod_bool(self.overlap_forbidden)));
        c.push((0x24, cod_ber(self.animation_type.a_i32())));
        if self.move_speed != p.move_speed { c.push((0x25, cod_ber(self.move_speed.a_i32()))); }
        c.push((0x29, cod_struct(&self.move_route)?));
        let v_event_commands = cod_comandos_evento(&self.event_commands);
        c.push((0x33, cod_ber(v_event_commands.len() as i32)));
        c.push((0x34, v_event_commands));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Event {
    const NOMBRE: &'static str = "Event";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.x = dec_ber(d),
            0x03 => self.y = dec_ber(d),
            0x05 => self.pages = dec_array::<EventPage>(d)?,
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Event::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        if self.x != p.x { c.push((0x02, cod_ber(self.x))); }
        if self.y != p.y { c.push((0x03, cod_ber(self.y))); }
        c.push((0x05, cod_array(&self.pages)?));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Map {
    const NOMBRE: &'static str = "Map";
    const TERMINADOR: bool = true;
    const CON_ID: bool = false;
    fn id(&self) -> i32 { 0 }
    fn poner_id(&mut self, v: i32) { let _ = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.chipset_id = dec_ber(d),
            0x02 => self.width = dec_ber(d),
            0x03 => self.height = dec_ber(d),
            0x0b => self.scroll_type = MapScrollType::de_i32(dec_ber(d)),
            0x1f => self.parallax_flag = dec_bool(d),
            0x20 => self.parallax_name = dec_texto(d),
            0x21 => self.parallax_loop_x = dec_bool(d),
            0x22 => self.parallax_loop_y = dec_bool(d),
            0x23 => self.parallax_auto_loop_x = dec_bool(d),
            0x24 => self.parallax_sx = dec_ber(d),
            0x25 => self.parallax_auto_loop_y = dec_bool(d),
            0x26 => self.parallax_sy = dec_ber(d),
            0x28 => self.generator_flag = dec_bool(d),
            0x29 => self.generator_mode = MapGeneratorMode::de_i32(dec_ber(d)),
            0x2a => self.top_level = dec_bool(d),
            0x30 => self.generator_tiles = MapGeneratorTiles::de_i32(dec_ber(d)),
            0x31 => self.generator_width = dec_ber(d),
            0x32 => self.generator_height = dec_ber(d),
            0x33 => self.generator_surround = dec_bool(d),
            0x34 => self.generator_upper_wall = dec_bool(d),
            0x35 => self.generator_floor_b = dec_bool(d),
            0x36 => self.generator_floor_c = dec_bool(d),
            0x37 => self.generator_extra_b = dec_bool(d),
            0x38 => self.generator_extra_c = dec_bool(d),
            0x3c => self.generator_x = dec_vec_u32(d),
            0x3d => self.generator_y = dec_vec_u32(d),
            0x3e => self.generator_tile_ids = dec_vec_i16(d),
            0x47 => self.lower_layer = dec_vec_i16(d),
            0x48 => self.upper_layer = dec_vec_i16(d),
            0x51 => self.events = dec_array::<Event>(d)?,
            0x5b => self.save_count = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Map::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.chipset_id != p.chipset_id { c.push((0x01, cod_ber(self.chipset_id))); }
        if self.width != p.width { c.push((0x02, cod_ber(self.width))); }
        if self.height != p.height { c.push((0x03, cod_ber(self.height))); }
        c.push((0x0b, cod_ber(self.scroll_type.a_i32())));
        if self.parallax_flag != p.parallax_flag { c.push((0x1f, cod_bool(self.parallax_flag))); }
        if self.parallax_name != p.parallax_name { c.push((0x20, cod_texto(&self.parallax_name))); }
        if self.parallax_loop_x != p.parallax_loop_x { c.push((0x21, cod_bool(self.parallax_loop_x))); }
        if self.parallax_loop_y != p.parallax_loop_y { c.push((0x22, cod_bool(self.parallax_loop_y))); }
        if self.parallax_auto_loop_x != p.parallax_auto_loop_x { c.push((0x23, cod_bool(self.parallax_auto_loop_x))); }
        if self.parallax_sx != p.parallax_sx { c.push((0x24, cod_ber(self.parallax_sx))); }
        if self.parallax_auto_loop_y != p.parallax_auto_loop_y { c.push((0x25, cod_bool(self.parallax_auto_loop_y))); }
        if self.parallax_sy != p.parallax_sy { c.push((0x26, cod_ber(self.parallax_sy))); }
        if self.generator_flag != p.generator_flag { c.push((0x28, cod_bool(self.generator_flag))); }
        if self.generator_mode != p.generator_mode { c.push((0x29, cod_ber(self.generator_mode.a_i32()))); }
        if self.top_level != p.top_level { c.push((0x2a, cod_bool(self.top_level))); }
        if self.generator_tiles != p.generator_tiles { c.push((0x30, cod_ber(self.generator_tiles.a_i32()))); }
        if self.generator_width != p.generator_width { c.push((0x31, cod_ber(self.generator_width))); }
        if self.generator_height != p.generator_height { c.push((0x32, cod_ber(self.generator_height))); }
        if self.generator_surround != p.generator_surround { c.push((0x33, cod_bool(self.generator_surround))); }
        if self.generator_upper_wall != p.generator_upper_wall { c.push((0x34, cod_bool(self.generator_upper_wall))); }
        if self.generator_floor_b != p.generator_floor_b { c.push((0x35, cod_bool(self.generator_floor_b))); }
        if self.generator_floor_c != p.generator_floor_c { c.push((0x36, cod_bool(self.generator_floor_c))); }
        if self.generator_extra_b != p.generator_extra_b { c.push((0x37, cod_bool(self.generator_extra_b))); }
        if self.generator_extra_c != p.generator_extra_c { c.push((0x38, cod_bool(self.generator_extra_c))); }
        if self.generator_x != p.generator_x { c.push((0x3c, cod_vec_u32(&self.generator_x))); }
        if self.generator_y != p.generator_y { c.push((0x3d, cod_vec_u32(&self.generator_y))); }
        if self.generator_tile_ids != p.generator_tile_ids { c.push((0x3e, cod_vec_i16(&self.generator_tile_ids))); }
        c.push((0x47, cod_vec_i16(&self.lower_layer)));
        c.push((0x48, cod_vec_i16(&self.upper_layer)));
        c.push((0x51, cod_array(&self.events)?));
        if self.save_count != p.save_count { c.push((0x5b, cod_ber(self.save_count))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Encounter {
    const NOMBRE: &'static str = "Encounter";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.troop_id = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Encounter::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.troop_id != p.troop_id { c.push((0x01, cod_ber(self.troop_id))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for MapInfo {
    const NOMBRE: &'static str = "MapInfo";
    const TERMINADOR: bool = true;
    const CON_ID: bool = true;
    fn id(&self) -> i32 { self.id }
    fn poner_id(&mut self, v: i32) { self.id = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.name = dec_texto(d),
            0x02 => self.parent_map = dec_ber(d),
            0x03 => self.indentation = dec_ber(d),
            0x04 => self.r#type = TreeMapMapType::de_i32(dec_ber(d)),
            0x05 => self.scrollbar_x = dec_ber(d),
            0x06 => self.scrollbar_y = dec_ber(d),
            0x07 => self.expanded_node = dec_bool(d),
            0x0b => self.music_type = MapInfoMusicType::de_i32(dec_ber(d)),
            0x0c => self.music = dec_struct::<Music>(d)?,
            0x15 => self.background_type = MapInfoBGMType::de_i32(dec_ber(d)),
            0x16 => self.background_name = dec_texto(d),
            0x1f => self.teleport = MapInfoTriState::de_i32(dec_ber(d)),
            0x20 => self.escape = MapInfoTriState::de_i32(dec_ber(d)),
            0x21 => self.save = MapInfoTriState::de_i32(dec_ber(d)),
            0x29 => self.encounters = dec_array::<Encounter>(d)?,
            0x2c => self.encounter_steps = dec_ber(d),
            0x33 => self.area_rect = Rect::leer_crudo(d)?,
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = MapInfo::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.name != p.name { c.push((0x01, cod_texto(&self.name))); }
        if self.parent_map != p.parent_map { c.push((0x02, cod_ber(self.parent_map))); }
        if self.indentation != p.indentation { c.push((0x03, cod_ber(self.indentation))); }
        if self.r#type != p.r#type { c.push((0x04, cod_ber(self.r#type.a_i32()))); }
        if self.scrollbar_x != p.scrollbar_x { c.push((0x05, cod_ber(self.scrollbar_x))); }
        if self.scrollbar_y != p.scrollbar_y { c.push((0x06, cod_ber(self.scrollbar_y))); }
        if self.expanded_node != p.expanded_node { c.push((0x07, cod_bool(self.expanded_node))); }
        c.push((0x0b, cod_ber(self.music_type.a_i32())));
        c.push((0x0c, cod_struct(&self.music)?));
        c.push((0x15, cod_ber(self.background_type.a_i32())));
        if self.background_name != p.background_name { c.push((0x16, cod_texto(&self.background_name))); }
        c.push((0x1f, cod_ber(self.teleport.a_i32())));
        c.push((0x20, cod_ber(self.escape.a_i32())));
        c.push((0x21, cod_ber(self.save.a_i32())));
        c.push((0x29, cod_array(&self.encounters)?));
        if self.encounter_steps != p.encounter_steps { c.push((0x2c, cod_ber(self.encounter_steps))); }
        c.push((0x33, self.area_rect.escribir_crudo()));
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

impl Chunked for Start {
    const NOMBRE: &'static str = "Start";
    const TERMINADOR: bool = true;
    const CON_ID: bool = false;
    fn id(&self) -> i32 { 0 }
    fn poner_id(&mut self, v: i32) { let _ = v; }
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> { &mut self.desconocidos }
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {
        match id {
            0x01 => self.party_map_id = dec_ber(d),
            0x02 => self.party_x = dec_ber(d),
            0x03 => self.party_y = dec_ber(d),
            0x0b => self.boat_map_id = dec_ber(d),
            0x0c => self.boat_x = dec_ber(d),
            0x0d => self.boat_y = dec_ber(d),
            0x15 => self.ship_map_id = dec_ber(d),
            0x16 => self.ship_x = dec_ber(d),
            0x17 => self.ship_y = dec_ber(d),
            0x1f => self.airship_map_id = dec_ber(d),
            0x20 => self.airship_x = dec_ber(d),
            0x21 => self.airship_y = dec_ber(d),
            _ => return Ok(false),
        }
        Ok(true)
    }
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {
        let p = Start::default();
        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();
        if self.party_map_id != p.party_map_id { c.push((0x01, cod_ber(self.party_map_id))); }
        if self.party_x != p.party_x { c.push((0x02, cod_ber(self.party_x))); }
        if self.party_y != p.party_y { c.push((0x03, cod_ber(self.party_y))); }
        if self.boat_map_id != p.boat_map_id { c.push((0x0b, cod_ber(self.boat_map_id))); }
        if self.boat_x != p.boat_x { c.push((0x0c, cod_ber(self.boat_x))); }
        if self.boat_y != p.boat_y { c.push((0x0d, cod_ber(self.boat_y))); }
        if self.ship_map_id != p.ship_map_id { c.push((0x15, cod_ber(self.ship_map_id))); }
        if self.ship_x != p.ship_x { c.push((0x16, cod_ber(self.ship_x))); }
        if self.ship_y != p.ship_y { c.push((0x17, cod_ber(self.ship_y))); }
        if self.airship_map_id != p.airship_map_id { c.push((0x1f, cod_ber(self.airship_map_id))); }
        if self.airship_x != p.airship_x { c.push((0x20, cod_ber(self.airship_x))); }
        if self.airship_y != p.airship_y { c.push((0x21, cod_ber(self.airship_y))); }
        e.volcar(c, &self.desconocidos);
        Ok(())
    }
}

