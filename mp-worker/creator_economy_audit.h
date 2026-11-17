/* Measurement only (Claude 2026-11-12, mode "economy-ticks"): what the city's own finance records say after a run
 * of plain game ticks. No building, no money added, no rule changed: the mode only runs game_tick_run() like
 * "military-ticks" and then writes economy-audit.json next to the usual outputs.
 * this_year / last_year are the engine's own yearly finance overviews (cumulative inside the year; the yearly
 * rollover moves this_year to last_year). Monthly figures are differences of these records, taken by the caller.
 * Before writing, the same three finance refreshes the finance advisor runs when opened are run, so this_year shows
 * what the advisor would show. They only fill derived fields and run after city.sav has been written. */
static void economy_overview(FILE *f, const char *name, const finance_overview *o)
{
    fprintf(f, "\"%s\":{\"taxes\":%d,\"exports\":%d,\"donated\":%d,\"income_total\":%d,"
        "\"imports\":%d,\"wages\":%d,\"construction\":%d,\"interest\":%d,\"salary\":%d,\"sundries\":%d,"
        "\"tribute\":%d,\"levies\":%d,\"expenses_total\":%d,\"net_in_out\":%d,\"balance\":%d}",
        name, o->income.taxes, o->income.exports, o->income.donated, o->income.total,
        o->expenses.imports, o->expenses.wages, o->expenses.construction, o->expenses.interest, o->expenses.salary,
        o->expenses.sundries, o->expenses.tribute, o->expenses.levies, o->expenses.total, o->net_in_out, o->balance);
}
static int economy_audit(const char *out)
{
    char path[2048];
    city_finance_estimate_taxes();
    city_finance_estimate_wages();
    city_finance_calculate_totals();
    snprintf(path, sizeof(path), "%s/economy-audit.json", out);
    FILE *f = fopen(path, "w");
    if (!f) return 0;
    fprintf(f, "{\"year\":%d,\"month\":%d,\"day\":%d,\"tick\":%d,\"treasury\":%d,\"tax_percentage\":%d,"
        "\"estimated_tax_income\":%d,\"estimated_wages\":%d,\"wages_so_far\":%d,\"salary_so_far\":%d,"
        "\"interest_so_far\":%d,\"levies_so_far\":%d,\"wage_rate\":%d,\"population\":%d,"
        "\"workers_employed\":%d,\"workers_needed\":%d,\"unemployment_percentage\":%d,",
        game_time_year(), game_time_month(), game_time_day(), game_time_tick(), city_data.finance.treasury,
        city_data.finance.tax_percentage, city_data.finance.estimated_tax_income, city_data.finance.estimated_wages,
        city_data.finance.wages_so_far, city_data.finance.salary_so_far, city_data.finance.interest_so_far,
        city_data.finance.levies_so_far, city_data.labor.wages, city_data.population.population,
        city_data.labor.workers_employed, city_data.labor.workers_needed, city_data.labor.unemployment_percentage);
    economy_overview(f, "this_year", &city_data.finance.this_year);
    fputc(',', f);
    economy_overview(f, "last_year", &city_data.finance.last_year);
    fputc('}', f);
    return fclose(f) == 0;
}
