// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! The M467 front panel. Positions are the module on the rack drawing (Ward-Beck-Plugin-Core/art,
//! "module-m407" there), x along the module (0 = thumb screw, 702 = WBS badge), y across it.

use crate::plugin::{M467Params, Telemetry};
use nih_plug::prelude::*;
use std::sync::atomic::Ordering;
use std::sync::Arc;
use wbs_panel::egui::{self, Frame};
use wbs_panel::nih_plug_egui::{create_egui_editor, EguiState};
use wbs_panel::{ink, Button, Cap, Face, Led, Size};

const LEN: f32 = 702.0;

pub fn default_state() -> Arc<EguiState> {
    EguiState::from_size(214, 893)
}

pub fn create(params: Arc<M467Params>, tel: Arc<Telemetry>) -> Option<Box<dyn Editor>> {
    create_egui_editor(params.editor_state.clone(), (), |_, _| {}, move |ctx, setter, _| {
        egui::CentralPanel::default().frame(Frame::NONE.fill(ink::RACK)).show(ctx, |ui| {
            let face = Face::fit(ui.max_rect().shrink(8.0), LEN);
            face.panel(ui.painter(), "M467");
            draw(ui, &face, setter, &params, &tel);
        });
        ctx.request_repaint_after(std::time::Duration::from_millis(33));
    })
}

fn draw(ui: &mut egui::Ui, f: &Face, setter: &ParamSetter, p: &M467Params, t: &Telemetry) {
    let open = t.open.load(Ordering::Relaxed);

    // NG in / out, and its lamp: lit while the gate is holding the signal down
    f.text(ui.painter(), 122.0, 45.0, "NG", 12.0, ink::LABEL);
    f.push(ui, setter, &p.gate, 95.0, 45.0, Size::Large, Button::Red);
    f.led(ui.painter(), 95.0, 116.0, Led::Red, p.gate.value() && !open);

    f.knob(ui, setter, &p.rls, 148.0, 112.0, Size::Large, Cap::Black, &[(0.0, "0.1"), (0.55, "1"), (1.0, "5")], 8);
    f.text(ui.painter(), 104.0, 140.0, "RLS", 10.0, ink::LABEL);

    f.knob(ui, setter, &p.thld, 238.0, 45.0, Size::Large, Cap::Black, &[(0.0, "-50"), (1.0, "0")], 8);
    f.text(ui.painter(), 192.0, 45.0, "THLD", 10.0, ink::LABEL);

    f.text(ui.painter(), 348.0, 45.0, "GATE", 11.0, ink::LABEL);
    f.led(ui.painter(), 330.0, 45.0, Led::Green, p.gate.value() && open);

    f.knob(ui, setter, &p.atten, 330.0, 112.0, Size::Large, Cap::Black, &[(0.0, "0"), (1.0, "50")], 8);
    f.text(ui.painter(), 284.0, 112.0, "ATTEN", 10.0, ink::LABEL);

    f.lever(ui, setter, &p.fast, 412.0, 112.0);
    f.text(ui.painter(), 412.0, 136.0, "FAST", 8.5, ink::TINY);

    f.push_radio(ui, setter, &[&p.tie_out, &p.tie1, &p.tie2], &[470.0, 505.0, 540.0], 112.0, Size::Small, Button::White);
    f.text(ui.painter(), 470.0, 138.0, "OUT", 9.0, ink::TINY);
    f.text(ui.painter(), 505.0, 138.0, "1", 10.0, ink::TINY);
    f.text(ui.painter(), 540.0, 138.0, "2", 10.0, ink::TINY);
    f.text(ui.painter(), 568.0, 112.0, "COMP TIE", 10.0, ink::LABEL);

    // The edgewise VU on the output
    f.edgewise_vu(ui.painter(), 406.0, 630.0, 12.0, 58.0, Telemetry::get(&t.vu));
}
