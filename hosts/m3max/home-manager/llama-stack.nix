import ../../../modules/home-manager/llama-stack.nix {
  contextSize = 16384;
  parallel = 1;
  promptCacheMiB = 1024;
  speculativeDraftMax = 2;
}
