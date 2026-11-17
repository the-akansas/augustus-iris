#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "scenario/event/controller.h"
#include "multiplayer/city_adapter.h"
#include "building/building.h"
#include "building/state.h"
#include "building/storage.h"
#include "building/warehouse.h"
#include "city/finance.h"
#include "city/data_private.h"
#include "game/file.h"
static int warehouse(void) {
 building *b=building_create(BUILDING_WAREHOUSE,40,40);
 int id=b->id,prev=id;
 b->state=BUILDING_STATE_IN_USE;b->storage_id=building_storage_create(id);
 for(int i=0;i<8;i++){
  building *part=building_create(BUILDING_WAREHOUSE_SPACE,41+i%3,41+i/3);
  part->state=BUILDING_STATE_IN_USE;part->prev_part_building_id=prev;
  building_get(prev)->next_part_building_id=part->id;prev=part->id;
 }
 return id;
}
void test_city(const char *dir) {
 int id=warehouse();building *b=building_get(id);
 assert(building_warehouse_try_add_resource(b,RESOURCE_POTTERY,20,0)==20);
 city_finance_treasury_add(1000-city_finance_treasury());
 city_data.religion.neptune_trade_bonus_active=1;
 mp_city_receipt s={0};
 assert(mp_city_trade(&s,1,id,0,3,30)==MP_OK);
 assert(city_finance_treasury()==1030);
 assert(building_warehouse_get_amount(b,RESOURCE_POTTERY)==17);
 assert(mp_city_trade(&s,1,id,0,3,30)==MP_DUPLICATE);
 assert(mp_city_trade(&s,1,id,0,4,30)==MP_INVALID);
 assert(mp_city_trade(&s,2,id,0,30,300)==MP_STOCK);
 assert(mp_city_trade(&s,2,id,1,3,-2000)==MP_FUNDS);
 assert(city_finance_treasury()==1030);
 assert(mp_city_trade(&s,2,id,1,3,-30)==MP_OK);
 assert(s.pending_pottery==3 && city_finance_treasury()==1000);
 assert(building_warehouse_try_add_resource(b,RESOURCE_POTTERY,15,0)==15);
 assert(mp_city_deliver_pending(&s,id)==0 && s.pending_pottery==3);
 unsigned int text_id=scenario_text_get_new((const uint8_t *)"mp-save-test");
 unsigned int formula_id=scenario_formula_add((const uint8_t *)"123",0,999);
 char path[1024];snprintf(path,sizeof(path),"%s/city.sav",dir);
 assert(game_file_write_saved_game(path));
 snprintf(path,sizeof(path),"%s/receipt.bin",dir);FILE *f=fopen(path,"wb");assert(f);assert(fwrite(&s,sizeof(s),1,f)==1);assert(fclose(f)==0);
 snprintf(path,sizeof(path),"%s/city.sav",dir);
 assert(game_file_load_saved_game(path)==1);
 memset(&s,0,sizeof(s));
 snprintf(path,sizeof(path),"%s/receipt.bin",dir);f=fopen(path,"rb");assert(f);assert(fread(&s,sizeof(s),1,f)==1);fclose(f);
 assert(s.sequence==2 && s.pending_pottery==3);
 assert(strcmp((const char *)scenario_text_get_text(text_id),"mp-save-test")==0);
 assert(strcmp((const char *)scenario_formula_get_string(formula_id),"123")==0);
 b=building_get(id);
 assert(city_finance_treasury()==1000);
 assert(building_warehouse_get_amount(b,RESOURCE_POTTERY)==32);
 assert(building_warehouse_try_remove_resource(b,RESOURCE_POTTERY,3)==3);
 assert(mp_city_deliver_pending(&s,id)==3 && s.pending_pottery==0);
 assert(mp_city_trade(&s,2,id,1,3,-30)==MP_DUPLICATE);
 assert(city_finance_treasury()==1000);
 printf("ENGINE CITY ADAPTER: stock/funds/duplicate/Neptune/inbox/save-load PASS\n");
}

