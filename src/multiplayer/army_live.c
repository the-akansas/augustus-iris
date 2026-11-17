#include "mailbox_publish.h"
/* Main-thread military deltas. Receipt and native soldiers share one SAV.
 * Unknown/missing replies never authorize a second command or compensation. */
#include "army_live.h"
#include "army_seal.h"
#include "post_city.h"
#include "figure/figure.h"
#include "figure/formation.h"
#include "figure/properties.h"
#include "building/building.h"
#include "building/type.h"
#include "building/state.h"
#include "map/grid.h"
#include "core/log.h"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int allocation_budget=-1;
void mp_army_test_allocation_budget(int n){allocation_budget=n;}
static figure *army_allocate(figure_type type,int x,int y,direction_type d){if(allocation_budget==0)return figure_get(0);if(allocation_budget>0)allocation_budget--;return figure_create(type,x,y,d);}
#include "expedition_native.h"
#include "expedition_visit.h"
typedef struct {char id[65],request[4096],result[4096];int applied;} receipt;
/* last soldiers seen alive per visiting legion: see remember_legion() */
static struct {unsigned token;int role;unsigned alive;int damage[16];} last_seen_legion[32];
static struct {unsigned count;receipt rows[64];} book;
#include "emperor_raid.inc"
#include "emperor_visit.inc"
static unsigned crc(const unsigned char *p,size_t n){unsigned c=~0u;for(size_t i=0;i<n;i++){c^=p[i];for(int k=0;k<8;k++)c=(c>>1)^(0xedb88320u&-(int)(c&1));}return ~c;}
void mp_army_reset(void){memset(&book,0,sizeof(book));raid_reset();visit_reset();}
void mp_army_save(buffer *b){memset(b->data,0,b->size);memcpy(b->data,"MAL1",4);memcpy(b->data+4,&book,sizeof(book));raid_save(b->data+4+sizeof(book));visit_save(b->data+4+sizeof(book)+sizeof(raid));unsigned c=crc(b->data,b->size-4);memcpy(b->data+b->size-4,&c,4);}
int mp_army_restore(const buffer *b){if(!b){mp_army_reset();return 1;}unsigned c;memcpy(&c,b->data+b->size-4,4);if(b->size!=MP_ARMY_SAVE_BYTES || memcmp(b->data,"MAL1",4) || c!=crc(b->data,b->size-4))return 0;unsigned n;memcpy(&n,b->data+4,4);if(n>64)return 0;memcpy(&book,b->data+4,sizeof(book));for(unsigned i=0;i<n;i++)if(!memchr(book.rows[i].id,0,65)||!memchr(book.rows[i].request,0,4096)||!memchr(book.rows[i].result,0,4096))return 0;raid_restore(b->data+4+sizeof(book));visit_restore(b->data+4+sizeof(book)+sizeof(raid));return 1;}
static int manifest(const char *dir,unsigned token,int form,const char *expected,char *result){
 if(form<=0 || form>=formation_count())return 0;formation *m=formation_get(form);
 int fort,type,n,used;const char *p=expected;
 if(sscanf(p,"%d %d %d%n",&fort,&type,&n,&used)!=3 || n<1 || n>16 || m->building_id!=fort || m->figure_type!=type)return 0;p+=used;
 int ids[16],gens[16];for(int i=0;i<n;i++){if(sscanf(p,"%d %d%n",&ids[i],&gens[i],&used)!=2)return 0;p+=used;}
 int count=0;for(unsigned i=1;i<figure_count();i++){figure *v=figure_get(i);if(!figure_is_dead(v) && v->formation_id==(unsigned)form && figure_is_legion(v)){if(count>=n || v->id!=(unsigned)ids[count] || v->created_sequence!=(unsigned)gens[count])return 0;count++;}}
 if(count!=n)return 0;
 int pos=snprintf(result,4096,"EX2 %u %d %d %d %d %d %d %d %d %d %d\n",token,form,fort,type,m->morale,m->has_military_training,m->months_from_home,m->months_low_morale,m->months_very_low_morale,m->mess_hall_max_morale_modifier,n);
 for(int i=0;i<n;i++){figure *v=figure_get(ids[i]);pos+=snprintf(result+pos,4096-pos,"%u %u %u %u %u %d %d\n",v->id,v->created_sequence,v->damage,v->x,v->y,v->name,v->direction);}return pos<4096;
}
static int act(const char *dir,unsigned token,int step,int role,int form,const char *payload,char *result){
 char path[4096];
 if(step==1){if(!manifest(dir,token,form,payload,result))return 0;}
 else {if(strlen(payload)>=4096)return 0;strcpy(result,payload);}
 snprintf(path,sizeof(path),"%s/expedition.txt",dir);FILE *f=fopen(path,"wb");if(!f)return 0;fputs(result,f);if(fclose(f))return 0;
 if(step==1 || step==4)return expedition_transform(dir,step==4);
 unsigned saved_token;int home,fort,type,morale,trained,months,low,verylow,food,n,offset;
 if(sscanf(result,"EX2 %u %d %d %d %d %d %d %d %d %d %d%n",&saved_token,&home,&fort,&type,&morale,&trained,&months,&low,&verylow,&food,&n,&offset)!=11 || saved_token!=token || n<0 || n>16)return 0;
 int ids[16],gens[16],damage[16],x[16],y[16],names[16],dirs[16];char *p=result+offset;int used;
 for(int i=0;i<n;i++){if(sscanf(p,"%d %d %d %d %d %d %d%n",&ids[i],&gens[i],&damage[i],&x[i],&y[i],&names[i],&dirs[i],&used)!=7)return 0;p+=used;}
 int gone=0;
 if(step==3){
  formation *visitor=0;for(int i=1;i<formation_count();i++){formation *m=formation_get(i);if(m->in_use && m->mp_expedition_id==token && m->mp_expedition_role==role){if(visitor)return 0;visitor=m;}}
  int alive[16]={0};
  if(visitor){for(unsigned i=1;i<figure_count();i++){figure *v=figure_get(i);if(!figure_is_dead(v) && v->formation_id==visitor->id){int k=v->mp_source-1;if(k<0 || k>=n || alive[k])return 0;alive[k]=1;damage[k]=v->damage;}}morale=visitor->morale;}
  else{   /* left the map (an attack that retreated): those last seen alive go home; unknown -> not applied, as before */
   int slot=-1;for(int i=0;i<32;i++)if(last_seen_legion[i].token==token && last_seen_legion[i].role==role){slot=i;break;}
   if(slot<0)return 0;
   for(int i=0;i<n;i++)if(last_seen_legion[slot].alive&(1u<<i)){alive[i]=1;damage[i]=last_seen_legion[slot].damage[i];}
   gone=1;
  }
  int survivors=0;for(int i=0;i<n;i++)survivors+=alive[i];
  int pos=snprintf(result,4096,"EX2 %u %d %d %d %d %d %d %d %d %d %d\n",token,home,fort,type,morale,trained,months,low,verylow,food,survivors);
  for(int i=0;i<n;i++)if(alive[i])pos+=snprintf(result+pos,4096-pos,"%d %d %d %d %d %d %d\n",ids[i],gens[i],damage[i],x[i],y[i],names[i],dirs[i]);
 }
 snprintf(path,sizeof(path),"%s/visitor.txt",dir);f=fopen(path,"wb");if(!f)return 0;
 fprintf(f,"VIS1 %u %d %d %d %d %d %d %d\n",token,role,type,morale,trained,months,food,n);
 for(int i=0;i<n;i++)fprintf(f,"%d %d\n",damage[i],names[i]);if(fclose(f))return 0;
 if(gone)return 1;   /* nothing left on this map to remove */
 return expedition_visit(dir,step==3);
}
/* Last known soldiers of each visiting legion (which arrived soldiers were alive, and their damage). An attack force
 * that loots and retreats walks off the map and its formation is cleared: the recall (step 3) then sends home those
 * last seen alive instead of failing (user 2026-11-13: the sender's list kept it 'stationed' forever). */
static void remember_legion(const formation *m,int index){
 unsigned alive=0;int damage[16]={0};
 for(unsigned j=1;j<figure_count();j++){const figure *v=figure_get(j);if(v->formation_id!=(unsigned)index || figure_is_dead(v))continue;int k=v->mp_source-1;if(k>=0 && k<16){alive|=1u<<k;damage[k]=v->damage;}}
 int slot=-1;for(int i=0;i<32;i++)if(last_seen_legion[i].token==m->mp_expedition_id){slot=i;break;}
 if(slot<0)for(int i=0;i<32;i++)if(!last_seen_legion[i].token){slot=i;break;}
 if(slot<0)slot=(int)(m->mp_expedition_id%32);
 last_seen_legion[slot].token=m->mp_expedition_id;last_seen_legion[slot].role=m->mp_expedition_role;last_seen_legion[slot].alive=alive;
 memcpy(last_seen_legion[slot].damage,damage,sizeof(damage));
}
/* Visiting troops as this city sees them: "token role alive" per line. The room uses it
 * to send a wiped-out support legion home instead of listing it as stationed forever. */
static void publish_visitors(const char *dir){
 char text[2048];int used=0;
 for(int i=1;i<formation_count() && used<(int)sizeof(text)-48;i++){
  const formation *m=formation_get(i);if(!m->in_use || !m->mp_expedition_role)continue;
  int alive=0;for(unsigned j=1;j<figure_count();j++){const figure *v=figure_get(j);if(v->formation_id==(unsigned)i && !figure_is_dead(v))alive++;}
  used+=snprintf(text+used,sizeof(text)-used,"%u %d %d\n",m->mp_expedition_id,m->mp_expedition_role,alive);
  remember_legion(m,i);
  /* Game log: every change in a visiting legion's head count (2026-11-13: sixteen arrived, eight were left
   * forty seconds later and nothing recorded why). */
  {static unsigned seen_token[32];static int seen_alive[32];int k=i&31;
   if(seen_token[k]!=m->mp_expedition_id || seen_alive[k]!=alive){
    char note[96];snprintf(note,sizeof(note),"token %u role %d layout %d at %d,%d morale %d alive",m->mp_expedition_id,m->mp_expedition_role,m->layout,m->standard_x,m->standard_y,m->morale);
    log_info("Visiting legion",note,alive);seen_token[k]=m->mp_expedition_id;seen_alive[k]=alive;}}
 }
 mp_publish_text(dir,"army-visitors",text,(size_t)used);
}
void mp_army_poll(const char *dir){
 raid_poll(dir);visit_poll(dir);   /* the emperor's punitive expedition (Race for the Throne): not part of the sealed dispatch */
 if(MP_ARMY_DISPATCH_SEALED)return;   /* sealed (army_seal.h): no visitors to report, no transfers to apply */
 publish_visitors(dir);
 char path[4096],tmp[4096],request[4096]={0},scope[65],id[65];unsigned owner,token;int step,role,form,offset;
 snprintf(path,sizeof(path),"%s/army-live-request.txt",dir);FILE *f=fopen(path,"rb");if(!f)return;size_t n=fread(request,1,4095,f);int extra=fgetc(f);fclose(f);if(!n || extra!=EOF)return;
 if(sscanf(request,"%64s %u %64s %u %d %d %d%n",scope,&owner,id,&token,&step,&role,&form,&offset)!=7 || strlen(id)!=32 || strspn(id,"0123456789abcdef")!=32 || !token || step<1 || step>4 || role<1 || role>2 || !mp_post_city_attach(scope,owner))return;
 while(request[offset]=='\n' || request[offset]=='\r' || request[offset]==' ' || request[offset]=='\t')offset++;
 receipt *r=0;for(unsigned i=0;i<book.count;i++)if(!strcmp(book.rows[i].id,id)){r=&book.rows[i];break;}
 if(r && strcmp(r->request,request))return;
 if(!r){if(book.count>=64)return;r=&book.rows[book.count];memset(r,0,sizeof(*r));strcpy(r->id,id);strcpy(r->request,request);r->applied=act(dir,token,step,role,form,request+offset,r->result);book.count++;}
 char output[4200];int length=snprintf(output,sizeof(output),"%s %d\n%s",r->id,r->applied,r->result);
 if(length>=0 && length<(int)sizeof(output))mp_publish_text(dir,"army-live-response",output,(size_t)length);
}
