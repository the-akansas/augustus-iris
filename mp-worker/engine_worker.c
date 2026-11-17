#include "multiplayer/army_install_native.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <limits.h>
#include <errno.h>
#include <string.h>
#include "multiplayer/city_adapter.h"
#include "multiplayer/transport.h"
#include "multiplayer/cargo.h"
#include "building/building.h"
#include "building/state.h"
#include "building/storage.h"
#include "building/warehouse.h"
#include "building/granary.h"
#include "city/data_private.h"
#include "city/finance.h"
#include "city/ratings.h"
#include "game/file.h"
#include "empire/city.h"
#include "empire/trade_route.h"
#include "scenario/property.h"
#include "game/difficulty.h"
#include "game/settings.h"
#include "game/time.h"
#include "game/tick.h"
#include "creator_preset.h"
#include "creator_terrain.h"
#include "creator_native_map.h"
#include "creator_save_terrain.h"
#include "creator_economy_audit.h"
#include "shared_empire.h"
#include "restore_roster.h"
static void put(unsigned char *p,uint64_t n,int len){for(int i=0;i<len;i++)p[i]=(unsigned char)(n>>(8*i));}
static uint64_t get(const unsigned char *p,int len){uint64_t n=0;for(int i=0;i<len;i++)n|=(uint64_t)p[i]<<(8*i);return n;}
static int recfile(const char *path,mp_city_receipt *s,int write){
 unsigned char b[32]={0};FILE *f=fopen(path,write?"wb":"rb");if(!f)return 0;
 int ok=0;
 if(write){memcpy(b,"MPC1",4);put(b+4,s->sequence,8);put(b+12,s->warehouse,4);put(b+16,s->quantity,4);put(b+20,(uint32_t)s->money_delta,4);put(b+24,s->incoming,4);put(b+28,s->pending_pottery,4);ok=fwrite(b,1,32,f)==32;}
 else if(fread(b,1,32,f)==32 && fgetc(f)==EOF && !memcmp(b,"MPC1",4)){
  s->sequence=get(b+4,8);s->warehouse=(int32_t)get(b+12,4);s->quantity=(int32_t)get(b+16,4);s->money_delta=(int32_t)get(b+20,4);s->incoming=(int32_t)get(b+24,4);s->pending_pottery=(int32_t)get(b+28,4);ok=1;
 }
 return fclose(f)==0 && ok;
}
#include "transport_fixture.h"
#include "sea_fixture.h"
#include "creator_map_export.h"
#include "walk_assets.h"
#include "building_pictures.h"
#include "expedition_native.h"
#include "expedition_visit.h"
#include "training_town.h"
#include "plague_probe.h"
#include "health_audit.h"
#include "plague_animation_audit.h"
static int cargo_file(const char *path,mp_cargo *c,int writing){
 unsigned char b[28]={0};FILE *f=fopen(path,writing?"wb":"rb");if(!f)return 0;int ok=0;
 if(writing){memcpy(b,"MPCG",4);put(b+4,c->contract,8);put(b+12,c->resource,4);put(b+16,c->total,4);put(b+20,c->remaining,4);put(b+24,c->state,4);ok=fwrite(b,1,28,f)==28;}
 else if(fread(b,1,28,f)==28 && fgetc(f)==EOF && !memcmp(b,"MPCG",4)){
  *c=(mp_cargo){get(b+4,8),(int)get(b+12,4),(int)get(b+16,4),(int)get(b+20,4),(int)get(b+24,4)};ok=mp_cargo_valid(c);
 }
 return fclose(f)==0 && ok;
}
static int army_worker_load(const char *path){return game_file_load_saved_game(path)==FILE_LOAD_SUCCESS;}
int worker(int argc,char **argv){
 if(argc!=8)return 80;
 const char *mode=argv[2],*in=argv[3],*out=argv[4];int qty=atoi(argv[5]),money=atoi(argv[6]);uint64_t seq=strtoull(argv[7],0,10);
 char path[2048];mp_city_receipt s={0};mp_cargo cargo={0};int cargo_mode=!strncmp(mode,"cargo-",6);
 if(!strcmp(mode,"plague-animation-capua"))return plague_animation_audit(out)?0:122;
 if(!strcmp(mode,"walk-assets"))return walk_export(out)?0:119;
 if(!strcmp(mode,"building-pictures"))return building_pictures(in,out)?0:123;   /* in: building types "10,5,..." */
 if(!strcmp(mode,"plague-probe-capua"))return plague_probe(out,qty,money,(int)seq)?0:120;
 if(!strcmp(mode,"health-audit-capua"))return health_audit(out,qty)?0:121;
 if(!strcmp(mode,"native-editor-roundtrip") || !strcmp(mode,"native-editor-probe"))return creator_native_roundtrip(in,out,!strcmp(mode,"native-editor-probe"))?0:109;
 if(!strcmp(mode,"native-save-terrain"))return creator_save_terrain(in,out)?0:110;   /* .svx -> terrain-only .mapx */
 if(!strcmp(mode,"native-map-inspect")){
  snprintf(path,sizeof(path),"%s/terrain.mapx",in);
  if(!creator_load_native_map(path))return 109;
  creator_reset_mission(10000);
 }
 if(!strncmp(mode,"start-",6) && !creator_start_profile(mode,in,argv[0]))return 93;
 if(strncmp(mode,"start-",6) && strstr(mode,"-capua") && !build_shared_empire(2,in,argv[0]))return 93;
 if(strncmp(mode,"start-",6) && strstr(mode,"-tarentum") && !build_shared_empire(1,in,argv[0]))return 93;
 if(!strncmp(mode,"sea-seed-",9)){
  s.warehouse=sea_seed_fixture(out,strstr(mode,"source")!=0,strstr(mode,"docker-mid")?2:strstr(mode,"mid")!=0);
 }else if(!strcmp(mode,"source-caravan") || !strcmp(mode,"source-caravan-midway")){
  s.warehouse=transport_split_fixture(out,!strcmp(mode,"source-caravan-midway"),1);
 }else if(!strcmp(mode,"caravan-split") || !strcmp(mode,"caravan-split-midway")){
  s.warehouse=transport_split_fixture(out,!strcmp(mode,"caravan-split-midway"),0);
 }else if(!strcmp(mode,"caravan-test") || !strcmp(mode,"caravan-blocked") || !strcmp(mode,"caravan-midway")){
  s.warehouse=transport_fixture(out,!strcmp(mode,"caravan-blocked")?1:!strcmp(mode,"caravan-midway")?2:0);if((int)s.warehouse<=0)return 101;
 }else if(!strncmp(mode,"seed-food",9)){
  building *b=building_create(BUILDING_GRANARY,40,40);b->state=BUILDING_STATE_IN_USE;b->storage_id=building_storage_create(b->id);
  if(qty && building_granary_try_add_resource(b,RESOURCE_WHEAT,qty,0,0)!=qty)return 81;
  if(strstr(mode,"blocked")){
   for(int k=0;k<8 && building_storage_get_state(b,RESOURCE_WHEAT,1)!=BUILDING_STORAGE_STATE_NOT_ACCEPTING;k++)building_storage_cycle_resource_state(b->storage_id,RESOURCE_WHEAT,0);
  }
  city_finance_treasury_add(money-city_finance_treasury());
 }else if(!strncmp(mode,"seed",4)){
  building *b=building_create(BUILDING_WAREHOUSE,40,40);int id=b->id,prev=id;
  b->state=BUILDING_STATE_IN_USE;b->storage_id=building_storage_create(id);
  for(int i=0;i<8;i++){
   building *part=building_create(BUILDING_WAREHOUSE_SPACE,41+i%3,41+i/3);
   part->state=BUILDING_STATE_IN_USE;part->prev_part_building_id=prev;building_get(prev)->next_part_building_id=part->id;prev=part->id;
  }
  s.warehouse=id;
  if(qty && building_warehouse_try_add_resource(building_get(id),RESOURCE_POTTERY,qty,0)!=qty)return 81;
  city_finance_treasury_add(money-city_finance_treasury());
 }else if(!strncmp(mode,"start-",6) || !strcmp(mode,"creator-map-capua") || !strncmp(mode,"inventory-",10) || !strcmp(mode,"native-map-inspect")){
  /* Pristine campaign start: no test warehouse, stock or money override. */
  /* Fresh multiplayer scenario only: both players start at the same epoch. */
  game_time_init(scenario_property_start_year());
 }else{
  /* Measurement import only: load the approved SVX copy without requiring a multiplayer receipt.
   * No ticks, city reset, building edits or finance changes; normal output creates an isolated receipt. */
  int economy_import = !strcmp(mode,"economy-import-svx");
  if(economy_import && qty!=0)return 112;
  snprintf(path,sizeof(path),economy_import?"%s/city.svx":"%s/city.sav",in);
  if(game_file_load_saved_game(path)!=1)return 82;
  if(!economy_import){snprintf(path,sizeof(path),"%s/receipt.bin",in);if(!recfile(path,&s,0))return 83;}
  if(cargo_mode){
   snprintf(path,sizeof(path),"%s/cargo.bin",in);if(!cargo_file(path,&cargo,0))return 102;
   if(!strcmp(mode,"cargo-load-caravan")){
    int target=0;unsigned int contract=0;
    snprintf(path,sizeof(path),"%s/transport.txt",in);FILE *tf=fopen(path,"rb");if(!tf)return 103;
    int count=fscanf(tf,"%u %d",&contract,&target);fclose(tf);
    if(count!=2 || contract!=seq || cargo.contract || !mp_transport_validate_source(contract,target,money,qty) || mp_transport_collect(contract,money,qty)!=qty)return 103;
    cargo=(mp_cargo){seq,money,qty,qty,MP_CARGO_LOADED};mp_transport_depart(contract);
   }else if(!strcmp(mode,"cargo-load")){if(!mp_cargo_load(&cargo,seq,money,qty))return 103;}
   else{
    if(cargo.contract!=seq || cargo.resource!=money || cargo.total!=qty)return 103;
    if(!strcmp(mode,"cargo-depart")){
     if(cargo.state!=MP_CARGO_LOADED || !mp_transport_validate_departed(seq,money,qty))return 103;
     mp_transport_release(seq);
    }else if(!strcmp(mode,"cargo-return-sea")){if(!mp_cargo_return_by_sea(&cargo))return 103;}
    else if(!strcmp(mode,"cargo-return")){if(!mp_cargo_return(&cargo))return 103;}
    else if(!strcmp(mode,"cargo-consume")){if(!mp_cargo_consume(&cargo))return 103;}
    else return 103;
   }
  }else if(!strcmp(mode,"source-depart") || !strcmp(mode,"source-depart-midway")){s.warehouse=transport_depart_fixture(out,!strcmp(mode,"source-depart-midway"));}
  else if(!strncmp(mode,"sea-fail-",9)){sea_failure_fixture(mode);}
  else if(!strcmp(mode,"sea-resume")){s.warehouse=sea_run_fixture(out,0,0);}
  else if(!strcmp(mode,"sea-depart")){s.warehouse=sea_run_fixture(out,0,1);}
  else if(!strcmp(mode,"sea-depart-midway")){s.warehouse=sea_run_fixture(out,1,1);}
  else if(!strcmp(mode,"transport-reset")){transport_reset_fixture(out);}
  else if(!strcmp(mode,"caravan-resume")){s.warehouse=transport_resume_fixture(out);}
  else if(!strcmp(mode,"live-in") || !strcmp(mode,"live-out") || !strcmp(mode,"live-in-caravan") || !strcmp(mode,"live-out-cargo")){
   int resource=(int)seq;
   if(qty<0 || qty>32 || (qty && (resource<RESOURCE_MIN || resource>=RESOURCE_MAX)) || (!qty && resource!=0))return 97;
   int64_t balance=(int64_t)city_finance_treasury()+money;
   if(balance<0 || balance>INT_MAX)return 98;
   int incoming=strncmp(mode,"live-in",7)==0;int transport_target=0;unsigned int contract=0;
   if(!strcmp(mode,"live-in-caravan")){
    snprintf(path,sizeof(path),"%s/transport.txt",in);FILE *tf=fopen(path,"rb");if(!tf)return 100;
    int count=fscanf(tf,"%u %d",&contract,&transport_target);fclose(tf);
    if(count!=2 || !mp_transport_validate(contract,transport_target,resource,qty))return 100;
   }
   if(money < -1000000 || money > 1000000 || (qty && (incoming?money>0:money<0)) || (!qty && (incoming?money<=0:money>=0)))return 98;
   finance_overview *fin=&city_data.finance.this_year;
   int *account=qty?(incoming?&fin->expenses.imports:&fin->income.exports):(money>0?&fin->income.donated:&fin->expenses.sundries);
   int amount=money<0?-money:money;
   if((int64_t)*account+amount>INT_MAX)return 98;
   if(qty){
    int count=incoming?city_finance_trade_ledger_get_imported(resource,0):city_finance_trade_ledger_get_exported(resource,0);
    int64_t ledger=(int64_t)city_finance_trade_ledger_get_balance(resource,0)+money;
    if((int64_t)count+qty>INT_MAX || ledger>INT_MAX || ledger<INT_MIN)return 98;
   }
   int remaining=qty;
   if(!strcmp(mode,"live-out-cargo")){
    snprintf(path,sizeof(path),"%s/cargo.bin",in);
    if(!cargo_file(path,&cargo,0) || cargo.resource!=resource || cargo.total!=qty || cargo.state!=MP_CARGO_LOADED || !mp_cargo_consume(&cargo))return 103;
    remaining=0;
   }
   if(contract){if(mp_transport_deliver(contract,resource,qty)!=qty)return 99;remaining=0;}
   /* Prefer warehouses; food may also use healthy granaries. Receiver settings apply. */
   for(int pass=0;pass<2 && remaining;pass++)for(int id=1;id<building_count() && remaining;id++){
    building *b=building_get(id);
    if(transport_target && id!=transport_target)continue;
    if(b->state!=BUILDING_STATE_IN_USE || b->has_plague)continue;
    if(!pass && b->type==BUILDING_WAREHOUSE){
     if(incoming)remaining-=building_warehouse_try_add_resource(b,resource,remaining,1);
     else remaining-=building_warehouse_try_remove_resource(b,resource,remaining);
    }else if(pass && resource_is_food(resource) && b->type==BUILDING_GRANARY){
     if(incoming)remaining-=building_granary_try_add_resource(b,resource,remaining,0,1);
     else remaining-=building_granary_try_remove_resource(b,resource,remaining);
    }
   }
   /* Disposable snapshot: failure publishes neither stock nor finance changes. */
   if(remaining)return 99;
   if(contract)mp_transport_release(contract);
   city_finance_treasury_add(money);
   *account+=amount; /* Contract value only: no NPC/Neptune bonus can mint extra money. */
   if(qty){
    for(int i=0;i<qty;i++){
     if(incoming)city_finance_trade_ledger_add_imported(resource);
     else city_finance_trade_ledger_add_exported(resource);
    }
    city_finance_trade_ledger_add_balance(resource,money);
   }
  }else if(!strcmp(mode,"apply")){
   int result=mp_city_trade(&s,seq,s.warehouse,money<0,qty,money);
   if(result!=MP_OK && result!=MP_DUPLICATE)return 84;
  }else if(!strcmp(mode,"deliver")){if(mp_city_deliver_pending(&s,s.warehouse)<0)return 85;}
  else if(!strcmp(mode,"probe-peer")){
   int found=0,treasury=city_finance_treasury();
   for(int i=0;i<empire_city_get_array_size();i++){
    empire_city *c=empire_city_get(i);if(!c->in_use || c->type!=EMPIRE_CITY_PLAYER)continue;
    found++;empire_city_open_trade(i,1);if(c->is_open)return 94;
    c->is_open=1; /* Even a stale open flag must never spawn an AI trader. */
    for(int n=0;n<100;n++)empire_city_generate_trader();
    c->is_open=0;
    for(int n=0;n<EMPIRE_CITY_MAX_TRADERS;n++)if(c->trader_figure_ids[n])return 95;
   }
   if(found!=1 || treasury!=city_finance_treasury())return 96;
  }else if(!strcmp(mode,"roster-progress-fixture")){
   building *b=building_create(BUILDING_WAREHOUSE,40,40);int id=b->id,prev=id;
   b->state=BUILDING_STATE_IN_USE;b->storage_id=building_storage_create(id);
   for(int i=0;i<8;i++){building *part=building_create(BUILDING_WAREHOUSE_SPACE,41+i%3,41+i/3);part->state=BUILDING_STATE_IN_USE;part->prev_part_building_id=prev;building_get(prev)->next_part_building_id=part->id;prev=part->id;}
   if(building_warehouse_try_add_resource(building_get(id),RESOURCE_POTTERY,7,0)!=7)return 110;
   city_finance_treasury_add(43210-city_finance_treasury());
   if(!creator_align_roster_time(12345))return 110;
  }else if(!strcmp(mode,"expand-roster")){if(!creator_expand_roster(in,argv[0],qty))return 110;}
  else if(!strcmp(mode,"align-roster-time")){if(!creator_align_roster_time(seq))return 110;}
  else if(!strcmp(mode,"governance-year")){
   game_time_init(game_time_year()+1);
   city_data.finance.last_year.expenses.salary=city_data.emperor.salary_amount*12;
   city_data.finance.tribute_not_paid_last_year=0;
   city_ratings_update(1,1);
  }
  else if(!strcmp(mode,"events-dispatch-fixture")){
   /* Private test snapshot: provision the exact requested goods, then use the native dispatch. */
   const scenario_request *r=scenario_request_get(0);if(!r || !r->visible || r->resource!=RESOURCE_POTTERY)return 111;
   building *b=building_create(BUILDING_WAREHOUSE,40,40);int id=b->id,prev=id;
   b->state=BUILDING_STATE_IN_USE;b->storage_id=building_storage_create(id);
   for(int i=0;i<8;i++){building *part=building_create(BUILDING_WAREHOUSE_SPACE,41+i%3,41+i/3);part->state=BUILDING_STATE_IN_USE;part->prev_part_building_id=prev;building_get(prev)->next_part_building_id=part->id;prev=part->id;}
   if(building_warehouse_try_add_resource(building_get(id),r->resource,r->amount.requested,0)!=(int)r->amount.requested || !scenario_request_can_comply(0))return 111;
   scenario_request_dispatch(0);
  }
   else if(!strcmp(mode,"expedition-detach") || !strcmp(mode,"expedition-restore")){
    if(!expedition_transform(in,!strcmp(mode,"expedition-restore")))return 114;
   }
   else if(!strcmp(mode,"visit-arrive") || !strcmp(mode,"visit-remove")){
    if(!expedition_visit(in,!strcmp(mode,"visit-remove")))return 118;
   }
   else if(!strcmp(mode,"army-install-check")){
    char expected[65]={0},path[2048];snprintf(path,sizeof(path),"%s/expected.txt",in);
    FILE *f=fopen(path,"rb");if(!f)return 116;int ok=fscanf(f,"%64s",expected)==1;fclose(f);
    if(!ok || !army_install_poll(in,qty,expected,army_worker_load))return 116;
   }
   else if(!strcmp(mode,"expedition-fixture")){
    if(!expedition_fixture(qty))return 113;
   }
   else if(!strcmp(mode,"expedition-guards")){
    for(int id=1;id<formation_count();id++){
     formation *m=formation_get(id);if(!m->mp_expedition_id)continue;
     formation_toggle_empire_service(id);
     formation_legion_update_recruit_status(building_get(m->building_id));
     if(m->empire_service || m->legion_recruit_type!=LEGION_RECRUIT_NONE)return 115;
     if(qty==1){int bid=m->building_id;formation_legion_delete_for_fort(building_get(bid));building_get(bid)->state=BUILDING_STATE_DELETED_BY_PLAYER;}
    }
    formation_legions_dispatch_to_distant_battle();
    formation_legions_kill_in_distant_battle(100);
    formation_legions_return_from_distant_battle();
    formation_update_monthly_morale_at_rest();formation_update_monthly_morale_deployed();
   }
   else if(!strcmp(mode,"visit-defend-fixture")){
    const map_tile *entry=city_map_entry_point();
    for(int i=1;i<formation_count();i++){formation *m=formation_get(i);if(m->in_use && m->is_legion && !m->mp_expedition_id)formation_legion_move_to(m,entry);}
   }
   else if(!strcmp(mode,"economy-ticks") || !strcmp(mode,"economy-import-svx")){ /* measurement only: plain ticks, then economy-audit.json */
   if(qty<0 || qty>10000)return 112;
   for(int i=0;i<qty;i++)game_tick_run();
  }
   else if(!strcmp(mode,"military-ticks")){
   if(qty<0 || qty>10000)return 112;
   for(int i=0;i<qty;i++)game_tick_run();
  }
  else if(!strcmp(mode,"events-step")){
   if(qty<0 || qty>240)return 111;
   for(int m=0;m<qty;m++){
    for(int day=0;day<16;day++)game_time_advance_day();
    if(game_time_advance_month())game_time_advance_year();
    scenario_request_process();scenario_events_process_all();scenario_events_process_all();
   }
   scenario_events_process_all();
  }
  else if(strcmp(mode,"inspect") && strcmp(mode,"native-map-export"))return 86;
 }
 if(!strncmp(mode,"start-",6) && !training_start(in,mode+6,out))return 117;
 snprintf(path,sizeof(path),"%s/city.sav",out);if(!game_file_write_saved_game(path))return 87;
 snprintf(path,sizeof(path),"%s/receipt.bin",out);if(!recfile(path,&s,1))return 88;
 if(cargo_mode || !strcmp(mode,"live-out-cargo")){snprintf(path,sizeof(path),"%s/cargo.bin",out);if(!cargo_file(path,&cargo,1))return 104;}
 int camx,camy,vw,vh;city_view_get_camera(&camx,&camy);city_view_get_viewport_size_tiles(&vw,&vh);
 snprintf(path,sizeof(path),"%s/view-audit.json",out);FILE *vf=fopen(path,"w");if(!vf)return 89;
 fprintf(vf,"{\"camera\":[%d,%d],\"tiles\":[%d,%d],\"forts\":[",camx,camy,vw,vh);int comma=0;
 for(int bi=1;bi<building_count();bi++){building*b=building_get(bi);if(!b->formation_id)continue;int vx,vy;city_view_grid_offset_to_xy_view(map_grid_offset(b->x,b->y),&vx,&vy);fprintf(vf,"%s[%d,%d,%d,%d,%d]",comma++?",":"",b->id,b->x,b->y,vx,vy);}
 fputs("]}",vf);fclose(vf);
 snprintf(path,sizeof(path),"%s/summary.json",out);FILE *f=fopen(path,"w");if(!f)return 89;
 fprintf(f,"{\"money\":%d,\"pottery\":%d,\"pending\":%d,\"sequence\":%llu}",city_finance_treasury(),s.warehouse?building_warehouse_get_amount(building_get(s.warehouse),RESOURCE_POTTERY):0,s.pending_pottery,(unsigned long long)s.sequence);
 if(fclose(f))return 89;
 snprintf(path,sizeof(path),"%s/trade-audit.json",out);f=fopen(path,"w");if(!f)return 89;
 fprintf(f,"{\"imports_money\":%d,\"exports_money\":%d,\"donations\":%d,\"sundries\":%d,\"resources\":[",city_data.finance.this_year.expenses.imports,city_data.finance.this_year.income.exports,city_data.finance.this_year.income.donated,city_data.finance.this_year.expenses.sundries);
 for(int r=RESOURCE_MIN;r<RESOURCE_MAX;r++){
  int stock=0;for(int id=1;id<building_count();id++){
   building *b=building_get(id);if(b->state!=BUILDING_STATE_IN_USE)continue;
   if(b->type==BUILDING_WAREHOUSE)stock+=building_warehouse_get_amount(b,r);
   else if(b->type==BUILDING_GRANARY && resource_is_food(r))stock+=building_granary_get_amount(b,r);
  }
  fprintf(f,"%s{\"id\":%d,\"stock\":%d,\"imported\":%d,\"exported\":%d,\"balance\":%d}",r==RESOURCE_MIN?"":",",r,stock,city_finance_trade_ledger_get_imported(r,0),city_finance_trade_ledger_get_exported(r,0),city_finance_trade_ledger_get_balance(r,0));
 }fputs("]}",f);if(fclose(f))return 89;
 snprintf(path,sizeof(path),"%s/scenario.json",out);f=fopen(path,"w");if(!f)return 89;
 fprintf(f,"{\"year\":%d,\"initial_funds\":%d,\"adjusted_initial_funds\":%d,\"difficulty\":%d,\"cities\":[",scenario_property_start_year(),scenario_initial_funds(),difficulty_adjust_money(scenario_initial_funds()),setting_difficulty());
 int first=1;
 for(int i=0;i<empire_city_get_array_size();i++){
  empire_city *c=empire_city_get(i);if(!c->in_use)continue;
  if(!first)fputs(",",f);first=0;
  empire_object *obj=empire_object_get(c->empire_object_id);
  fprintf(f,"{\"name_id\":%d,\"type\":%d,\"buys_pottery\":%d,\"sells_pottery\":%d,\"x\":%d,\"y\":%d,\"sea\":%d,\"cost\":%d,\"route\":%d,\"sells\":[",c->name_id,c->type,c->buys_resource[RESOURCE_POTTERY],c->sells_resource[RESOURCE_POTTERY],obj->x,obj->y,c->is_sea_trade,c->cost_to_open,c->route_id);
  for(int r=0;r<RESOURCE_MAX;r++)fprintf(f,"%s%d",r?",":"",c->sells_resource[r]);
  fputs("],\"buys\":[",f);for(int r=0;r<RESOURCE_MAX;r++)fprintf(f,"%s%d",r?",":"",c->buys_resource[r]);fputs("],\"sell_limits\":[",f);
  for(int r=0;r<RESOURCE_MAX;r++)fprintf(f,"%s%d",r?",":"",trade_route_is_valid(c->route_id)?trade_route_limit(c->route_id,r,0):0);
  fputs("],\"buy_limits\":[",f);
  for(int r=0;r<RESOURCE_MAX;r++)fprintf(f,"%s%d",r?",":"",trade_route_is_valid(c->route_id)?trade_route_limit(c->route_id,r,1):0);
  fputs("]}",f);
 }
 fputs("],\"allowed_buildings\":[",f);int first_allowed=1;for(int t=1;t<BUILDING_TYPE_MAX;t++)if(scenario_allowed_building(t) && t!=BUILDING_FORT_GROUND && !building_menu_get_submenu_for_type(t)){ /* the authored list only: the fort ground and menu groups follow it (allowed_building.c, 2026-11-14) */fprintf(f,"%s%d",first_allowed?"":",",t);first_allowed=0;}fputs("],\"menu_enabled\":[",f);int first_menu=1;for(int t=1;t<BUILDING_TYPE_MAX;t++)if(building_menu_is_enabled(t)){fprintf(f,"%s%d",first_menu?"":",",t);first_menu=0;}fputs("]}",f);if(fclose(f))return 89;
 snprintf(path,sizeof(path),"%s/roster-audit.json",out);f=fopen(path,"w");if(!f)return 89;
 fprintf(f,"{\"year\":%d,\"month\":%d,\"day\":%d,\"tick\":%d,\"buildings\":[",game_time_year(),game_time_month(),game_time_day(),game_time_tick());
 int first_building=1;for(int i=1;i<building_count();i++){building *b=building_get(i);if(b->state!=BUILDING_STATE_IN_USE)continue;fprintf(f,"%s[%d,%d,%d,%d,%d,%d,%d,%d]",first_building?"":",",b->id,b->type,b->state,b->grid_offset,b->storage_id,b->x,b->y,b->size);first_building=0;}
 fputs("]}",f);if(fclose(f))return 89;
 if(!strcmp(mode,"creator-map-capua") && (!creator_export_map(out) || !creator_export_catalogs(out)))return 105;
 if(!creator_export_terrain(out))return 106;
 if(!creator_export_rules(out))return 108;
 if(!creator_export_events(out))return 111;
 if(!creator_export_military(out))return 112;
  if(!expedition_export(out))return 113;
 if(!strcmp(mode,"native-map-export")){
  /* The editor's copy of a map that came with a town (2026-11-15): the town is left out (the creator says so before
     it opens). The buildings, gardens, plazas, aqueducts, walls and rubble become the ground under them; roads stay
     (a map's own road from the entrance to the exit is one of them). Before, the building tiles stayed marked as
     built with no building and the editor drew stray pictures there. Native villages stay, as in creator_save_terrain.h. */
  int stripped=0;
  for(int y=0;y<map_grid_height();y++)for(int x=0;x<map_grid_width();x++){
   int offset=map_grid_offset(x,y);unsigned id=map_building_at(offset);
   if(id){const building *b=building_main(building_get(id));if(b && creator_native_village(b->type))continue;}
   int built=CREATOR_BUILT_TERRAIN&~(TERRAIN_ROAD|TERRAIN_HIGHWAY),terrain=map_terrain_get(offset);
   int plaza=(terrain&TERRAIN_ROAD) && map_property_is_plaza_earthquake_or_overgrown_garden(offset);
   if(!id && !(terrain&built) && !plaza)continue;
   int bare=terrain&~built;
   if((terrain&TERRAIN_ORIGINALLY_TREE) && !(terrain&TERRAIN_ROAD) && !(bare&(TERRAIN_WATER|TERRAIN_ROCK|TERRAIN_ELEVATION|TERRAIN_ACCESS_RAMP|TERRAIN_TREE)))bare|=TERRAIN_TREE;
   map_terrain_set(offset,bare);map_building_set(offset,0);map_property_clear_multi_tile_xy(offset);map_property_set_multi_tile_size(offset,1);
   map_property_mark_draw_tile(offset);map_property_clear_plaza_earthquake_or_overgrown_garden(offset);map_property_clear_constructing(offset);
   map_property_clear_deleted(offset);map_sprite_clear_tile(offset);stripped++;
  }
  for(unsigned i=1;i<building_count();i++){building *b=building_get(i);if(b->state!=BUILDING_STATE_UNUSED && !creator_native_village(building_main(b)->type))b->state=BUILDING_STATE_UNUSED;}
  if(stripped)map_tiles_update_all();
  snprintf(path,sizeof(path),"%s/town-removed.txt",out);FILE *note=fopen(path,"w");if(note){fprintf(note,"%d\n",stripped);fclose(note);}
  snprintf(path,sizeof(path),"%s/terrain.mapx",out);
  if(!game_file_editor_write_scenario(path))return 109;
 }
 if(!strncmp(mode,"inventory-",10) && (!creator_export_preset(out,creator_template_from_mode(mode)) || !creator_export_map(out)))return 107;
 if((!strcmp(mode,"economy-ticks") || !strcmp(mode,"economy-import-svx")) && !economy_audit(out))return 89;
 snprintf(path,sizeof(path),"%s/sea-access.json",out);f=fopen(path,"w");if(!f)return 89;
 fprintf(f,"{\"entry\":[%d,%d],\"exit\":[%d,%d]}",scenario.river_entry_point.x,scenario.river_entry_point.y,scenario.river_exit_point.x,scenario.river_exit_point.y);if(fclose(f))return 89;
 return 0;
}
