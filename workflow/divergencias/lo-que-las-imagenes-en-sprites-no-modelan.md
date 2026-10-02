# Qué

Las imágenes de `ShowPicture` que van en los sprites —ver
`tools/runtime/picture_far.s` y `tools/port/picture.py`— no hacen todo lo
que hacen en RM2k:

* **La transparencia no se dibuja**: una imagen con 76 % o más no se ve, y
  las demás van opacas. El humo del 207 (40 %) y la sombra del 311 (que
  llega a 50 %) salen opacos; la sombra aparece de golpe a mitad de su
  segundo de fundido.
* **`MovePicture` no mueve ni agranda**: cambia tono y transparencia. Uno
  que pide otro lugar u otro zoom no compila y se acepta sin hacerse.
* **Dos a la vez**, una por número, las dos primeras que muestre el mapa:
  la tercera no se dibuja.
* **Sin rotar ni ondear, sin agrandar, sin saturación**, y nada más grande
  que 256x128: ésas son del plano de BG1 (la fase 3).
* **Quince colores**, los de una paleta de sprite, contados por uso: los
  degradés se escalonan.
* **Van encima de la ventana de mensaje**: prioridad 3 de objeto, que es
  la de antes. En RM2k la ventana tapa las imágenes.
* **Las que van con la pantalla se escalan a 256x224, las del mapa no**: en
  la consola el mapa no se achica, así que una imagen pegada a él se queda
  con sus pixeles y sólo se le aplica el zoom.
* **El temblor de pantalla** mueve las del mapa —se restan con `screen_x`,
  como los personajes— pero no las de la pantalla.
* **Una página que sigue después de un `Teleport`** y muestra una imagen
  usa la tabla del mapa donde se compiló: la del destino puede ser otra.
  Medido sobre los mapas del juego: una sola página lo hace, la del 288,
  y sus dos imágenes son de las grandes.

# Medido

Sobre el cartucho `release`, el 2026-10-01: se dibujan el cartel del 4,
el del 81, el rótulo de la Fortitude del 95 y la sombra del 311. La sombra
cae en el mismo lugar del mapa que en el RPG_RT con Wine: su caja da
(39,59)-(140,179) allá y (40,60)-(138,178) acá, en pixeles del mapa. El
`ABLrec` del 45 no se dibuja porque el mapa usa siete paletas de personajes
y la caja de la animación de batalla la octava.

# Cuándo deja de alcanzar

Cuando entre al cartucho el 207 —el humo es lo único translúcido que se
mira de cerca— o la portable console, que muestra nueve a la vez.
