# Qué

Las imágenes de `ShowPicture` que tapan la pantalla van en BG1, con la
consola en modo 1 mientras se muestran —ver `tools/runtime/big_picture.s`,
`tools/port/picture.py` y `decisiones/las-imagenes-grandes-en-modo-1.md`—, y
no hacen todo lo que hacen en RM2k:

* **El zoom se hace en modo 7, con una textura de 255 tiles**, desde el
  2026-10-03 —ver `tools/runtime/big_picture_zoom.s` y
  `tasks/*/las-fotos-en-modo-7.md`—. Quieta, la imagen está a resolución
  completa en modo 1, como cualquier grande; al empezar el zoom pasa a
  modo 7, y ahí cada lugar de la imagen muestra el tile más parecido de
  los 255 que entran —en las fotos con ruido, a veces un pedazo de árbol o
  de lápida que no es el suyo—. El modo 7 no filtra: al achicarse, el
  grano titila. Lo que no entra en eso —una imagen de más de 960 tiles o de
  más de 32 filas— se sigue apagando a negro en vez de achicarse, como
  antes: lo que llega a la transparencia es lo que queda de su área.
* **El punto que queda quieto en el zoom de una recortada es el centro de
  la pantalla**, no el de la imagen de RM2k, que cae afuera de lo que se
  ve (en `PhoneCallDiff`, 24 pixeles a la izquierda y 8 arriba). Se achica
  lo que se ve, no la foto entera de 320x240. Es lo que taro vio en el
  piloto.
* **Con una imagen con textura quieta no hay mensajes**: la ventana vive en
  la mitad de la VRAM que la imagen ocupa mientras la textura sube. Vuelve
  durante el zoom, así que los mensajes sobre el negro de después de un
  zoom a cero se ven; **en modo 7 no hay segunda capa**, y un mensaje
  durante el zoom, o con la imagen quieta en otro tamaño, no se ve.
  Ninguna escena de ABL hace ninguna de las dos cosas.
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
* **Una imagen recortada es sólo la ventana de la consola.** Las que el
  juego pide en `[graphics] cropped_pictures` —en ABL, las fotos Diff,
  que son capturas del mapa— no se escalan: se corta de ellas la pantalla
  de 256x224 desde el pixel que dice el juego, que es donde está la cámara
  de la ROM cuando se muestran. Lo que RM2k muestra afuera de esa ventana
  no está en el cartucho, y el recorte es el mismo dondequiera que la
  ponga el `ShowPicture`. Un `MovePicture` que la sube o la baja la corre
  con la cuenta de las escaladas —14 líneas de la consola cada 15 de
  RM2k—, no línea por línea: ninguna recortada se mueve en el juego.
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
