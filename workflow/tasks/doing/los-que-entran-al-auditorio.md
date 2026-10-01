---
name: "Los que entran caminando al auditorio"
description: "En el mapa 18 (Auditorium), WalkIn1 y WalkIn2 entran caminando en RM2k y en la ROM no"
type: bug
assignee: Pecarí
---

De taro, el 2026-09-30, jugando: "en el auditorio hay dos NPCs que entran
caminando; en el juego original entran caminando y en la ROM no".

Son `WalkIn1` (evento 16, en (13,10)) y `WalkIn2` (evento 9, en (6,8)) del
mapa 18. Los mueve la página 1 del evento 36, automática con el switch 77:

    ChangeEventLocation 16 → (10,14)
    ControlSwitches 86 ON          ; WalkIn1 pasa a su página 2
    MoveEvent 16 (frecuencia 8): 0,0,0,0,1,1,1,12
    Wait 5
    ChangeEventLocation 9 → (8,14)
    ControlSwitches 87 ON          ; WalkIn2 pasa a su página 2
    MoveEvent 9: 0,0,0,0,0,0,3,3,12
    Wait 10
    …

Sospecha de Hornero, sin verificar: el cambio de página por el switch, justo
después del `ChangeEventLocation` y antes del `MoveEvent`, pisa la posición o
la ruta. Ver `decisiones/la-pagina-activa-se-congela-hasta-el-refresco.md`.
