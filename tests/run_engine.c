/* Offline harness: tests/run_engine in.f32 out.s16 key=value ...
 * in.f32: mono float32 at 44.1 kHz (fed as stereo). Writes interleaved int16 stereo. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "engine.h"

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "usage: %s in.f32 out.s16 [key=value ...]\n", argv[0]); return 2; }
    FILE *fi = fopen(argv[1], "rb"), *fo = fopen(argv[2], "wb");
    if (!fi || !fo) { perror("open"); return 1; }
    const mpc_engine_t *e = mpc_engine();
    void *inst = e->create(NULL);
    for (int a = 3; a < argc; ++a) {
        char k[64]; const char *eq = strchr(argv[a], '=');
        if (!eq) continue;
        snprintf(k, sizeof k, "%.*s", (int)(eq - argv[a]), argv[a]);
        e->set_param(inst, k, eq + 1);
    }
    float buf[128]; int16_t in[256], out[256]; size_t n;
    while ((n = fread(buf, sizeof(float), 128, fi)) > 0) {
        for (size_t i = 0; i < 128; ++i) {
            float v = i < n ? buf[i] : 0.0f;
            int s = (int)(v * 32767.0f); if (s > 32767) s = 32767; if (s < -32768) s = -32768;
            in[2 * i] = in[2 * i + 1] = (int16_t)s;
        }
        e->process(inst, in, out, 128);
        fwrite(out, sizeof(int16_t), 256, fo);
    }
    char lat[32]; e->get_param(inst, "latency", lat, sizeof lat);
    printf("%s\n", lat);
    e->destroy(inst);
    fclose(fi); fclose(fo);
    return 0;
}
