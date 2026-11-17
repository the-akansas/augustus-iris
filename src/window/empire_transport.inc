#include "input/mouse.h"
/* Read-only schematic animation. Never changes simulation, receipts or saves. */
typedef struct { int active,src,dst,res,at_dst,x,y,w,icon_x,icon_y,icon,quantity,tone,hover;
    unsigned int contract,animated_contract,frame_at; int motion,version,arrived,server_progress;
    float progress; char lines[3][768]; } freight_item;
static freight_item freight_items[64],*freight_selected;
static unsigned int freight_read_at;
#define mp_freight (*freight_selected)
static void freight_read(void)
{
    unsigned int now=time_get_millis();if(now-freight_read_at<250)return;freight_read_at=now;
    const char *root=getenv("AUGUSTUS_MP_BRIDGE");if(!root || !mp_clock_active())return;
    char path[2048],line[128];snprintf(path,sizeof(path),"%s/empire-fleet.txt",root);
    FILE*f=fopen(path,"rb");if(!f)return;
    freight_item incoming[64]={0};int count=-1,ok=1;
    if(!fgets(line,sizeof(line),f) || sscanf(line,"%d",&count)!=1 || count<0 || count>64){fclose(f);return;}
    for(int i=0;i<count && ok;i++){
        freight_item*v=&incoming[i];
        if(!fgets(line,sizeof(line),f)){ok=0;break;}
        int fields=sscanf(line,"%d %d %d %d %d %d %d %u %d %d",&v->version,&v->src,&v->dst,&v->res,&v->at_dst,&v->quantity,&v->tone,&v->contract,&v->motion,&v->server_progress);
        if(fields!=(v->version==3?10:9) || (v->version!=2 && v->version!=3) || v->server_progress<0 || v->server_progress>1000 || !v->contract || v->res<0 || v->res>=RESOURCE_MAX || v->motion<0 || v->motion>4){ok=0;break;}
        for(int j=0;j<i;j++)if(incoming[j].contract==v->contract)ok=0;
        for(int j=0;j<3;j++){if(!fgets(v->lines[j],sizeof(v->lines[j]),f)){ok=0;break;}v->lines[j][strcspn(v->lines[j],"\r\n")]=0;}
    }
    fclose(f);if(!ok)return;
    freight_item next[64]={0};
    for(int i=0;i<count;i++){
        next[i]=incoming[i];next[i].active=1;
        if(next[i].motion==2)next[i].progress=1000.0f;
        for(int j=0;j<64;j++)if(freight_items[j].contract==next[i].contract){
            next[i].progress=freight_items[j].progress;next[i].arrived=freight_items[j].arrived;
            next[i].frame_at=freight_items[j].frame_at;break;
        }
    }
    memcpy(freight_items,next,sizeof(next));
}
static const empire_object *freight_city(int name)
{
    for(int i=0;i<empire_object_count();i++){
        const full_empire_object*f=empire_object_get_full(i);
        if(f->in_use && f->obj.type==EMPIRE_OBJECT_CITY && f->city_name_id==name)return &f->obj;
    }
    return 0;
}
static void freight_advance(freight_item*f,unsigned int now){
    if(f->version==3){f->progress=f->server_progress;f->arrived=f->server_progress>=1000;f->frame_at=now;return;}
    unsigned int elapsed=now-f->frame_at;f->frame_at=now;
    if(elapsed>100)elapsed=100; /* No jump after closing/reopening the map. */
    if(f->progress>=1000.0f)f->arrived=1;
    float target=f->motion==1?850.0f:f->motion==2?1000.0f:f->motion==4?f->progress:0.0f;
    float step=elapsed*0.06f;
    if(f->progress<target){f->progress+=step;if(f->progress>target)f->progress=target;}
    else if(f->progress>target){f->progress-=step;if(f->progress<target)f->progress=target;}
}
static void freight_map_one(void)
{
    mp_freight.icon=0;if(!mp_freight.active || data.sidebar.trade_year)return;
    const empire_object*a=freight_city(mp_freight.src),*b=freight_city(mp_freight.dst);
    if(!a || !b)return;
    /* city centres through the map zoom (ezx/ezy, empire.c) */
    int ax=data.x_draw_offset+ezx((scenario_empire_is_expanded()?a->expanded.x:a->x)+25),ay=data.y_draw_offset+ezy((scenario_empire_is_expanded()?a->expanded.y:a->y)+25);
    int bx=data.x_draw_offset+ezx((scenario_empire_is_expanded()?b->expanded.x:b->x)+25),by=data.y_draw_offset+ezy((scenario_empire_is_expanded()?b->expanded.y:b->y)+25);
    freight_advance(&mp_freight,time_get_millis());
    float p=mp_freight.version==1?(mp_freight.at_dst?1.0f:0.0f):mp_freight.progress/1000.0f;
    int x=ax+(int)((bx-ax)*p)+18+((int)(mp_freight.contract%5)-2)*8,y=ay+(int)((by-ay)*p)-18+((int)(mp_freight.contract%3)-1)*8;
    mp_freight.icon_x=x;mp_freight.icon_y=y;
    mp_freight.icon=x>=data.x_min+16 && x+52<=data.sidebar.x_min && y>=data.y_min+16 && y+28<=data.y_max-BOTTOM_PANEL_HEIGHT;
    const mouse*m=mouse_get();
    mp_freight.hover=mp_freight.icon && m->x>=x && m->x<x+52 && m->y>=y && m->y<y+28;
    if(mp_freight.hover){
        /* Schematic relationship, not an actual land/sea route. */
        int steps=(abs(bx-ax)+abs(by-ay))/10+1;
        for(int i=0;i<=steps;i++){
            int px=ax+(bx-ax)*i/steps,py=ay+(by-ay)*i/steps;
            graphics_fill_rect(px-1,py-1,3,3,COLOR_BLACK);graphics_fill_rect(px,py,1,1,COLOR_FONT_YELLOW);
        }
    }
    if(!mp_freight.icon)return;
    color_t border=mp_freight.tone==2?0xffff8060:mp_freight.tone==3?0xff80d888:mp_freight.tone==1?0xffffcf70:0xffc79a59;
    graphics_fill_rect(x,y,52,28,0xff322a21);
    graphics_draw_rect(x,y,52,28,border);
    if(mp_freight.hover)graphics_draw_rect(x+1,y+1,50,26,COLOR_WHITE);
    if(mp_freight.res)image_draw(resource_get_data(mp_freight.res)->image.empire,x+1,y+1,COLOR_MASK_NONE,SCALE_NONE);
    else if(!mp_freight.quantity){
        /* Unloaded caravan on its way out of the destination city: no goods icon. */
        uint8_t leaving[32];encoding_from_utf8("퇴장",leaving,sizeof(leaving));
        text_draw_centered(leaving,x,y+7,52,FONT_NORMAL_WHITE,0);
    }
    else text_draw((const uint8_t*)"Dn",x+3,y+7,FONT_NORMAL_WHITE,0);
    char count[16];snprintf(count,sizeof(count),"%d",mp_freight.quantity);
    if(mp_freight.res)text_draw((const uint8_t*)count,x+32,y+7,FONT_NORMAL_WHITE,0);
}
static void freight_card_one(void)
{
    mp_freight.w=0;
    if(!mp_freight.active || !mp_freight.hover || !mp_freight.icon || data.sidebar.trade_year)return;
    int width=data.sidebar.x_min-data.x_min-40;if(width<100)return;if(width>320)width=320;
    int x=mp_freight.icon_x,y=mp_freight.icon_y+34;
    if(x+width>data.sidebar.x_min-8)x=data.sidebar.x_min-8-width;
    if(x<data.x_min+20)x=data.x_min+20;
    if(y+60>data.y_max-BOTTOM_PANEL_HEIGHT)y=mp_freight.icon_y-66;
    if(y<data.y_min+20)y=data.y_min+20;
    graphics_fill_rect(x,y,width,60,0xff322a21);graphics_draw_rect(x,y,width,60,COLOR_BORDER_BROWN);
    for(int i=0;i<3;i++){
        uint8_t buf[1024];encoding_from_utf8(mp_freight.lines[i],buf,sizeof(buf));
        text_draw_ellipsized(buf,x+6,y+5+i*17,width-12,FONT_NORMAL_WHITE,0);
    }
}

static int freight_input_one(const mouse*m)
{
    if(!mp_freight.active || !mp_clock_active() || data.sidebar.trade_year)return 0;
    int icon=mp_freight.icon && m->x>=data.x_min+16 && m->x<data.sidebar.x_min && m->y>=data.y_min+16 && m->y<data.y_max-BOTTOM_PANEL_HEIGHT && m->x>=mp_freight.icon_x && m->x<mp_freight.icon_x+52 && m->y>=mp_freight.icon_y && m->y<mp_freight.icon_y+28;
    if(!icon)return 0;
    if(m->left.went_up)window_multiplayer_transport_show();
    return 1;
}

static void freight_map(void){freight_read();for(int i=0;i<64;i++){freight_selected=&freight_items[i];freight_map_one();}}
static void freight_card(void){for(int i=0;i<64;i++){freight_selected=&freight_items[i];freight_card_one();}}
static int freight_input(const mouse*m){for(int i=63;i>=0;i--){freight_selected=&freight_items[i];if(freight_input_one(m))return 1;}return 0;}
#undef mp_freight
