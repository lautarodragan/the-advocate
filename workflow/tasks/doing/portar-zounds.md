---
name: "Portar Zounds, un juego de RPG Maker 2003"
description: "Un estudio de cuánto de Zounds —el juego de taro, de RPG Maker 2003— anda hoy con las herramientas: el proyecto, Ditto con los campos de 2003, qué compila, qué comandos faltan, y qué harían falta las peleas de 2003 y la música en .wav"
type: research
agents: [Aguará]
assignee: Aguará
---

De taro, el 2026-10-05: "me gustaría probar una cosa distinta: portar otro
juego, y ver qué tan bien anda … tengo un juego que hice yo (en su momento).
nunca fue terminado, pero me gustaría verlo en la SNES". Es
https://github.com/lautarodragan/zounds, clonado en `/extras/zounds-rm`.

Lo que se vio al clonarlo: la base de datos es de **RPG Maker 2003**
(`ldb_id` 2003), con `BattleCharSet/` y `System2/`; 188 mapas; 34 MIDI y
19 `.wav` en `Music/`. Ditto la lee, pero lo propio de 2003 —comandos de
batalla, clases, animaciones de battlers— le cae en `unknown`.
