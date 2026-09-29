---
name: "Tres divergencias, contra RM2k"
description: "Verificar con el RPG_RT en Wine tres divergencias que se midieron contra la referencia en Python y no contra RM2k"
type: test
assignee: Caranday
---

Las marcó Guayabo el 2026-09-29, al clasificar las divergencias por repo
(`testing/decisiones-y-divergencias-por-repo.md`): se midieron contra la
referencia en Python que existía hasta el 2026-09-16, no contra RM2k, así
que no se sabe si la ROM difiere de RM2k.

- `workflow/divergencias/fase-de-los-tiles-animados.md` (lo dice ella misma)
- `workflow/divergencias/cronometro-llegando-a-cero.md` (sus 252 pixeles son
  de `27c828de`, contra la referencia)
- `workflow/divergencias/move-event-tras-teleport-interno.md`

Para cada una: o se confirma contra el RPG_RT con Wine —y la divergencia
dice qué se midió—, o se descarta y se borra, contándolo en el commit.
