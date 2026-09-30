---
name: "Rust: la música del conversor"
description: "Lo que el conversor decide de la música y del .msu (music.py, msu_data.py) a rm2k-snes-audio, con las ROMs y el .msu byte por byte iguales"
type: refactor
assignee: Calandria
---

De taro, el 2026-09-30, en la migración del conversor a Rust. `music.py`
decide qué temas pide cada mapa, cuáles pueden estar sonando cuando carga un
paquete, el trabajo que le pasa a `rm2k-snes-audio` y el presupuesto de
cuadros del arranque; `msu_data.py` arma el `.msu` con los fondos de calidad
y los efectos. La música en sí ya es de `rm2k-snes-audio`.

Sale de `main` en el commit que lanza la tarea. Ahí: `NO_CACHE=1 just
cartuchos` da `abl.sfc` `241dc9ad2bf8b43c…`, `special` `63779e111ee18923…`,
`encounter-every-step` `200a0b7355289700…`; `just pruebas` 882,
`just -f tools/justfile test` 49.
