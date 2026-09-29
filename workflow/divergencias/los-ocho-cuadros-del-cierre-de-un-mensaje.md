# Qué

En RM2k el mensaje sigue **"activo" mientras se anima el cierre** —unos ocho
cuadros, easyrpg `window_message.cpp:379-403` y `window_message.h:216-218`— y
en ese rato el héroe no busca eventos, un `KeyInputProc` que espera no mira el
pad, y el paralelo que lo abrió sigue parado.

**Acá la ventana se apaga de golpe.** Lo que sí se copió es que **el A que
cierra** no lo vea nadie más: lo consume `espera_boton`, y lo cobran las
pruebas de `rom/pruebas/abl/test_piedras.py`. Lo que queda afuera es que **un A
nuevo** apretado dentro de esos ocho cuadros acá sí cuenta —le habla al de
enfrente, o saca una piedra— y en RM2k no.

# Medido

Para una persona son **dos toques en 130 ms**, así que no se nota jugando.

# Cómo se ve hoy

No lo prueba nada.
