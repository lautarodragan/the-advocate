---
name: "El conversor no limpia los parches viejos"
description: "rom/build/<cartucho>/parches/ conserva los toml de mapas que ya no entran, y test_parches cae por eso"
type: bug
---

Encontrado el 2026-09-25 midiendo si se juntan `release` y `test-main`: al
rearmar `release` sin los mapas de prueba siguió estando
`rom/build/release/parches/0052.toml`, de una corrida anterior que sí los
llevaba, y eso solo hace caer `test_parches`. El conversor escribe un parche
por mapa y no borra los de los mapas que dejaron de entrar. Que limpie el
directorio (o que escriba en uno nuevo y lo mueva) antes de escribir.
