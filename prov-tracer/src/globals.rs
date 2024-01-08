thread_local!{
    /** Globally enable or disable tracing.
     *
     * Note that this doesn't disable <emph>all</emph> trace functions,
     * only a few that I think are necessary to disable.
     * This creates a thread-local access
     *
     * This starts out as "false". Otherwise, somehow call logger gets
     * initialized twice (?).
     *
     * */
    pub static ENABLE_TRACE: std::cell::Cell<bool> = false.into();
}
