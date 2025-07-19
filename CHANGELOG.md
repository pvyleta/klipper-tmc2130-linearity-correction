# Changelog

All notable changes to the TMC2130 Linearity Correction Plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-06-13

### Added
- Initial release of TMC2130 Linearity Correction Plugin for Klipper
- Simplified plugin focusing on proven constant torque algorithm
- Fixed optimal parameters:
  - `amplitude`: 248 (optimal per AN-026)
  - `sin0`: 0 (standard starting value)
- Configuration parameters:
  - `linearity_factor`: Power factor for linearity correction (1000-1200)
- Prusa-compatible G-code commands:
  - `TMC_SET_WAVE_X200`: Set X axis to factor 1.2
  - `TMC_SET_WAVE_E0`: Set extruder to factor 1.0 (no correction)
  - Command format: `TMC_SET_WAVE_<AXIS><OFFSET>` where offset 0-200 is added to 1000
- Per-stepper configuration support
- Runtime parameter adjustment without Klipper restart
- Comprehensive documentation and examples
- Installation script with auto-detection
- Unit tests for plugin validation
- Example configuration with tuning macros

### Technical Details
- Based on Prusa Firmware TMC2130 constant torque algorithm
- Implements two-phase approach for constant torque:
  - Phase 1 (0-127): Power-corrected sine curve
  - Phase 2 (128-255): Constant torque constraint solving
- Uses Prusa-compatible G-code syntax for easy migration
- Follows Klipper plugin best practices
- Compatible with existing TMC2130 driver configurations
- Simplified architecture focusing on proven algorithm

### Documentation
- Comprehensive README with installation and tuning guide
- Example configuration file with multiple scenarios
- Technical background and algorithm explanation
- Troubleshooting guide and best practices
- Reference to original research and documentation

### Testing
- Unit test suite covering core functionality
- Mock-based testing for Klipper integration
- Validation of configuration parameters
- Error handling verification

## [Unreleased]

### Planned Features
- Integration with actual TMC2130 register writes
- Real-time monitoring of wave generation parameters
- Advanced tuning algorithms based on motor feedback
- Integration with Klipper's TMC driver infrastructure
- Web interface for easy configuration
- Automatic tuning based on print quality metrics
