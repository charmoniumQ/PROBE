# A note where to hook process/thread creation/destruction

We need to do something every time a process gets created.
Here are the options:

- We are already interposing `clone()`, `fork()`, and `exec*()`; modify the interpose handler to do the initialization.
  - Interposing clone, exec, fork would not work on the very first process, which is not created from an interposed library.
  - I can't think of a good way to shim the `exec`. We would need to inject code into the child's exec epoch, which does not seem possible.
- Use shared library constructor.
  - It appears the library constructor approach does not work in containers. Try setting `USE_LIB_CONSTRUCTOR=1` and `debug_print_start_of_interposition=True` set and running:

  - ```
    podman run \
        --rm \
        --volume /nix/store:/nix/store:ro \
        ubuntu:24.04 \
        $(nix build --no-link --print-out-paths '.#probe')/bin/probe record --debug -f ls
    ```

- On the first operation we intercept, check `is_initialized`. If not, initialize.

  - Checking on the first operation has the downside that it could slow down every operation a bit (although branch prediction mitigates this), and some processes might not get logged, if they do not do any prov operations before crashing.


Destruction is different. There is no indication which is the last operation in a given process or thread.

I don't know of a way of hooking a thread's exit. Threads will have to write their information into some structure that can get processed at process-exit time.

One can hook the process's exit with:

- atexit/on_exit()
- Interpose exit()
- library destructor

Not sure which is best.
