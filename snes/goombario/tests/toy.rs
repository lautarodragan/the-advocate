//! Each check, on toy programs assembled and linked here with `ca65` and
//! `ld65`. Without them on the PATH these tests are skipped, saying so.

use std::path::{Path, PathBuf};
use std::process::Command;

use goombario::allow::Annotation;
use goombario::{Check, Report};

/// Two banks of 32 KB, one after the other in the file: `CODE` in bank 0
/// and `FAR` in bank 1, like a LoROM cartridge.
const CONFIG: &str = r#"
MEMORY {
    ROM0: start = $008000, size = $7FE0, fill = yes, file = %O;
    VEC:  start = $00FFE0, size = $0020, fill = yes, file = %O;
    ROM1: start = $018000, size = $8000, fill = yes, file = %O;
}
SEGMENTS {
    CODE:    load = ROM0, type = ro;
    VECTORS: load = VEC, type = ro;
    FAR:     load = ROM1, type = ro;
}
"#;

const HEADER: &str = ".p816\n.smart\n.segment \"CODE\"\n.a8\n.i16\n";

fn tool(name: &str) -> bool {
    Command::new(name).arg("--version").output().is_ok()
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("goombario-test-{}-{}", std::process::id(), name));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// Assembles and links `source`, and lints it. None if `ca65` or `ld65` is
/// missing.
fn lint(name: &str, source: &str) -> Option<Vec<Report>> {
    lint_annotated(name, source).map(|(reports, _, _)| reports)
}

/// The same, and the annotations in the source with the ones that are
/// wrong.
fn lint_annotated(name: &str, source: &str) -> Option<(Vec<Report>, Vec<Annotation>, Vec<String>)> {
    if !tool("ca65") || !tool("ld65") {
        eprintln!("skipped: ca65 and ld65 are not on the PATH");
        return None;
    }
    let dir = scratch(name);
    // `main` is where the reset vector points: the walks start from it.
    let vectors = ".segment \"VECTORS\"\n.res 28\n.addr main\n.res 2\n";
    std::fs::write(
        dir.join("toy.s"),
        format!("{}{}{}", HEADER, source, vectors),
    )
    .unwrap();
    std::fs::write(dir.join("toy.cfg"), CONFIG).unwrap();
    let run = |cmd: &mut Command| {
        let out = cmd.current_dir(&dir).output().unwrap();
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
    };
    run(Command::new("ca65").args(["-g", "-o", "toy.o", "toy.s"]));
    run(Command::new("ld65").args([
        "-C",
        "toy.cfg",
        "--dbgfile",
        "toy.sfc.dbg",
        "-o",
        "toy.sfc",
        "toy.o",
    ]));
    let program = goombario::load(&dir.join("toy.sfc"), &dir.join("toy.sfc.dbg"), &dir).unwrap();
    assert!(program.undecoded.is_empty(), "{:?}", program.undecoded);
    assert!(
        program.missing_sources().is_empty(),
        "{:?}",
        program.missing_sources()
    );
    let (reports, _) = goombario::lint(&program, &dir);
    let (annotations, wrong) = goombario::annotations(&program, &dir, |_| true);
    let _ = std::fs::remove_dir_all(&dir);
    Some((reports, annotations, wrong))
}

fn found(reports: &[Report], check: Check) -> Vec<(String, String)> {
    let mut v: Vec<_> = reports
        .iter()
        .filter(|r| r.check == check)
        .map(|r| (r.routine.clone(), r.text.clone()))
        .collect();
    v.sort();
    v
}

fn pair(routine: &str, text: &str) -> (String, String) {
    (routine.to_string(), text.to_string())
}

#[test]
fn a_branch_on_what_a_pull_left() {
    let Some(r) = lint(
        "pull",
        r#"
.proc main
    jsr after_compare
    jsr compares_again
    jsr carry_survives
    jsr after_plp
    stp
.endproc
.proc after_compare
    phy
    lda $10
    cmp #3
    ply
    sep #$20
    sta $12
    beq done            ; Z is the ply's, not the cmp's
    nop
done:
    rts
.endproc
.proc compares_again
    phy
    ply
    cpy #0
    beq :+
    nop
:   rts
.endproc
.proc carry_survives
    pha
    cmp #3
    pla
    bcs :+              ; pla does not touch C
    nop
:   rts
.endproc
.proc after_plp
    php
    lda $10
    plp
    bne :+              ; plp sets every flag
    nop
:   rts
.endproc
"#,
    ) else {
        return;
    };
    assert_eq!(
        found(&r, Check::PullBranch),
        vec![
            pair("after_compare", "beq done"),
            pair("after_plp", "bne :+")
        ]
    );
}

#[test]
fn a_routine_comes_back_the_way_it_was_entered() {
    let Some(r) = lint(
        "calls",
        r#"
.proc main
    jsl far_with_rts
    jsr near_with_rtl
    jsl near_l
    jsl tail
    stp
.endproc
.proc near_with_rtl
    nop
    rtl
.endproc
.proc near
    nop
    rts
.endproc
; The `_l` entry: `jsr` to the routine and `rtl`.
.proc near_l
    jsr near
    rtl
.endproc
; A tail jump: the `rtl` that ends it is `ends_far`'s.
.proc tail
    nop
    jmp ends_far
.endproc
.proc ends_far
    rtl
.endproc
.segment "FAR"
.proc far_with_rts
    nop
    rts
.endproc
"#,
    ) else {
        return;
    };
    assert_eq!(
        found(&r, Check::CallReturn),
        vec![pair("far_with_rts", "rts"), pair("near_with_rtl", "rtl")]
    );
}

#[test]
fn what_a_routine_pushes_it_pulls() {
    let Some(r) = lint(
        "stack",
        r#"
.proc main
    jsr leaves_one
    jsr takes_one
    jsr on_one_path
    jsr balanced
    jsr counted_loop
    jsr bank_trick
    stp
.endproc
.proc leaves_one
    pha
    rts
.endproc
.proc takes_one
    pla
    rts
.endproc
.proc on_one_path
    phx
    lda $10
    beq out
    plx
    rts
out:
    rts
.endproc
; 16-bit pushes and pulls inside a php/plp, and the widths come back.
.proc balanced
    php
    rep #$30
    pha
    phx
    plx
    pla
    plp
    pha
    pla
    rts
.endproc
; How many bytes a loop pushes depends on X: not followed, not a finding.
.proc counted_loop
    ldx #3
each:
    pha
    dex
    bpl each
    pla
    pla
    pla
    pla
    rts
.endproc
; Two bytes with `pea`, one at a time with `plb`.
.proc bank_trick
    phb
    pea $7E7E
    plb
    plb
    plb
    rts
.endproc
"#,
    ) else {
        return;
    };
    assert_eq!(
        found(&r, Check::Stack),
        vec![
            pair("leaves_one", "rts"),
            pair("on_one_path", "rts"),
            pair("takes_one", "pla")
        ]
    );
}

#[test]
fn widths_against_what_the_source_declares() {
    let Some(r) = lint(
        "widths",
        r#"
.proc main
    jsr comes_back_wide
    lda #1              ; assembled for A8, run with A16
    sep #$20
    jsr wants_wide      ; called with A8
    rep #$20
.a16
    jsr wants_wide
    sep #$20
.a8
    jsr sets_its_own
    jsr comes_back_wide
.a16                    ; declared, so this one is right
    lda #2
    sep #$20
.a8
    stp
.endproc
.proc comes_back_wide
    rep #$20
.a16
    rts
.endproc
.a16
.proc wants_wide
    sta $10
    rts
.endproc
.a8
; It does not matter how it is entered: it sets A before using it.
.proc sets_its_own
    rep #$20
.a16
    lda #$1234
    sep #$20
.a8
    rts
.endproc
"#,
    ) else {
        return;
    };
    assert_eq!(
        found(&r, Check::Width),
        vec![pair("main", "jsr wants_wide"), pair("main", "lda #1")]
    );
}

#[test]
fn widths_inside_a_macro_follow_its_body() {
    let Some(r) = lint(
        "macro",
        r#"
.macro WIDEN
    rep #$20
.a16
    lda #$1234
    sep #$20
.a8
.endmacro
.proc main
    WIDEN
    lda #1
    stp
.endproc
"#,
    ) else {
        return;
    };
    assert!(r.is_empty(), "{:?}", r);
}

/// Two pulls and a branch on each: `one`'s on the line, `two`'s with the
/// annotation above it. `ANNOTATION_ONE` and `ANNOTATION_TWO` are replaced
/// by each test.
const ANNOTATED: &str = r#"
.proc main
    jsr one
    jsr two
    stp
.endproc
.proc one
    pha
    pla
    beq :+              ANNOTATION_ONE
    nop
:   rts
.endproc
.proc two
    pha
    pla
    ANNOTATION_TWO
    ; and the why goes on
    bne :+
    nop
:   rts
.endproc
"#;

fn annotated(
    name: &str,
    one: &str,
    two: &str,
) -> Option<(Vec<Report>, Vec<Annotation>, Vec<String>)> {
    lint_annotated(
        name,
        &ANNOTATED
            .replace("ANNOTATION_ONE", one)
            .replace("ANNOTATION_TWO", two),
    )
}

#[test]
fn an_annotation_allows_its_line_or_the_next_with_code() {
    let Some((r, list, wrong)) = annotated(
        "allow",
        "; goombario: pull-branch: the pulled value is the one it means",
        "; goombario: pull-branch: the same, from above",
    ) else {
        return;
    };
    assert_eq!(found(&r, Check::PullBranch).len(), 2, "{:?}", r);
    assert!(wrong.is_empty(), "{:?}", wrong);
    let (left, unused) = goombario::apply_exceptions(r, &list);
    assert!(left.is_empty(), "{:?}", left);
    assert!(unused.is_empty(), "{:?}", unused);
}

#[test]
fn an_annotation_without_its_why_is_wrong_and_allows_nothing() {
    let Some((r, list, wrong)) = annotated(
        "allow-why",
        "; goombario: pull-branch:",
        "; goombario: pull-branch",
    ) else {
        return;
    };
    assert_eq!(wrong.len(), 2, "{:?}", wrong);
    assert!(list.is_empty(), "{:?}", list);
    let (left, _) = goombario::apply_exceptions(r, &list);
    assert_eq!(left.len(), 2, "{:?}", left);
}

#[test]
fn an_annotation_for_another_check_allows_nothing_and_is_said() {
    let Some((r, list, wrong)) = annotated(
        "allow-other",
        "; goombario: stack: not this check",
        "; nothing",
    ) else {
        return;
    };
    assert!(wrong.is_empty(), "{:?}", wrong);
    let (left, unused) = goombario::apply_exceptions(r, &list);
    assert_eq!(
        found(&left, Check::PullBranch),
        vec![pair("one", "beq :+"), pair("two", "bne :+")]
    );
    assert_eq!(unused.len(), 1);
    assert_eq!(unused[0].check, Check::Stack);
}

#[test]
fn an_annotation_that_allows_nothing_is_said() {
    // On `nop`, which nothing flags.
    let Some((r, list, wrong)) = lint_annotated(
        "allow-stale",
        &ANNOTATED
            .replace("    nop\n:   rts\n.endproc\n.proc two", "    nop                 ; goombario: pull-branch: stale\n:   rts\n.endproc\n.proc two")
            .replace("ANNOTATION_ONE", "; goombario: pull-branch: why")
            .replace("ANNOTATION_TWO", "; goombario: pull-branch: why"),
    ) else {
        return;
    };
    assert!(wrong.is_empty(), "{:?}", wrong);
    let (left, unused) = goombario::apply_exceptions(r, &list);
    assert!(left.is_empty(), "{:?}", left);
    assert_eq!(unused.len(), 1, "{:?}", unused);
    assert_eq!(unused[0].why, "stale");
}

#[test]
fn data_without_a_type_in_the_debug_file_is_not_code() {
    // `.res` and `.dword` get no type in the debug file. Read as code, three
    // zeros are a `brk` and a half, and the `.dword` a `jsl` to `wrong`.
    let Some(r) = lint(
        "data",
        r#"
.proc main
    stp
.endproc
    .res 3
    .dword $00808522
    .byte $00
.proc wrong
    pha
    rts
.endproc
"#,
    ) else {
        return;
    };
    assert!(r.is_empty(), "{:?}", r);
}

#[test]
fn the_root_is_where_the_debug_file_names_are_from() {
    // Nothing to assemble: only that a missing source is said, not ignored.
    let dir = scratch("root");
    let dbg = "version\tmajor=2,minor=0\nfile\tid=0,name=\"nowhere.s\",size=1,mtime=0x0,mod=0\nmod\tid=0,name=\"x.o\",file=0\n";
    std::fs::write(dir.join("x.dbg"), dbg).unwrap();
    std::fs::write(dir.join("x.sfc"), [0u8; 16]).unwrap();
    let program = goombario::load(&dir.join("x.sfc"), &dir.join("x.dbg"), Path::new(&dir)).unwrap();
    assert_eq!(program.missing_sources().len(), 1);
    let _ = std::fs::remove_dir_all(&dir);
}
