// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! The M462B front panel, laid out as the VST suite maps it from the M462B photo (176 × 770, measured
//! across from the left and down from the top): HF red, HMF amber, LMF yellow, LF green, EQ IN at the foot.

use crate::plugin::Params462B;
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

pub fn create(params: Arc<Params462B>) -> Option<Box<dyn Editor>> {
    create_egui_editor(params.editor_state.clone(), (), |_, _| {}, move |ctx, setter, _| {
        egui::CentralPanel::default().frame(Frame::NONE.fill(ink::RACK)).show(ctx, |ui| {
            let f = Face::fit_size(ui.max_rect().shrink(8.0), W, LEN);
            f.panel(ui.painter(), "M462B");
            draw(ui, &f, setter, &params);
        });
    })
}

const GAIN: [(f32, &str); 5] = [(0.0, "-14"), (0.25, "-7"), (0.5, "0"), (0.75, "+7"), (1.0, "+14")];
const Q: [(f32, &str); 2] = [(0.0, ".5"), (1.0, "3")];

fn draw(ui: &mut egui::Ui, f: &Face, s: &ParamSetter, p: &Params462B) {
    let at = |a: f32, d: f32| f.at(a, d);
    let text = |ui: &egui::Ui, a: f32, d: f32, t: &str, size: f32| {
        let (x, y) = at(a, d);
        f.text(ui.painter(), x, y, t, size, ink::LABEL)
    };
    let knob = |ui: &mut egui::Ui, param: &FloatParam, a: f32, d: f32, cap: Cap, scale: &[(f32, &str)], ticks: usize| {
        let (x, y) = at(a, d);
        f.knob(ui, s, param, x, y, Size::Small, cap, scale, ticks);
    };

    text(ui, 88.0, 55.0, "HF", 12.0);
    knob(ui, &p.hf_hz, 50.0, 90.0, Cap::Red, &[(0.0, "3k"), (0.5, "8"), (1.0, "16")], 9);
    knob(ui, &p.hf_gain, 126.0, 90.0, Cap::Red, &GAIN, 11);

    text(ui, 88.0, 145.0, "HMF", 12.0);
    knob(ui, &p.hmf_hz, 50.0, 180.0, Cap::Amber, &[(0.0, ".8k"), (0.5, "3"), (1.0, "8")], 9);
    knob(ui, &p.hmf_gain, 126.0, 180.0, Cap::Amber, &GAIN, 11);
    knob(ui, &p.hmf_q, 88.0, 245.0, Cap::Black, &Q, 6);
    text(ui, 88.0, 280.0, "Q", 10.0);

    text(ui, 88.0, 295.0, "LMF", 12.0);
    knob(ui, &p.lmf_hz, 50.0, 330.0, Cap::Yellow, &[(0.0, "150"), (0.5, "600"), (1.0, "2k")], 9);
    knob(ui, &p.lmf_gain, 126.0, 330.0, Cap::Yellow, &GAIN, 11);
    knob(ui, &p.lmf_q, 88.0, 395.0, Cap::Black, &Q, 6);
    text(ui, 88.0, 430.0, "Q", 10.0);

    text(ui, 88.0, 445.0, "LF", 12.0);
    knob(ui, &p.lf_hz, 50.0, 480.0, Cap::Green, &[(0.0, "30"), (0.5, "120"), (1.0, "400")], 9);
    knob(ui, &p.lf_gain, 126.0, 480.0, Cap::Green, &GAIN, 11);

    let (x, y) = at(88.0, 584.0);
    f.push(ui, s, &p.eq_in, x, y, Size::Large, Button::Red);
    text(ui, 88.0, 557.0, "EQ IN", 11.0);
}
