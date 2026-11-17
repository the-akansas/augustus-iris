#ifndef CORE_MP_LANGUAGE_H
#define CORE_MP_LANGUAGE_H

#include "core/encoding.h"
#include "core/locale.h"

/* Display language of the multilingual build (docs/다국어-설계-20261113.md). The game keeps running on the Korean data
 * and encoding; the chosen language only decides which Augustus translation table and which multiplayer catalog
 * (i18n/<code>.tsv, from AUGUSTUS_I18N_DIR) are used. Config value: 0 = not chosen yet, else 1 + index below. */

#define MP_LANGUAGE_COUNT 6

const char *mp_language_code(int index);        /* "ko", "en", "ru", "de", "es", "fr" */
const char *mp_language_native_name(int index); /* UTF-8, in its own language */
int mp_language_chosen(void);                   /* index, or -1 when the player has not chosen yet */
int mp_language_current(void);                  /* index in use (the edition's first language when not chosen or not shipped) */
/* Editions (user 2026-11-14): a language is offered only when its catalog ships with the game
 * (AUGUSTUS_I18N_DIR/<code>.tsv) and the edition lists it (edition.txt, 2026-11-15: the English edition has no
 * Korean). Without edition.txt Korean always is. One language: no language choice at all. */
int mp_language_available(int index);
int mp_language_available_count(void);
/* Loads the Augustus translation table and the multiplayer catalog for the current choice. */
void mp_language_load(language_type detected, encoding_type encoding);
/* Saves the choice and reloads the texts. Returns 1 on success. */
int mp_language_set(int index);

#endif
