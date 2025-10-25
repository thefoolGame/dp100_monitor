"""DP100 device interface using HID communication."""

import hid
import time
import crcmod
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

from ..utils.logger import get_logger


@dataclass
class DP100Status:
    """DP100 device status information."""
    voltage_set: float
    current_set: float
    voltage_out: float
    current_out: float
    power_out: float
    output_enabled: bool
    temperature: float
    mode: str


class DP100Interface:
    """Interface for communicating with Alientek DP100 power supply."""
    
    # DP100 USB identifiers
    VENDOR_ID = 0x2E3C
    PRODUCT_ID = 0xAF01
    
    # Protocol constants (based on pydp100)
    DR_H2D = 0xFB  # Direction: Host to Device
    DR_D2H = 0xFA  # Direction: Device to Host
    OP_BASICINFO = 0x30  # Basic info command
    OP_BASICSET = 0x35   # Basic set command for voltage/current/output
    SET_MODIFY = 0x01    # Set modify flag
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize DP100 interface.
        
        Args:
            config: Device configuration
        """
        self.config = config['device']
        self.logger = get_logger('device.interface')
        
        self.device: Optional[hid.device] = None
        self.connected = False
        self.last_status: Optional[DP100Status] = None
        
        # Current settings (tracked locally)
        self.current_voltage_set = 0  # millivolts
        self.current_current_set = 1000  # milliamps (1A default)
        self.output_enabled = False
        
        # Communication settings
        self.timeout_ms = self.config.get('usb_timeout', 1000)
        self.retry_attempts = self.config.get('reconnect_attempts', 5)
        self.retry_delay = self.config.get('reconnect_delay', 2.0)
        
        # CRC calculation for protocol
        self.crc16 = crcmod.mkCrcFun(0x18005, rev=True, initCrc=0xFFFF, xorOut=0x0000)
    
    def connect(self) -> bool:
        """
        Connect to DP100 device.
        
        Returns:
            True if connection successful
        """
        if self.connected:
            return True
        
        try:
            # Try to open the device
            self.device = hid.device()
            self.device.open(self.VENDOR_ID, self.PRODUCT_ID)
            
            # Set non-blocking mode with timeout
            self.device.set_nonblocking(1)
            
            # Set connected to True temporarily for testing
            self.connected = True
            
            # Test communication
            if self._test_communication():
                self.logger.info("Connected to DP100 successfully")
                return True
            else:
                self.disconnect()
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to connect to DP100: {e}", exc_info=True)
            self.disconnect()
            return False
    
    def disconnect(self) -> None:
        """Disconnect from DP100 device."""
        if self.device:
            try:
                self.device.close()
            except Exception as e:
                self.logger.warning(f"Error closing device: {e}")
            finally:
                self.device = None
        
        self.connected = False
        self.logger.info("Disconnected from DP100")
    
    def _test_communication(self) -> bool:
        """
        Test communication with device.
        
        Returns:
            True if communication works
        """
        try:
            self.logger.debug("Testing communication with DP100...")
            status = self.get_status()
            if status is not None:
                self.logger.debug("Communication test successful")
                return True
            else:
                self.logger.error("Communication test failed: get_status returned None")
                return False
        except Exception as e:
            self.logger.error(f"Communication test failed: {e}", exc_info=True)
            return False
    
    def _gen_frame(self, op_code: int, data: bytes = b'') -> bytes:
        """
        Generate proper DP100 frame with CRC.
        
        Args:
            op_code: Operation code
            data: Optional data bytes
            
        Returns:
            Complete frame with CRC
        """
        frame = bytes([self.DR_H2D, op_code & 0xFF, 0x0, len(data) & 0xFF]) + data
        crc = self.crc16(frame)
        return frame + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    
    def _send_frame(self, op_code: int, data: bytes = b'') -> Optional[bytes]:
        """
        Send properly formatted frame to DP100.
        
        Args:
            op_code: Operation code
            data: Optional data bytes
            
        Returns:
            Response bytes or None if failed
        """
        if not self.connected or not self.device:
            self.logger.error("Not connected or device is None")
            return None
        
        try:
            # Generate frame with CRC
            frame = self._gen_frame(op_code, data)
            
            # Prepare 64-byte HID packet
            packet = bytearray(64)
            frame_len = min(len(frame), 64)
            packet[:frame_len] = frame[:frame_len]
            
            # Debug: log the frame being sent
            frame_hex = ' '.join(f'{b:02x}' for b in frame)
            self.logger.debug(f"Sending frame op=0x{op_code:02x}: {frame_hex}")
            
            # Send packet
            bytes_written = self.device.write(packet)
            self.logger.debug(f"Wrote {bytes_written} bytes")
            
            # Read response with timeout
            time.sleep(0.05)  # Small delay as in pydp100
            response = self.device.read(64)
            
            if response:
                response_bytes = bytes(response)
                response_hex = ' '.join(f'{b:02x}' for b in response_bytes[:16])
                self.logger.debug(f"Received response: {response_hex}...")
                return response_bytes
            else:
                self.logger.warning("No response received")
                return None
            
        except Exception as e:
            self.logger.error(f"Frame communication error: {e}", exc_info=True)
            return None
    
    def get_status(self) -> Optional[DP100Status]:
        """
        Get current device status using correct DP100 protocol.
        
        Returns:
            DP100Status object or None if failed
        """
        response = self._send_frame(self.OP_BASICINFO)
        if not response or len(response) < 11:
            return None
        
        try:
            # Check response header
            if response[0] != self.DR_D2H:
                self.logger.warning(f"Unexpected response header: 0x{response[0]:02x}")
                return None
            
            # Debug: log the full response for analysis
            response_hex = ' '.join(f'{b:02x}' for b in response[:16])
            self.logger.debug(f"Status response: {response_hex}")
            
            # Parse values using CORRECT protocol positions found by analysis
            # Current output: bytes 8-9 (little-endian, milliamps)
            current_out = ((response[9] << 8) | response[8]) / 1000.0
            
            # Voltage output: bytes 10-11 (little-endian, millivolts)  
            voltage_out = ((response[11] << 8) | response[10]) / 1000.0
            
            # Temperature: try bytes 12-13 (might be different position)
            if len(response) > 13:
                temperature = ((response[13] << 8) | response[12]) / 10.0
            else:
                temperature = 25.0  # Default
            
            # Calculate power
            power_out = voltage_out * current_out
            
            # Use tracked set values
            voltage_set = self.current_voltage_set / 1000.0  # Convert from mV to V
            current_set = self.current_current_set / 1000.0  # Convert from mA to A
            
            # Parse status flags (if available in response)
            output_enabled = current_out > 0.001  # Assume output is on if current flows
            
            self.logger.debug(f"Parsed: V={voltage_out:.3f}V, I={current_out:.3f}A, P={power_out:.3f}W, T={temperature:.1f}°C")
            
            status = DP100Status(
                voltage_set=voltage_set,
                current_set=current_set,
                voltage_out=voltage_out,
                current_out=current_out,
                power_out=power_out,
                output_enabled=output_enabled,
                temperature=temperature,
                mode="Normal"  # Placeholder
            )
            
            self.last_status = status
            return status
            
        except Exception as e:
            self.logger.error(f"Failed to parse status response: {e}")
            return None
    
    def _gen_set(self, output: bool = False, vset: int = 0, iset: int = 0, 
                 ovp: int = 30500, ocp: int = 5050) -> bytes:
        """
        Generate set command data (based on pydp100).
        
        Args:
            output: Output enable state
            vset: Voltage setting in millivolts
            iset: Current setting in milliamps
            ovp: Over-voltage protection in millivolts
            ocp: Over-current protection in milliamps
            
        Returns:
            Bytes for set command
        """
        output_flag = 1 if output else 0
        return bytes([
            self.SET_MODIFY, output_flag,
            vset & 0xFF, (vset >> 8) & 0xFF,       # voltage low and high bytes
            iset & 0xFF, (iset >> 8) & 0xFF,       # current low and high bytes
            ovp & 0xFF, (ovp >> 8) & 0xFF,         # over-voltage protection
            ocp & 0xFF, (ocp >> 8) & 0xFF          # over-current protection
        ])
    
    def set_voltage(self, voltage: float) -> bool:
        """
        Set output voltage.
        
        Args:
            voltage: Voltage in volts (0-30V)
            
        Returns:
            True if successful
        """
        if not 0 <= voltage <= 30.0:
            self.logger.error(f"Invalid voltage: {voltage}V (must be 0-30V)")
            return False
        
        try:
            # Convert to millivolts
            voltage_mv = int(voltage * 1000)
            
            # Use current settings and update voltage
            data = self._gen_set(
                output=self.output_enabled,
                vset=voltage_mv,
                iset=self.current_current_set
            )
            
            response = self._send_frame(self.OP_BASICSET, data)
            success = response is not None
            
            if success:
                self.current_voltage_set = voltage_mv
                self.logger.debug(f"Set voltage to {voltage}V")
            else:
                self.logger.error(f"Failed to set voltage to {voltage}V")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error setting voltage: {e}")
            return False
    
    def set_current(self, current: float) -> bool:
        """
        Set current limit.
        
        Args:
            current: Current in amperes (0-5A)
            
        Returns:
            True if successful
        """
        if not 0 <= current <= 5.0:
            self.logger.error(f"Invalid current: {current}A (must be 0-5A)")
            return False
        
        try:
            # Convert to milliamperes
            current_ma = int(current * 1000)
            
            # Use current settings and update current
            data = self._gen_set(
                output=self.output_enabled,
                vset=self.current_voltage_set,
                iset=current_ma
            )
            
            response = self._send_frame(self.OP_BASICSET, data)
            success = response is not None
            
            if success:
                self.current_current_set = current_ma
                self.logger.debug(f"Set current limit to {current}A")
            else:
                self.logger.error(f"Failed to set current to {current}A")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error setting current: {e}")
            return False
    
    def set_output(self, enabled: bool) -> bool:
        """
        Enable or disable output.
        
        Args:
            enabled: True to enable output, False to disable
            
        Returns:
            True if successful
        """
        try:
            # Use current settings and update output state
            data = self._gen_set(
                output=enabled,
                vset=self.current_voltage_set,
                iset=self.current_current_set
            )
            
            response = self._send_frame(self.OP_BASICSET, data)
            success = response is not None
            
            if success:
                self.output_enabled = enabled
                state = "enabled" if enabled else "disabled"
                self.logger.info(f"Output {state}")
            else:
                self.logger.error(f"Failed to {'enable' if enabled else 'disable'} output")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error setting output state: {e}")
            return False
    
    def get_measurement(self) -> Optional[Tuple[float, float, float]]:
        """
        Get current voltage, current, and power measurement.
        
        Returns:
            Tuple of (voltage, current, power) or None if failed
        """
        status = self.get_status()
        if status:
            return (status.voltage_out, status.current_out, status.power_out)
        return None
    
    def reconnect(self) -> bool:
        """
        Attempt to reconnect to device.
        
        Returns:
            True if reconnection successful
        """
        self.logger.info("Attempting to reconnect...")
        self.disconnect()
        
        for attempt in range(self.retry_attempts):
            self.logger.debug(f"Reconnection attempt {attempt + 1}/{self.retry_attempts}")
            
            if self.connect():
                self.logger.info("Reconnection successful")
                return True
            
            if attempt < self.retry_attempts - 1:
                time.sleep(self.retry_delay)
        
        self.logger.error("Reconnection failed after all attempts")
        return False
    
    def is_connected(self) -> bool:
        """Check if device is connected."""
        return self.connected
    
    def get_device_info(self) -> Dict[str, Any]:
        """
        Get device information.
        
        Returns:
            Dictionary with device info
        """
        info = {
            'vendor_id': hex(self.VENDOR_ID),
            'product_id': hex(self.PRODUCT_ID),
            'connected': self.connected,
            'last_status': self.last_status.voltage_out if self.last_status else None
        }
        
        if self.device and self.connected:
            try:
                info['manufacturer'] = self.device.get_manufacturer_string()
                info['product'] = self.device.get_product_string()
                info['serial_number'] = self.device.get_serial_number_string()
            except Exception as e:
                self.logger.warning(f"Could not get device strings: {e}")
        
        return info