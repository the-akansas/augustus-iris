#ifndef AUGUSTUS_WINDOWS_PATHS_H
#define AUGUSTUS_WINDOWS_PATHS_H
#include <wchar.h>
/* Allocated, absolute extended Win32 path. Caller frees; invalid UTF-8 fails. */
wchar_t *augustus_windows_path(const char *path);
int augustus_move_file(const char *from, const char *to, unsigned long flags);
int augustus_windows_set_base(const char *path);
#endif
