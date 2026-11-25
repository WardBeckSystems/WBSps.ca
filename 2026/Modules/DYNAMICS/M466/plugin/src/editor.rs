// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! The M466 front panel. Positions are the module on the rack drawing (Ward-Beck-Plugin-Core/art,
//! "module-m456" there), x along the module (0 = thumb screw, 702 = WBS badge), y across it.

use crate::plugin::{M466Params, Telemetry};
use nih_plug::prelude::*;
use std::sync::atomic::Ordering;
use std::sync::Arc;
use wbs_panel::egui::{self, Frame};
use wbs_panel::nih_plug_egui::{create_egui_editor, EguiState};
use wbs_panel::{ink, Button, Cap, Face, Led, Size};

const LEN: f32 = 702.0;

pub fn default_state() -> Arc<EguiState> {
    // 1.25 px per drawing unit, plus the rack margin
    EguiState::from_size(214, 893)
}

pub fn create(params: Arc<M466Params>, tel: Arc<Telemetry>) -> Option<Box<dyn Editor>> {
    create_egui_editor(params.editor_state.clone(), (), |_, _| {}, move |ctx, setter, _| {
        egui::CentralPanel::default().frame(Frame::NONE.fill(ink::RACK)).show(ctx, |ui| {
            let face = Face::fit(ui.max_rect().shrink(8.0), LEN);
            face.panel(ui.painter(), "M466");
            draw(ui, &face, setter, &params, &tel);
        });
        ctx.request_repaint_after(std::time::Duration::from_millis(33));
    })
}

fn draw(ui: &mut egui::Ui, f: &Face, setter: &ParamSetter, p: &M466Params, t: &Telemetry) {
    let lit = |b: &std::sync::atomic::AtomicBool| b.load(Ordering::Relaxed);
    let g = Telemetry::get;

    // Push-buttons and their legends
    f.text(ui.painter(), 117.0, 45.0, "INS", 11.0, ink::LABEL);
    f.push(ui, setter, &p.insert, 90.0, 45.0, Size::Large, Button::White);

    f.text(ui.painter(), 172.0, 45.0, "COMP", 11.0, ink::LABEL);
    f.push(ui, setter, &p.comp, 145.0, 45.0, Size::Large, Button::Red);
    f.led(ui.painter(), 145.0, 16.0, Led::Red, lit(&t.comp_led) && p.comp.value() && p.insert.value());

    f.text(ui.painter(), 349.0, 45.0, "GR  /  VU", 9.5, ink::LABEL);
    f.push(ui, setter, &p.meter_vu, 328.0, 45.0, Size::Small, Button::White);

    f.text(ui.painter(), 399.0, 45.0, "D S", 10.5, ink::LABEL);
    f.push(ui, setter, &p.de_ess, 378.0, 45.0, Size::Small, Button::White);

    f.text(ui.painter(), 469.0, 45.0, "LIM", 11.0, ink::LABEL);
    f.push(ui, setter, &p.lim, 442.0, 45.0, Size::Large, Button::Red);
    f.led(ui.painter(), 442.0, 16.0, Led::Red, lit(&t.lim_led) && p.lim.value() && p.insert.value());

    // LIMIT 6 / 12 dB lamps
    f.text(ui.painter(), 640.0, 34.0, "LIMIT", 9.5, ink::LABEL);
    f.led(ui.painter(), 612.0, 22.0, Led::Green, lit(&t.led6));
    f.text(ui.painter(), 598.0, 22.0, "6", 9.0, ink::TINY);
    f.led(ui.painter(), 612.0, 48.0, Led::Amber, lit(&t.led12));
    f.text(ui.painter(), 598.0, 48.0, "12", 9.0, ink::TINY);

    // Knobs: compressor (green), de-esser (black), limiter (yellow), SENS (white)
    f.knob(ui, setter, &p.comp_rls, 177.0, 112.0, Size::Small, Cap::Green, &[(0.0, "0.1"), (0.33, "0.5"), (0.7, "2"), (1.0, "5")], 6);
    f.text(ui.painter(), 141.0, 112.0, "RLS", 9.5, ink::TINY);

    f.knob(ui, setter, &p.comp_thld, 245.0, 45.0, Size::Small, Cap::Green, &[(0.0, "-20"), (0.2, "-16"), (0.4, "-12"), (0.6, "-8"), (0.8, "-4"), (1.0, "0")], 6);
    f.text(ui.painter(), 207.0, 45.0, "COMP THLD", 9.0, ink::LABEL);

    f.knob(ui, setter, &p.slope, 285.0, 112.0, Size::Small, Cap::Green, &[(0.0, "1.5"), (0.25, "2"), (0.5, "3"), (0.75, "5"), (1.0, "10")], 5);
    f.text(ui.painter(), 249.0, 112.0, "SLOPE", 9.5, ink::LABEL);

    f.knob(ui, setter, &p.ds_freq, 378.0, 112.0, Size::Large, Cap::Black, &[(0.0, "1kHz"), (1.0, "8kHz")], 0);
    f.text(ui.painter(), 330.0, 112.0, "DS-NG", 9.5, ink::LABEL);

    f.knob(ui, setter, &p.lim_rls, 486.0, 112.0, Size::Small, Cap::Yellow, &[(0.0, "0.1"), (0.33, "0.5"), (0.7, "2"), (1.0, "5")], 6);
    f.text(ui.painter(), 450.0, 112.0, "RLS", 9.5, ink::TINY);

    f.knob(ui, setter, &p.lim_thld, 550.0, 45.0, Size::Small, Cap::Yellow, &[(0.0, "0"), (0.2, "4"), (0.4, "8"), (0.6, "12"), (0.8, "16"), (1.0, "+20")], 6);
    f.text(ui.painter(), 512.0, 45.0, "LIMIT THLD", 9.0, ink::LABEL);

    f.knob(ui, setter, &p.sens, 610.0, 112.0, Size::Small, Cap::White, &[(0.0, "-8"), (0.222, "-4"), (0.444, "0"), (0.667, "+4"), (1.0, "+10")], 6);
    f.text(ui.painter(), 574.0, 112.0, "SENS", 9.5, ink::LABEL);

    // Gain reduction / output readout under the badge (the M466M meter's job on the console)
    let txt = if p.meter_vu.value() { format!("OUT {:+.1} dBFS", g(&t.out_db)) } else { format!("GR {:.1} dB", g(&t.comp_gr) + g(&t.lim_gr)) };
    f.text(ui.painter(), 660.0, 79.5, &txt, 8.5, ink::TINY);
}
