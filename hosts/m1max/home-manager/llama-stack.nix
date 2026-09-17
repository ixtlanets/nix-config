import ../../../modules/home-manager/llama-stack.nix {
  contextSize = 32768;
  parallel = 2;
  promptCacheMiB = 8192;
  speculativeDraftMax = 3;
}
