{
  inputs,
  outputs,
  lib,
  config,
  pkgs,
  ...
}:
let
  isLinux = pkgs.stdenv.isLinux;
in
{
  home.packages = with pkgs; [
    mu
  ];
  accounts.email.accounts = {
    "gmail" = {
      address = "snikulin@gmail.com";
      realName = "Sergey Nikulin";
      flavor = "gmail.com";
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
    };
    "GR" = {
      address = "sergey@grishinrobotics.com";
      realName = "Sergey Nikulin";
      flavor = "gmail.com";
      primary = false;
      passwordCommand = "pass mail/sergey@grishinrobotics.com";
      mbsync.enable = true;
      mbsync.create = "maildir";
      mu.enable = true;
      signature.text = ''
        Best wishes,
        Sergey Nikulin
      '';
    };
    "zencar" = {
      address = "sn@zencar.tech";
      realName = "Sergey Nikulin";
      flavor = "yandex.com";
      passwordCommand = "pass mail/sn@zen.car";
      mbsync.enable = true;
      mbsync.create = "maildir";
      mu.enable = true;
      signature.text = ''
        Best wishes,
        Sergey Nikulin
      '';
    };
  };
  programs.mbsync = {
    enable = true;
  };
  services.mbsync = {
    enable = isLinux;
    preExec = "mkdir -p %h/mail";
    postExec = "\${pkgs.mu}/bin/mu index";
  };
}
