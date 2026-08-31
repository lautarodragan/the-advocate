#!/usr/bin/env python3
"""Parchea el fin de ROM y el checksum de la cabecera, y padea a potencia de 2."""
import sys, struct

path = sys.argv[1]
d = bytearray(open(path, 'rb').read())

size = 1
while size < max(len(d), 0x8000):
    size <<= 1
d += b'\x00' * (size - len(d))

struct.pack_into('>I', d, 0x1A4, len(d) - 1)          # fin de ROM
struct.pack_into('>H', d, 0x18E, 0)                   # checksum en cero
chk = 0
for i in range(0x200, len(d), 2):
    chk = (chk + struct.unpack_from('>H', d, i)[0]) & 0xFFFF
struct.pack_into('>H', d, 0x18E, chk)

open(path, 'wb').write(d)
print(f"ROM: {len(d)} bytes ({len(d)//1024} KB), checksum 0x{chk:04X}")
