// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! M466 Compressor - Limiter signal path, free of any plugin framework (the Audio Tap uses this alone).
//!
//! Ported from the WBS VST suite (2030.env/vst/M466_Compressor_Limiter): a peak detector on all channels
//! (linked), SENS ahead of it, a compressor (10 ms attack, slope 1.5 … 10:1) and a 50:1 limiter (50 µs
//! attack) in series on one gain element, and a de-esser that band-passes the detector (DS-NG 1 … 8 kHz)
//! and halves the compressor release, as the WBS manual describes. Panel dB are dBFS + 20 (0 on the
//! panel = −20 dBFS, the console's nominal level).

/// Every control on the front panel.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Settings {
    /// INS: insert in (out = hard bypass)
    pub insert: bool,
    /// COMP: compressor in
    pub comp: bool,
    /// LIM: limiter in
    pub lim: bool,
    /// D S: de-esser in
    pub de_ess: bool,
    /// GR / VU: the meter shows gain reduction (false) or output level (true)
    pub meter_vu: bool,
    /// SENS: −8 … +10 dB ahead of the detector and the gain element
    pub sens_db: f32,
    /// COMP THLD: −20 … 0 dB (panel)
    pub comp_thld_db: f32,
    /// SLOPE: 1.5 … 10 (:1)
    pub slope: f32,
    /// RLS (compressor): 0.1 … 5 s
    pub comp_rls_s: f32,
    /// LIMIT THLD: 0 … +20 dB (panel)
    pub lim_thld_db: f32,
    /// RLS (limiter): 0.1 … 5 s
    pub lim_rls_s: f32,
    /// DS-NG: de-esser centre, 1 … 8 kHz
    pub ds_hz: f32,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            insert: true,
            comp: true,
            lim: true,
            de_ess: false,
            meter_vu: false,
            sens_db: 0.0,
            comp_thld_db: -10.0,
            slope: 2.0,
            comp_rls_s: 0.5,
            lim_thld_db: 12.0,
            lim_rls_s: 0.5,
            ds_hz: 4000.0,
        }
    }
}

/// What the panel shows: the LEDs and the meter.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Meters {
    pub comp_gr_db: f32,
    pub lim_gr_db: f32,
    /// LIMIT 6 / 12: the limiter is taking 6 / 12 dB or more
    pub led6: bool,
    pub led12: bool,
    /// COMP LED: the compressor is working (≥ 1 dB)
    pub comp_led: bool,
    /// LIM LED: the limiter is working (≥ 1 dB)
    pub lim_led: bool,
    /// Output peak of the last block, dBFS
    pub out_dbfs: f32,
}

/// The M466 itself.
pub struct M466 {
    rate: f32,
    s: Settings,
    comp_env: f32,
    lim_env: f32,
    // de-esser band-pass (RBJ, Q 1.8) on the detector
    b: [f32; 3],
    a: [f32; 2],
    x: [f32; 2],
    y: [f32; 2],
    pub meters: Meters,
}

impl M466 {
    pub fn new(sample_rate: f32) -> Self {
        let mut m = M466 { rate: sample_rate, s: Settings::default(), comp_env: 0.0, lim_env: 0.0, b: [0.0; 3], a: [0.0; 2], x: [0.0; 2], y: [0.0; 2], meters: Meters::default() };
        m.update_filter();
        m
    }

    pub fn set_sample_rate(&mut self, sample_rate: f32) {
        self.rate = sample_rate;
        self.reset();
        self.update_filter();
    }

    pub fn reset(&mut self) {
        self.comp_env = 0.0;
        self.lim_env = 0.0;
        self.x = [0.0; 2];
        self.y = [0.0; 2];
        self.meters = Meters::default();
    }

    pub fn settings(&self) -> Settings {
        self.s
    }

    pub fn set(&mut self, s: Settings) {
        let refilter = s.ds_hz != self.s.ds_hz;
        self.s = s;
        if refilter {
            self.update_filter();
        }
    }

    fn update_filter(&mut self) {
        let w = std::f32::consts::TAU * self.s.ds_hz.clamp(800.0, 8000.0).min(self.rate * 0.45) / self.rate;
        let alpha = w.sin() / (2.0 * 1.8);
        let a0 = 1.0 + alpha;
        self.b = [alpha / a0, 0.0, -alpha / a0];
        self.a = [-2.0 * w.cos() / a0, (1.0 - alpha) / a0];
    }

    /// Process planar channels in place (all channels share one detector, as the module's stereo link).
    pub fn process(&mut self, chans: &mut [&mut [f32]]) {
        let frames = chans.iter().map(|c| c.len()).min().unwrap_or(0);
        if frames == 0 {
            return;
        }
        let s = self.s;
        if !s.insert {
            let peak = chans.iter().flat_map(|c| c.iter()).fold(0.0f32, |m, v| m.max(v.abs()));
            self.meters = Meters { out_dbfs: db(peak), ..Meters::default() };
            return;
        }
        let sens = 10f32.powf(s.sens_db / 20.0);
        let coef = |sec: f32| 1.0 - (-1.0 / (sec.max(1e-6) * self.rate)).exp();
        let comp_att = coef(0.010);
        let comp_rls = coef(if s.de_ess { s.comp_rls_s * 0.5 } else { s.comp_rls_s });
        let lim_att = coef(0.000_05);
        let lim_rls = coef(s.lim_rls_s);
        let slope = s.slope.max(1.0);
        let (mut max_c, mut max_l, mut peak_out) = (0.0f32, 0.0f32, 0.0f32);

        for i in 0..frames {
            let mut det = 0.0f32;
            for c in chans.iter() {
                det = det.max((c[i] * sens).abs());
            }
            if s.de_ess {
                let bp = self.b[0] * det + self.b[1] * self.x[0] + self.b[2] * self.x[1] - self.a[0] * self.y[0] - self.a[1] * self.y[1];
                self.x = [det, self.x[0]];
                self.y = [bp, self.y[0]];
                det = bp.abs() * 2.5; // lift the sibilance so it drives the detector
            }
            let in_db = if det > 1e-5 { 20.0 * det.log10() + 20.0 } else { -40.0 };

            let tc = if s.comp && in_db > s.comp_thld_db { (in_db - s.comp_thld_db) * (1.0 - 1.0 / slope) } else { 0.0 };
            self.comp_env += if tc > self.comp_env { comp_att } else { comp_rls } * (tc - self.comp_env);
            let tl = if s.lim && in_db > s.lim_thld_db { (in_db - s.lim_thld_db) * (1.0 - 1.0 / 50.0) } else { 0.0 };
            self.lim_env += if tl > self.lim_env { lim_att } else { lim_rls } * (tl - self.lim_env);

            max_c = max_c.max(self.comp_env);
            max_l = max_l.max(self.lim_env);
            let g = 10f32.powf(-(self.comp_env + self.lim_env) / 20.0) * sens;
            for c in chans.iter_mut() {
                c[i] *= g;
                peak_out = peak_out.max(c[i].abs());
            }
        }
        if !self.comp_env.is_finite() || !self.lim_env.is_finite() {
            self.reset();
        }
        self.meters = Meters {
            comp_gr_db: max_c,
            lim_gr_db: max_l,
            led6: max_l >= 6.0,
            led12: max_l >= 12.0,
            comp_led: max_c >= 1.0,
            lim_led: max_l >= 1.0,
            out_dbfs: db(peak_out),
        };
    }
}

fn db(lin: f32) -> f32 {
    if lin > 1e-6 {
        20.0 * lin.log10()
    } else {
        -120.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sine(db_fs: f32, hz: f32, n: usize) -> Vec<f32> {
        let a = 10f32.powf(db_fs / 20.0);
        (0..n).map(|i| a * (std::f32::consts::TAU * hz * i as f32 / 48000.0).sin()).collect()
    }

    fn peak(v: &[f32]) -> f32 {
        v.iter().fold(0.0f32, |m, x| m.max(x.abs()))
    }

    #[test]
    fn quiet_signal_passes_untouched() {
        let mut m = M466::new(48000.0);
        let mut l = sine(-40.0, 1000.0, 48000);
        let before = peak(&l);
        m.process(&mut [&mut l[..]]);
        assert!((peak(&l) / before - 1.0).abs() < 1e-3);
        assert_eq!(m.meters.comp_gr_db, 0.0);
    }

    #[test]
    fn hot_signal_is_limited_and_lights_the_leds() {
        let mut m = M466::new(48000.0);
        let mut s = Settings::default();
        s.comp = false;
        s.lim_thld_db = 0.0; // limit at −20 dBFS
        m.set(s);
        let mut l = sine(-2.0, 1000.0, 48000); // 18 dB over
        m.process(&mut [&mut l[..]]);
        let tail = peak(&l[40000..]);
        assert!(20.0 * tail.log10() < -18.0, "limited to about −20 dBFS, got {}", 20.0 * tail.log10());
        assert!(m.meters.led6 && m.meters.led12);
    }

    #[test]
    fn compressor_follows_its_slope() {
        let mut m = M466::new(48000.0);
        let mut s = Settings::default();
        s.lim = false;
        s.comp_thld_db = -10.0; // −30 dBFS
        s.slope = 2.0;
        m.set(s);
        let mut l = sine(-10.0, 1000.0, 96000); // 20 dB over → 10 dB of reduction at 2:1
        m.process(&mut [&mut l[..]]);
        let out = 20.0 * peak(&l[90000..]).log10();
        assert!((out - (-20.0)).abs() < 1.0, "expected about −20 dBFS, got {out}");
    }

    #[test]
    fn insert_out_is_a_true_bypass() {
        let mut m = M466::new(48000.0);
        let mut s = Settings::default();
        s.insert = false;
        m.set(s);
        let mut l = sine(0.0, 1000.0, 4800);
        let orig = l.clone();
        m.process(&mut [&mut l[..]]);
        assert_eq!(l, orig);
    }
}
