# Qué

El System trae **dos dibujos del cursor**, en (64,0) y en (96,0), y RM2k los
alterna cada diez cuadros: `Window::Draw` de easyrpg dibuja `cursor1` con
`cursor_frame <= 10` y `cursor2` el resto de una vuelta de 21. La ROM dibuja
**sólo el primero**, en la barra de la elección de la ventana de mensajes
(`msg_bar_source` en `tools/runtime/message_arrow.s`) y en todas las
pantallas que ya tenían la barra —ítems, equipo, tienda, la pelea—, que
salen de `Skin::cursor` en `rm2k-snes-screens`.

# Por qué

La barra va compuesta adentro de los tiles de la ventana, igual que el
texto: alternarla sería recomponer la línea marcada cada diez cuadros, unos
1920 bytes de VRAM cada vez, o tener las dos versiones de la línea en VRAM y
cambiar el tilemap, que son sesenta tiles más en un banco que con *A Blurred
Line* quedó justo en 256.

# Medido

En *A Blurred Line* no se ve: los dos dibujos de su System, `ablskin`, son
iguales pixel por pixel —un rojo oscuro, (83,0,0), con el borde
transparente—. Medido el 2026-10-04 con el RPG_RT de 2015 en Wine: cuarenta
capturas seguidas del menú del título y de una elección dan el mismo color.

# Cómo se ve hoy

Igual que en RM2k con este System.

# Cuándo deja de alcanzar

Con un System cuyos dos dibujos difieran: ahí la barra de RM2k titila y la
de la ROM queda quieta en el primero. El arreglo en la ventana de mensajes
es un segundo `window_bar` y recomponer la línea marcada cada diez cuadros
desde `msg_arrow`, que ya corre en cada vblank con la ventana abierta.
