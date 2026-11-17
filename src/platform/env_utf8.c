/* Environment variables as UTF-8 on Windows (2026-11-14).
 *
 * The launcher hands folders to the game in environment variables (AUGUSTUS_MP_BRIDGE, AUGUSTUS_KO_USER_PATH,
 * AUGUSTUS_I18N_DIR, AUGUSTUS_CITY_VISIT ...). The game opens files with UTF-8 paths (platform/windows_paths.c),
 * but the C runtime's getenv() returns the value in the PC's ANSI code page. A package unpacked under a folder with
 * non-English letters (the Desktop of a Windows user whose name is in Korean, Russian, German ...) then could not
 * open its bridge, profile or catalog files.
 *
 * This file defines getenv() for the whole executable: the value is read with the wide Windows call and returned
 * as UTF-8. Every getenv("...") in the game, old or new, goes through it without being changed. Values are kept
 * for the life of the process (callers hold the pointer, as with the C runtime's own getenv); a value that
 * changed is read again and the earlier text is left alone.
 *
 * Other systems: nothing here, the C library's getenv() already returns the bytes the launcher wrote. */
#ifdef _WIN32

#include <windows.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    char *name;
    wchar_t *wide;
    char *utf8;
} env_slot;

static env_slot *slots;
static int slot_count;
static int slot_room;
static SRWLOCK slot_lock = SRWLOCK_INIT;

static env_slot *find_slot(const char *name)
{
    for (int i = 0; i < slot_count; i++) {
        if (strcmp(slots[i].name, name) == 0) {
            return &slots[i];
        }
    }
    return 0;
}

static env_slot *add_slot(const char *name)
{
    if (slot_count == slot_room) {
        int room = slot_room ? slot_room * 2 : 32;
        env_slot *grown = realloc(slots, (size_t) room * sizeof(env_slot));
        if (!grown) {
            return 0;
        }
        slots = grown;
        slot_room = room;
    }
    size_t length = strlen(name) + 1;
    char *copy = malloc(length);
    if (!copy) {
        return 0;
    }
    memcpy(copy, name, length);
    env_slot *slot = &slots[slot_count++];
    slot->name = copy;
    slot->wide = 0;
    slot->utf8 = 0;
    return slot;
}

char *getenv(const char *name)
{
    if (!name || !*name) {
        return 0;
    }
    wchar_t wide_name[256];
    if (!MultiByteToWideChar(CP_UTF8, 0, name, -1, wide_name, 256)) {
        return 0;
    }
    SetLastError(ERROR_SUCCESS);
    DWORD size = GetEnvironmentVariableW(wide_name, 0, 0);
    if (!size && GetLastError() == ERROR_ENVVAR_NOT_FOUND) {
        return 0;
    }
    wchar_t *wide = malloc(((size_t) size + 1) * sizeof(wchar_t));
    if (!wide) {
        return 0;
    }
    wide[0] = 0;
    DWORD got = size ? GetEnvironmentVariableW(wide_name, wide, size + 1) : 0;
    if (got > size) {   /* changed between the two calls: the next call reads it again */
        free(wide);
        return 0;
    }
    wide[got] = 0;

    char *result = 0;
    AcquireSRWLockExclusive(&slot_lock);
    env_slot *slot = find_slot(name);
    if (slot && slot->wide && wcscmp(slot->wide, wide) == 0) {
        result = slot->utf8;
        free(wide);
    } else {
        int bytes = WideCharToMultiByte(CP_UTF8, 0, wide, -1, 0, 0, 0, 0);
        char *utf8 = bytes > 0 ? malloc((size_t) bytes) : 0;
        if (utf8 && WideCharToMultiByte(CP_UTF8, 0, wide, -1, utf8, bytes, 0, 0)) {
            if (!slot) {
                slot = add_slot(name);
            }
            if (slot) {
                free(slot->wide);        /* the earlier utf8 text is not freed: a caller may still hold it */
                slot->wide = wide;
                slot->utf8 = utf8;
                result = utf8;
            } else {
                result = utf8;           /* no room to remember it: still a valid answer */
                free(wide);
            }
        } else {
            free(utf8);
            free(wide);
        }
    }
    ReleaseSRWLockExclusive(&slot_lock);
    return result;
}

#else

/* Keeps the file non-empty for compilers that warn about an empty translation unit. */
typedef int augustus_env_utf8_unused;

#endif
