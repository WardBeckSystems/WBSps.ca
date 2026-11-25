// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! The M462 front panel, laid out as the EQ module on the rack drawing (Ward-Beck-Plugin-Core/art,
//! "module-m582c" there): x along the module (0 = thumb screw, 702 = WBS badge), y across it. Inferred.

use crate::plugin::Params462;
use nih_plug::prelude::*;
use std::sync::Arc;
use wbs_panel::egui::{self, Frame, Stroke};
use wbs_panel::nih_plug_egui::{create_egui_editor, EguiState};
use wbs_panel::{ink, Button, Cap, Face, Led, Size};

const LEN: f32 = 702.0;

pub fn default_state() -> Arc<EguiState> {
    EguiState::from_size(214, 893)
}

pub fn create(params: Arc<Params462>) -> Option<Box<dyn Editor>> {
    create_egui_editor(params.editor_state.clone(), (), |_, _| {}, move |ctx, setter, _| {
        egui::CentralPanel::default().frame(Frame::NONE.fill(ink::RACK)).show(ctx, |ui| {
            let f = Face::fit(ui.max_rect().shrink(8.0), LEN);
            f.panel(ui.painter(), "M462");
            draw(ui, &f, setter, &params);
        });
    })
}

const GAIN: [(f32, &str); 7] = [(0.0, "15"), (0.1667, "10"), (0.333, "5"), (0.5, "0"), (0.667, "5"), (0.833, "10"), (1.0, "15")];

fn draw(ui: &mut egui::Ui, f: &Face, s: &ParamSetter, p: &Params462) {
    // The engraved leader lines from each band's gain to its frequency knob
    let st = Stroke::new(f.s(1.3), ink::TICK);
    let line = |pts: &[(f32, f32)]| {
        for w in pts.windows(2) {
            ui.painter().line_segment([f.p(w[0].0, w[0].1), f.p(w[1].0, w[1].1)], st);
        }
    };
    line(&[(90.0, 62.0), (90.0, 105.0)]);
    line(&[(175.0, 112.0), (238.0, 112.0), (238.0, 65.0)]);
    line(&[(365.0, 112.0), (424.0, 112.0), (424.0, 65.0)]);
    line(&[(555.0, 112.0), (616.0, 112.0), (616.0, 65.0)]);

    f.text(ui.painter(), 117.0, 45.0, "EQ", 12.0, ink::LABEL);
    f.push(ui, s, &p.eq_in, 90.0, 45.0, Size::Large, Button::Red);
    f.led(ui.painter(), 90.0, 116.0, Led::Red, p.eq_in.value());

    f.text(ui.painter(), 165.0, 45.0, "BELL", 8.5, ink::SUB);
    f.push(ui, s, &p.lf_bell, 143.0, 45.0, Size::Small, Button::White);
    f.knob(ui, s, &p.lf_gain, 143.0, 112.0, Size::Large, Cap::Green, &GAIN, 11);
    f.text(ui.painter(), 200.0, 135.0, "LF", 13.0, ink::LABEL);
    f.knob(ui, s, &p.lf_hz, 238.0, 45.0, Size::Small, Cap::Green, &[(0.0, "25"), (0.25, "40"), (0.6, "140"), (0.8, "200"), (1.0, "400")], 6);

    f.text(ui.painter(), 315.0, 19.0, "H", 11.0, ink::SUB);
    f.text(ui.painter(), 315.0, 72.0, "L", 11.0, ink::SUB);
    f.text(ui.painter(), 352.0, 45.0, "Q", 12.0, ink::LABEL);
    f.push(ui, s, &p.mf_q_high, 332.0, 45.0, Size::Small, Button::White);
    f.knob(ui, s, &p.mf_gain, 332.0, 112.0, Size::Large, Cap::Yellow, &GAIN, 11);
    f.text(ui.painter(), 388.0, 135.0, "MF", 13.0, ink::LABEL);
    f.knob(ui, s, &p.mf_hz, 424.0, 45.0, Size::Small, Cap::Yellow, &[(0.0, ".4"), (0.35, "1.2"), (0.7, "3"), (1.0, "5.4")], 8);

    f.text(ui.painter(), 542.0, 45.0, "BELL", 8.5, ink::SUB);
    f.push(ui, s, &p.hf_bell, 520.0, 45.0, Size::Small, Button::White);
    f.knob(ui, s, &p.hf_gain, 520.0, 112.0, Size::Large, Cap::Red, &GAIN, 11);
    f.text(ui.painter(), 580.0, 135.0, "HF", 13.0, ink::LABEL);
    f.knob(ui, s, &p.hf_hz, 616.0, 45.0, Size::Small, Cap::Red, &[(0.0, "1.6"), (0.3, "4"), (0.6, "10"), (1.0, "24")], 8);
}
