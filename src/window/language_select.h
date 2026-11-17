#ifndef WINDOW_LANGUAGE_SELECT_H
#define WINDOW_LANGUAGE_SELECT_H

/* First run of the multilingual build: pick the display language (later: options, General page).
 * done() is called after the choice was saved and the texts reloaded. */
void window_language_select_show(void (*done)(void));

#endif
