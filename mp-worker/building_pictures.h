/* Building pictures for the scenario editor's build list (user 2026-11-15: "like the game's build panel, friendlier").
   Read-only: the owner's own game graphics are drawn once into the editor's private cache, never shipped. Writes, for
   each building type asked for, the planes of the image the game draws for it (footprint and top, as walk_assets.h),
   and the build-menu buttons, with one line each in pictures.txt. */
#include "assets/assets.h"
#include "assets/image.h"
#include "building/image.h"
#include "building/properties.h"
#include "core/image_group.h"
static int picture_plane(const char *out,FILE *meta,const char *kind,int key,const image *im,int part){
 if(!im || im->width<=0 || im->height<=0)return 0;
 const image_atlas_data *a=graphics_renderer()->get_image_atlas(im->atlas.id>>IMAGE_ATLAS_BIT_OFFSET);
 int i=im->atlas.id&IMAGE_ATLAS_BIT_MASK;
 if(!a || i>=a->num_images || !a->buffers || !a->buffers[i])return 0;   /* an image the renderer keeps alone: see picture_alone */
 char p[2048];snprintf(p,sizeof(p),"%s/%s-%d-%d.bgra",out,kind,key,part);
 FILE *f=fopen(p,"wb");if(!f)return 0;int ok=1;
 for(int y=0;y<im->height;y++)if(fwrite(a->buffers[i]+(y+im->atlas.y_offset)*a->image_widths[i]+im->atlas.x_offset,4,im->width,f)!=(size_t)im->width)ok=0;
 if(fclose(f))ok=0;
 /* kind key part width height x_offset y_offset original_width original_height isometric */
 if(ok)fprintf(meta,"%s %d %d %d %d %d %d %d %d %d\n",kind,key,part,im->width,im->height,im->x_offset,im->y_offset,im->original.width,im->original.height,im->is_isometric);
 return ok;
}
/* A big extra-asset image (a grand temple, the pantheon) is not packed into an atlas: the renderer draws it from the
   asset's own pixels (assets_load_unpacked_asset, SDL renderer load_unpacked_image): one buffer as wide as the image,
   the footprint and the top at their atlas offsets in it. A reference image uses the pixels of the one it refers to. */
static int picture_buffer(const char *out,FILE *meta,const char *kind,int key,const image *im,int part,const color_t *pixels,int stride,int rows){
 if(!im || im->width<=0 || im->height<=0 || im->atlas.x_offset<0 || im->atlas.y_offset<0 || im->atlas.x_offset+im->width>stride || im->atlas.y_offset+im->height>rows)return 0;
 char p[2048];snprintf(p,sizeof(p),"%s/%s-%d-%d.bgra",out,kind,key,part);
 FILE *f=fopen(p,"wb");if(!f)return 0;int ok=1;
 for(int y=0;y<im->height;y++)if(fwrite(pixels+(size_t)(y+im->atlas.y_offset)*stride+im->atlas.x_offset,4,im->width,f)!=(size_t)im->width)ok=0;
 if(fclose(f))ok=0;
 if(ok)fprintf(meta,"%s %d %d %d %d %d %d %d %d %d\n",kind,key,part,im->width,im->height,im->x_offset,im->y_offset,im->original.width,im->original.height,im->is_isometric);
 return ok;
}
static int picture_alone(const char *out,FILE *meta,const char *kind,int key,int id){
 if(id<IMAGE_MAIN_ENTRIES)return 0;
 const asset_image *ai=asset_image_get_from_id(id-IMAGE_MAIN_ENTRIES);
 if(!ai)return 0;
 const color_t *pixels=ai->data;
 if(ai->is_reference){const asset_image *r=asset_image_get_from_id(ai->first_layer.calculated_image_id-IMAGE_MAIN_ENTRIES);pixels=r?r->data:0;}
 if(!pixels)return 0;
 const image *im=&ai->img;int rows=im->height+(im->top?im->top->height:0);
 if(!picture_buffer(out,meta,kind,key,im,0,pixels,im->width,rows))return 0;
 if(im->top)picture_buffer(out,meta,kind,key,im->top,1,pixels,im->width,rows);
 return 1;
}
static int picture_export(const char *out,FILE *meta,const char *kind,int key,int id){
 const image *im=image_get(id);
 if(picture_plane(out,meta,kind,key,im,0)){if(im->top)picture_plane(out,meta,kind,key,im->top,1);return 1;}
 return picture_alone(out,meta,kind,key,id);
}
/* Types drawn from the ground around them (roads, walls) or from several parts (farms): the game's own picture of
   one piece, as its build menu would show it. */
static int picture_fallback(int type){
 switch(type){
  case BUILDING_ROAD:return image_group(GROUP_TERRAIN_ROAD);
  case BUILDING_WALL:return image_group(GROUP_BUILDING_WALL)+22;   /* a standing piece of wall; the group's first picture is only the walkway floor (user 2026-11-17) */
  case BUILDING_DRAGGABLE_RESERVOIR:return image_group(GROUP_BUILDING_RESERVOIR);
  case BUILDING_AQUEDUCT:return image_group(GROUP_BUILDING_AQUEDUCT);
  case BUILDING_PLAZA:return image_group(GROUP_TERRAIN_PLAZA);
  case BUILDING_GARDENS:return image_group(GROUP_TERRAIN_GARDEN);
  case BUILDING_LOW_BRIDGE:case BUILDING_SHIP_BRIDGE:return image_group(GROUP_BUILDING_BRIDGE);
  case BUILDING_TRIUMPHAL_ARCH:return image_group(GROUP_BUILDING_TRIUMPHAL_ARCH);   /* the finished arch, not its building site */
  default:return type>=BUILDING_WHEAT_FARM && type<=BUILDING_PIG_FARM?image_group(GROUP_BUILDING_FARM_HOUSE):0;
 }
}
/* types: comma separated building type numbers (the editor's catalog). */
static int building_pictures(const char *types,const char *out){
 if(!image_load_climate(CLIMATE_CENTRAL,0,1,1))return 0;
 asset_image_keep_atlas_buffers=1;
 assets_init(1,graphics_renderer()->get_image_atlas(ATLAS_MAIN)->buffers,graphics_renderer()->get_image_atlas(ATLAS_MAIN)->image_widths);
 char p[2048];snprintf(p,sizeof(p),"%s/pictures.txt",out);FILE *f=fopen(p,"w");if(!f)return 0;
 for(const char *s=types;s && *s;){
  int type=atoi(s);
  if(type>0 && type<BUILDING_TYPE_MAX && building_properties_for_type(type)->size>0){int id=picture_fallback(type);if(!id)id=building_image_get_for_type(type);
   if(!picture_export(out,f,"building",type,id) && type==BUILDING_COLOSSEUM)picture_export(out,f,"building",type,image_group(GROUP_BUILDING_COLOSSEUM));   /* the original arena */
   /* The granary's walls and roof and the arch's upper part are a second picture the game draws over the first
      (widget/city/building_ghost.c draw_regular_building; creator_building_pictures.OVERLAY places it). */
   if(type==BUILDING_GRANARY || type==BUILDING_TRIUMPHAL_ARCH)picture_plane(out,f,"building",type,image_get(id+1),3);
   /* The warehouse's own picture is only the floor of its corner tile: the game draws the roofed hut over it
      (building_ghost.c image_draw_warehouse, user 2026-11-17: the editor showed a bare dark tile). */
   if(type==BUILDING_WAREHOUSE)picture_plane(out,f,"building",type,image_get(image_group(GROUP_BUILDING_WAREHOUSE)+17),3);}
  s=strchr(s,',');if(s)s++;
 }
 /* build-menu buttons: four pictures per button (normal first) */
 for(int n=0;n<12;n++)picture_export(out,f,"menu",n,image_group(GROUP_SIDEBAR_BUTTONS)+n*4);
 return fclose(f)==0;
}
