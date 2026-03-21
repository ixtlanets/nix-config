{
  config,
  pkgs,
  lib,
  ...
}:
{
  services.thermald.enable = true;

  # Optimize sleep/resume behavior to prevent slow unlock
  # Use mkDefault so hosts can override if needed (e.g., um960pro disables sleep)
  services.logind.settings.Login = {
    HandleLidSwitch = lib.mkDefault "suspend";
    HandleLidSwitchExternalPower = lib.mkDefault "suspend";
    HandleLidSwitchDocked = lib.mkDefault "ignore";
  };

  # Prevent hibernation which requires LUKS unlock on resume
  # This fixes the slow unlock issue after sleep
  boot.kernelParams = lib.mkDefault [ "nohibernate" ];

  # Optimize laptop power management
  boot.kernel.sysctl = {
    "vm.laptop_mode" = 5;
  };

  # Disable GDM auto-suspend to prevent conflicts
  services.displayManager.gdm.autoSuspend = lib.mkDefault false;
}
