// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! The M462A front panel, laid out as the VST suite maps it from the M462A photo (176 × 770, measured
//! across from the left and down from the top): HF red, mid yellow, LF green, EQ IN red at the foot.

use crate::plugin::Params462A;
use nih_plug::prelude::*;
use std::sync::Arc;
use wbs_panel::egui::{self, Frame};
use wbs_panel::nih_plug_egui::{create_egui_editor, EguiState};
use wbs_panel::{ink, Button, Cap, Face, Size};

const W: f32 = 176.0;
const LEN: f32 = 770.0;

pub fn default_state() -> Arc<EguiState> {
    EguiState::from_size(236, 979)
}

pub fn create(params: Arc<Params462A>) -> Option<Box<dyn Editor>> {
    create_egui_editor(params.editor_state.clone(), (), |_, _| {}, move |ctx, setter, _| {
        egui::CentralPanel::default().frame(Frame::NONE.fill(ink::RACK)).show(ctx, |ui| {
            let f = Face::fit_size(ui.max_rect().shrink(8.0), W, LEN);
            f.panel(ui.painter(), "M462A");
            draw(ui, &f, setter, &params);
        });
    })
}

const GAIN: [(f32, &str); 5] = [(0.0, "-14"), (0.25, "-7"), (0.5, "0"), (0.75, "+7"), (1.0, "+14")];

fn draw(ui: &mut egui::Ui, f: &Face, s: &ParamSetter, p: &Params462A) {
    let at = |a: f32, d: f32| f.at(a, d);
    let text = |ui: &egui::Ui, a: f32, d: f32, t: &str, size: f32| {
        let (x, y) = at(a, d);
        f.text(ui.painter(), x, y, t, size, ink::LABEL)
    };

    text(ui, 88.0, 58.0, "HF", 12.0);
    let (x, y) = at(50.0, 95.0);
    f.knob(ui, s, &p.hf_gain, x, y, Size::Small, Cap::Red, &GAIN, 11);
    let (x, y) = at(130.0, 95.0);
    f.push(ui, s, &p.hf_10k, x, y, Size::Small, Button::White);
    text(ui, 130.0, 74.0, "SHELF", 8.5);
    text(ui, 130.0, 116.0, "10k / 3k", 8.0);

    text(ui, 88.0, 150.0, "MID", 12.0);
    let (x, y) = at(50.0, 185.0);
    f.knob(ui, s, &p.mid_hz, x, y, Size::Small, Cap::Yellow, &[(0.0, ".2"), (0.35, "1"), (0.7, "3"), (1.0, "7k")], 9);
    let (x, y) = at(126.0, 185.0);
    f.knob(ui, s, &p.mid_gain, x, y, Size::Small, Cap::Yellow, &GAIN, 11);
    let (x, y) = at(88.0, 260.0);
    f.knob(ui, s, &p.mid_q, x, y, Size::Small, Cap::Black, &[(0.0, ".6"), (1.0, "2.5")], 6);
    text(ui, 88.0, 296.0, "Q", 10.0);

    text(ui, 88.0, 312.0, "LF", 12.0);
    let (x, y) = at(50.0, 345.0);
    f.knob(ui, s, &p.lf_gain, x, y, Size::Small, Cap::Green, &GAIN, 11);
    let (x, y) = at(130.0, 345.0);
    f.push(ui, s, &p.lf_150, x, y, Size::Small, Button::White);
    text(ui, 130.0, 324.0, "50 / 150", 8.5);
    let (x, y) = at(88.0, 407.0);
    f.push(ui, s, &p.lf_shelf, x, y, Size::Small, Button::White);
    text(ui, 88.0, 428.0, "LF SHELF", 8.5);

    let (x, y) = at(88.0, 480.0);
    f.knob(ui, s, &p.drive, x, y, Size::Small, Cap::White, &[(0.0, "0"), (0.5, "50"), (1.0, "100")], 6);
    text(ui, 88.0, 516.0, "OPAMP SAT", 8.5);

    let (x, y) = at(88.0, 574.0);
    f.push(ui, s, &p.eq_in, x, y, Size::Large, Button::Red);
    text(ui, 88.0, 547.0, "EQ IN", 11.0);
}
