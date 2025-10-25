"""Performance monitoring utilities for DP100 Monitor."""

import psutil
import threading
import time
from typing import Dict, Any, Optional, Callable
from collections import deque

from .logger import get_logger


class PerformanceMonitor:
    """Monitor system performance and memory usage."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize performance monitor.
        
        Args:
            config: Application configuration
        """
        self.config = config['performance']
        self.logger = get_logger('performance')
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # Performance history
        self.memory_history = deque(maxlen=100)
        self.cpu_history = deque(maxlen=100)
        
        # Callbacks for alerts
        self.memory_alert_callback: Optional[Callable[[float], None]] = None
        
    def start(self) -> None:
        """Start performance monitoring."""
        if self.running:
            return
            
        if not self.config.get('monitor_enabled', True):
            self.logger.info("Performance monitoring disabled")
            return
            
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("Performance monitoring started")
    
    def stop(self) -> None:
        """Stop performance monitoring."""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
        self.logger.info("Performance monitoring stopped")
    
    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        memory_interval = self.config.get('memory_check_interval', 10)
        cpu_interval = self.config.get('cpu_check_interval', 5)
        
        last_memory_check = 0
        last_cpu_check = 0
        
        while self.running:
            current_time = time.time()
            
            # Check memory usage
            if current_time - last_memory_check >= memory_interval:
                self._check_memory()
                last_memory_check = current_time
            
            # Check CPU usage
            if current_time - last_cpu_check >= cpu_interval:
                self._check_cpu()
                last_cpu_check = current_time
            
            time.sleep(1.0)
    
    def _check_memory(self) -> None:
        """Check memory usage."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            
            # Store in history
            self.memory_history.append({
                'timestamp': time.time(),
                'rss_mb': memory_info.rss / 1024 / 1024,
                'vms_mb': memory_info.vms / 1024 / 1024,
                'percent': memory_percent
            })
            
            # Check for alerts
            threshold = self.config.get('alert_memory_threshold', 80)
            if memory_percent > threshold:
                self.logger.warning(f"High memory usage: {memory_percent:.1f}%")
                if self.memory_alert_callback:
                    self.memory_alert_callback(memory_percent)
            
        except Exception as e:
            self.logger.error(f"Error checking memory: {e}")
    
    def _check_cpu(self) -> None:
        """Check CPU usage."""
        try:
            process = psutil.Process()
            cpu_percent = process.cpu_percent()
            
            # Store in history
            self.cpu_history.append({
                'timestamp': time.time(),
                'percent': cpu_percent
            })
            
        except Exception as e:
            self.logger.error(f"Error checking CPU: {e}")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get current memory statistics.
        
        Returns:
            Memory statistics dictionary
        """
        if not self.memory_history:
            return {}
        
        latest = self.memory_history[-1]
        return {
            'current_rss_mb': latest['rss_mb'],
            'current_vms_mb': latest['vms_mb'],
            'current_percent': latest['percent'],
            'history_length': len(self.memory_history)
        }
    
    def get_cpu_stats(self) -> Dict[str, Any]:
        """
        Get current CPU statistics.
        
        Returns:
            CPU statistics dictionary
        """
        if not self.cpu_history:
            return {}
        
        latest = self.cpu_history[-1]
        return {
            'current_percent': latest['percent'],
            'history_length': len(self.cpu_history)
        }
    
    def set_memory_alert_callback(self, callback: Callable[[float], None]) -> None:
        """
        Set callback for memory usage alerts.
        
        Args:
            callback: Function to call when memory usage exceeds threshold
        """
        self.memory_alert_callback = callback