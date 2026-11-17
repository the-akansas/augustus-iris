/* Keep FILE operations in this executable's CRT. SDL DLLs must not fclose
 * an application-owned FILE (UCRT and MSVCRT have incompatible layouts).
 * Retain file_open's Unicode/long-path handling and streaming music reads. */
#ifdef _WIN32
static Sint64 SDLCALL audio_file_seek(SDL_RWops *rw, Sint64 offset, int whence)
{
    FILE *fp = rw->hidden.unknown.data1;
    if (_fseeki64(fp, offset, whence)) return SDL_SetError("Audio file seek failed");
    return _ftelli64(fp);
}
static Sint64 SDLCALL audio_file_size(SDL_RWops *rw)
{
    FILE *fp = rw->hidden.unknown.data1;
    Sint64 original = _ftelli64(fp);
    if (original < 0 || _fseeki64(fp, 0, SEEK_END)) return -1;
    Sint64 size = _ftelli64(fp);
    if (_fseeki64(fp, original, SEEK_SET)) return -1;
    return size;
}
static size_t SDLCALL audio_file_read(SDL_RWops *rw, void *ptr, size_t size, size_t count)
{
    FILE *fp = rw->hidden.unknown.data1;
    size_t read = fread(ptr, size, count, fp);
    if (read < count && ferror(fp)) SDL_SetError("Audio file read failed");
    return read;
}
static size_t SDLCALL audio_file_write(SDL_RWops *rw, const void *ptr, size_t size, size_t count)
{
    (void) rw; (void) ptr; (void) size; (void) count;
    SDL_SetError("Audio stream is read-only");
    return 0;
}
static int SDLCALL audio_file_close(SDL_RWops *rw)
{
    int result = file_close(rw->hidden.unknown.data1);
    SDL_FreeRW(rw);
    return result;
}
static SDL_RWops *audio_file_open(const char *filename)
{
    FILE *fp = file_open(filename, "rb");
    if (!fp) { SDL_SetError("Cannot open audio file"); return NULL; }
    SDL_RWops *rw = SDL_AllocRW();
    if (!rw) { file_close(fp); return NULL; }
    rw->type = SDL_RWOPS_UNKNOWN;
    rw->size = audio_file_size;
    rw->seek = audio_file_seek;
    rw->read = audio_file_read;
    rw->write = audio_file_write;
    rw->close = audio_file_close;
    rw->hidden.unknown.data1 = fp;
    rw->hidden.unknown.data2 = NULL;
    return rw;
}
#endif
