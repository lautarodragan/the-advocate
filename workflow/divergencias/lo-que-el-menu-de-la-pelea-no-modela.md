# Qué

Desde el 2026-10-04 la pelea es la de RM2k: la escena arriba sin nada
escrito encima, y las ventanas del System —con su marco y su barra— en la
franja de abajo, el grupo a la izquierda y las órdenes a la derecha, como
quedan en RM2k después de deslizarse. Ver `ba_compose` en
`tools/runtime/battle_skills.s`, `screen.rs` en `rm2k-snes-battle` y
`battle.rs` en `rm2k-snes-screens`. Lo que todavía no es igual:

* **No hay deslizamiento**: RM2k abre cada turno con el menú del grupo
  —Engage, Automatic, Escape— a la izquierda, y al elegir Engage las
  ventanas se corren 76 pixeles. Acá no hay menú del grupo (ver
  `escape-es-la-quinta-orden.md`) y las ventanas están siempre donde RM2k
  las deja. Era opcional y no se hizo.
* **La lista de enemigos tapa la ventana del grupo entera**, y no sólo los
  nombres: la línea del grupo, en 256 pixeles, deja a los HP en la mitad de
  la ventana, y una lista de media ventana no tiene lugar para los nombres
  de los enemigos.
* **La ventana de las órdenes empieza en 178 y no en el 76% de la
  pantalla**, que es lo que le deja a "AgentTrain" sus 59 pixeles; la del
  grupo, por lo mismo, va al borde: el SP termina a dos pixeles del marco.
  El conversor avisa si con otra fuente no entra (`check_party_line`).
* **La barra usa el primero de los dos dibujos del cursor** del System, como
  el resto de las pantallas: ver
  `la-barra-de-la-eleccion-no-alterna-sus-dos-dibujos.md`.
* **El estado** es siempre `normal_status`, o el nombre del estado de
  muerto para un caído: la pelea no tiene otros estados.
* **Los HP y SP** van en el color del texto, y no los términos en el color
  del System.
* **La descripción de una habilidad o un ítem** va en la misma fuente que
  el resto, en un renglón cortado en el marco: RM2k la escribe entera con
  una más chica.
* **Los nombres de ítems y habilidades tienen once celdas** en cada
  columna; el conversor dice cuáles se cortan.

# Medido

Con el RPG_RT de 2015 en Wine, el 2026-10-04 —la prueba de pelea, tropas 82
y 87—, contra la ROM con la tanda de ABL. Las capturas lado a lado, con la
ROM, las dice la tarea `workflow/tasks/*/el-menu-de-la-pelea-como-rm2k.md`.

# Cuándo deja de alcanzar

La fila del grupo está medida para la fuente de *A Blurred Line*: los HP y
los SP son corridas que la consola no corta, y con una fuente más ancha se
pisan. El conversor lo avisa —"the party's line does not fit"—. Y una tropa
con ocho battlers distintos no entra: la última paleta es de las ventanas,
y el conversor se niega.
