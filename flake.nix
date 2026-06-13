{
  description = "Development shell for game-media-sync and its Decky plugin";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { nixpkgs, ... }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python314 or pkgs.python313 or pkgs.python312;
          nodejs = pkgs.nodejs_22 or pkgs.nodejs_20;
        in
        {
          default = pkgs.mkShell {
            packages = [
              python
              pkgs.uv
              pkgs.ruff
              nodejs
              pkgs.pnpm
              pkgs.ffmpeg
              pkgs.exiftool
              pkgs.zip
              pkgs.unzip
              pkgs.git
              pkgs.gnumake
              pkgs.pkg-config
            ];

            UV_PYTHON = "${python}/bin/python";

            shellHook = ''
              echo "game-media-sync dev shell"
              echo "Python: $(${python}/bin/python --version)"
            '';
          };
        });
    };
}
