#include "army_seal.h"

#include "building/building.h"
#include "core/log.h"
#include "figure/figure.h"
#include "figure/formation.h"

/* Sealed army dispatch (user 2026-11-14: "no effect in the game"): older saves can still hold what the dispatch
 * left behind. Called once when a save is loaded, before anything else looks at the legions.
 *  - another player's legion on this map (visiting support or attack force): removed with its soldiers;
 *  - this city's legion that was away: it becomes an ordinary legion again. With its fort still standing it waits
 *    there for new recruits; with the fort gone (it could never come back, user's 25th joint save) it is removed,
 *    so it no longer takes one of the legion places.
 * The soldiers that were away do not come back: the room closes those expeditions too (Augustus/army_live.py). */
int mp_army_seal_release(void)
{
#if MP_ARMY_DISPATCH_SEALED
    int released = 0;
    for (int i = 1; i < formation_count(); i++) {
        formation *m = formation_get(i);
        if (!m->in_use || (!m->mp_expedition_id && !m->mp_expedition_role)) {
            continue;
        }
        int keep = 0;
        if (!m->mp_expedition_role && m->is_legion && m->building_id > 0 && m->building_id < (int) building_count()) {
            const building *fort = building_get(m->building_id);
            keep = fort->state == BUILDING_STATE_IN_USE && fort->formation_id == i;
        }
        if (!keep) {
            for (unsigned int j = 1; j < figure_count(); j++) {
                figure *f = figure_get(j);
                if (f->state && f->formation_id == (unsigned) i) {
                    figure_delete(f);
                }
            }
        }
        m->mp_expedition_id = 0;
        m->mp_expedition_role = 0;
        if (keep) {
            m->is_at_fort = 1;
            m->in_distant_battle = 0;
        } else {
            formation_clear(i);
        }
        released++;
    }
    if (released) {
        formation_calculate_figures();
        formation_calculate_legion_totals();
        log_info("Sealed army dispatch: released legions", 0, released);
    }
    return released;
#else
    return 0;
#endif
}
