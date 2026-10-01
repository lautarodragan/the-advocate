---
name: "El cartucho a 8 MB, ExHiROM"
description: "Primero una ROM de prueba de ExHiROM para el FX Pak; después mudar release, con las goldens quietas"
type: feature
assignee: Ceibal
---

De taro, el 2026-10-01: `decisiones/el-cartucho-pasa-a-8-mb.md`. Lo que
cambia, según `docs/research/2026-10-01-el-juego-entero-sin-msu-1.md`
(Tucu-tucu): `memoria.cfg` a bancos de 64 KB (`banks.rs` ya está
parametrizado), la cabecera en `$40FFB0`, las tablas del banco 0 vistas como
32 KB en `$80`, lo que cruza bancos a mano (`.crossbank`, las muestras de
`emit.rs`) porque el banco empieza en `$0000`, y la SRAM a `$20-$3F:6000`.
No cambian la WRAM, la RAM lejana ni el `.msu`. Sin verificar: que Mednafen
arme ExHiROM.
