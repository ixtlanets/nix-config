{ pkgs, ... }:
{
  environment.systemPackages = with pkgs; [
    # SRC: https://github.com/FlyGoat/RyzenAdj
    # ./ryzenadj --stapm-limit=45000 --fast-limit=45000 --slow-limit=45000 --tctl-temp=90
    # ryzenAdj --info
    # radg [TEMP]
    ryzenadj

    # SRC: https://github.com/nbfc-linux/nbfc-linux
    nbfc-linux
  ];

  systemd.services.radj = {
    enable = true;
    description = "Ryzen Adj temperature limiter.";
    serviceConfig.Type = "simple";
    wantedBy = [ "multi-user.target" ];
    path = with pkgs; [
      coreutils
      ryzenadj
    ];
    script = ''
      ryzenadj --tctl-temp=55
      while true; do
        sleep 60
        ryzenadj --tctl-temp=55 &> /dev/null
      done
    '';
  };
}
