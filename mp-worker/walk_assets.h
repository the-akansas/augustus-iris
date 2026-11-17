/* Read-only original sprite export for the local city-walk experiment. */
#include "core/image_group.h"
static int walk_plane(const char *out,FILE *meta,const image *im,int id,int part){
 if(!im || im->width<=0 || im->height<=0)return 1;
 const image_atlas_data *a=graphics_renderer()->get_image_atlas(im->atlas.id>>IMAGE_ATLAS_BIT_OFFSET);
 int i=im->atlas.id&IMAGE_ATLAS_BIT_MASK;
 if(!a || i>=a->num_images || !a->buffers[i])return 0;
 char p[2048];snprintf(p,sizeof(p),"%s/sprite-%d-%d.bgra",out,id,part);
 FILE *f=fopen(p,"wb");if(!f)return 0;int ok=1;
 for(int y=0;y<im->height;y++)if(fwrite(a->buffers[i]+(y+im->atlas.y_offset)*a->image_widths[i]+im->atlas.x_offset,4,im->width,f)!=(size_t)im->width)ok=0;
 if(fclose(f))ok=0;
 fprintf(meta,"%d %d %d %d %d %d %d %d\n",id,part,im->width,im->height,im->x_offset,im->y_offset,im->original.height,im->is_isometric);
 return ok;
}
static int walk_export(const char *out){
 if(!image_load_climate(scenario_property_climate(),0,1,1))return 0;
 char p[2048];snprintf(p,sizeof(p),"%s/sprites.txt",out);FILE *f=fopen(p,"w");if(!f)return 0;int ok=1;
 int groups[]={29,30,32,37,57,7,10,112};int counts[]={4,4,4,2,8,8,8,16};
 for(int g=0;g<8;g++)for(int n=0;n<counts[g];n++){
  int id=image_group(groups[g])+n;const image *im=image_get(id);
  fprintf(f,"# %d %d %d\n",groups[g],n,id);
  if(!walk_plane(out,f,im,id,0) || (im->top && !walk_plane(out,f,im->top,id,1)))ok=0;
 }if(fclose(f))ok=0;return ok;
}
