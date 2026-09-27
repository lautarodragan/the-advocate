---
name: "Las otras transiciones"
description: "Bloques, persianas y demás transiciones que no son el fundido"
type: feature
---

# Qué

Las transiciones de RM2k que no son el fundido: las de bloques, persianas y
barridos que un evento puede pedir con `EraseScreen` y `ShowScreen`.

# Status

Anotado, sin empezar.

# Por qué

El fundido está, y es **la que este juego usa** para los teletransportes:
`transition_out` y `transition_in` valen 0 en su base. La pelea pide otras
dos —el zoom, 16, y el mosaico, 17—: el mosaico es el del PPU, y el zoom va
como fundido, porque acercar el mapa es modo 7. Ver `rom/src/fundido_de_pelea.s`.
Desde el 2026-09-27 `ChangeScreenTransitions` también: el teletransporte hace
el mosaico, y el zoom y las demás que la consola no hace van como fundido —ver
`divergencias/las-transiciones-del-teletransporte.md`—. Pero `Transition::Type`
tiene **38**, y un evento puede pedir cualquiera de ellas.

Lo que las hace caras no es la cantidad: las de bloques, persianas y barridos
**no son un brillo maestro**, piden tapar la pantalla por regiones, que en la
consola es otra máquina.
