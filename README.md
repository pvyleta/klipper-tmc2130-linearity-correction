# TMC2130 Linearity Correction for Klipper

A high-precision stepper motor linearity correction plugin that eliminates stepper-induced print quality artifacts through constant torque wave table optimization.

## Overview

The TMC2130 stepper driver's internal sine wave lookup table allows to comensate for motor non-linearities. The algorithm here is based powered sine function that is modified to satisfy the constant torque constraint. The original idea comes from [this](https://forum.prusa3d.com/forum/original-prusa-i3-mk3s-mk3-user-mods-octoprint-enclosures-nozzles/stepper-motor-upgrades-to-eliminate-vfa-s-vertical-fine-artifacts/paged/2/) forum post.

This plugin implements the syntax from Prusa Firmware for setting the wave correction and stepper position TMC_SET_WAVE and TMC_SET_STEP respectively. This allows to print the [prusa e-corr test tower](https://github.com/prusa3d/Prusa3D-Test-Objects/blob/master/MK3/ECOR_TOWER/PLA_MK3_ECOR_TOWER.gcode) gcode wihtout any modifications. the proven constant torque algorithm from Prusa firmware, providing identical functionality and G-code compatibility for seamless migration from Marlin-based systems.


## Constant Torque Algorithm

The plugin generates optimized wave tables where torque output remains constant across all microstep positions:

```
|A|² + |B|² = constant
```

Where A and B represent the two-phase current values.

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

- **linearity_factor**: Correction can be set in the range (1.0-1.2)

## G-code Commands

### TMC_SET_WAVE - Runtime Linearity Adjustment

```gcode
TMC_SET_WAVE_X100    # Set X-axis to factor 1.1
TMC_SET_WAVE_Y200    # Set Y-axis to factor 1.2
TMC_SET_WAVE_E0      # Set extruder to factor 1.0 (disable)
```

**Available factor offsets**: 0, 10, 20, 30, ..., 190, 200 (steps of 10)

### TMC_SET_STEP - Precise Stepper Positioning

```gcode
TMC_SET_STEP_X128    # Move X-axis to microstep position 128
TMC_SET_STEP_Y0      # Move Y-axis to microstep position 0
TMC_SET_STEP_E1000   # Move extruder to microstep position 1000
```

**Available step positions**: 0, 2, 4, 6, ..., 1048, 1050 (steps of 2)
- Range: 0-1050 (automatically masked to microstep resolution)
