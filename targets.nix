{
  # "nix system" = "rust target";
  "x86_64-linux" = "x86_64-unknown-linux-musl";
  # Even with Nextflow (requires OpenJDK) removed,
  # i686-linux still doesn't build.
  # Only the wind and water know why. Us mere mortals never will.
  #"i686-linux" = "i686-unknown-linux-musl";
  "aarch64-linux" = "aarch64-unknown-linux-musl";
  "armv7l-linux" = "armv7-unknown-linux-musleabi";
}
