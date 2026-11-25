// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! Ward-Beck M466 Compressor - Limiter (1976|9).
//!
//! `dsp` is the signal path on its own (used by the Ward-Beck Audio Tap). With the default feature `vst`
//! this crate is also a full VST3 / CLAP plugin whose editor is the M466 front panel.

pub mod dsp;

#[cfg(feature = "vst")]
mod editor;
#[cfg(feature = "vst")]
pub use plugin::*;

#[cfg(feature = "vst")]
mod plugin {
    use crate::dsp::{Settings, M466};
    use nih_plug::prelude::*;
    use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
    use std::sync::Arc;

    /// Meter readings handed from the audio thread to the panel.
    #[derive(Default)]
    pub struct Telemetry {
        pub comp_gr: AtomicU32,
        pub lim_gr: AtomicU32,
        pub out_db: AtomicU32,
        pub led6: AtomicBool,
        pub led12: AtomicBool,
        pub comp_led: AtomicBool,
        pub lim_led: AtomicBool,
    }

    impl Telemetry {
        pub fn get(a: &AtomicU32) -> f32 {
            f32::from_bits(a.load(Ordering::Relaxed))
        }
    }

    pub const SLOPES: [f32; 5] = [1.5, 2.0, 3.0, 5.0, 10.0];

    #[derive(Params)]
    pub struct M466Params {
        #[persist = "editor-state"]
        pub editor_state: Arc<wbs_panel::nih_plug_egui::EguiState>,
        #[id = "ins"]
        pub insert: BoolParam,
        #[id = "comp"]
        pub comp: BoolParam,
        #[id = "lim"]
        pub lim: BoolParam,
        #[id = "ds"]
        pub de_ess: BoolParam,
        #[id = "grvu"]
        pub meter_vu: BoolParam,
        #[id = "sens"]
        pub sens: FloatParam,
        #[id = "cthld"]
        pub comp_thld: FloatParam,
        #[id = "slope"]
        pub slope: IntParam,
        #[id = "crls"]
        pub comp_rls: FloatParam,
        #[id = "lthld"]
        pub lim_thld: FloatParam,
        #[id = "lrls"]
        pub lim_rls: FloatParam,
        #[id = "dsng"]
        pub ds_freq: FloatParam,
    }

    fn release(name: &str, default: f32) -> FloatParam {
        FloatParam::new(name, default, FloatRange::Skewed { min: 0.1, max: 5.0, factor: FloatRange::skew_factor(-1.6) })
            .with_unit(" s")
            .with_value_to_string(formatters::v2s_f32_rounded(2))
    }

    impl Default for M466Params {
        fn default() -> Self {
            let d = Settings::default();
            M466Params {
                editor_state: crate::editor::default_state(),
                insert: BoolParam::new("INS", d.insert),
                comp: BoolParam::new("COMP", d.comp),
                lim: BoolParam::new("LIM", d.lim),
                de_ess: BoolParam::new("D S", d.de_ess),
                meter_vu: BoolParam::new("GR / VU", d.meter_vu),
                sens: FloatParam::new("SENS", d.sens_db, FloatRange::Linear { min: -8.0, max: 10.0 })
                    .with_unit(" dB")
                    .with_smoother(SmoothingStyle::Linear(20.0))
                    .with_value_to_string(formatters::v2s_f32_rounded(1)),
                comp_thld: FloatParam::new("COMP THLD", d.comp_thld_db, FloatRange::Linear { min: -20.0, max: 0.0 })
                    .with_unit(" dB")
                    .with_value_to_string(formatters::v2s_f32_rounded(1)),
                slope: IntParam::new("SLOPE", 1, IntRange::Linear { min: 0, max: 4 })
                    .with_value_to_string(Arc::new(|i| format!("{}:1", SLOPES[i.clamp(0, 4) as usize])))
                    .with_string_to_value(Arc::new(|s| {
                        let v: f32 = s.trim_end_matches(":1").trim().parse().ok()?;
                        SLOPES.iter().position(|x| (*x - v).abs() < 0.01).map(|i| i as i32)
                    })),
                comp_rls: release("COMP RLS", d.comp_rls_s),
                lim_thld: FloatParam::new("LIMIT THLD", d.lim_thld_db, FloatRange::Linear { min: 0.0, max: 20.0 })
                    .with_unit(" dB")
                    .with_value_to_string(formatters::v2s_f32_rounded(1)),
                lim_rls: release("LIMIT RLS", d.lim_rls_s),
                ds_freq: FloatParam::new("DS-NG", d.ds_hz, FloatRange::Skewed { min: 1000.0, max: 8000.0, factor: FloatRange::skew_factor(-1.0) })
                    .with_value_to_string(formatters::v2s_f32_hz_then_khz(1))
                    .with_string_to_value(formatters::s2v_f32_hz_then_khz()),
            }
        }
    }

    impl M466Params {
        pub fn settings(&self) -> Settings {
            Settings {
                insert: self.insert.value(),
                comp: self.comp.value(),
                lim: self.lim.value(),
                de_ess: self.de_ess.value(),
                meter_vu: self.meter_vu.value(),
                sens_db: self.sens.smoothed.next(),
                comp_thld_db: self.comp_thld.value(),
                slope: SLOPES[self.slope.value().clamp(0, 4) as usize],
                comp_rls_s: self.comp_rls.value(),
                lim_thld_db: self.lim_thld.value(),
                lim_rls_s: self.lim_rls.value(),
                ds_hz: self.ds_freq.value(),
            }
        }
    }

    pub struct M466Plugin {
        params: Arc<M466Params>,
        dsp: M466,
        telemetry: Arc<Telemetry>,
    }

    impl Default for M466Plugin {
        fn default() -> Self {
            M466Plugin { params: Arc::new(M466Params::default()), dsp: M466::new(48000.0), telemetry: Arc::new(Telemetry::default()) }
        }
    }

    impl Plugin for M466Plugin {
        const NAME: &'static str = "WBS M466 Compressor - Limiter";
        const VENDOR: &'static str = "Ward-Beck Systems";
        const URL: &'static str = "https://ward-beck.ca";
        const EMAIL: &'static str = "info@ward-beck.ca";
        const VERSION: &'static str = env!("CARGO_PKG_VERSION");

        const AUDIO_IO_LAYOUTS: &'static [AudioIOLayout] = &[
            AudioIOLayout { main_input_channels: NonZeroU32::new(2), main_output_channels: NonZeroU32::new(2), ..AudioIOLayout::const_default() },
            AudioIOLayout { main_input_channels: NonZeroU32::new(1), main_output_channels: NonZeroU32::new(1), ..AudioIOLayout::const_default() },
        ];
        const SAMPLE_ACCURATE_AUTOMATION: bool = false;
        type SysExMessage = ();
        type BackgroundTask = ();

        fn params(&self) -> Arc<dyn Params> {
            self.params.clone()
        }

        fn editor(&mut self, _async_executor: AsyncExecutor<Self>) -> Option<Box<dyn Editor>> {
            crate::editor::create(self.params.clone(), self.telemetry.clone())
        }

        fn initialize(&mut self, _layout: &AudioIOLayout, config: &BufferConfig, _context: &mut impl InitContext<Self>) -> bool {
            self.dsp.set_sample_rate(config.sample_rate);
            true
        }

        fn reset(&mut self) {
            self.dsp.reset();
        }

        fn process(&mut self, buffer: &mut Buffer, _aux: &mut AuxiliaryBuffers, _context: &mut impl ProcessContext<Self>) -> ProcessStatus {
            self.dsp.set(self.params.settings());
            self.dsp.process(buffer.as_slice());
            let m = self.dsp.meters;
            let t = &self.telemetry;
            t.comp_gr.store(m.comp_gr_db.to_bits(), Ordering::Relaxed);
            t.lim_gr.store(m.lim_gr_db.to_bits(), Ordering::Relaxed);
            t.out_db.store(m.out_dbfs.to_bits(), Ordering::Relaxed);
            t.led6.store(m.led6, Ordering::Relaxed);
            t.led12.store(m.led12, Ordering::Relaxed);
            t.comp_led.store(m.comp_led, Ordering::Relaxed);
            t.lim_led.store(m.lim_led, Ordering::Relaxed);
            ProcessStatus::Normal
        }
    }

    impl ClapPlugin for M466Plugin {
        const CLAP_ID: &'static str = "ca.ward-beck.m466";
        const CLAP_DESCRIPTION: Option<&'static str> = Some("Ward-Beck M466 Compressor - Limiter (1976): compressor, 50:1 limiter, de-esser");
        const CLAP_MANUAL_URL: Option<&'static str> = Some("https://wardbecksystems.github.io/WBSps.ca/PAGES/M466.html");
        const CLAP_SUPPORT_URL: Option<&'static str> = None;
        const CLAP_FEATURES: &'static [ClapFeature] = &[ClapFeature::AudioEffect, ClapFeature::Stereo, ClapFeature::Mono, ClapFeature::Compressor, ClapFeature::Limiter];
    }

    impl Vst3Plugin for M466Plugin {
        const VST3_CLASS_ID: [u8; 16] = *b"WBS-M466-CmpLim1";
        const VST3_SUBCATEGORIES: &'static [Vst3SubCategory] = &[Vst3SubCategory::Fx, Vst3SubCategory::Dynamics];
    }

    nih_export_clap!(M466Plugin);
    nih_export_vst3!(M466Plugin);
}
