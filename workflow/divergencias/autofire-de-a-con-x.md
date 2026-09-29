# Qué

Sostener X aprieta y suelta A solo: `pad_a` pasa `AUTOFIRE_FRAMES` vueltas
prendido y otras tantas apagado, y como el juego mira el flanco de A
—RM2k cierra el mensaje con `Input::IsTriggered`—, cada vuelta a prendido es
un toque. Sirve para pasar textos y repetir elecciones sin machacar el botón.
Está todo en `read_pad` (`tools/runtime/control.s`), que es el único lugar que lee
el control, así que vale en el mapa, en los mensajes, en los menús, en la
tienda, en la pelea y en la pantalla de título.

RM2k no tiene nada de esto: usa dos botones, y el control de la SNES tiene
muchos más. Es una divergencia que **sólo suma**, porque en RM2k no hay
botón que corresponda a X; queda anotada para que nadie la tome por un error
ni la "arregle". Es idea de taro, el 2026-09-25.

**Sólo A, con X.** Un autofire de B se descartó: en el mapa B abre el menú de
pausa y adentro lo cierra, así que sostenerlo lo abriría y cerraría sin parar.

Lo que se decidió en la línea, y está comentado ahí:

* **La A de verdad gana.** Se suma con un OR: A y X juntos es sostener A,
  prendido y sin flancos.
* **Soltar X no deja nada trabado ni toca de más.** La vuelta siguiente
  escribe sólo la A de verdad, así que a lo sumo apaga un `pad_a` prendido.
* **El primer cuadro con X ya toca.** Soltar X reinicia el contador, así que
  cada vez que se aprieta arranca en la fase prendida.

# Medido

Con `AUTOFIRE_FRAMES` en 4 son cuatro cuadros prendido y cuatro apagado:
7,5 toques por segundo. taro pidió entre 3 y 4 para arrancar, y es una
constante con nombre para ajustarla jugando; tiene que ser potencia de dos,
y un `.assert` lo cuida.

Lo cubre `rom/pruebas/rpgmaker/test_autofire.py`: el ritmo cuadro por cuadro,
que la A de verdad gane, soltar X en cada una de las ocho fases, y el caso
`autofire` —cinco mensajes seguidos— cerrado entero con X sostenido y uno
solo con A sostenido. `test_cores.py` corre el mismo caso en los dos cores.

# Cómo reproducirlo

En cualquier mensaje, sostener X: se cierran uno detrás del otro.
