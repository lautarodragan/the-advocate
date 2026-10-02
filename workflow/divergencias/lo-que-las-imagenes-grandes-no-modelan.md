# Qué

Las imágenes de `ShowPicture` que tapan la pantalla van en BG1, con la
consola en modo 1 mientras se muestran —ver `tools/runtime/big_picture.s`,
`tools/port/picture.py` y `decisiones/las-imagenes-grandes-en-modo-1.md`—, y
no hacen todo lo que hacen en RM2k:

* **El zoom que achica es un fundido.** Las fotos del 212 al 216 se achican
  de 100 a 0 en dos segundos sobre la pantalla en negro; la consola no
  escala un fondo sin modo 7, así que en esos dos segundos la foto se
  apaga a negro. Lo que llega a la transparencia es lo que queda de su
  área: `100 - (100 - t) × zoom / el de mostrarla`.
* **La transparencia oscurece.** Debajo de la capa sólo está el color de
  fondo, que es negro, así que una imagen al 50 % es una imagen a la mitad
  de su color: exacto sobre la pantalla en negro, que es donde el juego
  las muestra. Con un tono que aclara y transparencia a la vez es una
  aproximación, que ninguna imagen del juego pide.
* **El mapa no se ve mientras está**: ni sus capas, ni los personajes, ni
  el cronómetro, ni las imágenes chicas. Las instrucciones del 285, que en
  RM2k van sobre el mapa con el mapa alrededor, acá van sobre negro. Y el
  menú no se abre.
* **Mostrarla y borrarla apagan la pantalla**: medido, dos cuadros al
  mostrar una y catorce al borrarla, que recarga el mapa como la vuelta de
  la pelea. Las del juego aparecen y se van sobre la pantalla en negro, salvo
  la foto del 212, que aparece sobre el mapa con un parpadeo.
* **El destello de pantalla no se ve encima**, ni el tinte —que RM2k
  tampoco aplica a las imágenes—: los dos son la paleta del mapa, y la de
  la imagen es otra. El blanco del 213, 214 y 216, que empieza justo antes
  de la foto, se corta al aparecer.
* **De costado no se mueve**: su lugar es donde la conversión la dibujó.
  `MovePicture` la sube o la baja —la capa es más alta que la pantalla si
  la imagen lo es— y le cambia tono, transparencia, saturación y ondas.
* **Las ondas muestran los bordes espejados**, si la imagen pasa los
  costados de la pantalla: RM2k muestra lo que la imagen tiene más allá, y
  la consola no tiene lugar para eso. `GTest4` mide 389 de ancho. Si no los
  pasa, como `ShipFlash`, lo de afuera es negro, igual que en RM2k.
* **105 colores**: siete paletas de quince, repartidas por celda de 8x8
  por Adeleine. Las fotos y `GTest4` pierden degradés.
* **Una sola a la vez**, y las que van con el mapa sólo si tapan la pantalla
  entera, que se dibujan como si fueran de la pantalla. El hovertram del 32,
  pegado al mapa y con la escena alrededor, sigue sin dibujarse.
* **El montaje del 217** —las cuatro fotos al 50 % una cada seis cuadros,
  con un destello blanco— carga cada foto con la pantalla apagada: cinco
  cuadros de foto y tres de negro, sin el blanco. La otra opción, sólo los
  destellos sin fotos, está capturada para que taro elija: ver la tarea.

# Medido

Sobre el cartucho `release`, el 2026-10-02, con las páginas de prueba de
`test_imagenes_grandes_golden.py`, contra las capturas del RPG_RT de 2015
con Wine de las seis escenas: ver
`workflow/tasks/*/las-imagenes-grandes-en-modo-1.md`.
