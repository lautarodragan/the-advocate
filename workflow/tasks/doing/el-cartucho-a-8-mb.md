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

## Fase A: la ROM de prueba (Ceibal, 2026-10-01)

`just exhirom` (`rom/experimentos/exhirom/`): un archivo de 8 MB de bytes
pseudoaleatorios con el código dos veces, que suma tramos de todo el mapa y
pinta nueve franjas; la SRAM se escribe por `$20:6000`, se lee por
`$A0:6000` y deja una marca para el arranque siguiente. Entregada en
`/shared/experimentos/2026-10-01-exhirom/`, con el `LEEME.txt` de qué
mirar; **falta que taro la pruebe en el FX Pak**.

Lo que dieron los emuladores, dos arranques cada uno:

- **snes9x y bsnes**: todo como el cartucho.
- **mesen-s** —y Mesen2 sin "strict board mappings", que es su opción por
  omisión, y el módulo `snes` de Mednafen—: ponen la SRAM de LoROM en
  `$70-$7D:0000-7FFF` también en ExHiROM. **Esas 14 mitades bajas, 448 KB,
  no se pueden usar para datos.** Lo dice el código de los dos Mesen
  (`BaseCartridge.cpp`, "some old romhacks seem to depend on this").
- **Mednafen `snes_faust`**, el que juega taro: arma ExHiROM, pero lee
  `$80-$BF:8000-FFFF` de los segundos 4 MB (`cart.cpp` le suma 4 MB a todo
  banco menor que `$C0`). El cartucho y el FX Pak (`address.v`:
  `{!A23, A21:0}`) los leen de los primeros. **Por eso el código del juego
  va dos veces**: en `$008000`/`$018000` del archivo —lo que la consola ve
  en `$80`/`$81`— y en `$408000`/`$418000` —lo que ve Mednafen, y donde la
  consola busca los vectores, en `$00`—. Cuesta 64 KB y deja el `FAST` y
  los `jsl` del runtime como están.
- FastROM anda en los cinco: el mismo bucle tarda 76 líneas desde `$C0` y
  99 desde `$40`. **Los segundos 4 MB son siempre lentos** —MEMSEL sólo
  acelera `$80-$FF`—: lo que la CPU lee byte a byte conviene en los
  primeros.
