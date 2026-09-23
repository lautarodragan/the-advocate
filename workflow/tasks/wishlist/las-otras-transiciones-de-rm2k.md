---
name: "Las otras transiciones"
description: "Bloques, persianas y demás transiciones que no son el fundido"
---

# Qué

Las transiciones de RM2k que no son el fundido: las de bloques, persianas y
barridos que un evento puede pedir con `EraseScreen` y `ShowScreen`.

# Status

Anotado, sin empezar.

# Por qué

El fundido está, y es **la que este juego usa**: `transition_out` y
`transition_in` valen 0 en su base. Pero `Transition::Type` tiene **38**, y un
evento puede pedir cualquiera de ellas.

Lo que las hace caras no es la cantidad: las de bloques, persianas y barridos
**no son un brillo maestro**, piden tapar la pantalla por regiones, que en la
consola es otra máquina.
