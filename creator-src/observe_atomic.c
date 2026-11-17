/* observe_atomic.dll: the two atomic operations Augustus/observe_channel.py uses on its shared memory channel
 * (ctypes cannot do them itself). Written again from the DLL that shipped without its source (2026-11-16, for the
 * public source); same exports, same argument order. build/build_launcher.py builds it with the project's compiler:
 *   x86_64-w64-mingw32-clang -O2 -shared -o observe_atomic.dll observe_atomic.c
 *
 *   obs_exchange(p, value)               *p = value, returns the old *p          (InterlockedExchange)
 *   obs_compare(p, exchange, comparand)  if *p == comparand then *p = exchange;
 *                                        returns the old *p                      (InterlockedCompareExchange)
 * observe_channel.py reads with obs_compare(p, 0, 0): it changes nothing and returns the current value. */
#include <windows.h>

__declspec(dllexport) LONG obs_exchange(LONG volatile *p, LONG value)
{
    return InterlockedExchange(p, value);
}

__declspec(dllexport) LONG obs_compare(LONG volatile *p, LONG exchange, LONG comparand)
{
    return InterlockedCompareExchange(p, exchange, comparand);
}
