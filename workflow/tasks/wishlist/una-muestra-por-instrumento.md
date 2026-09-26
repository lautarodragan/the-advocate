---
name: "Varias muestras por instrumento"
description: "Multimuestrear como un piano de verdad"
type: feature
---

# Qué

Más de una muestra por instrumento: multi-muestrear como lo hace un piano de
verdad, en vez de tomar una sola y transponerla.

# Status

Anotado, sin empezar.

# Por qué

Un piano real está muestreado **cada pocas notas**; nosotros tomamos la del do
central y transponemos. **En los extremos del teclado eso se nota.**

Lo que hay que mirar antes de encararlo es el otro lado de la cuenta: más
muestras por instrumento es más ARAM por programa, y desde el presupuesto por
paquete cada paquete lleno la reparte entera. Lo que ya se hizo, el
2026-09-26: cada programa lleva la muestra de la zona que más suena en el
cartucho, no la del do central (`zonas_mas_usadas` en
`tools/audio/snes_music.py`). Dos zonas por programa se midieron en el paso 6
de `tasks/todo/la-calidad-de-la-musica.md`: 149 muestras en vez de 116, cada
una a menos tasa.
