// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! Ward-Beck M467 Noise Gate (1976).
//!
//! `dsp` is the signal path on its own (used by the Ward-Beck Audio Tap). With the default feature `vst`
//! this crate is also a full VST3 / CLAP plugin whose editor is the M467 front panel.

pub mod dsp;

#[cfg(feature = "vst")]
mod editor;
#[cfg(feature = "vst")]
pub use plugin::*;

#[cfg(feature = "vst")]
mod plugin {
    use crate::dsp::{Settings, M467};
    use nih_plug::prelude::*;
    use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
    use std::sync::Arc;

    /// Meter readings handed from the audio thread to the panel.
    #[derive(Default)]
    pub struct Telemetry {
        pub open: AtomicBool,
        pub atten: AtomicU32,
        pub vu: AtomicU32,
    }

    impl Telemetry {
        pub fn get(a: &AtomicU32) -> f32 {
            f32::from_bits(a.load(Ordering::Relaxed))
        }
    }

    #[derive(Params)]
    pub struct M467Params {
        #[persist = "editor-state"]
        pub editor_state: Arc<wbs_panel::nih_plug_egui::EguiState>,
        #[id = "ng"]
        pub gate: BoolParam,
        #[id = "thld"]
        pub thld: FloatParam,
        #[id = "atten"]
        pub atten: FloatParam,
        #[id = "rls"]
        pub rls: FloatParam,
        #[id = "fast"]
        pub fast: BoolParam,
        #[id = "tie_out"]
        pub tie_out: BoolParam,
        #[id = "tie1"]
        pub tie1: BoolParam,
        #[id = "tie2"]
        pub tie2: BoolParam,
    }

    impl Default for M467Params {
        fn default() -> Self {
            let d = Settings::default();
            M467Params {
                editor_state: crate::editor::default_state(),
                gate: BoolParam::new("NG", d.gate),
                thld: FloatParam::new("THLD", d.thld_db, FloatRange::Linear { min: -50.0, max: 0.0 })
                    .with_unit(" dB")
                    .with_value_to_string(formatters::v2s_f32_rounded(1)),
                atten: FloatParam::new("ATTEN", d.atten_db, FloatRange::Linear { min: 0.0, max: 50.0 })
                    .with_unit(" dB")
                    .with_value_to_string(formatters::v2s_f32_rounded(1)),
                rls: FloatParam::new("RLS", d.rls_s, FloatRange::Skewed { min: 0.1, max: 5.0, factor: FloatRange::skew_factor(-1.6) })
                    .with_unit(" s")
                    .with_value_to_string(formatters::v2s_f32_rounded(2)),
                fast: BoolParam::new("FAST", d.fast),
                tie_out: BoolParam::new("COMP TIE OUT", true),
                tie1: BoolParam::new("COMP TIE 1", false),
                tie2: BoolParam::new("COMP TIE 2", false),
            }
        }
    }

    impl M467Params {
        pub fn settings(&self) -> Settings {
            Settings {
                gate: self.gate.value(),
                thld_db: self.thld.value(),
                atten_db: self.atten.value(),
                rls_s: self.rls.value(),
                fast: self.fast.value(),
                comp_tie: if self.tie1.value() { 1 } else if self.tie2.value() { 2 } else { 0 },
            }
        }
    }

    pub struct M467Plugin {
        params: Arc<M467Params>,
        dsp: M467,
        telemetry: Arc<Telemetry>,
    }

    impl Default for M467Plugin {
        fn default() -> Self {
            M467Plugin { params: Arc::new(M467Params::default()), dsp: M467::new(48000.0), telemetry: Arc::new(Telemetry::default()) }
        }
    }

    impl Plugin for M467Plugin {
        const NAME: &'static str = "WBS M467 Noise Gate";
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
            self.telemetry.open.store(m.open, Ordering::Relaxed);
            self.telemetry.atten.store(m.atten_db.to_bits(), Ordering::Relaxed);
            self.telemetry.vu.store(m.vu.to_bits(), Ordering::Relaxed);
            ProcessStatus::Normal
        }
    }

    impl ClapPlugin for M467Plugin {
        const CLAP_ID: &'static str = "ca.ward-beck.m467";
        const CLAP_DESCRIPTION: Option<&'static str> = Some("Ward-Beck M467 Noise Gate (1976) with its edgewise VU");
        const CLAP_MANUAL_URL: Option<&'static str> = Some("https://wardbecksystems.github.io/WBSps.ca/PAGES/M467.html");
        const CLAP_SUPPORT_URL: Option<&'static str> = None;
        const CLAP_FEATURES: &'static [ClapFeature] = &[ClapFeature::AudioEffect, ClapFeature::Stereo, ClapFeature::Mono, ClapFeature::Gate];
    }

    impl Vst3Plugin for M467Plugin {
        const VST3_CLASS_ID: [u8; 16] = *b"WBS-M467-NsGate1";
        const VST3_SUBCATEGORIES: &'static [Vst3SubCategory] = &[Vst3SubCategory::Fx, Vst3SubCategory::Dynamics];
    }

    nih_export_clap!(M467Plugin);
    nih_export_vst3!(M467Plugin);
}
