{
  lib,
  buildNpmPackage,
  fetchurl,
}:

buildNpmPackage rec {
  pname = "codebuddy-code";
  version = "1.0.14";

  src = fetchurl {
    url = "https://registry.npmjs.org/@tencent-ai/codebuddy-code/-/codebuddy-code-${version}.tgz";
    hash = "sha256-0shm3yvayy3ksiayllywsz7qw266qd769ciiws1d9nsdz43kkn59";
  };

  npmDepsHash = "sha256-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"; # TODO: get the correct hash

  meta = {
    description = "CodeBuddy Code is Tencent Cloud's official intelligent coding tool, supporting efficient collaboration and development through natural language in terminals, IDEs, and GitHub.";
    homepage = "https://cnb.cool/codebuddy/codebuddy-code";
    license = lib.licenses.unfree; # SEE LICENSE IN README.md, but assuming unfree for now
    maintainers = [ ];
    mainProgram = "codebuddy";
  };
}