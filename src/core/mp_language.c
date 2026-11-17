#include "core/mp_language.h"

#include "core/config.h"
#include "core/log.h"
#include "core/mp_i18n.h"
#include "game/game.h"
#include "translation/translation.h"

#include <stdio.h>
#include <stdlib.h>

static const struct {
    const char *code;
    const char *name;
    language_type language;
} languages[MP_LANGUAGE_COUNT] = {
    {"ko", "한국어", LANGUAGE_KOREAN},
    {"en", "English", LANGUAGE_ENGLISH},
    {"ru", "Русский", LANGUAGE_RUSSIAN},
    {"de", "Deutsch", LANGUAGE_GERMAN},
    {"es", "Español", LANGUAGE_SPANISH},
    {"fr", "Français", LANGUAGE_FRENCH},
};

const char *mp_language_code(int index)
{
    return index >= 0 && index < MP_LANGUAGE_COUNT ? languages[index].code : "ko";
}

const char *mp_language_native_name(int index)
{
    return index >= 0 && index < MP_LANGUAGE_COUNT ? languages[index].name : "";
}

int mp_language_chosen(void)
{
    int value = config_get(CONFIG_MP_LANGUAGE);
    return value >= 1 && value <= MP_LANGUAGE_COUNT ? value - 1 : -1;
}

/* AUGUSTUS_I18N_DIR/edition.txt (tools/make_release.py --languages): the display languages of this edition, e.g.
 * "ko", "en" or "ko en" (user 2026-11-15: the English edition has English only). Without the file every language
 * whose catalog ships is offered, and Korean always. Returns 1 listed, 0 not listed, -1 no edition file. */
static char edition_text[64];   /* edition.txt as read */

static int edition_lists(int index)
{
    static int state = 0;   /* 0 not read, 1 read, 2 no file */
    char *codes = edition_text;
    if (!state) {
        const char *dir = getenv("AUGUSTUS_I18N_DIR");
        char path[1024];
        FILE *f = 0;
        state = 2;
        if (dir && *dir) {
            snprintf(path, sizeof(path), "%s/edition.txt", dir);
            f = fopen(path, "rb");
        }
        if (f) {
            size_t n = fread(codes, 1, sizeof(edition_text) - 1, f);
            codes[n] = 0;
            fclose(f);
            state = 1;
        }
    }
    if (state != 1) return -1;
    const char *code = languages[index].code;
    for (const char *p = codes; *p; p++) {
        if ((p == codes || p[-1] == ' ' || p[-1] == ',' || p[-1] == '\n' || p[-1] == '\r') && p[0] == code[0] && p[1] == code[1] &&
            (p[2] == 0 || p[2] == ' ' || p[2] == ',' || p[2] == '\n' || p[2] == '\r')) {
            return 1;
        }
    }
    return 0;
}

/* Where language `index` stands in edition.txt (0 when it is not listed or there is no file). */
static const char *edition_position(int index)
{
    if (edition_lists(index) != 1) return 0;
    const char *code = languages[index].code;
    for (const char *p = edition_text; *p; p++) {
        if ((p == edition_text || p[-1] == ' ' || p[-1] == ',' || p[-1] == '\n' || p[-1] == '\r') && p[0] == code[0] && p[1] == code[1] &&
            (p[2] == 0 || p[2] == ' ' || p[2] == ',' || p[2] == '\n' || p[2] == '\r')) {
            return p;
        }
    }
    return 0;
}

int mp_language_available(int index)
{
    static int known[MP_LANGUAGE_COUNT];   /* 0 not checked, 1 yes, 2 no */
    if (index < 0 || index >= MP_LANGUAGE_COUNT) return 0;
    const char *forced = getenv("AUGUSTUS_LANG_FILE");   /* tests: the catalog is given directly */
    if (forced && *forced) return 1;
    if (edition_lists(index) == 0) return 0;
    if (index == 0) return 1;
    if (!known[index]) {
        const char *dir = getenv("AUGUSTUS_I18N_DIR");
        char path[1024];
        FILE *f = 0;
        if (dir && *dir) {
            snprintf(path, sizeof(path), "%s/%s.tsv", dir, languages[index].code);
            f = fopen(path, "rb");
        }
        known[index] = f ? 1 : 2;
        if (f) fclose(f);
    }
    return known[index] == 1;
}

int mp_language_available_count(void)
{
    int count = 0;
    for (int i = 0; i < MP_LANGUAGE_COUNT; i++) count += mp_language_available(i);
    return count;
}

int mp_language_current(void)
{
    int chosen = mp_language_chosen();
    if (chosen >= 0 && mp_language_available(chosen)) return chosen;
    /* Not chosen, or not in this edition: the edition's first language in edition.txt's own order (the Global
     * edition lists English first, user 2026-11-16). Without the file: the first one offered, Korean. */
    if (edition_lists(0) >= 0) {
        int best = -1;
        const char *best_at = 0;
        for (int i = 0; i < MP_LANGUAGE_COUNT; i++) {
            const char *at = edition_position(i);
            if (at && mp_language_available(i) && (!best_at || at < best_at)) {
                best = i;
                best_at = at;
            }
        }
        if (best >= 0) return best;
    }
    for (int i = 0; i < MP_LANGUAGE_COUNT; i++) {   /* not chosen or not in this edition: its first language */
        if (mp_language_available(i)) return i;
    }
    return 0;
}

void mp_language_load(language_type detected, encoding_type encoding)
{
    int index = mp_language_current();
    if (encoding != ENCODING_KOREAN) {
        /* Not our Korean data: the original Augustus behaviour, no catalog. */
        translation_load(detected);
        return;
    }
    /* AUGUSTUS_LANG_FILE (tests) wins; otherwise the catalog of the chosen language. Korean needs none. */
    const char *file = getenv("AUGUSTUS_LANG_FILE");
    char path[1024];
    if (!file || !*file) {
        const char *dir = getenv("AUGUSTUS_I18N_DIR");
        path[0] = 0;
        if (index && dir && *dir) {
            snprintf(path, sizeof(path), "%s/%s.tsv", dir, languages[index].code);
        }
        file = path;
    }
    int entries = mp_i18n_load(file);
    /* After the catalog, never before it: the game's own texts pass through the catalog while they are loaded, so
       switching from Spanish to Korean with the Spanish catalog still in place left 'Cancelar', 'Dificultad' ... in
       the Korean screens until the next start (user 2026-11-14). */
    translation_load(index ? languages[index].language : detected);
    if (*file) {
        log_info("Multiplayer catalog", file, entries);
    }
}

int mp_language_set(int index)
{
    if (index < 0 || index >= MP_LANGUAGE_COUNT || !mp_language_available(index)) {
        return 0;
    }
    int before = config_get(CONFIG_MP_LANGUAGE);
    config_set(CONFIG_MP_LANGUAGE, index + 1);
    if (!game_reload_language()) {
        config_set(CONFIG_MP_LANGUAGE, before);
        game_reload_language();
        return 0;
    }
    config_save();
    return 1;
}
