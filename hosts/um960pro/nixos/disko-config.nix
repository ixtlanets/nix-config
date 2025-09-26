{ lib, ... }:
{
  disko.devices = {
    disk = {
      main = {
        type = "disk";
        device = "/dev/nvme0n1";
        content = {
          type = "gpt";
          partitions = {
            boot = {
              size = "1M";
              type = "EF02";
            };
            ESP = {
              size = "1G";
              type = "EF00";
              content = {
                type = "filesystem";
                format = "vfat";
                mountpoint = "/boot";
                mountOptions = [ "umask=0077" ];
              };
            };
            root = {
              size = "100%";
              content = {
                type = "filesystem";
                format = "ext4";
                mountpoint = "/";
                mountOptions = [ "noatime" ];
              };
            };
          };
        };
      };
      data = {
        type = "disk";
        device = "/dev/nvme1n1";
        content = {
          type = "gpt";
          partitions = {
            nix = {
              size = "350G";
              type = "8300";
              content = {
                type = "filesystem";
                format = "ext4";
                mountpoint = "/nix";
                mountOptions = [
                  "noatime"
                  "discard"
                ];
              };
            };
            home = {
              size = "100%";
              type = "8300";
              content = {
                type = "filesystem";
                format = "ext4";
                mountpoint = "/home";
                mountOptions = [
                  "noatime"
                  "discard"
                ];
              };
            };
          };
        };
      };
    };
  };
}
