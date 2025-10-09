import json
import logging
import threading
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from utils.envvar import EnvHelper
from utils.latency_metric import LatencyMetric, OperationStatus, OperationType


class LatencyThresholds:
    """Latency threshold configuration for each operation type"""
    
    def __init__(self):
        # Default thresholds (in milliseconds)
        self.thresholds: dict[OperationType, dict[str, float]] = {
            OperationType.STT: {
                "warning": 2000,  # 2s
                "critical": 5000  # 5s
            },
            OperationType.TTS: {
                "warning": 1500,  # 1.5s
                "critical": 3000  # 3s
            },
            OperationType.SALESFORCE: {
                "warning": 1000,  # 1s
                "critical": 3000  # 3s
            },
            OperationType.RAG: {
                "warning": 3000,  # 3s
                "critical": 8000  # 8s
            },
            OperationType.CALL_DURATION: {
                "warning": 150_000,  # 2.5 minutes
                "critical": 300_000  # 5 minutes
            }
        }
    
    def get_warning_threshold(self, operation_type: OperationType) -> float:
        return self.thresholds.get(operation_type, {}).get("warning", 1000)
    
    def get_critical_threshold(self, operation_type: OperationType) -> float:
        return self.thresholds.get(operation_type, {}).get("critical", 3000)


class LatencyTracker:
    """Central service for collecting and analyzing latency metrics"""
    
    _instance: "LatencyTracker | None" = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "LatencyTracker":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        
        self._initialized = True
        self.logger = logging.getLogger(__name__)
        self.metrics: deque[LatencyMetric] = deque(maxlen=10000)  # Keep the last 10K metrics
        self.thresholds = LatencyThresholds()
        self.alert_callbacks: list[Callable[[LatencyMetric], None]] = []
        
        # Configuration from environment variables
        self.enabled = EnvHelper.get_latency_tracking_enabled()
        self.log_metrics = EnvHelper.get_latency_logging_enabled()
        self.save_to_file = EnvHelper.get_latency_file_logging_enabled()
        self.metrics_file_path = EnvHelper.get_latency_metrics_file_path()
        
        # Real-time statistics
        self.stats_by_operation: dict[str, dict] = defaultdict(lambda: {
            "count": 0,
            "total_time": 0.0,
            "avg_time": 0.0,
            "min_time": float("inf"),
            "max_time": 0.0,
            "recent_times": deque(maxlen=100)  # Last 100 measurements for moving average calculation
        })
        
        self.logger.info(f"LatencyTracker initialized - enabled: {self.enabled}, logging: {self.log_metrics}, file_logging: {self.save_to_file}")
    
    def add_metric(self, metric: LatencyMetric) -> None:
        """Add a latency metric"""
        if not self.enabled:
            return
            
        self.metrics.append(metric)
        self._update_stats(metric)
        
        if self.log_metrics:
            self.logger.info(f"Latency: {metric}")
        
        if self.save_to_file:
            self._save_metric_to_file(metric)
        
        # Check thresholds and trigger alerts if necessary
        self._check_thresholds(metric)
    
    def _update_stats(self, metric: LatencyMetric) -> None:
        """Update real-time statistics"""
        key = f"{metric.operation_type.value}/{metric.operation_name}"
        stats = self.stats_by_operation[key]
        
        stats["count"] += 1
        stats["total_time"] += metric.latency_ms
        stats["avg_time"] = stats["total_time"] / stats["count"]
        stats["min_time"] = min(stats["min_time"], metric.latency_ms)
        stats["max_time"] = max(stats["max_time"], metric.latency_ms)
        stats["recent_times"].append(metric.latency_ms)
    
    def _save_metric_to_file(self, metric: LatencyMetric) -> None:
        """Save a metric to a file"""
        try:
            file_path = Path(self.metrics_file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(metric.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            self.logger.error(f"Error saving metric: {e}")
    
    def calculate_criticality(self, metric: LatencyMetric) -> str:
        """Calculate criticality level based on thresholds"""
        warning_threshold = self.thresholds.get_warning_threshold(metric.operation_type)
        critical_threshold = self.thresholds.get_critical_threshold(metric.operation_type)
        
        if metric.latency_ms > critical_threshold:
            return "critical"
        elif metric.latency_ms > warning_threshold:
            return "warning"
        else:
            return "normal"
    
    def _check_thresholds(self, metric: LatencyMetric) -> None:
        """Check thresholds and trigger alerts"""
        # Always trigger alerts for error metrics
        if metric.status == OperationStatus.ERROR:
            self.logger.error(f"ERROR METRIC: {metric}")
            self._trigger_alerts(metric, "error")
            return
        
        # Check latency thresholds for successful operations
        criticality = self.calculate_criticality(metric)
        
        if criticality == "critical":
            critical_threshold = self.thresholds.get_critical_threshold(metric.operation_type)
            self.logger.warning(f"CRITICAL LATENCY: {metric} (threshold: {critical_threshold}ms)")
            self._trigger_alerts(metric, "critical")
        elif criticality == "warning":
            warning_threshold = self.thresholds.get_warning_threshold(metric.operation_type)
            self.logger.warning(f"HIGH LATENCY: {metric} (threshold: {warning_threshold}ms)")
            self._trigger_alerts(metric, "warning")
    
    def _trigger_alerts(self, metric: LatencyMetric, level: str) -> None:
        """Trigger alert callbacks"""
        for callback in self.alert_callbacks:
            try:
                callback(metric)
            except Exception as e:
                self.logger.error(f"Error in alert callback: {e}")
    
    def add_alert_callback(self, callback: Callable[[LatencyMetric], None]) -> None:
        """Add a callback to execute on alert"""
        self.alert_callbacks.append(callback)
    
    def get_stats(self, operation_type: OperationType | None = None) -> dict:
        """Return latency statistics"""
        if operation_type:
            prefix = f"{operation_type.value}/"
            return {k: v for k, v in self.stats_by_operation.items() if k.startswith(prefix)}
        return dict(self.stats_by_operation)
    
    def get_recent_metrics(self, limit: int = 100, operation_type: OperationType | None = None) -> list[LatencyMetric]:
        """Return recent metrics"""
        recent = list(self.metrics)[-limit:]
        if operation_type:
            recent = [m for m in recent if m.operation_type == operation_type]
        return recent
    
    def get_average_latency(self, operation_type: OperationType, minutes: int = 5) -> float | None:
        """Return average latency over the last X minutes"""
        cutoff_time = datetime.now(UTC) - timedelta(minutes=minutes)
        recent_metrics = [
            m for m in self.metrics
            if m.operation_type == operation_type and m.timestamp > cutoff_time
        ]
        
        if not recent_metrics:
            return None
        
        return sum(m.latency_ms for m in recent_metrics) / len(recent_metrics)
    
    def export_metrics(self, file_path: str, format: str = "json") -> None:
        """Export all metrics to a file"""
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            if format.lower() == "json":
                with open(path, "w", encoding="utf-8") as f:
                    metrics_data = [m.to_dict() for m in self.metrics]
                    json.dump(metrics_data, f, indent=2, ensure_ascii=False)
            else:
                raise ValueError(f"Unsupported format: {format}")
                
            self.logger.info(f"Metrics exported to {file_path}")
        except Exception as e:
            self.logger.error(f"Error exporting metrics: {e}")
            raise
    
    def reset_stats(self) -> None:
        """Reset all statistics"""
        self.metrics.clear()
        self.stats_by_operation.clear()
        self.logger.info("Latency statistics reset")


# Global singleton instance
latency_tracker = LatencyTracker()
