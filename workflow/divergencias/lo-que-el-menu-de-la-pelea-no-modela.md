# Qué

Desde el 2026-10-04 la pelea es la de RM2k en lo grande: la escena arriba
sin nada escrito encima, y todas las ventanas en la franja de abajo, sobre
negro —ver `ba_compose` en `tools/runtime/battle_skills.s` y `screen.rs` en
`rm2k-snes-battle`—. Lo que todavía no es igual:

* **Las órdenes van a la izquierda y el grupo a la derecha**, quietos. En
  RM2k, al pasar del menú del grupo a las órdenes, las ventanas se deslizan
  76 pixeles y quedan el grupo a la izquierda y las órdenes a la derecha.
  Lo de la izquierda es de taro; el deslizamiento era opcional y no se
  hizo: pediría correr el texto de la franja con su propio scroll
  horizontal, por HDMA en la línea donde empieza.
* **El cursor es un ">"** y no la barra del System. La barra de la ventana
  de mensajes —`window_bar`, de la flecha y la barra de la elección— se
  compone en los tiles de la ventana, y el texto de la pelea es otra capa
  sin fondo: BG2 en modo 3, encima de la escena de 8bpp, sin una capa libre
  debajo donde pintarla. Hacerlo pediría la franja en otro modo, por HDMA.
* **No hay marcos**: las ventanas son texto sobre negro, sin el borde del
  System.
* **El estado** es siempre `normal_status`, o el nombre del estado de
  muerto para un caído: la pelea no tiene otros estados.
* **Los HP y SP** van en el color del texto, y no los términos en el color
  del System.
* **La victoria parte su término por letras**, a 31, y no por pixeles: en
  *A Blurred Line*, "The combat has resulted in victory!" va en dos
  renglones, y en RM2k en uno. Ver `victory_lines` en `screen.rs`.
* **La descripción de una habilidad o un ítem** va en la misma fuente que
  el resto, cortada a 31 celdas: RM2k la escribe entera.

# Medido

Con el RPG_RT de 2015 en Wine, el 2026-10-04 —la prueba de pelea, tropas 82
y 87—, contra la ROM con la tanda de ABL. Las capturas lado a lado, con la
ROM, las dice la tarea `workflow/tasks/*/el-menu-de-la-pelea-como-rm2k.md`.

# Cuándo deja de alcanzar

La fila del grupo está medida para la fuente de *A Blurred Line*: los HP y
los SP son corridas que la consola no corta, y con una fuente más ancha se
pisan. El conversor lo avisa —"the party's line does not fit"—, con
`check_party_line` de `screen.rs`.
