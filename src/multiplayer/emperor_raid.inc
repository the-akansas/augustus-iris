/* The emperor's punitive expedition against this city (Race for the Throne, 황위 시험 규칙 v1, 2026-11-14).
 * Included by army_live.c. The room decides when an expedition comes and when it is called back
 * (Augustus/throne_play.py, throne_state.step_raids); this city fights it with the original Caesar legions and
 * says what it sees. Nothing here touches money or the paranoia value.
 *
 * emperor-raid-request.txt (the player's bridge, throne_client.raid_sync): "<roster> <slot> <count> <size> <order>"
 *   order 1  expedition <count> belongs in the city. A number above the last one known here is let in once:
 *            <size> legionaries at the city's entry, with the original "Caesar's legions" message.
 *   order 2  expedition <count> is over (tribute paid, siege time up, trial ended): legions still here retreat.
 *            A number never seen here is only noted and never let in.
 * emperor-raid.txt (written here): "<count> <state> <size> <killed> <alive>"
 *   state 1 attacking, 2 called back and leaving, 3 gone without having been called back (beaten or routed),
 *   4 gone after being called back.
 * The last number, its state and size are kept in the city save, in the unused tail of the army book piece: the
 * save format does not change, and a save without it reads as "none". A reload or a resent order therefore never
 * lets the same expedition in twice. */
#include "city/figures.h"
#include "scenario/invasion.h"
void city_emperor_mp_raid_begin(int size);
void city_emperor_mp_raid_end(void);
int city_emperor_mp_raid_killed(void);
enum {RAID_NONE,RAID_ATTACKING,RAID_LEAVING,RAID_BEATEN,RAID_LEFT};
static struct {char magic[4];unsigned count;int state,size,seen;} raid;
typedef char raid_fits_in_the_army_book[(4+sizeof(book)+sizeof(raid)+4<=MP_ARMY_SAVE_BYTES)?1:-1];
static void raid_reset(void){memset(&raid,0,sizeof(raid));}
static void raid_save(unsigned char *p){if(raid.count){memcpy(raid.magic,"RAID",4);memcpy(p,&raid,sizeof(raid));}}
static void raid_restore(const unsigned char *p){
 memcpy(&raid,p,sizeof(raid));
 if(memcmp(raid.magic,"RAID",4) || !raid.count || raid.count>1000000 || raid.state<RAID_ATTACKING || raid.state>RAID_LEFT || raid.size<1 || raid.size>200)raid_reset();
}
/* While an expedition is in the city the original favour logic (pause, recall, "Caesar respects you") stays out of
 * it (city/emperor.c): the room decides how it ends. */
int mp_emperor_raid_active(void){return raid.state==RAID_ATTACKING || raid.state==RAID_LEAVING;}
static void raid_poll(const char *dir){
 int alive=city_figures_imperial_soldiers();
 if(mp_emperor_raid_active()){
  if(alive>0)raid.seen=1;
  else if(raid.seen){raid.state=raid.state==RAID_ATTACKING?RAID_BEATEN:RAID_LEFT;city_emperor_mp_raid_end();}
  if(raid.state==RAID_LEAVING)formation_caesar_retreat();   /* every time: a formation must not change its mind */
 }
 char path[4096],scope[65];unsigned owner,count;int size,order;
 snprintf(path,sizeof(path),"%s/emperor-raid-request.txt",dir);FILE *f=fopen(path,"rb");
 if(f){
  int n=fscanf(f,"%64s %u %u %d %d",scope,&owner,&count,&size,&order);fclose(f);
  if(n==5 && count>0 && count<=1000000 && size>=1 && size<=200 && (order==1 || order==2) && mp_post_city_attach(scope,owner)){
   if(count>raid.count){
    if(order==1){
     if(scenario_invasion_start_from_caesar(size)){   /* not let in (no entry point yet, invasions off): tried again next time */
      city_emperor_mp_raid_begin(size);raid.count=count;raid.state=RAID_ATTACKING;raid.size=size;raid.seen=0;
      log_info("Emperor's expedition let in, legionaries:",0,size);
     }
    }else{   /* over before this city ever saw it: legions of an older one, if any, go home with it */
     raid.state=mp_emperor_raid_active()?RAID_LEAVING:RAID_LEFT;raid.count=count;raid.size=size;if(raid.state==RAID_LEFT)raid.seen=1;
    }
   }else if(count==raid.count && order==2 && raid.state==RAID_ATTACKING){
    raid.state=RAID_LEAVING;formation_caesar_retreat();log_info("Emperor's expedition called back",0,0);
   }
  }
 }
 if(raid.count){
  char text[96];int n=snprintf(text,sizeof(text),"%u %d %d %d %d\n",raid.count,raid.state,raid.size,city_emperor_mp_raid_killed(),alive);
  if(n>0 && n<(int)sizeof(text))mp_publish_text(dir,"emperor-raid",text,(size_t)n);
 }
}
