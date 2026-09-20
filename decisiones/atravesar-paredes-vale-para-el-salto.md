# Qué

**Atravesar paredes vale también para el salto**, no sólo para la caminata.
Pero **no es salirse del mapa**.

# Por qué

`CheckOrMakeWayEx` corta con `if (self.GetThrough()) return true;` antes de
mirar la pasabilidad, y `BeginMoveRouteJump` pasa por ahí.

El chequeo de límites va antes, así que el que atraviesa **se queda clavado en
la última columna**.
