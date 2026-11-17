/* Test stub: see shim_post.c. Only the SHA-256 entry points used by mp_post_city_compact. */
#ifndef SHIM_WINDOWS_H
#define SHIM_WINDOWS_H
typedef void *BCRYPT_ALG_HANDLE; typedef void *BCRYPT_HASH_HANDLE; typedef long NTSTATUS; typedef unsigned char UCHAR; typedef unsigned long ULONG;
#define BCRYPT_SHA256_ALGORITHM L"SHA256"
static inline NTSTATUS BCryptOpenAlgorithmProvider(BCRYPT_ALG_HANDLE*a,const void*b,const void*c,ULONG d){(void)a;(void)b;(void)c;(void)d;return -1;}
static inline NTSTATUS BCryptCreateHash(BCRYPT_ALG_HANDLE a,BCRYPT_HASH_HANDLE*b,void*c,ULONG d,void*e,ULONG f,ULONG g){(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;return -1;}
static inline NTSTATUS BCryptHashData(BCRYPT_HASH_HANDLE a,UCHAR*b,ULONG c,ULONG d){(void)a;(void)b;(void)c;(void)d;return -1;}
static inline NTSTATUS BCryptFinishHash(BCRYPT_HASH_HANDLE a,UCHAR*b,ULONG c,ULONG d){(void)a;(void)b;(void)c;(void)d;return -1;}
static inline NTSTATUS BCryptDestroyHash(BCRYPT_HASH_HANDLE a){(void)a;return 0;}
static inline NTSTATUS BCryptCloseAlgorithmProvider(BCRYPT_ALG_HANDLE a,ULONG b){(void)a;(void)b;return 0;}
#endif
