# TMC2130 Linearity Correction for Klipper

A high-precision stepper motor linearity correction plugin that eliminates TMC2130-induced print quality artifacts through constant torque wave table optimization.

## Overview

The TMC2130 stepper driver's internal sine wave lookup table (MSLUT) contains inherent non-linearities that create uneven torque distribution across microstep positions. This results in periodic variations in actual step size, manifesting as:

- **Salmon skin surface artifacts** - periodic texture variations
- **Dimensional inaccuracies** - systematic errors in printed dimensions  
- **Layer inconsistencies** - visible banding in solid fills

This plugin implements the proven constant torque algorithm from Prusa firmware, providing identical functionality and G-code compatibility for seamless migration from Marlin-based systems.

## Technical Implementation

### Constant Torque Algorithm

The plugin generates optimized wave tables where torque output remains constant across all microstep positions:

```
|A|² + |B|² = constant
```

Where A and B represent the two-phase current values. This ensures uniform step sizes and eliminates the non-linear torque characteristics of standard sine wave tables.

### Prusa Firmware Compatibility

The implementation provides 100% algorithmic compatibility with Prusa firmware:

- **tmc2130_goto_step**: Exact line-by-line algorithm match for precise stepper positioning
- **Auto-direction mode**: Shortest path calculation with XOR direction flipping
- **Position verification**: Step-by-step MSCNT register monitoring
- **Timing precision**: Microsecond-accurate delays matching hardware behavior

## Installation

1. Copy `tmc2130_linearity.py` to your Klipper extras directory
2. Add configuration sections for each TMC2130-equipped axis
3. Restart Klipper service

## Configuration

```ini
[tmc2130_linearity stepper_x]
linearity_factor: 1.0

[tmc2130_linearity stepper_y] 
linearity_factor: 1.0

[tmc2130_linearity extruder]
linearity_factor: 1.0
```

### Parameters

- **linearity_factor**: Correction strength (1.0-1.2)
  - `1.0`: No correction (default sine wave)
  - `1.1`: Moderate correction for most applications
  - `1.2`: Maximum correction for problematic motors

## G-code Commands

### TMC_SET_WAVE - Runtime Linearity Adjustment

```gcode
TMC_SET_WAVE_X100    # Set X-axis to factor 1.1
TMC_SET_WAVE_Y200    # Set Y-axis to factor 1.2
TMC_SET_WAVE_E0      # Set extruder to factor 1.0 (disable)
```

**Available factor offsets**: 0, 10, 20, 30, ..., 190, 200 (steps of 10)
- `TMC_SET_WAVE_E0` → factor 1.0 (no correction)
- `TMC_SET_WAVE_E100` → factor 1.1 (moderate correction)
- `TMC_SET_WAVE_E200` → factor 1.2 (maximum correction)

### TMC_SET_STEP - Precise Stepper Positioning

```gcode
TMC_SET_STEP_X128    # Move X-axis to microstep position 128
TMC_SET_STEP_Y0      # Move Y-axis to microstep position 0
TMC_SET_STEP_E1000   # Move extruder to microstep position 1000
```

**Available step positions**: 0, 2, 4, 6, ..., 1048, 1050 (steps of 2)
- Range: 0-1050 (automatically masked to microstep resolution)

## Calibration Workflow

1. **Baseline measurement**: Print test object with `linearity_factor: 1.0`
2. **Apply correction**: Set `linearity_factor: 1.1` and reprint
3. **Fine-tune**: Adjust factor based on dimensional accuracy and surface quality
4. **Validate**: Use TMC_SET_STEP commands to verify precise positioning

## Hardware Requirements

- **TMC2130 stepper drivers** with SPI interface
- **Klipper firmware** with TMC driver support
- **Pin access** (optional): For hardware step/direction control during calibration

## Architecture

The plugin integrates seamlessly with Klipper's event-driven architecture:

- **Non-blocking operation**: All pin control uses scheduled callbacks
- **MCU synchronization**: Precise timing through Klipper's clock system
- **Graceful degradation**: Algorithm-only mode when hardware pins unavailable
- **Error resilience**: Comprehensive exception handling and logging

## Performance Impact

- **Initialization**: One-time wave table calculation and register programming
- **Runtime**: Zero performance overhead during normal printing
- **Memory**: Minimal footprint (~2KB per configured axis)

## Compatibility

- **Klipper**: All recent versions with TMC driver support
- **Hardware**: TMC2130, TMC2160, TMC5160 (with appropriate driver configuration)
- **Firmware**: Drop-in replacement for Prusa firmware TMC functionality

## License

GNU GPLv3 - See LICENSE file for details

## Author

Petr Vyleta <pvyleta+pure@purestorage.com>

---

*This implementation is based on extensive analysis of Prusa firmware's TMC2130 algorithms and provides production-ready linearity correction for professional 3D printing applications.*
