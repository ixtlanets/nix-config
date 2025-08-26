{ lib, ... }:
{
  programs.starship = {
    enable = true;
    settings = {
      add_newline = false;
      format = lib.strings.concatStrings [
        "$nix_shell"
        "$username"
        "$hostname"
        "$directory"
        "$container"
        "$git_branch $git_status"
        "$python"
        "$nodejs"
        "$lua"
        "$rust"
        "$java"
        "$c"
        "$golang"
        "$status"
        "$character"
      ];
      right_format = lib.strings.concatStrings [
        "$battery"
        "$time"
      ];
      battery = {
        full_symbol = "";
        charging_symbol = "";
        discharging_symbol = "";
        unknown_symbol = "";
        format = "[$symbol$percentage]($style)";
      };
      time = {
        format = "[$time]($style)";
      };
      status = {
        symbol = "✗";
        not_found_symbol = "󰍉 Not Found";
        not_executable_symbol = " Can't Execute E";
        sigint_symbol = "󰂭 ";
        signal_symbol = "󱑽 ";
        success_symbol = "";
        format = "[$symbol](fg:red)";
        map_symbol = true;
        disabled = false;
      };
      character = {
        success_symbol = "[❯](bold purple)";
        error_symbol = "[❯](bold red)";
      };
      nix_shell = {
        disabled = false;
        format = "[](fg:white)[ ](bg:white fg:black)[](fg:white) ";
      };
      container = {
        symbol = " 󰏖";
        format = "[$symbol ](yellow dimmed)";
      };
      username = {
        show_always = true;
        style_user = "yellow";
        style_root = "red";
        format = "[$user]($style)";
      };

      hostname = {
        ssh_only = false;
        format = "[@$hostname]($style): ";
        style = "green";
      };

      directory = {
        format = "[$path]($style)[$read_only]($read_only_style) ";
        style = "blue";
        read_only = " ";
        fish_style_pwd_dir_length = 1;
      };
      git_branch = {
        symbol = "";
        style = "";
        format = "[ $symbol $branch](fg:purple)(:$remote_branch)";
      };
      python = {
        symbol = "";
        format = "[$symbol ](yellow)";
      };
      nodejs = {
        symbol = " ";
        format = "[$symbol ](yellow)";
      };
      lua = {
        symbol = "󰢱";
        format = "[$symbol ](blue)";
      };
      rust = {
        symbol = "";
        format = "[$symbol ](red)";
      };
      java = {
        symbol = "";
        format = "[$symbol ](red)";
      };
      c = {
        symbol = "";
        format = "[$symbol ](blue)";
      };
      golang = {
        symbol = "";
        format = "[$symbol ](blue)";
      };
    };
  };
}
