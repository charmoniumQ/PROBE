{
  description = "Flake utils demo";
  outputs = { self, nixpkgs }:
    let
      system = "x86_64";
      pkgs = nixpkgs.legacyPackages.${system};
    in
      {
        "packages.${system}" = {
          env = pkgs.symlinkJoin {
            name = "env";
            paths = [
              pkgs.fsatrace
              # Deps of runner script and notebook workloads
              (pkgs.python311.withPackages (pypkgs: [
                pypkgs.seaborn
                pypkgs.scikit-learn
                pypkgs.nbconvert
                # pypkgs.notebook
                (pypkgs.jupyter-contrib-nbextensions.overrideAttrs (self: super: {
                  # Yes, this was very recently broken by [1]
                  # But it was even more recently fixed by [2].
                  # But it has not yet been marked as fixed.
                  # So I will do that manually here.
                  # [1]: https://github.com/ipython-contrib/jupyter_contrib_nbextensions/issues/1647
                  # [2]: https://github.com/NixOS/nixpkgs/commit/ba873b2be6252a5144c9f37fae1341973ac155ae
                  meta.broken = false;
                  patches = (({ patches = []; } // super).patches) ++ [
                    (pkgs.fetchpatch {
                      name = "notebook-v7-compat.patch";
                      url = "https://github.com/ipython-contrib/jupyter_contrib_nbextensions/commit/181e5f38f8c7e70a2e54a692f49564997f21a231.patch";
                      hash = "sha256-WrC9npEUAk3Hou8Tp8kK+Nw+H0bEEjR3GIoUTxrZxak=";
                    })
                  ];
                }))
              ]))
            ];
          };
        };
      }
    )
  ;
}
