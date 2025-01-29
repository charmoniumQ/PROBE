{ ... }: {
  systemd = {
    slices = {
      benchmark = {
        enable = true;
        description = "Slice for ad hoc benchmarking.";
      };
    };
  };
}
