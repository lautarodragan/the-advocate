//! The 65816, as much of it as the checks need: each opcode's mnemonic and
//! addressing mode, how long it is with each register width, and what it does
//! to the flags, the widths and the stack.

/// Addressing modes. `ImmM` and `ImmX` are the immediates whose size follows
/// the width of A or of X/Y; `AbsInd` is `jmp (abs)`, `AbsIndLong` is
/// `jml [abs]` and `AbsIndX` is `jmp`/`jsr (abs, x)`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    Imp,
    Imm8,
    ImmM,
    ImmX,
    Rel,
    RelLong,
    Sr,
    SrIndY,
    Dp,
    DpX,
    DpY,
    DpInd,
    DpIndLong,
    DpIndX,
    DpIndY,
    DpIndLongY,
    Abs,
    AbsX,
    AbsY,
    AbsInd,
    AbsIndLong,
    AbsIndX,
    Long,
    LongX,
    BlockMove,
}

use Mode::*;

const MNEMONICS: &str = "
brk ora cop ora tsb ora asl ora php ora asl phd tsb ora asl ora
bpl ora ora ora trb ora asl ora clc ora inc tcs trb ora asl ora
jsr and jsl and bit and rol and plp and rol pld bit and rol and
bmi and and and bit and rol and sec and dec tsc bit and rol and
rti eor wdm eor mvp eor lsr eor pha eor lsr phk jmp eor lsr eor
bvc eor eor eor mvn eor lsr eor cli eor phy tcd jml eor lsr eor
rts adc per adc stz adc ror adc pla adc ror rtl jmp adc ror adc
bvs adc adc adc stz adc ror adc sei adc ply tdc jmp adc ror adc
bra sta brl sta sty sta stx sta dey bit txa phb sty sta stx sta
bcc sta sta sta sty sta stx sta tya sta txs txy stz sta stz sta
ldy lda ldx lda ldy lda ldx lda tay lda tax plb ldy lda ldx lda
bcs lda lda lda ldy lda ldx lda clv lda tsx tyx ldy lda ldx lda
cpy cmp rep cmp cpy cmp dec cmp iny cmp dex wai cpy cmp dec cmp
bne cmp cmp cmp pei cmp dec cmp cld cmp phx stp jml cmp dec cmp
cpx sbc sep sbc cpx sbc inc sbc inx sbc nop xba cpx sbc inc sbc
beq sbc sbc sbc pea sbc inc sbc sed sbc plx xce jsr sbc inc sbc
";

/// The mode of each opcode, sixteen to a row.
const MODES: [Mode; 256] = [
    Imm8, DpIndX, Imm8, Sr, Dp, Dp, Dp, DpIndLong, Imp, ImmM, Imp, Imp, Abs, Abs, Abs, Long,
    Rel, DpIndY, DpInd, SrIndY, Dp, DpX, DpX, DpIndLongY, Imp, AbsY, Imp, Imp, Abs, AbsX, AbsX, LongX,
    Abs, DpIndX, Long, Sr, Dp, Dp, Dp, DpIndLong, Imp, ImmM, Imp, Imp, Abs, Abs, Abs, Long,
    Rel, DpIndY, DpInd, SrIndY, DpX, DpX, DpX, DpIndLongY, Imp, AbsY, Imp, Imp, AbsX, AbsX, AbsX, LongX,
    Imp, DpIndX, Imm8, Sr, BlockMove, Dp, Dp, DpIndLong, Imp, ImmM, Imp, Imp, Abs, Abs, Abs, Long,
    Rel, DpIndY, DpInd, SrIndY, BlockMove, DpX, DpX, DpIndLongY, Imp, AbsY, Imp, Imp, Long, AbsX, AbsX, LongX,
    Imp, DpIndX, RelLong, Sr, Dp, Dp, Dp, DpIndLong, Imp, ImmM, Imp, Imp, AbsInd, Abs, Abs, Long,
    Rel, DpIndY, DpInd, SrIndY, DpX, DpX, DpX, DpIndLongY, Imp, AbsY, Imp, Imp, AbsIndX, AbsX, AbsX, LongX,
    Rel, DpIndX, RelLong, Sr, Dp, Dp, Dp, DpIndLong, Imp, ImmM, Imp, Imp, Abs, Abs, Abs, Long,
    Rel, DpIndY, DpInd, SrIndY, DpX, DpX, DpY, DpIndLongY, Imp, AbsY, Imp, Imp, Abs, AbsX, AbsX, LongX,
    ImmX, DpIndX, ImmX, Sr, Dp, Dp, Dp, DpIndLong, Imp, ImmM, Imp, Imp, Abs, Abs, Abs, Long,
    Rel, DpIndY, DpInd, SrIndY, DpX, DpX, DpY, DpIndLongY, Imp, AbsY, Imp, Imp, AbsX, AbsX, AbsY, LongX,
    ImmX, DpIndX, Imm8, Sr, Dp, Dp, Dp, DpIndLong, Imp, ImmM, Imp, Imp, Abs, Abs, Abs, Long,
    Rel, DpIndY, DpInd, SrIndY, Dp, DpX, DpX, DpIndLongY, Imp, AbsY, Imp, Imp, AbsIndLong, AbsX, AbsX, LongX,
    ImmX, DpIndX, Imm8, Sr, Dp, Dp, Dp, DpIndLong, Imp, ImmM, Imp, Imp, Abs, Abs, Abs, Long,
    Rel, DpIndY, DpInd, SrIndY, Abs, DpX, DpX, DpIndLongY, Imp, AbsY, Imp, Imp, AbsIndX, AbsX, AbsX, LongX,
];

pub fn mnemonic(op: u8) -> &'static str {
    let i = op as usize * 4 + 1;
    &MNEMONICS[i..i + 3]
}

pub fn mode(op: u8) -> Mode {
    MODES[op as usize]
}

/// How many bytes the instruction takes, with A and X/Y 8 bits wide or not.
pub fn length(op: u8, m8: bool, x8: bool) -> u32 {
    match mode(op) {
        Imp => 1,
        ImmM => if m8 { 2 } else { 3 },
        ImmX => if x8 { 2 } else { 3 },
        Imm8 | Rel | Sr | SrIndY | Dp | DpX | DpY | DpInd | DpIndLong | DpIndX | DpIndY
        | DpIndLongY => 2,
        Abs | AbsX | AbsY | AbsInd | AbsIndLong | AbsIndX | RelLong | BlockMove => 3,
        Long | LongX => 4,
    }
}

/// The lengths the instruction can have, with any width.
pub fn lengths(op: u8) -> &'static [u32] {
    match mode(op) {
        ImmM | ImmX => &[2, 3],
        _ => match length(op, true, true) {
            1 => &[1],
            2 => &[2],
            3 => &[3],
            _ => &[4],
        },
    }
}

pub const N: u8 = 0x80;
pub const V: u8 = 0x40;
pub const Z: u8 = 0x02;
pub const C: u8 = 0x01;

/// The flags of N, V, Z and C an instruction writes. `rep` and `sep` write
/// the ones in their operand, which is passed in `imm`.
pub fn writes_flags(op: u8, imm: u8) -> u8 {
    match mnemonic(op) {
        "lda" | "ldx" | "ldy" | "ora" | "and" | "eor" | "inc" | "dec" | "inx" | "iny"
        | "dex" | "dey" | "tax" | "tay" | "txa" | "tya" | "txy" | "tyx" | "tsx" | "tsc"
        | "tdc" | "tcd" | "pla" | "plx" | "ply" | "plb" | "pld" | "xba" => N | Z,
        "asl" | "lsr" | "rol" | "ror" | "cmp" | "cpx" | "cpy" => N | Z | C,
        "adc" | "sbc" => N | V | Z | C,
        "bit" => if mode(op) == ImmM { Z } else { N | V | Z },
        "tsb" | "trb" => Z,
        "clc" | "sec" | "xce" => C,
        "clv" => V,
        "plp" | "rti" => N | V | Z | C,
        "rep" | "sep" => imm & (N | V | Z | C),
        _ => 0,
    }
}

/// The flag a conditional branch looks at, or None if it is not one.
pub fn branch_flag(op: u8) -> Option<u8> {
    match mnemonic(op) {
        "beq" | "bne" => Some(Z),
        "bpl" | "bmi" => Some(N),
        "bcc" | "bcs" => Some(C),
        "bvc" | "bvs" => Some(V),
        _ => None,
    }
}

pub fn flag_name(flag: u8) -> &'static str {
    match flag {
        N => "N",
        V => "V",
        Z => "Z",
        _ => "C",
    }
}

/// The pulls, and which flags each one leaves from what it pulled.
pub fn pull_flags(op: u8) -> u8 {
    match mnemonic(op) {
        "pla" | "plx" | "ply" | "plb" | "pld" => N | Z,
        "plp" => N | V | Z | C,
        _ => 0,
    }
}

/// Which register's width an instruction's behaviour depends on: `'m'` for
/// A and memory, `'x'` for the index registers, or neither.
pub fn width_of(op: u8) -> Option<char> {
    match mnemonic(op) {
        "lda" | "sta" | "adc" | "sbc" | "and" | "ora" | "eor" | "cmp" | "bit" | "stz"
        | "tsb" | "trb" | "asl" | "lsr" | "rol" | "ror" | "pha" | "pla" | "txa" | "tya" => {
            Some('m')
        }
        // `inc`/`dec` of A or of memory, not `inx` and the like.
        "inc" | "dec" => Some('m'),
        "ldx" | "ldy" | "stx" | "sty" | "cpx" | "cpy" | "inx" | "iny" | "dex" | "dey"
        | "phx" | "phy" | "plx" | "ply" | "tax" | "tay" | "txy" | "tyx" | "tsx" => Some('x'),
        _ => None,
    }
}

/// The opcodes the walks treat specially.
pub const JSR: u8 = 0x20;
pub const JSL: u8 = 0x22;
pub const JSR_X: u8 = 0xFC;
pub const JMP: u8 = 0x4C;
pub const JML: u8 = 0x5C;
pub const JMP_IND: u8 = 0x6C;
pub const JMP_X: u8 = 0x7C;
pub const JML_IND: u8 = 0xDC;
pub const BRA: u8 = 0x80;
pub const BRL: u8 = 0x82;
pub const RTS: u8 = 0x60;
pub const RTL: u8 = 0x6B;
pub const RTI: u8 = 0x40;
pub const REP: u8 = 0xC2;
pub const SEP: u8 = 0xE2;
pub const PLP: u8 = 0x28;
pub const PHP: u8 = 0x08;
pub const XCE: u8 = 0xFB;
pub const TCS: u8 = 0x1B;
pub const TXS: u8 = 0x9A;

/// What an instruction does to the stack: bytes pushed (positive) or pulled
/// (negative), when it does not depend on a width; `'m'` or `'x'` when its
/// size is the width of that register.
pub enum StackEffect {
    None,
    Push(u8),
    Pull(u8),
    PushWidth(char),
    PullWidth(char),
}

pub fn stack_effect(op: u8) -> StackEffect {
    use StackEffect::*;
    match mnemonic(op) {
        "pha" => PushWidth('m'),
        "phx" | "phy" => PushWidth('x'),
        "pla" => PullWidth('m'),
        "plx" | "ply" => PullWidth('x'),
        "php" | "phb" | "phk" => Push(1),
        "phd" | "pea" | "pei" | "per" => Push(2),
        "plp" | "plb" => Pull(1),
        "pld" => Pull(2),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_table_lines_up() {
        assert_eq!(MNEMONICS.split_whitespace().count(), 256);
        assert_eq!(mnemonic(0x00), "brk");
        assert_eq!(mnemonic(0x22), "jsl");
        assert_eq!(mnemonic(0x6B), "rtl");
        assert_eq!(mnemonic(0xA9), "lda");
        assert_eq!(mnemonic(0xFA), "plx");
        assert_eq!(mnemonic(0xFF), "sbc");
        assert_eq!(length(0xA9, true, true), 2);
        assert_eq!(length(0xA9, false, true), 3);
        assert_eq!(length(0xA2, true, false), 3);
        assert_eq!(length(0x22, true, true), 4);
        assert_eq!(length(0xF4, true, true), 3); // pea
        assert_eq!(length(0xD4, true, true), 2); // pei
    }
}
