{
  capturedAt = "2026-03-07";

  devices = {
    x1carbon = "ACDNQPU-AYZTZJD-43ZO52W-DJQNMLQ-PZWOHHQ-M7LCWID-7WUGJ2U-DJJ4RQS";
    um790pro = "OKR2QCL-FLJ7JE5-HPWXEKY-SV2BHIA-I24BTUD-CJRVW4Y-VUFRT7H-YFPWOQL";
    matebook = "SN3LGTL-TJ3OHYQ-FSGQVFH-CQQ34XJ-UF4J3ZV-AHBEAI4-GEQBVVA-CWMFYAY";
    x13 = "NZ4IHCR-OW6F44P-FPNHA6M-PE44VY7-ZXPCEEB-QSLKP6J-I56KPSA-4AX5VQX";
    m1max = "VY7DPRY-MD4DGDF-HXQ63HT-NTZY5BN-GPY4SAT-OQN7BD4-OXM7DQD-XO2MMA3";
    zenbook = "H5LDAHA-HZQTPI6-S75ZBJ3-LZUFTBM-FW55GVP-DUKYHBB-G73AHIJ-CCCNNQ7";
    desktop = "6BIM5VG-DXQR6OY-YYVFQWQ-JJ2UADE-ZY2UDWF-EEX2D6F-UFUCEXT-CN7RQQS";

    android-phone = "66MSI5D-LTA44T5-VYMLLN7-2XVEN2F-WBR2CKJ-WWDAEOE-R3VUFIH-4NAZQA6";
    android-tablet = "7LI7XA5-TKD43OY-RZZIYRC-5CE35VG-YTGAYD7-JZEFRZK-XIQKZGP-L4TZXQQ";
  };

  computerDevices = [
    "x1carbon"
    "um790pro"
    "matebook"
    "x13"
    "m1max"
    "zenbook"
    "desktop"
  ];

  mobileDevices = [
    "android-phone"
    "android-tablet"
  ];

  folders = {
    obsidian-vault = {
      id = "3y3qt-shfv6";
      path = "/home/nik/obsidian-vault";
      type = "sendreceive";
      devices = [
        "x1carbon"
        "um790pro"
        "matebook"
        "x13"
        "m1max"
        "zenbook"
        "desktop"
        "android-phone"
        "android-tablet"
      ];
    };

    projects = {
      id = "lavhv-cjakz";
      label = "Проекты";
      path = "/home/nik/Documents/Проекты";
      type = "sendreceive";
      devices = [
        "x1carbon"
        "um790pro"
        "matebook"
        "x13"
        "m1max"
        "zenbook"
        "desktop"
        "android-phone"
      ];
    };

    wallpapers = {
      id = "wallpapers";
      path = "/home/nik/wallpapers";
      type = "sendreceive";
      devices = [
        "x1carbon"
        "um790pro"
        "x13"
        "m1max"
        "zenbook"
        "desktop"
      ];
    };

    razvedmobil = {
      id = "разведмобиль";
      label = "разведмобиль";
      path = "/home/nik/Documents/разведмобиль";
      type = "sendreceive";
      devices = [
        "x1carbon"
        "m1max"
      ];
    };
  };
}
