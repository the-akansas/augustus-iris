#ifndef CREATOR_PRESET_H
#define CREATOR_PRESET_H
#include "game/campaign.h"
#include "game/file.h"
#include "scenario/property.h"
#include "scenario/data.h"
#include "scenario/criteria.h"
#include "scenario/request.h"
#include "scenario/invasion.h"
#include "scenario/price_change.h"
#include "scenario/demand_change.h"
#include "scenario/custom_variable.h"
#include "scenario/custom_messages.h"
#include "scenario/event/controller.h"
#include "scenario/earthquake.h"
#include "scenario/emperor_change.h"
#include "scenario/gladiator_revolt.h"
#include "city/emperor.h"
#include "city/message.h"
#include "city/victory.h"
#include "city/gods.h"
#include "game/tutorial.h"
#include "game/state.h"
#include "game/time.h"
#include "empire/trade_prices.h"
#include "figure/figure.h"
#include "figure/formation.h"
#include "figure/enemy_army.h"
#include "map/grid.h"
#include "map/property.h"
static const char *CREATOR_BUILTIN_MAPS[]={"Caesarea","Carthago","Corinthus","Cyrene","Hierosolyma","Lindum","Londinium","Lugdunum","Mediolanum","Tarraco","Toletum","Valentia"};
static const int CREATOR_BUILTIN_NAMES[]={31,6,15,20,24,25,36,30,4,7,11,16};
static int creator_template_valid(int id){return (id>=0 && id<20) || (id>=100 && id<112);}
static int creator_template_from_mode(const char *mode){
 if(strncmp(mode,"inventory-",10))return -1;char *end;long id=strtol(mode+10,&end,10);
 return *end || !creator_template_valid((int)id)?-2:(int)id;
}
int creator_worker_load_template(int id){
 if(!creator_template_valid(id))return 0;
 if(id<20)return game_campaign_load_scenario(id);
 return game_file_start_scenario_by_name((const uint8_t*)CREATOR_BUILTIN_MAPS[id-100]);
}
/* Only schema 3 opts into a fresh sandbox. Keep terrain, buildings, native villages,
 * resources and entry markers intact; remove every inherited campaign schedule. */
static void creator_reset_mission(int funds){
 game_campaign_clear();
 scenario.settings.is_custom=1;scenario.settings.starting_favor=50;scenario.settings.starting_personal_savings=0;
 memset(&scenario.campaign,0,sizeof(scenario.campaign));scenario.player_rank=0;scenario.caesar_salary=100;
 scenario.start_year=-350;scenario.initial_funds=funds;scenario.rescue_loan=0;
 scenario.rome_supplies_wheat=0;scenario.is_open_play=1;scenario.open_play_scenario_id=0;
 scenario.intro_custom_message_id=0;scenario.victory_custom_message_id=0;scenario.reset_favour_monthly=0;
 memset(scenario.brief_description,0,sizeof(scenario.brief_description));memset(scenario.briefing,0,sizeof(scenario.briefing));
 memset(&scenario.win_criteria,0,sizeof(scenario.win_criteria));
 memset(&scenario.earthquake,0,sizeof(scenario.earthquake));
 memset(&scenario.emperor_change,0,sizeof(scenario.emperor_change));
 memset(&scenario.gladiator_revolt,0,sizeof(scenario.gladiator_revolt));
 memset(&scenario.random_events,0,sizeof(scenario.random_events));
 scenario.random_events.max_wages=45;scenario.random_events.min_wages=5; /* Inactive wage limits have stable SAV defaults. */
 scenario.empire.expansion_year=0;scenario.empire.is_expanded=0;
 scenario.empire.distant_battle_roman_travel_months=0;scenario.empire.distant_battle_enemy_travel_months=0;
 scenario_events_clear();scenario_custom_variable_delete_all();custom_messages_clear_all();
 scenario_request_clear_all();scenario_invasion_clear();scenario_price_change_clear_all();scenario_demand_change_clear_all();
 /* Epoch and event countdowns must agree before saving, including loaded SAV templates. */
 game_time_init(scenario.start_year);scenario_criteria_init_max_year();
 scenario_earthquake_init();scenario_emperor_change_init();scenario_gladiator_revolt_init();
 for(int y=0;y<map_grid_height();y++)for(int x=0;x<map_grid_width();x++)map_property_clear_future_earthquake(map_grid_offset(x,y));
 memset(&city_data.finance,0,sizeof(city_data.finance));city_data.finance.tax_percentage=7;
 city_data.finance.treasury=funds;city_data.finance.last_year.balance=funds;
 city_finance_ledger_init();trade_prices_reset();
 memset(&city_data.emperor,0,sizeof(city_data.emperor));city_emperor_init_scenario(0);
 memset(&city_data.distant_battle,0,sizeof(city_data.distant_battle));
 memset(&city_data.mission,0,sizeof(city_data.mission));
 memset(&city_data.ratings,0,sizeof(city_data.ratings));city_data.ratings.favor=50;
 city_data.labor.wages=30;city_data.labor.wages_rome=30;
 city_data.trade.land_trade_problem_duration=0;city_data.trade.sea_trade_problem_duration=0;
 city_data.trade.months_since_last_land_trade_problem=0;city_data.trade.months_since_last_sea_trade_problem=0;
 city_data.building.months_since_last_destroyed_iron_mine=0;city_data.building.months_since_last_flooded_clay_pit=0;
 city_data.military.native_attack_duration=0;city_gods_reset();
 /* Campaign army state is independent of invasion schedules. Preserve wildlife formations. */
 for(unsigned int i=1;i<figure_count();i++){figure *f=figure_get(i);if(f->state && figure_is_enemy(f))figure_delete(f);}
 for(int i=1;i<formation_count();i++){formation *f=formation_get(i);if(f->in_use && !f->is_herd && !f->is_legion)formation_clear(i);}
 enemy_armies_clear();city_data.figure.enemies=0;city_data.figure.imperial_soldiers=0;
 tutorial_init();city_victory_reset();city_message_init_scenario();game_state_unpause();
}
/* Written for every worker result so tests also audit the state after SAV reload. */
static int creator_export_rules(const char *out){
 char path[2048];snprintf(path,sizeof(path),"%s/rules-audit.json",out);FILE *f=fopen(path,"w");if(!f)return 0;
 int variables=0;for(unsigned int i=0;i<scenario_custom_variable_count();i++)variables+=scenario_custom_variable_exists(i)!=0;
 int random_events=(scenario.random_events.sea_trade_problem!=0)+(scenario.random_events.land_trade_problem!=0)+(scenario.random_events.raise_wages!=0)+(scenario.random_events.lower_wages!=0)+(scenario.random_events.contaminated_water!=0)+(scenario.random_events.iron_mine_collapse!=0)+(scenario.random_events.clay_pit_flooded!=0);
 int enemies=0;for(unsigned int i=1;i<figure_count();i++){figure *q=figure_get(i);enemies+=q->state && figure_is_enemy(q);}
 fprintf(f,"{\"campaign_active\":%d,\"custom\":%d,\"tutorial\":%d,\"year\":%d,\"initial_funds\":%d,\"treasury\":%d,\"events\":%d,\"invasions\":%d,\"requests\":%u,\"price_changes\":%d,\"demand_changes\":%d,\"custom_variables\":%d,\"custom_messages\":%d,\"messages\":%d,\"goals\":[%d,%d,%d,%d,%d],\"time_limit\":%d,\"survival_time\":%d,\"earthquake\":%d,\"emperor_change\":%d,\"gladiator_revolt\":%d,\"random_events\":%d,\"expansion_year\":%d,\"distant_battle\":%d,\"rescue_loan\":%d,\"debt\":%d,\"savings\":%d,\"salary\":%d,\"enemy_figures\":%d,\"population\":%d}",
 game_campaign_is_active(),scenario_is_custom(),scenario_is_tutorial_1()||scenario_is_tutorial_2()||scenario_is_tutorial_3(),game_time_year(),scenario.initial_funds,city_finance_treasury(),scenario_events_get_count(),scenario_invasion_count_active(),scenario_request_count_active(),scenario_price_change_count_active(),scenario_demand_change_count_active(),variables,custom_messages_count(),city_message_count(),scenario.win_criteria.population.enabled,scenario.win_criteria.culture.enabled,scenario.win_criteria.prosperity.enabled,scenario.win_criteria.peace.enabled,scenario.win_criteria.favor.enabled,scenario.win_criteria.time_limit.enabled,scenario.win_criteria.survival_time.enabled,scenario.earthquake.severity,scenario.emperor_change.enabled,scenario.gladiator_revolt.enabled,random_events,scenario.empire.expansion_year,city_data.distant_battle.total_count,scenario.rescue_loan,city_data.emperor.debt_state,city_data.emperor.personal_savings,city_data.emperor.salary_amount,enemies,city_data.population.population);
 if(fclose(f)!=0)return 0;
 snprintf(path,sizeof(path),"%s/governance-audit.json",out);f=fopen(path,"w");if(!f)return 0;
 /* Salary display in the editor: the base this start really uses and the engine's own amount for every rank
  * (city_emperor_salary_for_rank), so no salary table is copied outside the engine. Read-only. */
 fprintf(f,"{\"rank\":%d,\"salary_rank\":%d,\"savings\":%d,\"favor\":%d,\"policy_code\":%d,\"caesar_salary\":%d,\"salary_amount\":%d,\"salary_for_rank\":[",city_data.emperor.player_rank,city_data.emperor.salary_rank,city_data.emperor.personal_savings,city_data.ratings.favor,scenario.reset_favour_monthly,city_data.emperor.caesar_salary,city_data.emperor.salary_amount);
 for(int r=0;r<=10;r++)fprintf(f,"%s%d",r?",":"",city_emperor_salary_for_rank(r));
 fputs("]}",f);
 return fclose(f)==0;
}
#endif
