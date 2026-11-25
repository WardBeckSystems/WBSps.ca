// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! M462 Equalizer (1974|7) signal path, free of any plugin framework (the Audio Tap uses this alone).
//!
//! Three sweepable bands, ±15 dB: LF 25 … 400 Hz (shelf, or bell with its shape button in), MF bell
//! 400 Hz … 5.4 kHz with a Q switch (H narrow 2.5 / L wide 0.7), HF 1.6 … 24 kHz (shelf, or bell).
//! The ranges and switches follow the concept rendering of the panel (Ward-Beck-Plugin-Core/art,
//! drawn there as "M582C"): inferred, not taken from an M462 drawing.

use crate::eq::{Section, Shape, MAX_CH};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Settings {
    pub eq_in: bool,
    pub lf_bell: bool,
    pub lf_hz: f32,
    pub lf_gain_db: f32,
    /// Q switch: H (narrow) when true
    pub mf_q_high: bool,
    pub mf_hz: f32,
    pub mf_gain_db: f32,
    pub hf_bell: bool,
    pub hf_hz: f32,
    pub hf_gain_db: f32,
}

impl Default for Settings {
    fn default() -> Self {
        Settings { eq_in: true, lf_bell: false, lf_hz: 100.0, lf_gain_db: 0.0, mf_q_high: false, mf_hz: 1200.0, mf_gain_db: 0.0, hf_bell: false, hf_hz: 8000.0, hf_gain_db: 0.0 }
    }
}

pub struct M462 {
    rate: f32,
    s: Settings,
    bands: [Section; 3],
}

impl M462 {
    pub fn new(sample_rate: f32) -> Self {
        let mut m = M462 { rate: sample_rate, s: Settings::default(), bands: [Section::default(); 3] };
        m.update();
        m
    }
    pub fn set_sample_rate(&mut self, r: f32) {
        self.rate = r;
        self.reset();
        self.update();
    }
    pub fn reset(&mut self) {
        self.bands.iter_mut().for_each(Section::reset);
    }
    pub fn settings(&self) -> Settings {
        self.s
    }
    pub fn set(&mut self, s: Settings) {
        if s != self.s {
            self.s = s;
            self.update();
        }
    }
    fn update(&mut self) {
        let (s, r) = (self.s, self.rate);
        self.bands[0].set(if s.lf_bell { Shape::Bell } else { Shape::LowShelf }, s.lf_hz, 0.9, s.lf_gain_db, r);
        self.bands[1].set(Shape::Bell, s.mf_hz, if s.mf_q_high { 2.5 } else { 0.7 }, s.mf_gain_db, r);
        self.bands[2].set(if s.hf_bell { Shape::Bell } else { Shape::HighShelf }, s.hf_hz, 0.9, s.hf_gain_db, r);
    }
    pub fn process(&mut self, chans: &mut [&mut [f32]]) {
        if !self.s.eq_in {
            return;
        }
        for (ch, data) in chans.iter_mut().enumerate().take(MAX_CH) {
            for v in data.iter_mut() {
                let mut x = *v;
                for b in self.bands.iter_mut() {
                    x = b.run(ch, x);
                }
                *v = x;
            }
        }
        self.bands.iter_mut().for_each(Section::ok);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::eq::response_db;

    #[test]
    fn q_switch_narrows_the_mid() {
        let mut m = M462::new(48000.0);
        m.set(Settings { mf_gain_db: 12.0, mf_hz: 1000.0, ..Settings::default() });
        let wide = response_db(&m.bands[1], 2000.0, 48000.0);
        m.set(Settings { mf_gain_db: 12.0, mf_hz: 1000.0, mf_q_high: true, ..Settings::default() });
        let narrow = response_db(&m.bands[1], 2000.0, 48000.0);
        assert!((response_db(&m.bands[1], 1000.0, 48000.0) - 12.0).abs() < 0.1);
        assert!(narrow < wide - 3.0, "H is narrower: {narrow} vs {wide}");
    }
}
