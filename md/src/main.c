/* ---------------------------------------------------------------------------
 * Renderiza un mapa de A Blurred Line en el VDP de la Mega Drive.
 *
 * Sólo los tiles: sin sprites, sin scroll, sin input. El mapa entero entra en
 * el plano A y se queda ahí.
 *
 * Map0007 mide 20x15 celdas de RM2k, o sea 320x240 pixeles. Eso no entra en
 * los 224 renglones del modo NTSC, pero sí en los 240 del modo V30 de PAL, que
 * es exactamente el tamaño del mapa.
 *
 * V30 sólo funciona a 50 Hz: en una consola NTSC el VDP no lo muestra. Así que
 * el modo se elige mirando la consola en la que arrancamos, y en NTSC se ven
 * los primeros 224 renglones del mapa.
 * --------------------------------------------------------------------------- */
#include "mapdata.h"

typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;

#define VDP_DATA_W   (*(volatile u16 *)0xC00000)
#define VDP_DATA_L   (*(volatile u32 *)0xC00000)
#define VDP_CTRL_W   (*(volatile u16 *)0xC00004)
#define VDP_CTRL_L   (*(volatile u32 *)0xC00004)

/* Bit 6 del registro de versión: 1 = consola PAL de 50 Hz. */
#define VERSION_REG  (*(volatile u8 *)0xA10001)

/* --- mapa de la VRAM ------------------------------------------------------
 * El tile 0 se deja en blanco y el tileset arranca en el 1, así que una celda
 * vacía del plano (valor 0) se ve transparente en vez de basura.
 */
#define TILESET_ADDR 0x0020
#define PLANE_W      0xB000
#define PLANE_A      0xC000
#define PLANE_B      0xE000
#define SPRITE_TAB   0xF000
#define HSCROLL_TAB  0xFC00

#define PLANE_CELLS_W 64        /* el plano es de 64x32 celdas: 512x256 px */
#define PLANE_CELLS_H 32

static void vdp_reg(u8 reg, u8 value)
{
    VDP_CTRL_W = (u16)(0x8000 | (reg << 8) | value);
}

/* El VDP direcciona con un patrón de bits repartido en dos palabras. */
static void vdp_addr(u32 kind, u16 addr)
{
    VDP_CTRL_L = kind | ((u32)(addr & 0x3FFF) << 16) | ((addr >> 14) & 3);
}

#define VRAM_WRITE 0x40000000u
#define CRAM_WRITE 0xC0000000u
#define VSRAM_WRITE 0x40000010u

static void vdp_init(void)
{
    vdp_reg(0,  0x04);   /* modo 1: MODE5, sin interrupción de línea        */
    vdp_reg(1,  0x04);   /* modo 2: display OFF hasta terminar de cargar     */
    vdp_reg(2,  PLANE_A >> 10);
    vdp_reg(3,  PLANE_W >> 10);
    vdp_reg(4,  PLANE_B >> 13);
    vdp_reg(5,  SPRITE_TAB >> 9);
    vdp_reg(6,  0x00);
    vdp_reg(7,  0x3F);   /* color de fondo: paleta 3, índice 15             */
    vdp_reg(10, 0xFF);   /* contador de HINT, sin uso                       */
    vdp_reg(11, 0x00);   /* scroll de pantalla completa                     */
    vdp_reg(12, 0x81);   /* modo 4: H40 (320 px), sin entrelazado           */
    vdp_reg(13, HSCROLL_TAB >> 10);
    vdp_reg(15, 0x02);   /* autoincremento de 2 bytes por escritura         */
    vdp_reg(16, 0x01);   /* tamaño de los planos: 64x32 celdas              */
    vdp_reg(17, 0x00);
    vdp_reg(18, 0x00);
}

static void vram_clear(void)
{
    u16 i;
    vdp_addr(VRAM_WRITE, 0x0000);
    for (i = 0; i < 0x8000; i++)
        VDP_DATA_W = 0x0000;
}

static void load_palette(void)
{
    u16 i;
    vdp_addr(CRAM_WRITE, 0x0000);
    for (i = 0; i < 64; i++)
        VDP_DATA_W = md_palette[i];

    /* El índice 15 de la paleta 3 es el color de fondo, y ningún tile lo usa.
     * Magenta: si aparece dentro de la imagen, algo salió mal. */
    vdp_addr(CRAM_WRITE, 63 * 2);
    VDP_DATA_W = 0x0E0E;
}

static void load_tiles(void)
{
    u16 i;
    vdp_addr(VRAM_WRITE, TILESET_ADDR);
    for (i = 0; i < MAP_TILE_COUNT * 8; i++)
        VDP_DATA_L = md_tiles[i];
}

static void load_tilemap(void)
{
    u16 x, y;
    for (y = 0; y < MAP_CELLS_H && y < PLANE_CELLS_H; y++) {
        vdp_addr(VRAM_WRITE, (u16)(PLANE_A + y * PLANE_CELLS_W * 2));
        for (x = 0; x < MAP_CELLS_W; x++)
            VDP_DATA_W = md_tilemap[y * MAP_CELLS_W + x];
    }
}

int main(void)
{
    /* En PAL entra el mapa entero; en NTSC, los primeros 224 renglones. */
    u8 pal = (VERSION_REG & 0x40) != 0;

    vdp_init();
    vram_clear();
    load_palette();
    load_tiles();
    load_tilemap();

    /* Sin scroll: el mapa arranca en la esquina de arriba a la izquierda. */
    vdp_addr(VSRAM_WRITE, 0x0000);
    VDP_DATA_L = 0x00000000;
    vdp_addr(VRAM_WRITE, HSCROLL_TAB);
    VDP_DATA_L = 0x00000000;

    /* Recién ahora se prende el display, así no se ve la VRAM sin inicializar
     * mientras se carga. 0x4C = V30 (240 renglones), 0x44 = V28 (224). */
    vdp_reg(1, pal ? 0x4C : 0x44);

    for (;;)
        ;
}
