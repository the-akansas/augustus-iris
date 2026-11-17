#ifndef PLATFORM_SDL2_SHARP_SCALE_H
#define PLATFORM_SDL2_SHARP_SCALE_H

#include "SDL.h"
#include <math.h>

/* Nearest integer pre-expansion limits the width of the final linear blend.
 * This preserves the existing raster appearance, not vector glyph detail. */
static SDL_Texture *sharp_scale_create(SDL_Renderer *renderer, int width, int height)
{
#if SDL_VERSION_ATLEAST(2, 0, 12)
    int out_width, out_height;
    if (width <= 0 || height <= 0 || SDL_GetRendererOutputSize(renderer, &out_width, &out_height)) return NULL;
    double scale = fmin((double) out_width / width, (double) out_height / height);
    if (scale <= 1.001 || fabs(scale - round(scale)) < 0.001) return NULL;
    int factor = (int) ceil(scale);
    SDL_RendererInfo info;
    if (SDL_GetRendererInfo(renderer, &info)) return NULL;
    long long w = (long long) width * factor, h = (long long) height * factor;
    /* Bound the added VRAM; keep the original renderer path on allocation failure. */
    if (w * h > 16 * 1024 * 1024 || (info.max_texture_width && w > info.max_texture_width) ||
        (info.max_texture_height && h > info.max_texture_height)) return NULL;
    SDL_Texture *texture = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ABGR8888,
        SDL_TEXTUREACCESS_TARGET, (int) w, (int) h);
    if (texture) {
        SDL_SetTextureBlendMode(texture, SDL_BLENDMODE_NONE);
        SDL_SetTextureScaleMode(texture, SDL_ScaleModeLinear);
    }
    return texture;
#else
    return NULL;
#endif
}

static int sharp_scale_copy(SDL_Renderer *renderer, SDL_Texture *source, SDL_Texture *intermediate)
{
    if (!intermediate || SDL_SetRenderTarget(renderer, intermediate)) return 0;
    /* Target-local state is reset explicitly so stale clip/viewport cannot crop a frame. */
    SDL_RenderSetViewport(renderer, NULL);
    SDL_RenderSetClipRect(renderer, NULL);
    SDL_RenderSetScale(renderer, 1.0f, 1.0f);
    int ok = SDL_RenderCopy(renderer, source, NULL, NULL) == 0;
    SDL_SetRenderTarget(renderer, NULL);
    return ok && SDL_RenderCopy(renderer, intermediate, NULL, NULL) == 0;
}

#endif
