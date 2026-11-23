# fxpak: usb2snes over the FX Pak's USB

The FX Pak (sd2snes) has a USB port that enumerates as a serial port, a CDC
ACM device with vendor `1209` and product `5a22`, and its firmware answers
the usb2snes protocol on it: read and write the SD card, read and write the
cartridge's memory while a game runs, boot a ROM. This tool speaks it
directly, without the usb2snes/QUsb2snes websocket server in between.

    fxpak info                         the ROM running, firmware, device name
    fxpak peek $18E93 16               a hex dump of the FX Pak's memory
    fxpak peek $F50000 0x20000 --out wram.bin
    fxpak ls /advocate
    fxpak get /advocate/x/game.sfc game.sfc
    fxpak mkdir /advocate/x
    fxpak put game.sfc /advocate/x/game.sfc      read back after, unless --no-verify
    fxpak boot /advocate/x/game.sfc    prints what was running first
    fxpak reset | fxpak menu
    fxpak poke $8000 'a9 00' --write-memory

The port is found by its USB ids in sysfs, on Linux; `--device <tty>` or
`FXPAK_DEVICE` name it by hand, and are the only way elsewhere. Addresses
take `$` or `0x` for hex, decimal otherwise.

`cargo test` needs nothing: the protocol tests build their blocks from the
source, and `tests/pty.rs` runs the client against a fake FX Pak on a
pseudo-terminal that answers —and hangs— as the firmware does. The test in
`tests/hardware.rs` runs against a real one when `FXPAK_DEVICE` names its
port, and is skipped otherwise; it boots and resets nothing, and writes one
file under `/advocate/tmp/fxpak-test/`.

## Where the protocol comes from

From the firmware's source, **sd2snes v1.11.0**, `src/usbinterface.c`, and
nothing else: no other client, nothing from memory. The comments in
`src/protocol.rs` and `src/client.rs` cite its lines. In short:

* every command is a 512-byte block: `USBA`, the opcode at 4, the space
  (0 the SD card, 1 the FX Pak's memory) at 5, the flags at 6, the size as
  a big-endian U32 at 252, and at 256 either a big-endian U32 address or a
  NUL-ended file name;
* every command is answered by a 512-byte RESPONSE block (opcode 15) with
  the error at 5 and a size at 252;
* data goes in 512-byte blocks, the last one padded: after the response for
  GET and LS, after the response for PUT the other way.

Another firmware version may differ: check the source of the one on the
card (`fxpak info` prints it) before trusting this against it.

## What it refuses, and why

**Writes go only under `/advocate/` on the card.** `put` and `mkdir`
refuse any other path, after normalising it: an SD path must be absolute,
`.` and `..` are resolved here and `..` above the root is refused, `\`, `:`
and FAT's illegal characters are refused, and so is a component ending in
a dot or a space, which FAT would drop. There is no `rm` and no `mv`.

**Some error paths of this firmware never return**, and the FX Pak then
answers nothing until the console is off with the USB cable out. The tool
looks before it acts so they are never taken:

* GET of a file that does not exist loops forever in the firmware: `get`
  lists the parent directory first and refuses a missing file;
* PUT of a file whose directory does not exist waits for data and then
  loops forever on each block: `put` checks the directory first, and sends
  no data if the PUT is refused anyway;
* a GET of 0 bytes leaves the firmware waiting for a disconnect: `peek`
  refuses it, and an empty file makes the tool reopen the port, which the
  firmware takes as a disconnect;
* BOOT of a missing file takes the console out of reset with nothing
  loaded: `boot` checks the file first.

**`poke` writes only the ROM's copy in PSRAM, below `$C00000`**, and only
with `--write-memory`. It changes the running game's code or data until the
ROM is loaded again; nothing reaches the card. Above `$C00000` are the
menu's own image, its directory and database, the cheats, the save RAM at
`$E00000` —which the FX Pak writes back to the card's `.srm`—, the WRAM
copy, and the menu's mailboxes at `$FF0000`, through which a write can make
the firmware load a ROM.

**`boot`, `reset` and `menu` cut whatever is running.** The tool cannot ask
whether someone is playing; it prints what was running before. BOOT also
records the ROM as the last game in the firmware's settings, as booting from
the menu does.

**Every read has a timeout**: a response 5 s (BOOT 60 s, since it answers
after loading the ROM), and each wait for the next byte of a transfer 5 s,
so a long transfer that keeps moving is not cut. If a transfer stops
halfway the tool drains what is still coming and says the FX Pak may be
waiting; closing the port usually frees it, and a power-off with the cable
out always does. On opening the port it drops whatever an earlier client
left unread, and it takes an exclusive `flock` so a second `fxpak` does not
interleave its blocks (a client that does not `flock` is not kept out).

`put` reads the file back and compares it by default, whatever its size: at
the FX Pak's USB speed that is seconds for a ROM, and an upload that came
out wrong costs more. `--no-verify` skips it.
