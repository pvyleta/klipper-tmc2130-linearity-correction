# Changelog

All notable changes to the TMC2130 Linearity Correction Plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-06-13

### Added
- Initial release of TMC2130 Linearity Correction Plugin for Klipper
- Prusa-compatible G-code commands:
  - `TMC_SET_WAVE_X200`: Set X axis to factor 1.2
  - `TMC_SET_WAVE_E0`: Set extruder to factor 1.0 (no correction)
  - Command format: `TMC_SET_WAVE_<AXIS><OFFSET>` where offset 0-200 is added to 1000
- Implements two-phase approach for constant torque:
  - Phase 1 (0-127): Power-corrected sine curve
  - Phase 2 (128-255): Constant torque constraint solving
- Uses Prusa-compatible G-code syntax for easy migration
