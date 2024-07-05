{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  buildInputs = [
    pkgs.python3
    pkgs.python3Packages.virtualenv
  ];

  shellHook = ''
    if [ ! -d ".venv" ]; then
      virtualenv .venv
    fi
    source .venv/bin/activate
    pip install psutil
  '';
}

