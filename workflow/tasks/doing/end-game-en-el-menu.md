---
name: "End Game en el menú de pausa"
description: "La orden End Game del menú de pausa tiene que andar como en RM2k"
type: feature
assignee: Yaguareté
---

De taro, el 2026-09-28: "que End Game ande bien".

En RM2k, End Game abre `Scene_End`: una ventana que pregunta si volver al
título, con "Yes"/"No" (los términos del LDB), y "Yes" funde la pantalla y la
música y va al título. Hay que ver qué hace hoy la ROM con esa orden (el
menú está en `rom/src/menu.s`; las órdenes y cuándo van en gris, en
`tools/port/titulo.py`).
