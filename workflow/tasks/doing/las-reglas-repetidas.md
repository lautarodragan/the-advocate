---
name: "Las reglas repetidas, en un solo lugar"
description: "Lo que varios agentes dejaron anotado dos o tres veces: las reglas del actor, las constantes del motor, equip y la cola de escapes; cada una a un solo lugar, con las ROMs byte por byte iguales"
type: refactor
assignee: Cachirla
---

Del 2026-10-02, mientras taro no puede revisar nada: un refactor que se
verifica solo. Lo anotaron:

- Cardón (`testing/rust-el-dominio-de-la-pelea.md`): el parámetro del actor
  en su nivel y el equipo sumado están en `rm2k-snes-battle`, en
  `rm2k-snes-screens` y en `port/rules.py`; su lugar es `rm2k-rules`.
- Timbó (`testing/rust-la-emision.md`): las constantes del motor están en
  `engine.rs` de `rm2k-snes-mapdata` y en `events.py`, que leen las pruebas
  de ABL; lo mismo `SUB_MAX`, `PARALLEL_MAX`, `ROUTE_EV_MAX`, `OBJ_PRIORITY`
  y `block_tile`.
- Tataupá (`testing/rust-el-dominio-de-las-pantallas.md`): `equip` en la
  etapa y en el arnés de pruebas; la cola de escapes en el compilador de
  eventos y en `rm2k-snes-text`.
