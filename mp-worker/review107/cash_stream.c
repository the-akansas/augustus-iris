#include "multiplayer/post_runtime.h"
#include "multiplayer/post_city.h"
#include "city/finance.h"
#include "city/data_private.h"
#include "game/file_io.h"
#include "multiplayer/transport.h"
#include "multiplayer/clock.h"
#include "building/building.h"
#include "building/state.h"
#include "building/storage.h"
#include "building/construction_building.h"
#include "building/figure.h"
#include "building/properties.h"
#include "building/warehouse.h"
#include "building/granary.h"
#include "figuretype/trader.h"
#include "map/building.h"
#include "map/grid.h"
#include "map/terrain.h"
#include "map/routing_terrain.h"
#include "map/routing.h"
#include "map/road_access.h"
#include "city/map.h"
#include "city/resource.h"
#include "city/view.h"
#include "empire/city.h"
#include "empire/trade_route.h"
#include "empire/trade_prices.h"
#include "window/city.h"
#include "game/game.h"
#include "game/time.h"
#include "game/animation.h"
#include "platform/renderer.h"
#include "core/time.h"
#include <SDL.h>
#include "game/tick.h"
#include "scenario/data.h"
#include "scenario/map.h"
#include "building/dock.h"
#include "figuretype/docker.h"
#define army_allocate figure_create
#include "multiplayer/expedition_native.h"
#undef army_allocate
void mp_army_test_allocation_budget(int n);
#include "figuretype/soldier.h"
#include <stdlib.h>
#include <stdio.h>
static int fixture_resource=RESOURCE_POTTERY;
static long long simulation_cash_delta, simulation_stock_delta;
static int npc_city, npc_route, render_started;
static void seed_npc(int importing) {
    empire_city *c=empire_city_get_new();
    for(int i=1;i<empire_city_get_array_size();i++)if(empire_city_get(i)==c){npc_city=i;break;}
    c->in_use=1;c->type=EMPIRE_CITY_TRADE;c->is_open=1;c->is_sea_trade=0;
    npc_route=c->route_id=trade_route_new();trade_route_set_open(npc_route);
    c->buys_resource[fixture_resource]=!importing;c->sells_resource[fixture_resource]=importing;
    trade_route_set_limit(npc_route,fixture_resource,4,!importing);
    city_data.resource.trade_status[fixture_resource]=0;
    city_resource_cycle_trade_status(fixture_resource,importing?TRADE_STATUS_IMPORT:TRADE_STATUS_EXPORT);
    city_resource_change_import_over(fixture_resource,32-city_resource_import_over(fixture_resource));
    city_resource_change_export_over(fixture_resource,-city_resource_export_over(fixture_resource));
    city_resource_calculate_warehouse_stocks();
    for(unsigned i=1;i<building_count();i++){building *b=building_get(i);if(b->type==BUILDING_WAREHOUSE && !building_storage_get_permission(BUILDING_STORAGE_PERMISSION_TRADERS,b))building_storage_toggle_permission(BUILDING_STORAGE_PERMISSION_TRADERS,b);}
    const map_tile *entry=city_map_entry_point();
    c->trader_figure_ids[0]=figure_create_trade_caravan(entry->x,entry->y,npc_city);
}
/* The headless worker never opens windows; production links the real dialog. */
void window_multiplayer_trade_show_for_post(unsigned id){(void)id;}
void window_multiplayer_transport_show(void){}
static int stock(void) {
    int n=0;for(unsigned i=1;i<building_count();i++)if(building_get(i)->type==BUILDING_WAREHOUSE)
        n+=building_warehouse_get_amount(building_get(i),fixture_resource);
    for(unsigned i=1;i<building_count();i++)if(building_get(i)->type==BUILDING_GRANARY)n+=building_granary_get_amount(building_get(i),fixture_resource);
    return n;
}
static int sea_fixture;
static int catalog_fighter;
static int army_fixture;
static void army_rest(void){for(unsigned i=1;i<building_count();i++){building *b=building_get(i);if(b->type==BUILDING_PLAYER_TRADE_POST && b->state==BUILDING_STATE_IN_USE){b->num_workers=5;b->houses_covered=100;}}if(!army_fixture)return;for(int i=1;i<formation_count();i++){formation *m=formation_get(i);if(m->in_use && m->is_legion && !m->mp_expedition_id){m->is_at_fort=1;m->recent_fight=0;for(unsigned j=1;j<figure_count();j++){figure *v=figure_get(j);if(!figure_is_dead(v) && v->formation_id==m->id){v->formation_at_rest=1;v->action_state=80;}}}}}
static void seed_sea(void) {
    sea_fixture=1;
    for(int y=25;y<=52;y++)for(int x=25;x<=64;x++){
        int o=map_grid_offset(x,y);map_building_set(o,0);map_terrain_set(o,y<=40?TERRAIN_WATER:TERRAIN_CLEAR);
    }
    scenario.river_entry_point=(map_point){28,32};scenario.river_exit_point=(map_point){61,32};
    for(int x=40;x<=50;x++)map_terrain_set(map_grid_offset(x,43),TERRAIN_ROAD);
    city_map_set_entry_point(40,43);city_map_set_exit_point(40,43);
    building *dock=building_create(BUILDING_DOCK,40,40);int dockid=dock->id;
    dock->state=BUILDING_STATE_IN_USE;dock->num_workers=10;dock->has_water_access=1;dock->has_road_access=1;
    dock->data.dock.orientation=0;dock->accepted_goods[RESOURCE_POTTERY]=1;
    for(int y=40;y<43;y++)for(int x=40;x<43;x++){map_building_set(map_grid_offset(x,y),dockid);map_terrain_set(map_grid_offset(x,y),TERRAIN_BUILDING | (y==40?TERRAIN_WATER:0));}
    building *b=building_create(BUILDING_WAREHOUSE,50,44);int id=b->id,prev=id;
    b->state=BUILDING_STATE_IN_USE;b->has_road_access=1;b->storage_id=building_storage_create(id);
    map_building_set(map_grid_offset(50,44),id);map_terrain_set(map_grid_offset(50,44),TERRAIN_BUILDING);
    for(int i=0;i<8;i++){
        building *part=building_create(BUILDING_WAREHOUSE_SPACE,51+i%3,45+i/3);part->state=BUILDING_STATE_IN_USE;
        part->prev_part_building_id=prev;building_get(prev)->next_part_building_id=part->id;prev=part->id;
    }
    building_warehouse_try_add_resource(b,RESOURCE_POTTERY,20,0);
    building_storage_toggle_permission(BUILDING_STORAGE_PERMISSION_TRADERS,b);
    map_routing_update_land();map_routing_update_water();
}
static void seed(int food) {
    if(food)fixture_resource=RESOURCE_WHEAT;
    for(int y=32;y<=46;y++)for(int x=30;x<=56;x++){
        int o=map_grid_offset(x,y);map_terrain_set(o,TERRAIN_CLEAR);map_building_set(o,0);
    }
    for(int x=32;x<=50;x++)map_terrain_set(map_grid_offset(x,39),TERRAIN_ROAD);
    city_map_set_entry_point(32,39);city_map_set_exit_point(32,39);
    building *b=building_create(food?BUILDING_GRANARY:BUILDING_WAREHOUSE,40,40);int prev=b->id;
    b->state=BUILDING_STATE_IN_USE;b->has_road_access=1;b->storage_id=building_storage_create(b->id);
    map_building_set(map_grid_offset(40,40),b->id);
    for(int k=0;!food && k<8;k++){
        building *v=building_create(BUILDING_WAREHOUSE_SPACE,41+k%3,40+k/3);
        v->state=BUILDING_STATE_IN_USE;v->prev_part_building_id=prev;
        building_get(prev)->next_part_building_id=v->id;prev=v->id;
    }
    if(food)building_granary_try_add_resource(b,RESOURCE_WHEAT,20,0,0);else building_warehouse_try_add_resource(b,RESOURCE_POTTERY,20,0);map_routing_update_land();
}

#include <string.h>
int cash_stream(const char *dir) {
    char line[8192],path[4096];mp_post_city_reset();mp_post_runtime_reset();
    city_finance_treasury_add(1000-city_finance_treasury());puts("RESULT ready");fflush(stdout);
    while(fgets(line,sizeof(line),stdin)){
        int result=1;
        if(!strncmp(line,"quit",4))return 0;
        if(!strncmp(line,"seed",4)){if(!strncmp(line,"seedsea",7))seed_sea();else seed(!strncmp(line,"seedfood",8));_putenv_s("AUGUSTUS_MP_BRIDGE",dir);mp_clock_start();}
        else if(!strncmp(line,"npcseed",7)){seed_npc(atoi(line+8));}
        else if(!strncmp(line,"npcmove",7)){
            int before_stock=stock(),before=city_finance_treasury();
            for(int k=0;k<600;k++)for(unsigned i=1;i<figure_count();i++){figure *v=figure_get(i);if(v->type==FIGURE_TRADE_CARAVAN && !v->mp_contract_id && !figure_is_dead(v))figure_trade_caravan_action(v);}
            simulation_stock_delta+=stock()-before_stock;simulation_cash_delta+=city_finance_treasury()-before;
        }
        else if(!strncmp(line,"npcinspect",10)){
            snprintf(path,sizeof(path),"%s/npc-native.json",dir);FILE *f=fopen(path,"wb");if(f){fprintf(f,"{\"bought\":%d,\"sold\":%d,\"buy_price\":%d,\"sell_price\":%d}",trade_route_traded(npc_route,fixture_resource,1),trade_route_traded(npc_route,fixture_resource,0),trade_price_buy(fixture_resource,1),trade_price_sell(fixture_resource,1));fclose(f);}
        }
        else if(!strncmp(line,"frame",5)){
            if(!render_started){window_city_show();city_view_go_to_grid_offset(map_grid_offset(40,40));render_started=1;}
            time_set_millis(SDL_GetTicks());game_animation_update();game_draw();platform_renderer_render();
        }
        else if(!strncmp(line,"postseed",8)){
            for(int x=34;x<=36;x+=2){
                result=building_construction_place_building(BUILDING_PLAYER_TRADE_POST,x,40,1);
                building *b=building_get(map_building_at(map_grid_offset(x,40)));
                if(b->type!=BUILDING_PLAYER_TRADE_POST){result=0;break;}
                b->state=BUILDING_STATE_IN_USE;b->num_workers=5;b->has_road_access=1;
            }
            mp_transport_poll();
        }
        else if(!strncmp(line,"armyseed",8)){result=expedition_fixture(FIGURE_FORT_LEGIONARY);army_fixture=1;army_rest();}
        else if(!strncmp(line,"treasury",8)){int amount=atoi(line+9);if(amount<0 || amount>1000000)return 116;city_finance_treasury_add(amount-city_finance_treasury());}
        else if(!strncmp(line,"consume",7)){
            int amount=atoi(line+8),before=stock();if(amount<0 || amount>32)return 117;
            for(unsigned i=1;i<building_count() && amount>0;i++){building *b=building_get(i);if(b->type==BUILDING_WAREHOUSE)amount-=building_warehouse_try_remove_resource(b,fixture_resource,amount);}
            simulation_stock_delta+=stock()-before;
        }
        else if(!strncmp(line,"catalogworkers",14)){
            int n=atoi(line+15);for(unsigned i=1;i<building_count();i++){building*b=building_get(i);if(b->type==BUILDING_PLAYER_TRADE_POST)b->num_workers=n;}
        }
        else if(!strncmp(line,"catalogcut",10)){
            for(int y=0;y<scenario_map_size();y++)map_terrain_set(map_grid_offset(33,y),TERRAIN_WATER);
            map_routing_update_land();
        }
        else if(!strncmp(line,"cataloggate",11)){
            for(int y=0;y<scenario_map_size();y++)map_terrain_set(map_grid_offset(33,y),TERRAIN_WATER);
            map_terrain_set(map_grid_offset(33,39),TERRAIN_ROAD);map_routing_update_land();
        }
        else if(!strncmp(line,"catalogfight",12)){
            figure*f=figure_create(FIGURE_FORT_LEGIONARY,33,39,0);catalog_fighter=f->id;
            f->is_friendly=1;f->action_state=FIGURE_ACTION_150_ATTACK;
        }
        else if(!strncmp(line,"catalogpeace",12)){
            if(catalog_fighter)figure_delete(figure_get(catalog_fighter));catalog_fighter=0;
        }
        else if(!strncmp(line,"catalogverify",13)){
            int strict=atoi(line+14);unsigned id,generation;int available;result=1;
            snprintf(path,sizeof(path),"%s/fleet-posts.txt",dir);FILE*f=fopen(path,"rb");if(!f)result=0;
            if(f){while(fscanf(f,"%u %u %d",&id,&generation,&available)==3){
                building*b=building_get(id);map_point road;const map_tile*entry=city_map_entry_point(),*exit=city_map_exit_point();
                int valid=b->type==BUILDING_PLAYER_TRADE_POST && b->state==BUILDING_STATE_IN_USE && b->created_sequence==generation && !b->has_plague && b->num_workers>0 && map_has_road_access(b->x,b->y,b->size,&road);
                if(valid)valid=map_routing_citizen_can_travel_over_land(entry->x,entry->y,road.x,road.y,8,0) && map_routing_citizen_can_travel_over_land(road.x,road.y,exit->x,exit->y,8,0);
                if((available && !valid) || (strict && available!=valid))result=0;
            }fclose(f);}
        }
        else if(!strncmp(line,"postgeneration",14)){for(unsigned i=1;i<building_count();i++){building *b=building_get(i);if(b->type==BUILDING_PLAYER_TRADE_POST){b->created_sequence=atoi(line+15);break;}}mp_transport_poll();}
        else if(!strncmp(line,"postlabor",9)){
            int population=city_data.population.population;city_data.population.population=100;
            building_figure_generate();city_data.population.population=population;result=0;
            for(unsigned i=1;i<building_count();i++){building *b=building_get(i);if(b->type==BUILDING_PLAYER_TRADE_POST && b->figure_id2 && figure_get(b->figure_id2)->type==FIGURE_LABOR_SEEKER)result++;}
        }
        else if(!strncmp(line,"buildpost",9)){
            result=0;int positions[]={32,38};
            for(int i=0;i<2;i++){
                int x=positions[i];if(map_building_at(map_grid_offset(x,40)))continue;
                int cost=model_get_building(BUILDING_PLAYER_TRADE_POST)->cost;
                if(city_finance_treasury()<cost)break;
                if(building_construction_place_building(BUILDING_PLAYER_TRADE_POST,x,40,1)){
                    city_finance_treasury_add(-cost);simulation_cash_delta-=cost;result=1;break;
                }
            }
        }
        else if(!strncmp(line,"fleetinspect",12)){
            snprintf(path,sizeof(path),"%s/fleet-native.json",dir);FILE *f=fopen(path,"wb");
            if(f){fputs("[",f);int count=0;for(unsigned i=1;i<figure_count();i++){figure *v=figure_get(i);if(v->type==FIGURE_TRADE_CARAVAN && v->mp_contract_id && !figure_is_dead(v)){
                fprintf(f,"%s{\"figure\":%u,\"contract\":%u,\"action\":%d,\"target\":%u,\"generation\":%u,\"source\":%d}",count++?",":"",i,v->mp_contract_id,v->action_state,v->destination_building_id,v->mp_stops[0].building_id,v->mp_source);
            }}fputs("]",f);fclose(f);}
        }
        else if(!strncmp(line,"economy",7)){snprintf(path,sizeof(path),"%s/economy.json",dir);FILE *f=fopen(path,"wb");if(f){fprintf(f,"{\"ordinary_cash_delta\":%lld,\"ordinary_stock_delta\":%lld}",simulation_cash_delta,simulation_stock_delta);fclose(f);}}
        else if(!strncmp(line,"armyfailalloc",13)){mp_army_test_allocation_budget(atoi(line+14));}
        else if(!strncmp(line,"armycombat",10)){army_fixture=0;}
        else if(!strncmp(line,"armyinspect",11)){result=expedition_export(dir);}
        else if(!strncmp(line,"armycasualty",12)){for(unsigned i=1;i<figure_count();i++){figure *v=figure_get(i);if(!figure_is_dead(v) && formation_get(v->formation_id)->mp_expedition_role){figure_delete(v);break;}}formation_calculate_figures();}
        else if(!strncmp(line,"nodock",6)){for(unsigned i=1;i<building_count();i++)if(building_get(i)->type==BUILDING_DOCK)building_get(i)->state=BUILDING_STATE_UNUSED;}
        else if(!strncmp(line,"lake",4)){for(int y=25;y<=40;y++)map_terrain_set(map_grid_offset(35,y),TERRAIN_CLEAR);map_routing_update_water();}
        else if(!strncmp(line,"inlandlake",10)){
            for(int y=10;y<=20;y++)for(int x=10;x<=20;x++){map_building_set(map_grid_offset(x,y),0);map_terrain_set(map_grid_offset(x,y),TERRAIN_WATER);}
            scenario.river_entry_point=(map_point){5,15};scenario.river_exit_point=(map_point){25,15};map_routing_update_water();
        }
        else if(!strncmp(line,"move",4)){
            for(int k=0;k<600;k++)for(unsigned i=1;i<figure_count();i++) {
                figure *f=figure_get(i);if(f->mp_contract_id && !figure_is_dead(f)){if(f->type==FIGURE_TRADE_CARAVAN)figure_trade_caravan_action(f);else if(f->type==FIGURE_TRADE_SHIP)figure_trade_ship_action(f);else if(f->type==FIGURE_DOCKER)figure_docker_action(f);}
            }
            mp_transport_poll();
        }
        else if(!strncmp(line,"tick",4)){int n=atoi(line+5);if(n<0 || n>192)return 115;for(int k=0;k<n;k++){if(sea_fixture){city_data.labor.workers_available=100;for(unsigned i=1;i<building_count();i++)if(building_get(i)->type==BUILDING_DOCK){building_get(i)->num_workers=10;building_get(i)->houses_covered=100;}}int before_stock=stock();int before=city_finance_treasury();game_tick_run();simulation_stock_delta+=stock()-before_stock;simulation_cash_delta+=(long long)city_finance_treasury()-before;mp_clock_did_tick();army_rest();}}
        else if(!strncmp(line,"empty",5) || !strncmp(line,"full",4) || !strncmp(line,"demolish",8)){
            for(unsigned i=1;i<building_count();i++){building *b=building_get(i);if(b->type!=BUILDING_WAREHOUSE)continue;
                if(line[0]=='e')building_warehouse_try_remove_resource(b,RESOURCE_POTTERY,32);
                else if(line[0]=='f')building_warehouse_try_add_resource(b,RESOURCE_POTTERY,32,0);
                else b->state=BUILDING_STATE_UNUSED;
            }
        }
        else if(!strncmp(line,"poll",4)){mp_transport_poll();mp_post_runtime_poll(dir);
            snprintf(path,sizeof(path),"%s/calendar.txt",dir);FILE *f=fopen(path,"wb");if(f){fprintf(f,"%d %d %d %d",game_time_year(),game_time_month(),game_time_day(),game_time_tick());fclose(f);}
        }
        else if(!strncmp(line,"savepath ",9)){line[strcspn(line,"\r\n")]=0;result=game_file_io_write_saved_game(line+9);}
        else if(!strncmp(line,"loadpath ",9)){line[strcspn(line,"\r\n")]=0;result=game_file_io_read_saved_game(line+9,0);}
        else if(!strncmp(line,"armyinvasioncheck",17)){result=1;for(int i=1;i<formation_count();i++){formation*a=formation_get(i);if(!a->in_use || !a->mp_expedition_role)continue;for(int j=i+1;j<formation_count();j++){formation*b=formation_get(j);if(b->in_use && b->mp_expedition_role && (a->mp_expedition_id==b->mp_expedition_id || a->invasion_id==b->invasion_id))result=0;}}}
        else if(!strncmp(line,"save",4)){snprintf(path,sizeof(path),"%s/checkpoint.sav",dir);result=game_file_io_write_saved_game(path);}
        else if(!strncmp(line,"load",4)){snprintf(path,sizeof(path),"%s/checkpoint.sav",dir);result=game_file_io_read_saved_game(path,0);}
        else if(strncmp(line,"inspect",7))return 114;
        if(!strncmp(line,"inspect",7))for(unsigned i=1;i<building_count();i++)if(building_get(i)->type==BUILDING_WAREHOUSE){building *b=building_get(i);fprintf(stderr,"DIAG warehouse %u state=%d road=%d plague=%d permission=%d pos=%d,%d\n",i,b->state,b->has_road_access,b->has_plague,building_storage_get_permission(BUILDING_STORAGE_PERMISSION_TRADERS,b),b->x,b->y);}
        if(!strncmp(line,"inspect",7)){
            map_point road={0};int access=map_has_road_access_warehouse(40,40,&road);
            fprintf(stderr,"DIAG road=%d coords=%d,%d route=%d entry=%d,%d\n",access,road.x,road.y,access?map_routing_citizen_can_travel_over_land(32,39,road.x,road.y,8,0):0,city_map_entry_point()->x,city_map_entry_point()->y);
            for(unsigned i=1;i<figure_count();i++){figure *f=figure_get(i);if(f->mp_contract_id)fprintf(stderr,"DIAG figure %u state=%d type=%d action=%d pos=%d,%d target=%u stops=%d\n",i,f->state,f->type,f->action_state,f->x,f->y,f->destination_building_id,f->mp_stop_count);}
        }
        const post_book *book=mp_post_city_book();printf("RESULT %d %d %d %u\n",result,city_finance_treasury(),stock(),book?book->count:0);fflush(stdout);
    }return 0;
}
