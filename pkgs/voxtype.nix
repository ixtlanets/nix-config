{
  cairo,
  fetchFromGitHub,
  glib,
  gtk4,
  gtk4-layer-shell,
  voxtype,
}:

voxtype.overrideAttrs (
  _finalAttrs: previousAttrs: rec {
    version = "0.7.1";

    src = fetchFromGitHub {
      owner = "peteonrails";
      repo = "voxtype";
      tag = "v0.7.1";
      hash = "sha256-yJElO/tq7RK4zSiDV3TgUV3dr7byk6KCbsWiyOf62GQ=";
    };

    buildFeatures = previousAttrs.buildFeatures ++ [ "osd-gtk4" ];
    cargoBuildFeatures = previousAttrs.cargoBuildFeatures ++ [ "osd-gtk4" ];
    cargoCheckFeatures = previousAttrs.cargoCheckFeatures ++ [ "osd-gtk4" ];

    buildInputs = previousAttrs.buildInputs ++ [
      cairo
      glib
      gtk4
      gtk4-layer-shell
    ];

    cargoDeps = previousAttrs.cargoDeps.overrideAttrs (previousCargoAttrs: {
      name = "voxtype-${version}-vendor";
      vendorStaging = previousCargoAttrs.vendorStaging.overrideAttrs {
        name = "voxtype-${version}-vendor-staging";
        inherit src;
        outputHashAlgo = "sha256";
        outputHash = "sha256-fD6YSGFi4SOuJBkKzALQCywss2N41HZE7wYkwMSUBrg=";
      };
    });
  }
)
