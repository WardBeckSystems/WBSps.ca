// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! M462A Equalizer Module (1976|9) signal path, free of any plugin framework (the Audio Tap uses this alone).
//!
//! Ported from the WBS VST suite (2030.env/vst/M462A_Channel_EQ): the 4-126 op-amp front end (OPAMP SAT),
//! then an LF section at 50 or 150 Hz (shelf, or bell with LF SHELF out), a sweepable mid bell
//! (200 Hz … 7 kHz, Q 0.6 … 2.5) and an HF shelf at 10 kHz (3 kHz with HF SHELF out). ±14 dB each.

use crate::eq::{saturate, Section, Shape, MAX_CH};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Settings {
    /// EQ IN (out = straight through)
    pub eq_in: bool,
    pub lf_gain_db: f32,
    /// 50 / 150: LF turnover at 150 Hz (else 50 Hz)
    pub lf_150: bool,
    /// LF SHELF: shelf (else bell)
    pub lf_shelf: bool,
    pub mid_hz: f32,
    pub mid_q: f32,
    pub mid_gain_db: f32,
    pub hf_gain_db: f32,
    /// HF SHELF: shelf at 10 kHz (else 3 kHz)
    pub hf_10k: bool,
    /// OPAMP SAT: 0 … 100 %
    pub drive_pct: f32,
}

impl Default for Settings {
    fn default() -> Self {
        Settings { eq_in: true, lf_gain_db: 0.0, lf_150: false, lf_shelf: true, mid_hz: 1200.0, mid_q: 1.2, mid_gain_db: 0.0, hf_gain_db: 0.0, hf_10k: true, drive_pct: 20.0 }
    }
}

pub struct M462A {
    rate: f32,
    s: Settings,
    lf: Section,
    mid: Section,
    hf: Section,
}

impl M462A {
    pub fn new(sample_rate: f32) -> Self {
        let mut m = M462A { rate: sample_rate, s: Settings::default(), lf: Section::default(), mid: Section::default(), hf: Section::default() };
        m.update();
        m
    }
    pub fn set_sample_rate(&mut self, r: f32) {
        self.rate = r;
        self.reset();
        self.update();
    }
    pub fn reset(&mut self) {
        self.lf.reset();
        self.mid.reset();
        self.hf.reset();
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
        let s = self.s;
        let lf_hz = if s.lf_150 { 150.0 } else { 50.0 };
        self.lf.set(if s.lf_shelf { Shape::LowShelf } else { Shape::Bell }, lf_hz, 0.9, s.lf_gain_db, self.rate);
        self.mid.set(Shape::Bell, s.mid_hz, s.mid_q, s.mid_gain_db, self.rate);
        self.hf.set(Shape::HighShelf, if s.hf_10k { 10000.0 } else { 3000.0 }, 0.707, s.hf_gain_db, self.rate);
    }
    pub fn process(&mut self, chans: &mut [&mut [f32]]) {
        if !self.s.eq_in {
            return;
        }
        let d = self.s.drive_pct;
        for (ch, data) in chans.iter_mut().enumerate().take(MAX_CH) {
            for v in data.iter_mut() {
                let x = saturate(*v, d);
                *v = self.hf.run(ch, self.mid.run(ch, self.lf.run(ch, x)));
            }
        }
        self.lf.ok();
        self.mid.ok();
        self.hf.ok();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::eq::response_db;

    #[test]
    fn bands_land_where_the_panel_says() {
        let mut m = M462A::new(48000.0);
        m.set(Settings { mid_gain_db: 10.0, mid_hz: 1000.0, lf_gain_db: -8.0, hf_gain_db: 6.0, drive_pct: 0.0, ..Settings::default() });
        assert!((response_db(&m.mid, 1000.0, 48000.0) - 10.0).abs() < 0.1);
        assert!((response_db(&m.lf, 20.0, 48000.0) + 8.0).abs() < 0.6);
        assert!((response_db(&m.hf, 20000.0, 48000.0) - 6.0).abs() < 0.6);
        assert!(response_db(&m.mid, 100.0, 48000.0).abs() < 0.5);
    }

    #[test]
    fn eq_out_is_straight_through() {
        let mut m = M462A::new(48000.0);
        m.set(Settings { eq_in: false, mid_gain_db: 14.0, ..Settings::default() });
        let mut v: Vec<f32> = (0..480).map(|i| (i as f32 * 0.1).sin() * 0.5).collect();
        let o = v.clone();
        m.process(&mut [&mut v[..]]);
        assert_eq!(v, o);
    }
}
