# Qué

**Las imágenes grandes de `ShowPicture` se dibujan en BG1 en modo 1, sólo
mientras se muestran con el mapa tapado.** El mapa sigue siempre en modo 3,
y BG2 —la capa de encima y la ventana de mensaje— no cambia, porque en modo
3 ya es de 4 bits.

# Por qué

De taro, el 2026-10-01, con la opción E de
`docs/research/2026-10-01-el-sistema-de-imagenes.md` delante: "estoy OK con
usar el modo 1". No contradice `modo3-y-poses-en-caliente`, del 2026-09-05,
que descartó el modo 1 **para el mapa** (el fondo de 256 colores se queda):
acá el mapa no se ve. Es lo mismo que se evaluó para el menú en modo 5.

# Cómo se aplica

El conversor elige el plano de cada imagen: las chicas sobre el mapa van en
objetos; las grandes, con el mapa tapado, en BG1 en modo 1, y al borrarse se
vuelve al modo 3 recargando lo que haga falta del mapa.

Desde el 2026-10-03, una que un `MovePicture` agranda o achica **hace el
zoom en modo 7**, con una textura de 255 tiles parecidos, y quieta sigue
acá, en modo 1 a resolución completa: es la variante híbrida vq que taro
eligió en el piloto. Ver `tasks/*/las-fotos-en-modo-7.md`.
