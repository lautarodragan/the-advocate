---
name: "La ventana de mensajes arriba, al medio y sin fondo"
description: "MessageOptions de RM2k: la posición de la ventana (arriba, medio, abajo), sin fondo, correrse si tapa al héroe y los eventos que siguen durante el mensaje; hoy el compilador lo ignora y todo sale abajo con fondo"
type: feature
assignee: Quirquincho
---

De taro, el 2026-10-04: "podés hacer que el texto se pueda mostrar en el
medio o arriba de la pantalla, como en el rpg maker 2000 original? … puede
que también haya una opción para mostrarlo sin fondo".

Es `MessageOptions` (10120), que `compile.rs` tiene en `IGNORABLE` desde
`c64e4d96`: "where and how the message window is drawn, which without
messages is drawn nowhere". ABL lo usa 1110 veces en 202 mapas (contado el
2026-10-04 sobre el volcado); los parámetros más comunes, en el orden
[sin fondo, posición, correrse si tapa al héroe, eventos durante el
mensaje], con la posición 0 arriba, 1 medio, 2 abajo:

    (0,2,0,0) 284   (0,0,0,0) 223   (1,1,0,0) 175   (1,0,0,0) 134
    (0,1,0,0)  89   (1,2,0,0)  74   (0,2,1,0)  72   (0,0,1,0)  46
