{
  description = "GestureLight webcam hand-tracking development environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in
    {
      devShells = forAllSystems (system:
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
    };
}
