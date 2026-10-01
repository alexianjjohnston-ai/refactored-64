/* Local adapter for the pinned reference libpdtex decoder. Writes RGBA8. */
#include <stdio.h>
#include <stdint.h>
#include "pdtex.h"
void pdtex_flip(struct pd_tex *tex);

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    struct pd_tex *tex = pdtex_allocate();
    if (!tex || pdtex_read(tex, argv[1])) return 3;
    pdtex_flip(tex);
    struct pd_image *im = &tex->images[0];
    if (!im->exists || im->width < 1 || im->height < 1 ||
        im->width > 256 || im->height > 256) return 4;
    FILE *out = fopen(argv[2], "wb");
    if (!out) return 5;
    /* libpdtex flips rows for image export; undo that for original N64 UVs. */
    for (int y = 0; y < im->height; ++y) {
        for (int x = 0; x < im->width; ++x) {
            int i = y * im->width + x, f = im->format;
            uint8_t *p = im->pixels, rgba[4] = {255,255,255,255};
            unsigned v;
            if (f >= 9) {
                if (p[i] >= tex->numcolours) return 6;
                p = tex->palette; i = im->pixels[i];
                f = f <= 10 ? 1 : (f == 11 ? 4 : 5);
            }
            switch (f) {
            case 0: for (int k=0;k<4;++k) rgba[k]=p[4*i+k]; break;
            case 2: for (int k=0;k<3;++k) rgba[k]=p[3*i+k]; break;
            case 1: case 3:
                v=(p[2*i]<<8)|p[2*i+1];
                rgba[0]=((v>>11)&31)*255/31;
                rgba[1]=((v>>6)&31)*255/31;
                rgba[2]=((v>>1)&31)*255/31;
                rgba[3]=f==1 ? (v&1)*255 : 255; break;
            case 4: rgba[0]=rgba[1]=rgba[2]=p[2*i]; rgba[3]=p[2*i+1]; break;
            case 5: rgba[0]=rgba[1]=rgba[2]=(p[i]>>4)*17; rgba[3]=(p[i]&15)*17; break;
            case 6:
                v=(p[i/2] >> ((i&1)?0:4))&15;
                rgba[0]=rgba[1]=rgba[2]=(v>>1)*255/7;
                rgba[3]=(v&1)*255; break;
            case 7: rgba[0]=rgba[1]=rgba[2]=p[i]; break;
            case 8:
                v=im->compression>=5 && im->compression<=7 ?
                    (p[i/2] >> ((i&1)?0:4))&15 : p[i];
                rgba[0]=rgba[1]=rgba[2]=v*17; break;
            default: fclose(out); return 7;
            }
            if (fwrite(rgba,1,4,out)!=4) return 8;
        }
    }
    fclose(out);
    printf("%d %d %d\n", im->width, im->height, im->format);
    pdtex_free(tex);
    return 0;
}
