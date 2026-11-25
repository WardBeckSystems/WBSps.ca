// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! M462B Parametric EQ (1974|7) signal path, free of any plugin framework (the Audio Tap uses this alone).
//!
//! Ported from the WBS VST suite (2030.env/vst/M462B_Parametric_EQ): four sections in series, LF shelf
//! (30 … 400 Hz), LMF bell (150 Hz … 2 kHz, Q 0.5 … 3), HMF bell (800 Hz … 8 kHz, Q 0.5 … 3) and HF shelf
//! (3 … 16 kHz), ±14 dB each, into the class-A output driver (a light, fixed saturation).

use crate::eq::{saturate, Section, Shape, MAX_CH};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Settings {
    pub eq_in: bool,
    pub lf_hz: f32,
    pub lf_gain_db: f32,
    pub lmf_hz: f32,
    pub lmf_q: f32,
    pub lmf_gain_db: f32,
    pub hmf_hz: f32,
    pub hmf_q: f32,
    pub hmf_gain_db: f32,
    pub hf_hz: f32,
    pub hf_gain_db: f32,
}

impl Default for Settings {
    fn default() -> Self {
        Settings { eq_in: true, lf_hz: 80.0, lf_gain_db: 0.0, lmf_hz: 500.0, lmf_q: 1.2, lmf_gain_db: 0.0, hmf_hz: 3000.0, hmf_q: 1.2, hmf_gain_db: 0.0, hf_hz: 10000.0, hf_gain_db: 0.0 }
    }
}

pub struct M462B {
    rate: f32,
    s: Settings,
    bands: [Section; 4],
}

impl M462B {
    pub fn new(sample_rate: f32) -> Self {
        let mut m = M462B { rate: sample_rate, s: Settings::default(), bands: [Section::default(); 4] };
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
        self.bands[0].set(Shape::LowShelf, s.lf_hz, 0.707, s.lf_gain_db, r);
        self.bands[1].set(Shape::Bell, s.lmf_hz, s.lmf_q, s.lmf_gain_db, r);
        self.bands[2].set(Shape::Bell, s.hmf_hz, s.hmf_q, s.hmf_gain_db, r);
        self.bands[3].set(Shape::HighShelf, s.hf_hz, 0.707, s.hf_gain_db, r);
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
                *v = saturate(x, 20.0);
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
    fn each_band_where_it_is_set() {
        let mut m = M462B::new(48000.0);
        m.set(Settings { lmf_gain_db: 8.0, lmf_hz: 400.0, hmf_gain_db: -6.0, hmf_hz: 4000.0, ..Settings::default() });
        assert!((response_db(&m.bands[1], 400.0, 48000.0) - 8.0).abs() < 0.1);
        assert!((response_db(&m.bands[2], 4000.0, 48000.0) + 6.0).abs() < 0.1);
        assert!(response_db(&m.bands[0], 1000.0, 48000.0).abs() < 0.01, "flat band");
    }
}
