{
  description = "ropro-bypass";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
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
      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          package = pkgs.stdenvNoCC.mkDerivation {
            pname = "ropro-bypass";
            version = "0.1.0";
            src = self;

            nativeBuildInputs = [ pkgs.makeWrapper ];
            dontBuild = true;

            installPhase = ''
              runHook preInstall
              install -Dm755 patch_ropro.py "$out/lib/ropro-bypass/patch_ropro.py"
              mkdir -p "$out/lib/ropro-bypass/audits" "$out/bin"
              cp audits/*.json "$out/lib/ropro-bypass/audits/"
              makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/ropro-bypass" \
                --add-flags "$out/lib/ropro-bypass/patch_ropro.py" \
                --set PYTHONDONTWRITEBYTECODE 1 \
                --set SSL_CERT_FILE ${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
              runHook postInstall
            '';

            doInstallCheck = true;
            installCheckPhase = ''
              "$out/bin/ropro-bypass" --help >/dev/null
            '';

            meta = {
              description = "Apply RoPro bypasses in place";
              license = pkgs.lib.licenses.mit;
              mainProgram = "ropro-bypass";
              platforms = systems;
            };
          };
        in
        {
          default = package;
          ropro-bypass = package;
        }
      );

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/ropro-bypass";
        };
        ropro-bypass = {
          type = "app";
          program = "${self.packages.${system}.ropro-bypass}/bin/ropro-bypass";
        };
      });

      checks = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          package = self.packages.${system}.default;
          tests = pkgs.runCommand "ropro-bypass-tests" { nativeBuildInputs = [ pkgs.python3 ]; } ''
            cp -R ${self} source
            chmod -R u+w source
            cd source
            python3 -m py_compile patch_ropro.py build_release.py tools/update_audits.py
            python3 -m unittest discover -s tests -v
            sha256sum -c MANIFEST.sha256
            touch "$out"
          '';
          formatting = pkgs.runCommand "ropro-bypass-formatting" {
            nativeBuildInputs = [ pkgs.nixfmt-rfc-style ];
          } ''
            nixfmt --check ${self}/flake.nix
            touch "$out"
          '';
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          default = pkgs.mkShellNoCC {
            packages = [
              pkgs.git
              pkgs.nixfmt-rfc-style
              pkgs.nodejs
              pkgs.python3
            ];
          };
        }
      );

      formatter = forAllSystems (system: (import nixpkgs { inherit system; }).nixfmt-rfc-style);
    };
}
