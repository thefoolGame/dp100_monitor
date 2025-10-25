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


    


    # Protocol constants based on pydp100 library


    DR_H2D = 0xFB


    DR_D2H = 0xFA


    OP_BASICINFO = 0x30


    OP_BASICSET = 0x35


    SET_MODIFY = 0x20  # Correct flag to write/modify settings


    SET_ACT = 0x80     # Flag to read current settings


    


    def __init__(self, config: Dict[str, Any]):


        self.config = config['device']


        self.logger = get_logger('device.interface')


        self.device: Optional[hid.device] = None


        self.connected = False


        


        # Local state tracking


        self.current_voltage_set = 0


        self.current_current_set = 1000


        self.output_enabled = False


        


        self.retry_attempts = self.config.get('reconnect_attempts', 5)


        self.retry_delay = self.config.get('reconnect_delay', 2.0)


        self.crc16 = crcmod.mkCrcFun(0x18005, rev=True, initCrc=0xFFFF, xorOut=0x0000)


    


    def connect(self) -> bool:


        if self.connected: return True


        try:


            self.device = hid.device()


            self.device.open(self.VENDOR_ID, self.PRODUCT_ID)


            self.device.set_nonblocking(1)


            self.connected = True


            if self._test_communication():


                self.logger.info("Connected to DP100 successfully")


                return True


            self.disconnect()


            return False


        except Exception as e:


            self.logger.error(f"Failed to connect to DP100: {e}", exc_info=True)


            self.disconnect()


            return False


    


    def disconnect(self) -> None:


        if self.device:


            try: self.device.close()


            except Exception: pass


            self.device = None


        self.connected = False


        self.logger.info("Disconnected from DP100")





    def _test_communication(self) -> bool:


        try:


            status = self.get_full_status() # Use full status for initial sync


            if status:


                self.logger.debug("Communication test successful, syncing state.")


                self.current_voltage_set = int(status.voltage_set * 1000)


                self.current_current_set = int(status.current_set * 1000)


                self.output_enabled = status.output_enabled


                return True


            return False


        except Exception as e:


            self.logger.error(f"Communication test failed: {e}", exc_info=True)


            return False





    def _gen_frame(self, op_code: int, data: bytes = b'') -> bytes:


        frame = bytes([self.DR_H2D, op_code & 0xFF, 0x0, len(data) & 0xFF]) + data


        crc = self.crc16(frame)


        return frame + bytes([crc & 0xFF, (crc >> 8) & 0xFF])





    def _send_frame(self, op_code: int, data: bytes = b'') -> Optional[bytes]:


        if not self.connected or not self.device: return None


        try:


            frame = self._gen_frame(op_code, data)


            packet = bytearray(64)


            packet[:len(frame)] = frame


            self.device.write(packet)


            time.sleep(0.005) # Reverted to 5ms for max sample rate


            response = self.device.read(64)


            return bytes(response) if response else None


        except Exception as e:


            self.logger.error(f"Frame communication error: {e}", exc_info=True)


            return None





    def get_full_status(self) -> Optional[DP100Status]:


        """Gets full status from device, including setpoints. Slower due to 2 HID calls."""


        response = self._send_frame(self.OP_BASICINFO)


        if not response or len(response) < 10 or response[0] != self.DR_D2H:


            return None


        try:


            voltage_out = ((response[7] << 8) | response[6]) / 1000.0


            current_out = ((response[9] << 8) | response[8]) / 1000.0


            power_out = voltage_out * current_out





            response_set = self._send_frame(self.OP_BASICSET, bytes([self.SET_ACT]))


            if not response_set or len(response_set) < 10:


                return None





            voltage_set = ((response_set[3] << 8) | response_set[2]) / 1000.0


            current_set = ((response_set[5] << 8) | response_set[4]) / 1000.0


            output_enabled = (response_set[1] & 0x01) == 0x01





            temperature = ((response[15] << 8) | response[14]) / 10.0 if len(response) > 15 else 25.0





            return DP100Status(voltage_set, current_set, voltage_out, current_out, power_out, output_enabled, temperature, "Normal")


        except Exception as e:


            self.logger.error(f"Failed to parse status response: {e}")


            return None





    def _gen_set_payload(self, output: bool, vset: int, iset: int, ovp: int = 30500, ocp: int = 5050) -> bytes:


        output_flag = 1 if output else 0


        return bytes([


            self.SET_MODIFY, 


            output_flag,


            vset & 0xFF, (vset >> 8) & 0xFF,


            iset & 0xFF, (iset >> 8) & 0xFF,


            ovp & 0xFF, (ovp >> 8) & 0xFF,


            ocp & 0xFF, (ocp >> 8) & 0xFF


        ])





    def set_voltage(self, voltage: float) -> bool:


        if not 0 <= voltage <= 30.0: return False


        try:


            voltage_mv = int(voltage * 1000)


            data = self._gen_set_payload(self.output_enabled, voltage_mv, self.current_current_set)


            response = self._send_frame(self.OP_BASICSET, data)


            if response:


                self.current_voltage_set = voltage_mv


                return True


            return False


        except Exception as e:


            self.logger.error(f"Error setting voltage: {e}")


            return False





    def set_current(self, current: float) -> bool:


        if not 0 <= current <= 5.0: return False


        try:


            current_ma = int(current * 1000)


            data = self._gen_set_payload(self.output_enabled, self.current_voltage_set, current_ma)


            response = self._send_frame(self.OP_BASICSET, data)


            if response:


                self.current_current_set = current_ma


                return True


            return False


        except Exception as e:


            self.logger.error(f"Error setting current: {e}")


            return False





    def set_output(self, enabled: bool) -> bool:


        try:


            data = self._gen_set_payload(enabled, self.current_voltage_set, self.current_current_set)


            response = self._send_frame(self.OP_BASICSET, data)


            if response:


                self.output_enabled = enabled


                return True


            return False


        except Exception as e:


            self.logger.error(f"Error setting output state: {e}")


            return False


    


    def get_measurement(self) -> Optional[Tuple[float, float, float]]:


        """Gets live measurement data. Fast, for high-frequency polling."""


        response = self._send_frame(self.OP_BASICINFO)


        if not response or len(response) < 10 or response[0] != self.DR_D2H:


            return None


        try:


            voltage_out = ((response[7] << 8) | response[6]) / 1000.0


            current_out = ((response[9] << 8) | response[8]) / 1000.0


            power_out = voltage_out * current_out


            return (voltage_out, current_out, power_out)


        except Exception:


            return None


    


    def reconnect(self) -> bool:


        self.disconnect()


        for _ in range(self.retry_attempts):


            if self.connect(): return True


            time.sleep(self.retry_delay)


        return False


    


    def is_connected(self) -> bool:


        return self.connected


    


    def get_device_info(self) -> Dict[str, Any]:


        return {'connected': self.connected}




