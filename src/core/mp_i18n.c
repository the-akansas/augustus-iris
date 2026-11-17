#include "core/mp_i18n.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_SLOTS 8
#define RESULT_SIZE 4096
#define RESULTS 16

typedef struct {
    char *key, *value;
    unsigned hash;
} exact_entry;

typedef struct {
    char *pieces[MAX_SLOTS + 1];   /* literal text around the slots (pieces[slots] may be "") */
    int slots, order[MAX_SLOTS];   /* order[i]: the {n} number of the i-th slot in the key */
    int literal_length;
    char *value;
} template_entry;

static struct {
    int loaded, tried, suspended;
    exact_entry *table; int capacity, count;
    template_entry *templates; int template_count;
    char results[RESULTS][RESULT_SIZE]; char inputs[RESULTS][RESULT_SIZE]; int next;
} data;

static unsigned hash_text(const char *s)
{
    unsigned h = 2166136261u;
    while (*s) { h ^= (unsigned char) *s++; h *= 16777619u; }
    return h ? h : 1;
}

static char *dup(const char *s, size_t n)
{
    char *out = malloc(n + 1);
    if (out) { memcpy(out, s, n); out[n] = 0; }
    return out;
}

static char *unescape(const char *s, size_t n)
{
    char *out = malloc(n + 1), *o = out;
    if (!out) return 0;
    for (size_t i = 0; i < n; i++) {
        if (s[i] == '\\' && i + 1 < n) {
            char c = s[++i];
            *o++ = c == 'n' ? '\n' : c == 't' ? '\t' : c;
        } else *o++ = s[i];
    }
    *o = 0;
    return out;
}

/* Length of a slot starting at s (printf spec or {n}), 0 if none; *number gets n for {n}, -1 for printf. */
static int slot_at(const char *s, int *number)
{
    if (s[0] == '{' && s[1] >= '0' && s[1] <= '9') {
        int i = 1, n = 0;
        while (s[i] >= '0' && s[i] <= '9') n = n * 10 + (s[i++] - '0');
        if (s[i] == '}') { *number = n; return i + 1; }
        return 0;
    }
    if (s[0] != '%' || s[1] == '%') return 0;
    int i = 1;
    while (strchr("-+ #0", s[i]) && s[i]) i++;
    while (s[i] >= '0' && s[i] <= '9') i++;
    if (s[i] == '.') { i++; while (s[i] >= '0' && s[i] <= '9') i++; }
    while (s[i] == 'l' || s[i] == 'h' || s[i] == 'z') i++;
    if (s[i] && strchr("diuxXsScfgeEp", s[i])) { *number = -1; return i + 1; }
    return 0;
}

static void add_exact(char *key, char *value)
{
    if (data.count * 2 >= data.capacity) {
        int capacity = data.capacity ? data.capacity * 2 : 1024;
        exact_entry *table = calloc(capacity, sizeof(exact_entry));
        if (!table) return;
        for (int i = 0; i < data.capacity; i++) {
            if (!data.table[i].key) continue;
            int j = data.table[i].hash & (capacity - 1);
            while (table[j].key) j = (j + 1) & (capacity - 1);
            table[j] = data.table[i];
        }
        free(data.table); data.table = table; data.capacity = capacity;
    }
    unsigned h = hash_text(key);
    int j = h & (data.capacity - 1);
    while (data.table[j].key) {
        if (data.table[j].hash == h && !strcmp(data.table[j].key, key)) { free(key); free(value); return; }
        j = (j + 1) & (data.capacity - 1);
    }
    data.table[j].key = key; data.table[j].value = value; data.table[j].hash = h; data.count++;
}

static int add_template(char *key, char *value)
{
    template_entry t = {0};
    const char *p = key, *start = key;
    int printf_slots = 0;
    while (*p) {
        int number, n = slot_at(p, &number);
        if (!n) { p += (p[0] == '%' && p[1] == '%') ? 2 : 1; continue; }
        if (t.slots == MAX_SLOTS) return 0;
        t.pieces[t.slots] = dup(start, p - start);
        t.order[t.slots] = number >= 0 ? number : printf_slots;
        if (number < 0) printf_slots++;
        t.slots++;
        p += n; start = p;
    }
    if (!t.slots) return 0;
    t.pieces[t.slots] = dup(start, p - start);
    for (int i = 0; i <= t.slots; i++) {
        if (!t.pieces[i]) return 0;
        /* %% in a printf key stands for % in the text */
        char *s = t.pieces[i], *d = s;
        for (; *s; s++) { *d++ = *s; if (s[0] == '%' && s[1] == '%') s++; }
        *d = 0;
        t.literal_length += (int) strlen(t.pieces[i]);
    }
    t.value = value;
    template_entry *grown = realloc(data.templates, (data.template_count + 1) * sizeof(template_entry));
    if (!grown) return 0;
    data.templates = grown;
    data.templates[data.template_count++] = t;
    free(key);
    return 1;
}

static int by_specificity(const void *a, const void *b)
{
    return ((const template_entry *) b)->literal_length - ((const template_entry *) a)->literal_length;
}

static void unload(void)
{
    for (int i = 0; i < data.capacity; i++) { free(data.table[i].key); free(data.table[i].value); }
    for (int i = 0; i < data.template_count; i++) {
        for (int k = 0; k <= data.templates[i].slots; k++) free(data.templates[i].pieces[k]);
        free(data.templates[i].value);
    }
    free(data.table); free(data.templates);
    memset(&data, 0, sizeof(data));
}

int mp_i18n_load(const char *path)
{
    unload();
    data.tried = 1;
    if (!path || !*path) return 0;
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    char line[16384];
    int entries = 0;
    while (fgets(line, sizeof(line), f)) {
        size_t n = strlen(line);
        while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
        if (!n || line[0] == '#') continue;
        char *tab = strchr(line, '\t');
        if (!tab || !tab[1]) continue;              /* untranslated: keep the Korean text */
        char *key = unescape(line, tab - line), *value = unescape(tab + 1, strlen(tab + 1));
        if (!key || !value || !*key) { free(key); free(value); continue; }
        int number;
        int has_slot = 0;
        for (const char *p = key; *p; p++) if (slot_at(p, &number)) { has_slot = 1; break; }
        if (has_slot ? add_template(key, value) : (add_exact(key, value), 1)) entries++;
        else { free(key); free(value); }
    }
    fclose(f);
    qsort(data.templates, data.template_count, sizeof(template_entry), by_specificity);
    data.loaded = entries > 0;
    return entries;
}

static void ensure_loaded(void)
{
    if (data.tried) return;
    mp_i18n_load(getenv("AUGUSTUS_LANG_FILE"));
}

int mp_i18n_active(void)
{
    ensure_loaded();
    return data.loaded && !data.suspended;
}

void mp_i18n_suspend(int on) { data.suspended += on ? 1 : (data.suspended > 0 ? -1 : 0); }
int mp_i18n_suspended(void) { return data.suspended; }

static const char *exact(const char *s)
{
    if (!data.capacity) return 0;
    unsigned h = hash_text(s);
    int j = h & (data.capacity - 1);
    while (data.table[j].key) {
        if (data.table[j].hash == h && !strcmp(data.table[j].key, s)) return data.table[j].value;
        j = (j + 1) & (data.capacity - 1);
    }
    return 0;
}

static int translate_line(const char *line, size_t length, char *out, size_t size, int depth);

static size_t copy_text(const char *s, size_t length, char *out, size_t size)
{
    if (!size) return 0;
    size_t c = length < size - 1 ? length : size - 1;
    memcpy(out, s, c); out[c] = 0;
    return c;
}

/* The text filled into a slot, shown in the reader's language (2026-11-14): a known text ("밀"), a list of known
 * texts ("밀, 보리" or "밀·보리"), or a text that itself fits a template ("로마 [방장]", tried before the list). Numbers, player names and
 * anything unknown stay as they are. depth stops nested slots after four levels. */
static size_t translate_slot(const char *s, size_t length, char *out, size_t size, int depth)
{
    char word[RESULT_SIZE];
    if (!size) return 0;
    if (length >= sizeof(word)) return copy_text(s, length, out, size);
    memcpy(word, s, length); word[length] = 0;
    const char *known = exact(word);
    if (known) return copy_text(known, strlen(known), out, size);
    int wide = 0;
    for (size_t i = 0; i < length; i++) if ((unsigned char) word[i] >= 0x80) { wide = 1; break; }
    if (!wide || depth >= 4) return copy_text(s, length, out, size);
    /* A sentence of its own first: "A · B" may be one whole template (2026-11-14: "철수 공물 3,000 Dn · 황제군 철수 ·
     * 편집증 -80" was cut into list items and stayed Korean). Only then a list. */
    if (translate_line(word, length, out, size, depth + 1)) return strlen(out);
    /* a list: translate every item, keep the separators and the blanks around the items. Items are split at ", "
     * when there is one (an item such as "게임 설정·단축키" keeps its "·"), otherwise at "·". */
    const char *separator = strstr(word, ", ") ? ", " : strstr(word, "\xc2\xb7") ? "\xc2\xb7" : 0;
    if (separator) {
        size_t o = 0; const char *p = word, *end = word + length;
        int changed = 0;
        while (p <= end && o + 1 < size) {
            const char *sep = strstr(p, separator);
            const char *stop = sep ? sep : end;
            const char *x = p, *y = stop;
            while (x < y && *x == ' ') x++;
            while (y > x && y[-1] == ' ') y--;
            o += copy_text(p, (size_t) (x - p), out + o, size - o);
            if (y > x) {
                char item[RESULT_SIZE];
                size_t n = translate_slot(x, (size_t) (y - x), item, sizeof(item), depth + 1);
                if (n != (size_t) (y - x) || memcmp(item, x, n)) changed = 1;
                o += copy_text(item, n, out + o, size - o);
            }
            o += copy_text(y, (size_t) (stop - y), out + o, size - o);
            if (!sep) break;
            o += copy_text(sep, 2, out + o, size - o);   /* ", " and "·" are both two bytes long */
            p = sep + 2;
        }
        if (changed) return o;
    }
    return copy_text(s, length, out, size);
}

/* Fill out with the translation of one line, 1 if translated. */
static int translate_line(const char *line, size_t length, char *out, size_t size, int depth)
{
    char text[RESULT_SIZE];
    if (length >= sizeof(text)) return 0;
    memcpy(text, line, length); text[length] = 0;
    const char *found = exact(text);
    if (found) { snprintf(out, size, "%s", found); return 1; }
    for (int i = 0; i < data.template_count; i++) {
        template_entry *t = &data.templates[i];
        const char *p = text, *slot_start[MAX_SLOTS]; size_t slot_length[MAX_SLOTS];
        size_t first = strlen(t->pieces[0]);
        if (strncmp(p, t->pieces[0], first)) continue;
        p += first;
        int ok = 1;
        for (int k = 0; k < t->slots && ok; k++) {
            const char *next = t->pieces[k + 1];
            const char *end;
            if (k + 1 == t->slots) {
                size_t tail = strlen(next), rest = strlen(p);
                end = rest >= tail && !strcmp(p + rest - tail, next) ? p + rest - tail : 0;
            } else end = *next ? strstr(p + 1, next) : 0;
            if (!end || end == p) { ok = 0; break; }
            slot_start[k] = p; slot_length[k] = end - p;
            p = end + strlen(next);
        }
        if (!ok || (t->slots && *p)) continue;
        /* write the value, {n} = the n-th slot of the key */
        size_t o = 0;
        for (const char *v = t->value; *v && o + 1 < size;) {
            int number, n = v[0] == '{' ? slot_at(v, &number) : 0;
            if (n && number >= 0) {
                for (int k = 0; k < t->slots; k++) if (t->order[k] == number) {
                    /* A value that is itself a known text (a Korean word filled into a sentence, such as
                     * "사겠다" in "...%s고 합니다") is shown translated too. Numbers and names stay as they are. */
                    o += translate_slot(slot_start[k], slot_length[k], out + o, size - o, depth);
                    break;
                }
                v += n;
            } else out[o++] = *v++;
        }
        out[o] = 0;
        return 1;
    }
    return 0;
}

const char *mp_i18n_translate(const char *utf8)
{
    if (!utf8 || !*utf8 || !mp_i18n_active()) return utf8;
    for (int i = 0; i < RESULTS; i++) if (!strcmp(data.inputs[i], utf8)) return data.results[i];
    char out[RESULT_SIZE]; size_t o = 0; int changed = 0;
    const char *line = utf8;
    while (1) {
        const char *end = strchr(line, '\n');
        size_t length = end ? (size_t) (end - line) : strlen(line);
        char piece[RESULT_SIZE];
        if (translate_line(line, length, piece, sizeof(piece), 0)) {
            changed = 1;
            size_t c = strlen(piece);
            if (o + c >= sizeof(out)) return utf8;
            memcpy(out + o, piece, c); o += c;
        } else {
            if (o + length >= sizeof(out)) return utf8;
            memcpy(out + o, line, length); o += length;
        }
        if (!end) break;
        if (o + 1 >= sizeof(out)) return utf8;
        out[o++] = '\n';
        line = end + 1;
    }
    out[o] = 0;
    if (!changed || strlen(utf8) >= RESULT_SIZE) return utf8;
    int slot = data.next++ % RESULTS;
    snprintf(data.inputs[slot], RESULT_SIZE, "%s", utf8);
    snprintf(data.results[slot], RESULT_SIZE, "%s", out);
    return data.results[slot];
}
