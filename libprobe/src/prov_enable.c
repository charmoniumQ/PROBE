/*
 * TODO: Do I really need prov_log_disable?
 *
 * Libc functions called from libprobe _won't_ get hooked, so long as we _always_ use the unwrapped functions.
 * Maybe we should grep for that instead?
 */

static _Atomic bool __prov_log_disable = false;
static void prov_log_disable() { __prov_log_disable = true; }
static void prov_log_enable () { __prov_log_disable = false; }
static bool prov_log_is_enabled () { return !__prov_log_disable; }
