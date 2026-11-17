#ifndef CORE_MP_I18N_H
#define CORE_MP_I18N_H

/* Multilingual display of the Korean texts we added (docs/다국어-설계-20261113.md).
 * The Korean source text is the key. A catalog (UTF-8, one "korean<TAB>translation" per line, \n \t \\ escaped) is
 * named by AUGUSTUS_LANG_FILE; without it nothing changes. Slots: C printf (%d %s ...) or {0} {1} ... in the key;
 * the translation uses {0} {1} ... in any order. Unknown text is shown as it is (Korean). */

int mp_i18n_active(void);
/* The translation of a whole UTF-8 text (line by line), or the text itself. The pointer stays valid until the next
 * call with a different text (a small ring of results). */
const char *mp_i18n_translate(const char *utf8);
/* Player chat must never be translated: callers wrap it. Nested calls are counted. */
void mp_i18n_suspend(int on);
int mp_i18n_suspended(void);
/* Tests: load a catalog from a path (0 = unload). Returns entries loaded, -1 on error. */
int mp_i18n_load(const char *path);

#endif
