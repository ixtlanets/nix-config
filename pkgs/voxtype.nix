{
  cairo,
  fetchFromGitHub,
  glib,
  gtk4,
  gtk4-layer-shell,
  perl,
  voxtype,
}:

voxtype.overrideAttrs (
  _finalAttrs: previousAttrs: rec {
    version = "0.7.1";

    src = fetchFromGitHub {
      owner = "peteonrails";
      repo = "voxtype";
      tag = "v0.7.1";
      hash = "sha256-yJElO/tq7RK4zSiDV3TgUV3dr7byk6KCbsWiyOf62GQ=";
    };

    buildFeatures = previousAttrs.buildFeatures ++ [ "osd-gtk4" ];
    cargoBuildFeatures = previousAttrs.cargoBuildFeatures ++ [ "osd-gtk4" ];
    cargoCheckFeatures = previousAttrs.cargoCheckFeatures ++ [ "osd-gtk4" ];

    buildInputs = previousAttrs.buildInputs ++ [
      cairo
      glib
      gtk4
      gtk4-layer-shell
    ];

    nativeBuildInputs = previousAttrs.nativeBuildInputs ++ [ perl ];

    # Local backport for https://github.com/peteonrails/voxtype/pull/355.
    # PR is closed unmerged, but equivalent fix is on upstream main as a06f82d.
    # Drop this once a tagged release includes the GTK4 OSD startup visibility fix.
    postPatch = (previousAttrs.postPatch or "") + ''
      substituteInPlace src/bin/voxtype_osd_gtk4.rs \
        --replace-fail 'let visible = Cell::new(false);' 'let visible = Cell::new(true);'

      substituteInPlace src/osd/visual.rs \
        --replace-fail 'background: Color::rgba(0.10, 0.10, 0.12, 0.85),' 'background: Color::rgba(0.102, 0.106, 0.149, 0.97),' \
        --replace-fail 'accent: Color::rgb(0.40, 0.78, 1.00),' 'accent: Color::rgb(0.663, 0.694, 0.839),' \
        --replace-fail 'meter_low: Color::rgb(0.30, 0.85, 0.45),' 'meter_low: Color::rgb(0.663, 0.694, 0.839),' \
        --replace-fail 'meter_mid: Color::rgb(0.95, 0.80, 0.30),' 'meter_mid: Color::rgb(0.663, 0.694, 0.839),' \
        --replace-fail 'meter_high: Color::rgb(0.95, 0.35, 0.30),' 'meter_high: Color::rgb(0.663, 0.694, 0.839),' \
        --replace-fail 'foreground: Color::rgb(0.92, 0.92, 0.95),' 'foreground: Color::rgb(0.663, 0.694, 0.839),'

      perl -0pi -e 's|fn draw\(\n    cr: &Context,|const SWAYOSD_BORDER: (f64, f64, f64, f64) = (0.20, 0.80, 1.00, 1.00);\nconst SWAYOSD_BORDER_WIDTH: f64 = 2.0;\nconst SWAYOSD_RADIUS: f64 = 40.0;\nconst SWAYOSD_PADDING_X: f64 = 16.0;\nconst SWAYOSD_PADDING_Y: f64 = 8.0;\n\nfn rounded_rectangle(cr: &Context, x: f64, y: f64, w: f64, h: f64, radius: f64) {\n    let r = radius.min(w * 0.5).min(h * 0.5).max(0.0);\n    cr.new_sub_path();\n    cr.arc(x + w - r, y + r, r, -std::f64::consts::FRAC_PI_2, 0.0);\n    cr.arc(x + w - r, y + h - r, r, 0.0, std::f64::consts::FRAC_PI_2);\n    cr.arc(x + r, y + h - r, r, std::f64::consts::FRAC_PI_2, std::f64::consts::PI);\n    cr.arc(x + r, y + r, r, std::f64::consts::PI, std::f64::consts::PI * 1.5);\n    cr.close_path();\n}\n\nfn draw(\n    cr: &Context,|' src/bin/voxtype_osd_gtk4.rs

      perl -0pi -e 's|    // Clear background\.\n    cr\.set_source_rgba\(\n        palette\.background\.r as f64,\n        palette\.background\.g as f64,\n        palette\.background\.b as f64,\n        palette\.background\.a as f64,\n    \);\n    cr\.set_operator\(cairo::Operator::Source\);\n    cr\.paint\(\)\.ok\(\);\n    cr\.set_operator\(cairo::Operator::Over\);\n\n    // Layout: waveform area on the left \(~92% width\), gap \(1%\), then peak\n    // meter on the right \(~7% width\)\.\n    let meter_width = \(w \* 0\.07\)\.max\(8\.0\);\n    let gap = \(w \* 0\.01\)\.max\(2\.0\);\n    let wave_width = \(w - meter_width - gap\)\.max\(0\.0\);\n\n    draw_waveform\(cr, 0\.0, 0\.0, wave_width, h, palette, state, gain\);\n    draw_peak_meter\(cr, wave_width \+ gap, 0\.0, meter_width, h, palette, state\);|    cr.set_operator(cairo::Operator::Source);\n    cr.set_source_rgba(0.0, 0.0, 0.0, 0.0);\n    cr.paint().ok();\n    cr.set_operator(cairo::Operator::Over);\n\n    let radius = SWAYOSD_RADIUS.min(w * 0.5).min(h * 0.5);\n    let stroke_offset = SWAYOSD_BORDER_WIDTH * 0.5;\n    rounded_rectangle(cr, stroke_offset, stroke_offset, w - SWAYOSD_BORDER_WIDTH, h - SWAYOSD_BORDER_WIDTH, radius);\n    cr.set_source_rgba(\n        palette.background.r as f64,\n        palette.background.g as f64,\n        palette.background.b as f64,\n        palette.background.a as f64,\n    );\n    cr.fill_preserve().ok();\n    cr.set_source_rgba(SWAYOSD_BORDER.0, SWAYOSD_BORDER.1, SWAYOSD_BORDER.2, SWAYOSD_BORDER.3);\n    cr.set_line_width(SWAYOSD_BORDER_WIDTH);\n    cr.stroke().ok();\n\n    let content_x = SWAYOSD_PADDING_X;\n    let content_y = SWAYOSD_PADDING_Y;\n    let content_w = (w - SWAYOSD_PADDING_X * 2.0).max(0.0);\n    let content_h = (h - SWAYOSD_PADDING_Y * 2.0).max(0.0);\n\n    // Layout: waveform area on the left (~92% width), gap (1%), then peak\n    // meter on the right (~7% width).\n    let meter_width = (content_w * 0.07).max(8.0);\n    let gap = (content_w * 0.01).max(2.0);\n    let wave_width = (content_w - meter_width - gap).max(0.0);\n\n    draw_waveform(cr, content_x, content_y, wave_width, content_h, palette, state, gain);\n    draw_peak_meter(cr, content_x + wave_width + gap, content_y, meter_width, content_h, palette, state);|s' src/bin/voxtype_osd_gtk4.rs
    '';

    cargoDeps = previousAttrs.cargoDeps.overrideAttrs (previousCargoAttrs: {
      name = "voxtype-${version}-vendor";
      vendorStaging = previousCargoAttrs.vendorStaging.overrideAttrs {
        name = "voxtype-${version}-vendor-staging";
        inherit src;
        outputHashAlgo = "sha256";
        outputHash = "sha256-fD6YSGFi4SOuJBkKzALQCywss2N41HZE7wYkwMSUBrg=";
      };
    });
  }
)
