#ifndef MP_VISIT_H
#define MP_VISIT_H
#include <stdlib.h>
static inline int mp_visit_active(void){const char *p=getenv("AUGUSTUS_CITY_VISIT");return p && *p;}
#endif
