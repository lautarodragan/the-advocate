---
name: "Ignorar los códigos de color en los mensajes, por ahora"
description: "\\c[n], \\C[n] y \\s[n] en una caja la dejan afuera entera; que se ignoren como ya se ignoran las esperas, como deuda"
type: feature
agents: [Tijereta]
assignee: taro
---

Del análisis de Aguará del 2026-10-06: Desert Nightmare (`\c[1]Sandra: \c[0]`
en casi todos los mensajes, 1345 páginas afuera), Sunset Over Imdahl (unas 870)
y Dooms 2 (`\S[n]`). taro, el 2026-10-06: "Vamos con el 1 en sonnet".

## Hecho (Tijereta, 2026-10-06)

`without_waits` de `tools/rm2k-snes/text/src/refit.rs` descarta también
`\c[n]`, `\C[n]`, `\s[n]` y `\S[n]` (con dígitos y `]`; otra cosa, como
`\c[x]`, sigue sin compilar). Como `escape_tail` los saca antes de medir, no
cuentan en el ancho. Casos en `text/tests/escapes.json`; el rojo se vio con
la regla desactivada.

**Deuda declarada**: se pierde el color y la velocidad. Está anotada acá y en
`todo/las-caras-y-las-esperas.md`, donde ya vive `without_waits`.

Páginas de mapa que compilan (`rm2k-snes-events culprits --every-map`, antes
-> después): Desert Nightmare 5738 -> 7034 de 7340; Sunset Over Imdahl 898 ->
1151 de 1369. ABL no usa los códigos en `data/` y `abl.sfc` sale con la misma
huella, `27e94e67039533a2…`.

`-p rm2k-snes-screens`: `the_boxes_of_the_maps_and_the_common_events` falla
(`left: 5, right: 4`), **y falla igual sin este cambio**: es el caso de
`todo/una-prueba-de-screens-cambia-con-el-workspace.md`, que acá falla también
con `-p`. Al mergear: instalar `text events screens convert cartridge`.
