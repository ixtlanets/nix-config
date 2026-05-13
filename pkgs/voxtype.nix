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

    # Local backport for https://github.com/peteonrails/voxtype/pull/355.
    # PR is closed unmerged, but equivalent fix is on upstream main as a06f82d.
    # Drop this once a tagged release includes the GTK4 OSD startup visibility fix.
    postPatch = (previousAttrs.postPatch or "") + ''
      substituteInPlace src/bin/voxtype_osd_gtk4.rs \
        --replace-fail 'let visible = Cell::new(false);' 'let visible = Cell::new(true);'
    '';

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
