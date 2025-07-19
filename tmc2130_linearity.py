# TMC2130 Linearity Correction Plugin for Klipper
#
# Corrects TMC2130 stepper driver non-linearities that cause salmon skin artifacts
# and dimensional inaccuracies in 3D prints.
#
# The TMC2130's MSLUT sine wave table has inherent non-linearities causing uneven
# torque distribution across microsteps. This results in periodic step size variations
# that manifest as surface artifacts and dimensional errors.
#
# Features:
# - Constant torque wave table generation
# - Runtime linearity adjustment via G-code
# - Precise stepper positioning for calibration
# - Prusa firmware algorithm compatibility
#
# Implementation matches Prusa firmware's tmc2130_goto_step for seamless migration
# from Marlin-based systems.
#
# G-code syntax: TMC_SET_WAVE_X200 sets X axis to factor 1.2
#
# Copyright (C) 2024 Petr Vyleta <pvyleta+pure@purestorage.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import math
import logging

# Constants from Prusa firmware
AMPLITUDE = 248  # Max amplitude per AN-026
SIN0 = 0  # Starting sine value

# Factor limits (internal format: 1000 = 1.0, 1200 = 1.2)
MIN_LINEARITY_FACTOR = 1000  # 1.0 (no correction)
MAX_LINEARITY_FACTOR = 1200  # 1.2 (maximum recommended correction)

# Axis mapping for G-code commands
AXIS_MAPPING = {
    'stepper_x': 'X',
    'stepper_y': 'Y',
    'stepper_z': 'Z',
    'extruder': 'E'
}

class TMC2130LinearityCorrection:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name().split(None, 1)[-1]

        # Locate corresponding TMC2130 driver section
        self.tmc_section_name = f"tmc2130 {self.name}"
        if not config.has_section(self.tmc_section_name):
            raise config.error(
                f"Could not find TMC2130 driver config section '[{self.tmc_section_name}]' "
                f"required by TMC2130 linearity correction"
            )

        # Parse linearity factor (accept 1.0-1.2, convert to 1000-1200)
        linearity_factor_float = config.getfloat(
            'linearity_factor',
            default=1.0,
            minval=1.0,
            maxval=1.2
        )
        self.linearity_factor = int(linearity_factor_float * 1000)

        # TMC driver object (set during connect)
        self.tmc_object = None
        self.stepper_object = None
        self.step_pin = None
        self.dir_pin = None
        self.current_direction = None

        # Register event handlers
        self.printer.register_event_handler("klippy:connect", self.handle_connect)
        self.printer.register_event_handler("klippy:ready", self.handle_ready)

        # Register individual Prusa-style G-code commands for exact compatibility
        gcode = self.printer.lookup_object("gcode")

        # Get axis letter for command names
        axis_letter = AXIS_MAPPING.get(self.name, self.name.upper())

        # Register TMC_SET_WAVE commands: TMC_SET_WAVE_E0, TMC_SET_WAVE_E10, ..., TMC_SET_WAVE_E200
        for factor_offset in range(0, 201, 10):  # 0, 10, 20, ..., 200
            cmd_name = f"TMC_SET_WAVE_{axis_letter}{factor_offset}"
            gcode.register_command(
                cmd_name,
                lambda gcmd, offset=factor_offset: self._cmd_set_wave_with_offset(gcmd, offset),
                desc=f"Set TMC2130 linearity factor to {1.0 + factor_offset/1000:.3f}"
            )

        # Register TMC_SET_STEP commands: TMC_SET_STEP_E0, TMC_SET_STEP_E2, ..., TMC_SET_STEP_E1050
        for step_pos in range(0, 1051, 2):  # 0, 2, 4, ..., 1050
            cmd_name = f"TMC_SET_STEP_{axis_letter}{step_pos}"
            gcode.register_command(
                cmd_name,
                lambda gcmd, step=step_pos: self._cmd_set_step_with_position(gcmd, step),
                desc=f"Move TMC2130 to microstep position {step_pos}"
            )
    
    def handle_connect(self):
        """Called when Klipper connects to MCU"""
        try:
            self.tmc_object = self.printer.lookup_object(self.tmc_section_name)
        except Exception:
            raise self.printer.config_error(
                f"Could not find TMC2130 driver object '{self.tmc_section_name}' "
                f"required by TMC2130 linearity correction"
            )

        # Try to find stepper object and extract pin info
        try:
            self.stepper_object = self.printer.lookup_object(self.name)
            self._detect_stepper_pins()
        except Exception as e:
            logging.warning(f"Could not detect stepper pins for {self.name}: {e}")
            # Non-fatal - TMC_SET_STEP will log instead of moving

    def _detect_stepper_pins(self):
        """Detect step and dir pins from stepper configuration"""
        try:
            # Get pin configuration from stepper config
            stepper_config = self._get_stepper_config()
            if not stepper_config:
                logging.warning(f"No stepper config found for {self.name}")
                return

            # Get pins object for pin creation
            ppins = self.printer.lookup_object('pins')

            # Read step pin configuration
            step_pin_name = stepper_config.get('step_pin', None)
            if step_pin_name:
                try:
                    # Create step pin object
                    step_pin_params = ppins.lookup_pin(step_pin_name, can_invert=True)
                    self.step_pin = step_pin_params['chip'].setup_pin('digital_out', step_pin_params)
                    self.step_pin.setup_max_duration(0.)  # No timeout
                    logging.info(f"Created step pin for {self.name}: {step_pin_name}")
                except Exception as e:
                    logging.warning(f"Failed to create step pin for {self.name}: {e}")

            # Read dir pin configuration
            dir_pin_name = stepper_config.get('dir_pin', None)
            if dir_pin_name:
                try:
                    # Create dir pin object
                    dir_pin_params = ppins.lookup_pin(dir_pin_name, can_invert=True)
                    self.dir_pin = dir_pin_params['chip'].setup_pin('digital_out', dir_pin_params)
                    self.dir_pin.setup_max_duration(0.)  # No timeout
                    logging.info(f"Created dir pin for {self.name}: {dir_pin_name}")
                except Exception as e:
                    logging.warning(f"Failed to create dir pin for {self.name}: {e}")

            # Initialize direction state
            self.current_direction = None

            if self.step_pin and self.dir_pin:
                logging.info(f"Pin control enabled for {self.name}")
            else:
                logging.info(f"Pin control disabled for {self.name} - algorithm will calculate movements only")

        except Exception as e:
            logging.warning(f"Failed to detect pins for {self.name}: {e}")
            # Pin control will be disabled, but calculations will still work
            self.step_pin = None
            self.dir_pin = None
            self.current_direction = None

    def _get_stepper_config(self):
        """Get stepper configuration from Klipper config"""
        try:
            # Get the config file object
            config_file = self.printer.lookup_object('configfile')

            # Access the config sections through the proper API
            if hasattr(config_file, 'get_status'):
                # Try to get config status which contains sections
                status = config_file.get_status()
                if 'settings' in status:
                    sections = status['settings']
                else:
                    logging.warning(f"No settings found in config status for {self.name}")
                    return None
            else:
                logging.warning(f"Config file object has no get_status method for {self.name}")
                return None

            # Look for stepper section matching our name
            stepper_section_name = self.name
            if stepper_section_name in sections:
                return sections[stepper_section_name]

            # Try alternative naming patterns
            alt_names = [
                f"stepper_{self.name}",
                f"stepper {self.name}",
            ]

            for alt_name in alt_names:
                if alt_name in sections:
                    return sections[alt_name]

            logging.warning(f"No stepper config section found for {self.name}")
            return None

        except Exception as e:
            logging.warning(f"Failed to get stepper config for {self.name}: {e}")
            return None

    def handle_ready(self):
        """Called when Klipper is ready"""
        # Apply initial configuration
        self.printer.reactor.register_callback(self._apply_initial_config)
    
    def _apply_initial_config(self, eventtime):
        """Apply the initial linearity correction configuration"""
        try:
            self._apply_linearity_correction()
            logging.info(
                f"TMC2130 linearity correction initialized for {self.name}: "
                f"factor={self.linearity_factor/1000.0:.3f}, "
                f"amplitude={AMPLITUDE}, sin0={SIN0}"
            )
        except Exception as e:
            logging.error(f"Failed to apply TMC2130 linearity correction for {self.name}: {e}")
    
    def _apply_linearity_correction(self):
        """Apply constant torque linearity correction to the TMC2130 driver"""
        if not self.tmc_object:
            raise RuntimeError("TMC2130 driver object not available")

        logging.info(
            f"Applying TMC2130 constant torque wave for {self.name}: "
            f"amplitude={AMPLITUDE}, sin0={SIN0}, "
            f"linearity_factor={self.linearity_factor} (factor={self.linearity_factor/1000.0:.3f})"
        )

        try:
            # Generate the constant torque wave table
            wave_table = self._generate_constant_torque_wave()

            # Write the wave table to TMC2130 registers
            self._write_wave_table(wave_table)

            logging.info(f"Successfully applied linearity correction to {self.name}")

        except Exception as e:
            logging.error(f"Failed to write TMC2130 registers for {self.name}: {e}")
            raise

    def _tmc2130_calc_constant_torque_value(self, i, va, fac, tcorr, carry, prev_theoretical_value):
        """
        Prusa's tmc2130_calc_constant_torque_value function
        Lines 1065-1140 in tmc2130.cpp
        """
        # Constants
        SIN0 = 0
        AMP = 248  # Amplitude limit as per AN-026 recommendation
        TARGET_MAGNITUDE_SQUARED = float(AMP * AMP + SIN0 * SIN0)

        # Calculate theoretical constant torque value at position i
        if i < 128:
            # Phase 1 (0-127): Power-corrected sine curve
            sin_val = math.sin(math.pi * float(i) / 512.0)
            theoretical_value = (AMP - SIN0) * pow(sin_val, fac) * tcorr + SIN0
        else:
            # Phase 2 (128-255): Constant torque constraint solving
            # For constant torque: |A(i)|² + |B(i)|² = TARGET_MAGNITUDE_SQUARED
            # Since B(i) = A(255-i), solve: |A(i)|² + |A(255-i)|² = TARGET_MAGNITUDE_SQUARED
            # Therefore: A(i) = sqrt(TARGET_MAGNITUDE_SQUARED - A(255-i)²)

            # Calculate mirror position value from Phase 1 curve
            mirror_i = 255 - i
            sin_val = math.sin(math.pi * float(mirror_i) / 512.0)
            mirror_theoretical = (AMP - SIN0) * pow(sin_val, fac) * tcorr + SIN0

            # Apply constant torque constraint
            theoretical_value = math.sqrt(TARGET_MAGNITUDE_SQUARED - mirror_theoretical * mirror_theoretical)

        # Apply carry mechanism and initial quantization
        # Carry compensates for accumulated rounding errors
        adjusted_theoretical = theoretical_value - carry[0]
        candidate_value = int(adjusted_theoretical + 0.5)

        # Slope-based delta limiting for TMC2130 compression
        # Calculate slope between current and previous theoretical values
        slope = theoretical_value - prev_theoretical_value[0]

        # Determine allowed delta range
        # Ensures delta ranges match slope ranges for optimal compression:
        # slope ∈ [0,1) → deltas ∈ [0,1], slope ∈ [1,2) → deltas ∈ [1,2], etc.
        min_delta = int(math.floor(slope))

        # Clamp to TMC2130 hardware delta limits [-1, 3]
        # Max delta is 2 because we need range [min_delta, min_delta+1]
        if min_delta < -1:
            min_delta = -1
        elif min_delta > 2:
            min_delta = 2

        # Enforce delta limits: constrain actual delta to [min_delta, min_delta+1]
        delta = candidate_value - va
        if delta < min_delta:
            candidate_value = va + min_delta
        elif delta > min_delta + 1:
            candidate_value = va + min_delta + 1

        # Step 3: Final amplitude clamping to valid TMC2130 range
        if candidate_value < SIN0:
            candidate_value = SIN0
        elif candidate_value > AMP:
            candidate_value = AMP

        # Step 4: Update carry for next iteration
        # Carry = quantization_error = actual_output - theoretical_target
        carry[0] = candidate_value - theoretical_value

        # Update previous theoretical value for next slope calculation
        prev_theoretical_value[0] = theoretical_value

        return candidate_value

    def _generate_constant_torque_wave(self):
        """
        Prusa's constant torque wave generation
        Based on tmc2130_set_wave lines 1148-1250
        """
        # Convert linearity_factor back to actual factor value
        # Our linearity_factor is stored as int(factor * 1000), so divide by 1000 to get actual factor
        fac1000 = self.linearity_factor
        if fac1000:
            fac = float(fac1000) / 1000.0  # Convert back to actual factor (1.05, 1.1, etc.)
        else:
            fac = 1.0

        # Constant torque algorithm parameters
        carry = [0.0]  # Carry value to handle rounding adjustments (use list for reference)
        prev_theoretical_value = [0.0]  # Cache previous theoretical value for slope calculation
        tcorr = 1.0  # Pre-calculated correction factor for constant torque algorithm

        # Pre-calculate tcorr for constant torque algorithm
        SIN0 = 0
        AMP = 248  # Amplitude limit as per AD recommendation
        MIDPOINT_VALUE = 175.362481734263781  # sqrt((AMP² + SIN0²) / 2)
        SIN_127_5 = 0.704934080375905  # sin(M_PI * 127.5f / 512.0f)

        tcorr = (MIDPOINT_VALUE - SIN0) / ((AMP - SIN0) * pow(SIN_127_5, fac))

        # Generate wave table using exact Prusa algorithm
        wave_table = []
        va = 0  # previous vA

        for i in range(256):
            # Call exact Prusa constant torque calculation
            vA = self._tmc2130_calc_constant_torque_value(i, va, fac, tcorr, carry, prev_theoretical_value)
            wave_table.append(vA)
            va = vA  # Update previous value

        return wave_table

    def _write_wave_table(self, wave_table):
        """
        Prusa's tmc2130_set_wave compression algorithm
        Lines 1190-1250 in tmc2130.cpp
        """
        if not self.tmc_object:
            raise RuntimeError("TMC2130 driver object not available")

        logging.info(f"TMC2130 {self.name}: Writing wave table with exact Prusa compression")

        # Log sample wave values for debugging
        sample_values = [wave_table[i] for i in [0, 32, 64, 96, 127, 128, 160, 192, 224, 255]]
        logging.info(f"TMC2130 {self.name}: Sample wave values: {sample_values}")

        # Set MSLUTSTART register
        # For constant torque: tmc2130_wr_MSLUTSTART(axis, SIN0, AMP);
        SIN0 = 0
        AMP = 248
        self._set_tmc_field('start_sin', SIN0 & 0xFF)
        self._set_tmc_field('start_sin90', AMP & 0xFF)
        logging.info(f"TMC2130 {self.name}: MSLUTSTART start_sin={SIN0}, start_sin90={AMP}")

        # Initialize compression state variables
        vA = 0                      # value of currentA
        va = 0                      # previous vA
        d0 = 0                      # delta0
        d1 = 1                      # delta1
        w = [1, 1, 1, 1]           # W bits (MSLUTSEL)
        x = [255, 255, 255]        # X segment bounds (MSLUTSEL)
        s = 0                       # current segment
        b = 0                       # encoded bit value
        dA = 0                      # delta value
        i = 0                       # microstep index
        reg = 0                     # tmc2130 register

        # Main compression loop
        while True:
            if (i & 0x1f) == 0:  # Every 32 values, start new register
                reg = 0

            vA = wave_table[i]  # Get wave value (equivalent to line 1196)
            dA = vA - va        # calculate delta
            va = vA             # update previous value

            b = -1              # initialize encoded bit

            # Exact Prusa delta encoding logic
            if dA == d0:
                b = 0           # delta == delta0 => bit=0
            elif dA == d1:
                b = 1           # delta == delta1 => bit=1
            else:
                # Adaptive delta switching
                if dA < d0:     # delta < delta0 => switch wbit down
                    b = 0
                    # Exact Prusa switch cases
                    if dA == -1:
                        d0, d1 = -1, 0
                        if s+1 < 4:  # Bounds check
                            w[s+1] = 0
                    elif dA == 0:
                        d0, d1 = 0, 1
                        if s+1 < 4:  # Bounds check
                            w[s+1] = 1
                    elif dA == 1:
                        d0, d1 = 1, 2
                        if s+1 < 4:  # Bounds check
                            w[s+1] = 2
                    else:
                        b = -1  # delta out of range

                    if b >= 0 and s < 3:  # Bounds check for both x and s
                        x[s] = i    # set segment boundary
                        s += 1      # increment segment

                elif dA > d1:   # delta > delta1 => switch wbit up
                    b = 1
                    # Exact Prusa switch cases
                    if dA == 1:
                        d0, d1 = 0, 1
                        if s+1 < 4:  # Bounds check
                            w[s+1] = 1
                    elif dA == 2:
                        d0, d1 = 1, 2
                        if s+1 < 4:  # Bounds check
                            w[s+1] = 2
                    elif dA == 3:
                        d0, d1 = 2, 3
                        if s+1 < 4:  # Bounds check
                            w[s+1] = 3
                    else:
                        b = -1  # delta out of range

                    if b >= 0 and s < 3:  # Bounds check for both x and s
                        x[s] = i    # set segment boundary
                        s += 1      # increment segment

            # Check for compression failure
            if b < 0:   # delta out of range (<-1 or >3)
                break
            if s > 3:   # segment out of range (> 3)
                break

            # Exact Prusa bit encoding
            if b == 1:
                reg |= 0x80000000   # set MSB if bit=1

            if (i & 31) == 31:      # Every 32nd value, write register
                field_name = f'mslut{i >> 5}'
                self._set_tmc_field(field_name, reg)
                logging.info(f"TMC2130 {self.name}: {field_name}=0x{reg:08x}")
            else:
                reg >>= 1           # shift right

            # Increment and check loop termination
            if i == 255:
                break
            i += 1

        # Write MSLUTSEL register
        # tmc2130_wr_MSLUTSEL(axis, x[0], x[1], x[2], w[0], w[1], w[2], w[3]);
        self._set_tmc_field('w0', w[0])
        self._set_tmc_field('w1', w[1])
        self._set_tmc_field('w2', w[2])
        self._set_tmc_field('w3', w[3])
        self._set_tmc_field('x1', x[0])
        self._set_tmc_field('x2', x[1])
        self._set_tmc_field('x3', x[2])

        logging.info(f"TMC2130 {self.name}: MSLUTSEL w=[{w[0]},{w[1]},{w[2]},{w[3]}] x=[{x[0]},{x[1]},{x[2]}]")
        logging.info(f"TMC2130 {self.name}: Exact Prusa compression completed")

    def _set_tmc_field(self, field_name, value):
        """Set a TMC2130 register field using Klipper's TMC interface"""
        try:
            # Look up the register for this field
            register = self.tmc_object.fields.lookup_register(field_name, None)
            if register is None:
                logging.warning(f"TMC2130 field '{field_name}' not found for {self.name}")
                return

            # Set the field value and write to register
            logging.debug(f"Setting TMC2130 {self.name} {field_name} = 0x{value:08x}")
            val = self.tmc_object.fields.set_field(field_name, value)
            self.tmc_object.mcu_tmc.set_register(register, val, None)

        except Exception as e:
            logging.error(f"Failed to set TMC2130 field {field_name} for {self.name}: {e}")
            raise

    def _cmd_set_wave_with_offset(self, gcmd, factor_offset):
        """Handle individual TMC_SET_WAVE_X### commands"""
        try:
            # Convert offset to linearity factor (0-200 -> 1000-1200)
            self.linearity_factor = 1000 + factor_offset

            # Apply the new linearity correction
            self._apply_linearity_correction()

            gcmd.respond_info(
                f"TMC2130 linearity factor for {self.name} set to {self.linearity_factor/1000.0:.3f} "
                f"(offset: {factor_offset})"
            )

        except Exception as e:
            gcmd.respond_info(f"Failed to set linearity factor: {e}")

    def _cmd_set_step_with_position(self, gcmd, target_step):
        """Handle individual TMC_SET_STEP_X### commands"""
        try:
            # Get current microstep resolution
            microstep_resolution = self._get_microstep_resolution()

            # Mask step position to valid range (4 * resolution - 1)
            max_step = 4 * microstep_resolution - 1
            masked_step = target_step & max_step

            # Move to target step position (matches Prusa: dir=2, delay_us=1000)
            self._goto_step(masked_step, microstep_resolution, delay_us=1000)

            gcmd.respond_info(
                f"TMC2130 {self.name} moved to microstep position {masked_step} "
                f"(requested: {target_step}, resolution: {microstep_resolution})"
            )

        except Exception as e:
            gcmd.respond_info(f"Failed to move to step position: {e}")

    def _get_microstep_resolution(self):
        """Get current microstep resolution from TMC2130 (matches tmc2130_get_res)"""
        try:
            # Read MRES field from CHOPCONF register
            mres = self._get_tmc_field('mres')
            if mres is None:
                # Default to 256 microsteps if we can't read it
                return 256

            # Convert MRES to microsteps: microsteps = 256 >> mres
            # This matches tmc2130_mres2usteps() in Prusa firmware
            microsteps = 256 >> mres
            return microsteps

        except Exception as e:
            logging.warning(f"Failed to read microstep resolution for {self.name}: {e}")
            return 256  # Default fallback

    def _get_current_step_position(self):
        """Get current microstep position from TMC2130 MSCNT register"""
        try:
            # Read MSCNT field which contains current microstep position
            mscnt = self._get_tmc_field('mscnt')
            if mscnt is None:
                raise RuntimeError("Could not read MSCNT register")

            # MSCNT is 10-bit value (0-1023), convert to 8-bit step position (0-255)
            step_position = (mscnt >> 2) & 0xFF
            return step_position

        except Exception as e:
            logging.warning(f"Failed to read current step position for {self.name}: {e}")
            raise

    def _get_tmc_register(self, register_name):
        """Get a TMC2130 register value using Klipper's TMC interface"""
        try:
            if not self.tmc_object:
                return None

            # Use Klipper's TMC interface to read register
            # This handles the SPI communication properly
            if hasattr(self.tmc_object, 'get_register'):
                return self.tmc_object.get_register(register_name)
            elif hasattr(self.tmc_object, 'mcu_tmc'):
                return self.tmc_object.mcu_tmc.get_register(register_name)
            else:
                logging.warning(f"No register access method found for {self.name}")
                return None

        except Exception as e:
            logging.warning(f"Failed to get TMC2130 register {register_name} for {self.name}: {e}")
            return None

    def _get_tmc_field(self, field_name):
        """Get a TMC2130 register field value using Klipper's TMC interface"""
        try:
            if not self.tmc_object:
                return None

            # Use Klipper's TMC field interface
            if hasattr(self.tmc_object, 'get_field'):
                return self.tmc_object.get_field(field_name)
            elif hasattr(self.tmc_object, 'fields'):
                # Get current register values and extract field
                register_name = self.tmc_object.fields.lookup_register(field_name, None)
                if register_name is None:
                    return None

                # Get register value
                reg_value = self._get_tmc_register(register_name)
                if reg_value is None:
                    return None

                # Extract field value
                return self.tmc_object.fields.get_field(field_name, reg_value)
            else:
                logging.warning(f"No field access method found for {self.name}")
                return None

        except Exception as e:
            logging.warning(f"Failed to get TMC2130 field {field_name} for {self.name}: {e}")
            return None

    def _goto_step(self, target_step, microstep_resolution, delay_us=1000):
        """Move TMC2130 to specific microstep position (equivalent to tmc2130_goto_step)

        This method implements the exact algorithm from Prusa firmware's tmc2130_goto_step
        function. It's critical for calibration and testing because it allows precise
        positioning of the stepper motor to specific microstep positions.

        The algorithm uses auto-direction mode (dir=2) to automatically choose the
        shortest path to the target position, which minimizes movement time and
        reduces the chance of losing steps during positioning.
        """
        if not self.tmc_object:
            raise RuntimeError("TMC2130 driver object not available")

        try:
            # Read current microstep counter (MSCNT register) - matches tmc2130_rd_MSCNT
            mscnt_reg = self._get_tmc_register('MSCNT')
            if mscnt_reg is None:
                raise RuntimeError("Failed to read MSCNT register")

            # Apply mask like Prusa firmware: return val32 & 0x3ff
            mscnt = mscnt_reg & 0x3ff

            # Calculate shift based on microstep resolution - matches Prusa algorithm
            shift = 0
            for shift in range(8):
                if microstep_resolution == (256 >> shift):
                    break

            # Calculate total steps in full cycle - matches Prusa: cnt = 4 * (1 << (8 - shift))
            cnt = 4 * (1 << (8 - shift))

            # Implement Prusa's dir=2 auto-direction algorithm             # This matches lines 990-1004 in tmc2130_goto_step
            dir = 2  # Auto-direction mode (matches Prusa default)

            if dir == 2:
                # Get axis inversion setting (matches: dir = tmc2130_get_inv(axis)?0:1)
                axis_inverted = self._get_axis_inversion()
                dir = 0 if axis_inverted else 1

                # Calculate steps needed (matches: int steps = (int)step - (int)(mscnt >> shift))
                steps = target_step - (mscnt >> shift)

                # Choose shortest path with direction flipping (matches Prusa )
                # Note: Prusa uses static_cast<int>(cnt / 2) which is integer division
                if steps > (cnt // 2):
                    dir ^= 1  # XOR flip direction (matches: dir ^= 1)
                    steps = cnt - steps  # This can create negative value (matches comment)

                if steps < 0:
                    dir ^= 1  # XOR flip direction again (matches: dir ^= 1)
                    steps = -steps  # Make positive (matches: steps = -steps)

                # cnt becomes the number of steps to move (matches: cnt = steps)
                cnt = steps

            if cnt == 0:
                logging.info(f"TMC2130 {self.name} already at target step {target_step}")
                return

            logging.info(
                f"TMC2130 {self.name}: mscnt={mscnt}, current_step={mscnt >> shift}, "
                f"target_step={target_step}, steps_to_move={cnt}, direction={dir}, shift={shift}"
            )

            # Perform actual stepper movement using Klipper's force_move system
            try:
                self._perform_force_move_steps(cnt, dir, microstep_resolution)
                logging.info(f"TMC2130 {self.name}: Successfully moved {cnt} steps (dir={dir})")
            except Exception as e:
                logging.error(f"TMC2130 {self.name}: Failed to perform movement: {e}")
                raise

        except Exception as e:
            logging.error(f"Failed to move TMC2130 {self.name} to step {target_step}: {e}")
            raise

    def _perform_force_move_steps(self, steps, direction, microstep_resolution):
        """Perform stepper movement using direct pin control (matches Prusa )"""
        try:
            logging.info(
                f"TMC2130 {self.name}: Performing {steps} steps, direction={direction}, "
                f"using direct pin control (Prusa-compatible)"
            )

            # Check if we have pin access for direct control
            if not self.step_pin or not self.dir_pin:
                logging.warning(
                    f"TMC2130 {self.name}: No pin access available, skipping step movement. "
                    f"step_pin={self.step_pin}, dir_pin={self.dir_pin}"
                )
                return

            # Get toolhead for timing
            toolhead = self.printer.lookup_object('toolhead')
            print_time = toolhead.get_last_move_time()

            # Set direction pin first (matches Prusa: tmc2130_set_dir)
            self._set_dir_pin_direct(direction, print_time)
            print_time += 0.000001  # 1μs delay after direction change

            # Perform steps using direct pin control (matches Prusa: tmc2130_do_step)
            step_delay = 1000  # microseconds (matches Prusa default delay)
            step_interval = step_delay / 1000000.0  # Convert to seconds

            for step in range(steps):
                # Execute single step pulse (matches Prusa: _DO_STEP_X macros)
                self._execute_step_pulse_direct(print_time)
                print_time += step_interval

                # Log progress for debugging
                if step < 5 or step % 10 == 0 or step >= steps - 5:
                    logging.debug(f"TMC2130 {self.name}: Step {step + 1}/{steps} executed")

            # Update toolhead timing to account for all steps
            toolhead.note_kinematic_activity(print_time)

            logging.info(
                f"TMC2130 {self.name}: Completed {steps} direct pin steps, "
                f"direction={direction}, total_time={steps * step_interval:.6f}s"
            )

        except Exception as e:
            logging.error(f"Failed to perform direct pin steps for {self.name}: {e}")
            raise

    def _get_axis_inversion(self):
        """Get axis inversion setting (matches tmc2130_get_inv)"""
        try:
            # Get stepper configuration
            stepper_config = self._get_stepper_config()
            if not stepper_config:
                return False

            # Check dir_pin for inversion (! prefix)
            dir_pin_name = stepper_config.get('dir_pin', '')
            if dir_pin_name.startswith('!'):
                return True

            return False
        except Exception:
            return False

    def _get_current_direction(self):
        """Get current direction setting (matches tmc2130_get_dir)"""
        # Return stored direction state
        return self.current_direction if self.current_direction is not None else 0

    def _do_steps_with_verification(self, steps, direction, target_step, shift, delay_us):
        """Perform steps with position verification (matches Prusa while loop)"""
        try:
            # Set direction (matches Prusa line 1006: tmc2130_set_dir(axis, dir))
            self._set_dir_pin(direction)

            # Re-read MSCNT after direction change (matches Prusa line 1007)
            mscnt_reg = self._get_tmc_register('MSCNT')
            if mscnt_reg is None:
                raise RuntimeError("Failed to read MSCNT register after direction change")
            mscnt = mscnt_reg & 0x3ff

            # Get toolhead for timing
            toolhead = self.printer.lookup_object('toolhead')
            print_time = toolhead.get_last_move_time()

            # Add direction setup delay (matches TMC2130_SET_DIR_DELAY)
            print_time += 0.000001  # 1 microsecond

            # Implement Prusa's step-by-step verification loop
            # while ((cnt--) && ((mscnt >> shift) != step))

            if self.step_pin and self.dir_pin:
                # Real pin control: implement true step-by-step verification
                self._execute_steps_with_real_verification(steps, target_step, shift, delay_us, print_time)
            else:
                # Simulation mode: calculate what would happen
                cnt = steps
                step_interval = delay_us / 1000000.0  # Convert microseconds to seconds

                current_time = print_time
                steps_taken = 0

                # Simulate the Prusa while loop
                while cnt > 0 and (mscnt >> shift) != target_step:
                    steps_taken += 1
                    cnt -= 1

                    # In real hardware, we would read MSCNT here
                    # For simulation, we assume perfect stepping
                    current_position = (mscnt >> shift) + steps_taken
                    if current_position >= target_step:
                        break

                # Schedule final verification
                verify_time = current_time + (steps_taken * step_interval) + 0.001
                self.printer.reactor.register_callback(
                    lambda eventtime: self._verify_final_position(target_step, shift, steps_taken)
                )

                # Update toolhead timing
                toolhead.note_kinematic_activity(verify_time)

                logging.info(f"TMC2130 {self.name}: Simulated {steps_taken} steps, direction={direction}")

        except Exception as e:
            logging.error(f"Failed to perform verified steps for {self.name}: {e}")
            raise

    def _execute_steps_with_real_verification(self, steps, target_step, shift, delay_us, start_time):
        """Execute steps with real hardware verification (matches Prusa )"""
        try:
            cnt = steps
            step_interval = delay_us / 1000000.0
            current_time = start_time
            steps_taken = 0

            # This would be the real implementation matching Prusa's while loop:
            # while ((cnt--) && ((mscnt >> shift) != step))
            while cnt > 0:
                # Read current MSCNT (matches: mscnt = tmc2130_rd_MSCNT(axis))
                mscnt_reg = self._get_tmc_register('MSCNT')
                if mscnt_reg is not None:
                    mscnt = mscnt_reg & 0x3ff
                    if (mscnt >> shift) == target_step:
                        break  # Target reached

                # Execute step (matches: tmc2130_do_step(axis))
                self._execute_step_pulse_direct(current_time)
                current_time += step_interval
                steps_taken += 1
                cnt -= 1

                # Add delay (matches: delayMicroseconds(delay_us))
                # Note: In Klipper, this is handled by the step_interval timing

            # Schedule final verification
            verify_time = current_time + 0.001
            self.printer.reactor.register_callback(
                lambda eventtime: self._verify_final_position(target_step, shift, steps_taken)
            )

            # Update toolhead timing
            toolhead = self.printer.lookup_object('toolhead')
            toolhead.note_kinematic_activity(verify_time)

            logging.info(f"TMC2130 {self.name}: Executed {steps_taken} real steps, direction={self.current_direction}")

        except Exception as e:
            logging.error(f"Failed to execute real steps for {self.name}: {e}")
            raise

    def _verify_final_position(self, target_step, shift, steps_sent):
        """Verify final position after steps complete"""
        try:
            # Read MSCNT to verify position
            mscnt_reg = self._get_tmc_register('MSCNT')
            if mscnt_reg is not None:
                mscnt = mscnt_reg & 0x3ff
                final_position = mscnt >> shift

                logging.info(
                    f"TMC2130 {self.name}: Sent {steps_sent} steps, "
                    f"final_position={final_position}, target={target_step}"
                )

                if final_position != target_step:
                    logging.warning(
                        f"TMC2130 {self.name}: Position verification failed - "
                        f"target={target_step}, actual={final_position}"
                    )
            else:
                logging.warning(f"TMC2130 {self.name}: Could not verify final position")

        except Exception as e:
            logging.error(f"Failed to verify position for {self.name}: {e}")



    def _set_dir_pin_direct(self, direction, print_time):
        """Set direction pin directly (matches tmc2130_set_dir and _SET_DIR_X macros)"""
        try:
            if not self.dir_pin:
                logging.warning(f"Direction pin not available for {self.name}")
                return

            # Apply direction inversion (matches _SET_DIR_X macros)
            # Prusa: WRITE(X_DIR_PIN, dir?INVERT_X_DIR:!INVERT_X_DIR)
            axis_inverted = self._get_axis_inversion()
            actual_direction = direction if not axis_inverted else (1 - direction)

            # Schedule direction pin change (matches Prusa: always set, no check)
            self.dir_pin.set_digital(print_time, actual_direction)

            # Store current direction
            self.current_direction = direction

            logging.debug(f"Set direction pin for {self.name}: {direction} (actual: {actual_direction})")

        except Exception as e:
            logging.error(f"Failed to set direction pin for {self.name}: {e}")
            raise

    def _execute_step_pulse_direct(self, print_time):
        """Execute a single step pulse directly (matches _DO_STEP_X macros)"""
        try:
            if not self.step_pin:
                logging.warning(f"Step pin not available for {self.name}")
                return

            # Get step pin inversion setting
            step_inverted = self._get_step_pin_inversion()

            # Calculate pulse levels (matches _DO_STEP_X macros)
            # Prusa: WRITE(X_STEP_PIN, !INVERT_X_STEP_PIN); TMC2130_MINIMUM_DELAY; WRITE(X_STEP_PIN, INVERT_X_STEP_PIN);
            active_level = 0 if step_inverted else 1
            inactive_level = 1 if step_inverted else 0

            # Schedule step pulse: active -> inactive with proper timing
            # Matches Prusa TMC2130_MINIMUM_DELAY (1μs minimum pulse width)
            pulse_width = 0.000001  # 1 microsecond

            self.step_pin.set_digital(print_time, active_level)  # Step active
            self.step_pin.set_digital(print_time + pulse_width, inactive_level)  # Step inactive

            logging.debug(f"Step pulse executed for {self.name} at {print_time}")

        except Exception as e:
            logging.error(f"Failed to execute step pulse for {self.name}: {e}")
            raise

    def _set_dir_pin(self, direction):
        """Set direction pin (legacy method for compatibility)"""
        try:
            toolhead = self.printer.lookup_object('toolhead')
            print_time = toolhead.get_last_move_time()
            self._set_dir_pin_direct(direction, print_time)
        except Exception as e:
            logging.error(f"Failed to set direction pin for {self.name}: {e}")
            raise



    def _get_step_pin_inversion(self):
        """Get step pin inversion setting"""
        try:
            # Get stepper configuration
            stepper_config = self._get_stepper_config()
            if not stepper_config:
                return False

            # Check step_pin for inversion (! prefix)
            step_pin_name = stepper_config.get('step_pin', '')
            if step_pin_name.startswith('!'):
                return True

            return False
        except Exception:
            return False

def load_config_prefix(config):
    """Load configuration for TMC2130 linearity correction"""
    return TMC2130LinearityCorrection(config)
