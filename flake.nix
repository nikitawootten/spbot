{
  description = "A very basic flake";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
  };

  outputs = { self, nixpkgs }: let
    forEachSystem = f: nixpkgs.lib.genAttrs ["x86_64-linux"] f;
  in {
    devShells = forEachSystem(system: let
      pkgs = import nixpkgs { inherit system; config.allowUnfree = true; };
    in {
      default = pkgs.mkShell {
        packages = with pkgs; [
          poetry
          python311Full
          (pkgs.ollama.override { acceleration = "cuda"; })
        ];
      };
    });
  };
}
