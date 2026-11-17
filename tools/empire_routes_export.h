/* Development aid for tools/build_empire_passage.py (not part of any build).
   Writes <out>/routes.json: every empire object of the loaded template (type, x, y, image size, route id, city name
   id, city type). Types 4/5 are the original land/sea route dots, type 1 the cities.
   To regenerate Augustus/empire-passage.json on a development copy (never in the shipped worker):
     1. copy this file next to engine_worker.c and add   #include "empire_routes_export.h"   after the other includes;
     2. after the line that runs creator_export_map for "inventory-" modes, add
          if(!strncmp(mode,"inventory-",10))creator_export_routes(out);
     3. build the worker, run   engine inventory-<id> <in> <out> 0 0 0   for every template id (0-19, 100-111);
     4. python tools/build_empire_passage.py --image <out of any id>/empire.bmp --routes <every out>/routes.json
   Then undo steps 1-2. Reading pixels is not needed and not done. */
static int creator_export_routes(const char *out){
 char path[2048];snprintf(path,sizeof(path),"%s/routes.json",out);FILE*f=fopen(path,"w");if(!f)return 0;
 fprintf(f,"[");int first=1;
 for(int i=0;i<empire_object_count();i++){
  full_empire_object *fo=empire_object_get_full(i);if(!fo->in_use)continue;const empire_object*o=&fo->obj;
  const image*img=image_get(o->image_id);
  fprintf(f,"%s{\"i\":%d,\"type\":%d,\"x\":%d,\"y\":%d,\"w\":%d,\"h\":%d,\"img\":%d,\"route\":%d,\"name\":%d,\"ctype\":%d}",first?"":",",i,o->type,o->x,o->y,img?img->width:-1,img?img->height:-1,o->image_id,o->trade_route_id,fo->city_name_id,fo->city_type);first=0;
 }
 fprintf(f,"]");return fclose(f)==0;
}
