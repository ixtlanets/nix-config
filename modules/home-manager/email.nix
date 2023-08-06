{ inputs, outputs, lib, config, pkgs, ... }:
{
  accounts.email.accounts = {
    "gmail" = {
      address = "snikulin@gmail.com";
      realName = "Sergey Nikulin";
      flavor = "gmail";
      primary = true;
      passwordCommand = "pass mail/snikulin@gmail.com";
      mbsync.enable = true;
      mbsync.create = "maildir";
      mu.enable = true;
      signature.text = ''
      Best wishes,
      Sergey Nikulin
      '';
      gpg = {
        key = "6EA4E8EBBC9094DDF20B112D539459F1879941F7";
      };
      thunderbird.enable = true;
    };
    "zencar" = {
      address = "sn@zen.car";
      flavor = "yandex.com";
      passwordCommand = "pass mail/sn@zen.car";
      mbsync.enable = true;
      mbsync.create = "maildir";
      mu.enable = true;
      signature.text = ''
      Best wishes,
      Sergey Nikulin
      '';
      thunderbird.enable = true;
    };
  };
  programs.thunderbird = {
    enable = true;
  };
}
