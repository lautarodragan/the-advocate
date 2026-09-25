---
name: "Las goldens del recorrido de los Neon Vipers"
description: "Las fotos del recorrido vipers no tienen golden, así que pasan siempre"
type: test
assignee: taro
---

`pruebas/abl/test_recorrido_vipers_golden.py` saca sus fotos, pero ninguna
tiene golden, y una foto sin golden pasa siempre (`pruebas/arnes/recorrido.py`,
a propósito: nadie la bendijo). Hasta que se congelen, el recorrido cobra lo
que mira en la RAM pero no lo que se ve.

**Está bloqueada por taro**: congelarlas es decir "así se tiene que ver", y
eso lo decide él mirando las fotos. Lo que hace falta de este lado es dejarle
las fotos actuales en `/shared/goldens/<fecha>-vipers/` para que las mire; con
su ok, se copian a `pruebas/golden/` en un commit que diga que las miró.
