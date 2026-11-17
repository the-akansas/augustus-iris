/* Local creator cache only: decode the owner's original map with the game engine. */
#include "graphics/renderer.h"
static int creator_export_map(const char *out)
{
    const image *img=image_get(empire_get_image_id());
    int w=img->width,h=img->height;
    if(image_is_external(img) && !image_get_external_dimensions(img,&w,&h))return 0;
    if(w<=0 || h<=0 || w>4096 || h>4096)return 0;
    color_t *pixels=calloc((size_t)w*h,sizeof(color_t));if(!pixels)return 0;
    int ok=0;
    if(image_is_external(img))ok=image_load_external_pixels(pixels,img,w);
    else {
        if(image_load_climate(scenario_property_climate(),0,1,1)){
            img=image_get(empire_get_image_id());
            const image_atlas_data *a=graphics_renderer()->get_image_atlas(img->atlas.id>>IMAGE_ATLAS_BIT_OFFSET);
            int i=img->atlas.id & IMAGE_ATLAS_BIT_MASK;
            if(a && i<a->num_images && a->buffers[i]){
                for(int y=0;y<h;y++)memcpy(pixels+y*w,a->buffers[i]+(y+img->atlas.y_offset)*a->image_widths[i]+img->atlas.x_offset,w*4);
                ok=1;
            }
        }
    }
    if(!ok){free(pixels);return 0;}
    char path[2048];snprintf(path,sizeof(path),"%s/empire.bmp",out);
    FILE *f=fopen(path,"wb");if(!f){free(pixels);return 0;}
    unsigned char head[54]={0};head[0]='B';head[1]='M';
    put(head+2,54+(uint64_t)w*h*4,4);put(head+10,54,4);put(head+14,40,4);
    put(head+18,w,4);put(head+22,h,4);put(head+26,1,2);put(head+28,32,2);
    ok=fwrite(head,1,54,f)==54;
    for(int y=h-1;y>=0 && ok;y--)ok=fwrite(pixels+y*w,4,w,f)==(size_t)w;
    free(pixels);if(fclose(f))ok=0;return ok;
}

#include "core/encoding.h"
#include "core/lang.h"
static void creator_json_text(FILE *f,const uint8_t *value){
 char text[1024];encoding_to_utf8(value,text,sizeof(text),0);fputc('"',f);
 for(unsigned char *c=(unsigned char*)text;*c;c++){if(*c=='"' || *c==92)fputc(92,f);if(*c<32)fputc(' ',f);else fputc(*c,f);}fputc('"',f);
}
static int creator_export_catalogs(const char *out){
 static const char *groups[]={"주택","정리","도로","물 공급","보건","종교","교육","오락","행정","시설","치안과 군사","산업","농장","원자재","공방","소형 신전","대형 신전","군단 요새","공원","나무","정원 길","대신전","조각상","총독 관저","성소","정원"};
 char path[2048];snprintf(path,sizeof(path),"%s/building-catalog.json",out);FILE *f=fopen(path,"wb");if(!f)return 0;
 fputc('[',f);int seen[BUILDING_TYPE_MAX]={0},first=1;
 for(int menu=0;menu<BUILD_MENU_MAX;menu++)for(int item=0;item<building_menu_count_all_items(menu);item++){
  int type=building_menu_type(menu,item);if(type<=0 || type>=BUILDING_TYPE_MAX || seen[type] || type==BUILDING_CLEAR_LAND || type==BUILDING_REPAIR_LAND || building_menu_get_submenu_for_type(type)>0)continue;
  seen[type]=1;fprintf(f,"%s{\"id\":%d,\"name\":",first?"":",",type);first=0;creator_json_text(f,lang_get_string(28,type));fprintf(f,",\"category\":\"%s\",\"menu\":%d}",groups[menu],menu);
 }fputc(']',f);if(fclose(f))return 0;
 snprintf(path,sizeof(path),"%s/creator-city-catalog.json",out);f=fopen(path,"wb");if(!f)return 0;fputc('[',f);
 for(int id=1;id<=39;id++){fprintf(f,"%s{\"name_id\":%d,\"name\":",id==1?"":",",id);creator_json_text(f,lang_get_string(21,id));fputc('}',f);}fputc(']',f);return fclose(f)==0;
}

#include "scenario/invasion.h"
#include "scenario/request.h"
#include "scenario/price_change.h"
#include "scenario/demand_change.h"
#include "scenario/event/controller.h"
/* Inventory contains metadata only; decoded tiles remain in each owner's private cache. */
static int creator_export_preset(const char *out,int id){
 char path[2048];snprintf(path,sizeof(path),"%s/preset.json",out);FILE *f=fopen(path,"w");if(!f)return 0;
 int own=0;for(int i=0;i<empire_city_get_array_size();i++){empire_city *c=empire_city_get(i);if(c->in_use && c->type==EMPIRE_CITY_OURS)own=c->name_id;}
 const campaign_scenario *mission=id<20?game_campaign_get_scenario(id):0;
 fprintf(f,"{\"id\":%d,\"title\":",id);
 creator_json_text(f,mission?mission->name:lang_get_string(21,CREATOR_BUILTIN_NAMES[id-100]));
 fprintf(f,",\"name_id\":%d,\"climate\":%d,\"width\":%d,\"height\":%d,\"empire_template\":%d,\"empire_raw_id\":%d,\"empire_source\":\"%s\",\"source_file\":\"",own,scenario.climate,map_grid_width(),map_grid_height(),scenario.empire.id+(id>=100?1000:0),scenario.empire.id,id>=100?"c32.emp":"c3.emp");
 fprintf(f,id<20?"mission1.pak":"%s.map",id>=100?CREATOR_BUILTIN_MAPS[id-100]:"");
 fprintf(f,"\",\"original_start_year\":%d,\"original_funds\":%d,\"original_rules\":{\"events\":%d,\"invasions\":%d,\"requests\":%u,\"price_changes\":%d,\"demand_changes\":%d,\"population_goal\":%d,\"culture_goal\":%d,\"prosperity_goal\":%d,\"peace_goal\":%d,\"favor_goal\":%d,\"time_limit\":%d,\"survival_years\":%d}}",scenario.start_year,scenario.initial_funds,scenario_events_get_count(),scenario_invasion_count_active(),scenario_request_count_active(),scenario_price_change_count_active(),scenario_demand_change_count_active(),scenario.win_criteria.population.enabled?scenario.win_criteria.population.goal:0,scenario.win_criteria.culture.enabled?scenario.win_criteria.culture.goal:0,scenario.win_criteria.prosperity.enabled?scenario.win_criteria.prosperity.goal:0,scenario.win_criteria.peace.enabled?scenario.win_criteria.peace.goal:0,scenario.win_criteria.favor.enabled?scenario.win_criteria.favor.goal:0,scenario.win_criteria.time_limit.enabled?scenario.win_criteria.time_limit.years:0,scenario.win_criteria.survival_time.enabled?scenario.win_criteria.survival_time.years:0);
 return fclose(f)==0;
}
