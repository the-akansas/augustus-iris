#include "windows_paths.h"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
static wchar_t *game_base;

wchar_t *augustus_windows_path(const char *path)
{
    if (!path || !*path) { errno = EINVAL; return NULL; }
    int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
    if (!n) { errno = EILSEQ; return NULL; }
    wchar_t *input = malloc((size_t)n * sizeof(wchar_t));
    if (!input) return NULL;
    MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, input, n);
    for (int i = 0; i < n; i++) if (input[i] == L'/') input[i] = L'\\';
    /* SDL joins its trailing base separator with /assets. Extended paths
       bypass Win32 normalization, so normalize before restoring the prefix. */
    if (!wcsncmp(input, L"\\\\?\\UNC\\", 8)) {
        memmove(input + 2, input + 8, (wcslen(input + 8) + 1) * sizeof(wchar_t));
        input[0] = input[1] = L'\\';
    } else if (!wcsncmp(input, L"\\\\?\\", 4)) {
        memmove(input, input + 4, (wcslen(input + 4) + 1) * sizeof(wchar_t));
    }
    if (game_base && input[0] != L'\\' && !(n > 2 && input[1] == L':')) {
        size_t size = wcslen(game_base) + wcslen(input) + 2;
        wchar_t *joined = malloc(size * sizeof(wchar_t));
        if (!joined) { free(input); return NULL; }
        wcscpy(joined, game_base); wcscat(joined, L"\\"); wcscat(joined, input);
        free(input); input = joined;
    }
    DWORD size = GetFullPathNameW(input, 0, NULL, NULL);
    if (!size || size > 32760) { free(input); errno = ENAMETOOLONG; return NULL; }
    wchar_t *full = malloc((size_t)size * sizeof(wchar_t));
    if (!full) { free(input); return NULL; }
    DWORD got = GetFullPathNameW(input, size, full, NULL);
    free(input);
    if (!got || got >= size) { free(full); errno = EINVAL; return NULL; }
    if (!wcsncmp(full, L"\\\\?\\", 4)) return full;
    int unc = full[0] == L'\\' && full[1] == L'\\';
    size_t length = wcslen(full) + (unc ? 6 : 4) + 1;
    wchar_t *result = malloc(length * sizeof(wchar_t));
    if (result) {
        wcscpy(result, unc ? L"\\\\?\\UNC\\" : L"\\\\?\\");
        wcscat(result, full + (unc ? 2 : 0));
    }
    free(full);
    return result;
}

int augustus_windows_set_base(const char *path)
{
    wchar_t *wide = augustus_windows_path(path);
    if (!wide) return 0;
    DWORD attr = GetFileAttributesW(wide);
    if (attr == INVALID_FILE_ATTRIBUTES || !(attr & FILE_ATTRIBUTE_DIRECTORY)) {
        free(wide); return 0;
    }
    /* Win32 still rejects a long process CWD even with an extended path.
       Resolve game-relative I/O against an explicit base instead. */
    if (!SetCurrentDirectoryW(wide) && GetLastError() != ERROR_FILENAME_EXCED_RANGE) {
        free(wide); return 0;
    }
    wchar_t *base = malloc((wcslen(wide) + 1) * sizeof(wchar_t));
    if (!base) { free(wide); return 0; }
    if (!wcsncmp(wide, L"\\\\?\\UNC\\", 8)) {
        wcscpy(base, L"\\\\"); wcscat(base, wide + 8);
    } else wcscpy(base, wide + 4);
    free(game_base); game_base = base; free(wide); return 1;
}

FILE *__wrap_fopen(const char *path, const char *mode)
{
    wchar_t *wide = augustus_windows_path(path), wmode[32];
    if (!wide) return NULL;
    if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, mode, -1, wmode, 32)) {
        free(wide); errno = EINVAL; return NULL;
    }
    FILE *file = _wfopen(wide, wmode);
    free(wide);
    return file;
}

int __wrap_remove(const char *path)
{
    wchar_t *wide = augustus_windows_path(path);
    if (!wide) return -1;
    int result = _wremove(wide);
    free(wide);
    return result;
}

int __wrap_rename(const char *from, const char *to)
{
    wchar_t *a = augustus_windows_path(from), *b = augustus_windows_path(to);
    int result = a && b ? _wrename(a, b) : -1;
    free(a); free(b);
    return result;
}

int augustus_move_file(const char *from, const char *to, unsigned long flags)
{
    wchar_t *a = augustus_windows_path(from), *b = augustus_windows_path(to);
    int result = a && b && MoveFileExW(a, b, flags);
    free(a); free(b); return result;
}
