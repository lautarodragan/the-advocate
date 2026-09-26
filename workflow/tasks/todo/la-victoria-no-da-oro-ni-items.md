---
name: "La victoria no da oro ni ítems"
description: "RM2k da y cuenta el oro y los ítems al ganar; el port todavía no"
type: feature
---

Quedó afuera de `testing/la-victoria-avisa-la-experiencia.md` (2026-09-26): en
RM2k, al ganar, la misma página de la victoria cuenta el oro ganado y los
ítems que dejaron los enemigos (`ProcessSceneActionVictory` en EasyRPG), y el
grupo los recibe. El port todavía no da ni oro ni ítems al ganar. Los datos
están en las tropas y los enemigos del LDB (`gold`, `drop_id`,
`drop_probability`); el azar de los ítems tiene que usar el generador de la
pelea (ver `ENC_SEMILLA` y la semilla propia de la pelea).
