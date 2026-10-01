---
name: "Un tema que ya suena no vuelve a empezar"
description: "En RM2k, PlayBGM con el tema que ya está sonando no lo reinicia; en la ROM sí: la victoria de la pelea y la caminata a la fábrica"
type: bug
assignee: Yacaré
---

De taro, el 2026-09-30: "creo que en el RPG Maker, cuando se ejecuta un play
bgm o algo transiciona a un nuevo tema, si el tema es el mismo que ya está
sonando, no comienza de cero, simplemente sigue sonando". Lo nota en dos
lugares:

- **La pelea**: el tema de batalla y el de "ganar batalla" son el mismo. En
  el original, probablemente, no cambiaba nada al ganar.
- **La cinemática de la caminata hacia la fábrica**: la música se reinicia
  en una de las transiciones.

A confirmar en easyrpg (`Game_System::BgmPlay` y cómo la pelea pide el tema
de victoria) y, si se puede, con el RPG_RT bajo Wine, grabando su audio.
