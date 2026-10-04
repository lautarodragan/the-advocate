---
name: "Los ítems de SP en la pelea y las píldoras"
description: "En la pelea no se pueden usar los ítems que recuperan SP, y la Agility Pill no se puede usar en ningún lado: medicinas con SP y los ítems de tipo 8 (los que suben atributos)"
type: bug
assignee: Mulita
---

De taro, el 2026-10-04: "no puedo usar items que recuperan SP en batalla, y
no puedo usar la Agility Pill en general".

En ABL (volcado, `data/db/items.json`):

* medicinas (tipo 6) con SP: 3 Magic Ether, 4 Miracle Drop, 8 Pocket
  Shelter, 103 Cheap Wine-SP, 107 Bottle of Health, 125 Bottled Water-SP,
  129 Motor Oil-HPSP, 258 Recharge Draught-SP;
* tipo 8, los que suben atributos: 10 Apple, 11 MP Apple, 12 Powr-Up, 13
  Defensive-Up, 14 Mind-Up, 15 Speed Up, 109 Agility Pill-AGL, 134 Vitality
  Pill-MHP, 259 Agility Potion-AGL, 260 Strength Potion-ATK (estos dos
  últimos además curan HP).
