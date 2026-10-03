{
  description = "GestureLight webcam hand-tracking and local lamp-control application";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
    };
  };

  outputs = {
    self,
    nixpkgs,
    pyproject-nix,
    uv2nix,
    pyproject-build-systems,
    ...
  }:
    let
      inherit (nixpkgs) lib;
      developmentSystems = [ "x86_64-linux" "aarch64-linux" ];
      packageSystems = [ "x86_64-linux" ];
      forAllDevelopmentSystems = lib.genAttrs developmentSystems;
      forAllPackageSystems = lib.genAttrs packageSystems;

      # Read the uv lockfile once. The package output below uses its Linux
      # wheels, while the development shell continues to use uv directly.
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
    in
    {
      devShells = forAllDevelopmentSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python311;
          # These libraries let the OpenCV and MediaPipe Python wheels use a
          # webcam and create a desktop window from inside a Nix shell.
          runtimeLibraries = with pkgs; [
            stdenv.cc.cc.lib
            zlib
            libGL
            glib
            libxkbcommon
            libx11
            libxcb
            libxcursor
            libxext
            libICE
            libxi
            libxrandr
            libxrender
            libSM
          ];
        in
        {
          default = pkgs.mkShell {
            packages = [
              python
              pkgs.pkg-config
              pkgs.uv
            ] ++ runtimeLibraries;

            LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath runtimeLibraries;
            # The OpenCV wheel bundles Qt's X11/xcb plugin, but not a native
            # Wayland Qt platform plugin. XWayland is available on this desktop.
            QT_QPA_PLATFORM = "xcb";
            UV_NO_MANAGED_PYTHON = "1";
            UV_PYTHON = "${python}/bin/python";
          };
        });

      # MediaPipe 0.10.21, which retains the required mp.solutions.hands API,
      # has a locked Linux wheel only for x86_64. Do not advertise an ARM
      # package that cannot be built from this lockfile.
      packages = forAllPackageSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = pkgs.python311;
          runtimeLibraries = with pkgs; [
            stdenv.cc.cc.lib
            zlib
            libGL
            glib
            libxkbcommon
            libx11
            libxcb
            libxcursor
            libxext
            libICE
            libxi
            libxrandr
            libxrender
            libSM
          ];
          runtimeLibraryPath = pkgs.lib.makeLibraryPath runtimeLibraries;

          pythonSet = (pkgs.callPackage pyproject-nix.build.packages { inherit python; }).overrideScope (
            lib.composeManyExtensions [
              pyproject-build-systems.overlays.wheel
              (workspace.mkPyprojectOverlay { sourcePreference = "wheel"; })
            ]
          );
          inherit (pkgs.callPackages pyproject-nix.build.util { }) mkApplication;

          desktopItem = pkgs.makeDesktopItem {
            name = "gesturelight";
            desktopName = "GestureLight";
            genericName = "Gesture-controlled lamp";
            comment = "Control a local ESP32 lamp with webcam hand gestures";
            exec = "@gesturelight-bin@";
            categories = [ "AudioVideo" "Video" ];
            terminal = false;
          };

          gesturelight = (mkApplication {
            venv = pythonSet.mkVirtualEnv "gesturelight-env" workspace.deps.default;
            package = pythonSet.gesturelight;
          }).overrideAttrs (old: {
            nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ pkgs.makeWrapper ];
            postInstall = (old.postInstall or "") + ''
              install -Dm444 ${desktopItem}/share/applications/gesturelight.desktop \
                "$out/share/applications/gesturelight.desktop"
              substituteInPlace "$out/share/applications/gesturelight.desktop" \
                --replace-fail '@gesturelight-bin@' "$out/bin/gesturelight-hand-tracker"
              wrapProgram "$out/bin/gesturelight-hand-tracker" \
                --set QT_QPA_PLATFORM xcb \
                --prefix LD_LIBRARY_PATH : ${runtimeLibraryPath}
            '';
            meta = (old.meta or { }) // {
              description = "Webcam hand tracking and local ESP32 lamp control";
              mainProgram = "gesturelight-hand-tracker";
              platforms = [ "x86_64-linux" ];
            };
          });
        in
        {
          inherit gesturelight;
          default = gesturelight;
        });

      apps = forAllPackageSystems (system:
        let
          program = "${self.packages.${system}.gesturelight}/bin/gesturelight-hand-tracker";
        in
        {
          gesturelight = {
            type = "app";
            inherit program;
            meta.description = "GestureLight webcam hand-tracking and local lamp-control app";
          };
          default = {
            type = "app";
            inherit program;
            meta.description = "GestureLight webcam hand-tracking and local lamp-control app";
          };
        });

      nixosModules =
        let
          gesturelightModule = { config, lib, pkgs, ... }:
            let
              cfg = config.gesturelight;
              basePackage = self.packages.${pkgs.system}.gesturelight;
              configuredUrl =
                if cfg.url == null then
                  null
                else if lib.hasPrefix "http://" cfg.url then
                  cfg.url
                else
                  "http://${cfg.url}";
              configuredPackage = pkgs.runCommand "gesturelight-configured" {
                nativeBuildInputs = [ pkgs.makeWrapper ];
              } ''
                mkdir -p "$out/bin" "$out/share/applications"
                makeWrapper ${basePackage}/bin/gesturelight-hand-tracker \
                  "$out/bin/gesturelight-hand-tracker" \
                  --set GESTURELIGHT_ESP32_URL ${lib.escapeShellArg configuredUrl}
                cp ${basePackage}/share/applications/gesturelight.desktop \
                  "$out/share/applications/gesturelight.desktop"
                substituteInPlace "$out/share/applications/gesturelight.desktop" \
                  --replace-fail ${lib.escapeShellArg "${basePackage}/bin/gesturelight-hand-tracker"} \
                  "$out/bin/gesturelight-hand-tracker"
              '';
            in
            {
              options.gesturelight = {
                enable = lib.mkEnableOption "GestureLight webcam lamp control";
                url = lib.mkOption {
                  type = lib.types.nullOr lib.types.str;
                  default = null;
                  example = "192.168.1.50";
                  description = ''
                    ESP32 IP address or hostname, optionally with a port. The module
                    adds the required http:// prefix when it is omitted.
                  '';
                };
              };

              config = lib.mkIf cfg.enable {
                assertions = [
                  {
                    assertion = cfg.url != null && cfg.url != "";
                    message = "gesturelight.url must be set when gesturelight.enable is true.";
                  }
                ];

                environment.systemPackages =
                  lib.optional (cfg.url != null && cfg.url != "") configuredPackage;
              };
            };
        in
        {
          default = gesturelightModule;
          gesturelight = gesturelightModule;
        };
    };
}
