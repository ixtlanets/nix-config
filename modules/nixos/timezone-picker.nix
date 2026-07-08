{ lib, ... }:
{
  security.polkit = {
    enable = true;
    extraConfig = ''
      polkit.addRule(function(action, subject) {
        if (
          action.id == "org.freedesktop.timedate1.set-timezone" &&
          subject.user == "nik" &&
          subject.local &&
          subject.active
        ) {
          return polkit.Result.YES;
        }
      });
    '';
  };

  time.timeZone = lib.mkForce null;
}
