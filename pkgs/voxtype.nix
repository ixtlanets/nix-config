{
  fetchFromGitHub,
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
