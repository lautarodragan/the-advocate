# Qué

**El refresco corre en tres momentos y está partido en dos mitades:**

    al salir del intérprete   elige sólo los eventos con automáticas
    al empezar el cuadro      elige todas las páginas activas
    ídem, después             recarga rutas y gráficos de los NPCs

# Por qué

No es una optimización de gusto: es lo que lo hace entrar en un cuadro.

Lo primero es el `if (GetNeedRefresh()) Refresh();` del final de
`Game_Interpreter::Update`, y de él depende que el idioma de RM2k funcione: una
página que prende el switch que la desactiva deja de ser la activa antes de que
se decida qué corre después. Sin eso perdía ocho cuadros en el mapa 2
arrancándose a sí misma.

EasyRPG además refresca **antes de cada comando**. Acá no hace falta y sale
caro —cinco cuadros en la cinemática de apertura, que prende switches de a
montones—: ningún opcode de los que hay lee cuál es la página activa de un
evento. **El día que aparezca uno que sí, esto vuelve al lazo.**

Y la mitad cara —recargar filas de OAM y ranuras de ruta— se posterga al cuadro
siguiente porque no se ve hasta que se dibuje.
