/* The emperor visits this city (황제의 순행, 2026-11-15). Included by army_live.c after emperor_raid.inc.
 * The room decides where the emperor goes, when he arrives and which one good his court uses
 * (Augustus/imperial_progress.py). This city hands over what it has, once, and says how much that was.
 *
 * emperor-visit-request.txt (the player's bridge, progress_client.visit_sync): "<roster> <slot> <visit> <resource> <amount>"
 *   A visit number above the last one known here is served once: up to <amount> loads of <resource> leave the
 *   warehouses, and for food the granaries after them (the original removal the emperor's requests use).
 * emperor-visit.txt (written here): "<visit> <resource> <amount> <taken> <treasury>"
 *   treasury: what this city has now; the room never asks for more money than that for missing goods.
 * The last visit, its good and what was taken are kept in the city save, in the unused tail of the army book piece
 * after the expedition record: the save format does not change, a save without it reads as "none". A reload or a
 * resent order therefore never takes the goods twice. */
#include "building/warehouse.h"
#include "building/granary.h"
#include "city/finance.h"
#include "game/resource.h"
static struct {char magic[4];unsigned id;int resource,amount,taken;} visit;
typedef char visit_fits_in_the_army_book[(4+sizeof(book)+sizeof(raid)+sizeof(visit)+4<=MP_ARMY_SAVE_BYTES)?1:-1];
static void visit_reset(void){memset(&visit,0,sizeof(visit));}
static void visit_save(unsigned char *p){if(visit.id){memcpy(visit.magic,"VIST",4);memcpy(p,&visit,sizeof(visit));}}
static void visit_restore(const unsigned char *p){
 memcpy(&visit,p,sizeof(visit));
 if(memcmp(visit.magic,"VIST",4) || !visit.id || visit.id>1000 || visit.resource<RESOURCE_MIN || visit.resource>=RESOURCE_MAX ||
    visit.amount<1 || visit.amount>32 || visit.taken<0 || visit.taken>visit.amount)visit_reset();
}
static void visit_poll(const char *dir){
 char path[4096],scope[65];unsigned owner,id;int resource,amount;
 snprintf(path,sizeof(path),"%s/emperor-visit-request.txt",dir);FILE *f=fopen(path,"rb");
 if(f){
  int n=fscanf(f,"%64s %u %u %d %d",scope,&owner,&id,&resource,&amount);fclose(f);
  if(n==5 && id>visit.id && id<=1000 && resource>=RESOURCE_MIN && resource<RESOURCE_MAX && amount>=1 && amount<=32 && mp_post_city_attach(scope,owner)){
   int left=building_warehouses_remove_resource(resource,amount);
   if(left>0 && resource_is_food(resource))left=building_granaries_remove_resource(resource,left);
   if(left<0)left=0;if(left>amount)left=amount;
   visit.id=id;visit.resource=resource;visit.amount=amount;visit.taken=amount-left;
   log_info("Emperor's visit served, loads:",0,visit.taken);
  }
 }
 if(visit.id){
  char text[96];int n=snprintf(text,sizeof(text),"%u %d %d %d %d\n",visit.id,visit.resource,visit.amount,visit.taken,(int)city_finance_treasury());
  if(n>0 && n<(int)sizeof(text))mp_publish_text(dir,"emperor-visit",text,(size_t)n);
 }
}
