---
name: "Las fotos Diff recortadas, y el montaje del 217 como en RM2k"
description: "Las fotos Diff son capturas del mapa a 320x240: recortarlas a la ventana de la ROM en vez de escalarlas, para que el paso de en vivo a foto coincida; y el montaje del 217 con la foto al 50 % y el destello blanco, que ahora se puede con el color math"
type: feature
---

De taro, el 2026-10-02, mirando las goldens de
`testing/las-imagenes-grandes-en-modo-1.md` (Aguilucho):

- **Las fotos Diff** (212, 213, 214, 216) son capturas del mapa en ese
  momento, y el original las usa para un efecto de "en vivo a foto" que
  funciona muy bien. Escaladas a 256 de ancho ya no coinciden con el mapa de
  la ROM y el efecto se pierde. La idea de taro: **recortarlas** a lo que
  muestra la ROM, algorítmicamente —dos capturas del RPG_RT, compararlas, y
  buscar que la diferencia sea la misma en la ROM—. La ROM no escala el
  mapa: el recorte es el corrimiento de la cámara (RM2k centra en 320x240,
  la ROM en 256x224) y el borde del mapa.
- **El montaje del 217**: las dos goldens `imagen-grande-montaje-fotos-3` y
  `-9` muestran escenas distintas de un lado y del otro, porque el cuadro del
  original es de otro momento del ciclo. Y ninguna de las dos opciones que
  dejó Aguilucho es lo que hace RM2k: el original pone cada foto al 50 % sobre
  negro con un destello blanco encima. Desde
  `decisiones/el-color-math-no-se-usa.md` (2026-10-02) el color math se usa
  para imágenes: la foto al 50 % sobre negro es la foto oscurecida, y el
  destello se puede hacer sumando un color fijo (`COLDATA`). La tira
  `tira-destellos.png` de Aguilucho son sólo esos destellos, sin foto: por eso
  son rectángulos grises.

Si el piloto de modo 7 (`doing/el-piloto-del-modo-7.md`) da bien, el zoom
de las fotos vuelve, y esto va junto con él.
