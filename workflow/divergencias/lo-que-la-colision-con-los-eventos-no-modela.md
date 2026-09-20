# Qué

La colisión con los eventos **está** —ver "La colisión con los eventos" en
`README.md`— y deja afuera cuatro cosas que RM2k sí hace:

* **`overlap_forbidden`**, que son 17 páginas del juego;
* el **conflicto de un evento con gráfico de tile contra su propio bloque**;
* que **un evento de contacto de la capa del héroe dispare al chocar con él**
  —`CheckCollisonOnMoveFailure`—;
* que una ruta forzada no salteable **reintente** el paso bloqueado en vez de
  saltearlo. Ésa tiene archivo propio, con lo medido y con la golden que hoy la
  congela: `divergencias/paso-bloqueado-de-una-ruta-forzada.md`.

# Medido

De los tres primeros, el que está más cerca de verse es el reintento —el cuarto,
el de su propio archivo—: **en la apertura la colisión no frena ningún paso**,
medido, pero **el droide del mapa 2 vive de eso**.

# Cómo se ve hoy

No se ve: ninguna prueba falla por esto, y ninguna página que hoy compile
ejercita las tres primeras. Los dos primeros puntos están además anotados en el
comentario de `celda_bloqueada`, en `rom/src/main.s`, que es donde vive la
mecánica: el campo `overlap_forbidden` se lee y se ignora, no es que la página
no compile.
