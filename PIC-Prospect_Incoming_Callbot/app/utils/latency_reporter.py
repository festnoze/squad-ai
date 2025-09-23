import asyncio
import logging
import time
from abc import ABC, abstractmethod

import httpx
from utils.latency_metric import LatencyMetric
from utils.latency_tracker import latency_tracker


class LatencyReporter(ABC):
    """Abstract interface for reporting latency metrics to external systems"""

    @abstractmethod
    async def report_metric(self, metric: LatencyMetric) -> None:
        """Report a latency metric to the external system"""
        pass

    @abstractmethod
    async def report_batch_metrics(self, metrics: list[LatencyMetric]) -> None:
        """Report a batch of metrics to the external system"""
        pass


class PrometheusReporter(LatencyReporter):
    """Reporter for Prometheus via pushgateway"""

    def __init__(self, pushgateway_url: str, job_name: str = "prospect_callbot"):
        self.pushgateway_url = pushgateway_url.rstrip("/")
        self.job_name = job_name
        self.logger = logging.getLogger(__name__)

    async def report_metric(self, metric: LatencyMetric) -> None:
        """Report a single metric to Prometheus"""
        metrics_text = self._format_metric_for_prometheus(metric)
        await self._push_to_prometheus(metrics_text)

    async def report_batch_metrics(self, metrics: list[LatencyMetric]) -> None:
        """Report a batch of metrics to Prometheus"""
        if not metrics:
            return

        metrics_text = "\n".join(self._format_metric_for_prometheus(m) for m in metrics)
        await self._push_to_prometheus(metrics_text)

    def _format_metric_for_prometheus(self, metric: LatencyMetric) -> str:
        """Format a metric for Prometheus"""
        labels = {"operation_type": metric.operation_type.value, "operation_name": metric.operation_name, "status": metric.status.value}

        if metric.provider:
            labels["provider"] = metric.provider
        if metric.call_sid:
            labels["call_sid"] = metric.call_sid
        if metric.stream_sid:
            labels["stream_sid"] = metric.stream_sid

        labels_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        timestamp_ms = int(metric.timestamp.timestamp() * 1000)

        return f"latency_ms{{{labels_str}}} {metric.latency_ms} {timestamp_ms}"

    async def _push_to_prometheus(self, metrics_text: str) -> None:
        """Push metrics to Prometheus pushgateway"""
        try:
            url = f"{self.pushgateway_url}/metrics/job/{self.job_name}"
            headers = {"Content-Type": "text/plain"}

            async with httpx.AsyncClient() as client:
                response = await client.put(url, content=metrics_text, headers=headers)
                response.raise_for_status()

            self.logger.debug(f"Metrics sent to Prometheus: {len(metrics_text.split(chr(10)))} metrics")
        except Exception as e:
            self.logger.error(f"Error sending to Prometheus: {e}")


class InfluxDBReporter(LatencyReporter):
    """Reporter for InfluxDB"""

    def __init__(self, influxdb_url: str, token: str, org: str, bucket: str):
        self.influxdb_url = influxdb_url.rstrip("/")
        self.token = token
        self.org = org
        self.bucket = bucket
        self.logger = logging.getLogger(__name__)

    async def report_metric(self, metric: LatencyMetric) -> None:
        """Report a single metric to InfluxDB"""
        line = self._format_metric_for_influxdb(metric)
        await self._write_to_influxdb(line)

    async def report_batch_metrics(self, metrics: list[LatencyMetric]) -> None:
        """Report a batch of metrics to InfluxDB"""
        if not metrics:
            return

        lines = "\n".join(self._format_metric_for_influxdb(m) for m in metrics)
        await self._write_to_influxdb(lines)

    def _format_metric_for_influxdb(self, metric: LatencyMetric) -> str:
        """Format a metric for InfluxDB line protocol"""
        tags = {"operation_type": metric.operation_type.value, "operation_name": metric.operation_name, "status": metric.status.value}

        if metric.provider:
            tags["provider"] = metric.provider
        if metric.call_sid:
            tags["call_sid"] = metric.call_sid
        if metric.stream_sid:
            tags["stream_sid"] = metric.stream_sid

        tags_str = ",".join(f"{k}={v}" for k, v in tags.items())
        timestamp_ns = int(metric.timestamp.timestamp() * 1_000_000_000)

        return f"latency,{tags_str} latency_ms={metric.latency_ms} {timestamp_ns}"

    async def _write_to_influxdb(self, data: str) -> None:
        """Write data to InfluxDB"""
        try:
            url = f"{self.influxdb_url}/api/v2/write?org={self.org}&bucket={self.bucket}"
            headers = {"Authorization": f"Token {self.token}", "Content-Type": "text/plain"}

            async with httpx.AsyncClient() as client:
                response = await client.post(url, content=data, headers=headers)
                response.raise_for_status()

            self.logger.debug(f"Metrics sent to InfluxDB: {len(data.split(chr(10)))} metrics")
        except Exception as e:
            self.logger.error(f"Error sending to InfluxDB: {e}")


class SlackReporter(LatencyReporter):
    """Reporter for sending Slack alerts"""

    def __init__(self, webhook_url: str, channel: str = "#alerts"):
        self.webhook_url = webhook_url
        self.channel = channel
        self.logger = logging.getLogger(__name__)

        # Avoid spam: limit one alert per minute per operation type
        self._last_alert_time: dict[str, float] = {}
        self._alert_cooldown = 60  # secondes

    async def report_metric(self, metric: LatencyMetric) -> None:
        """Report a critical metric to Slack"""
        # Only report metrics that exceed critical thresholds
        from utils.latency_tracker import LatencyThresholds

        thresholds = LatencyThresholds()

        if metric.latency_ms > thresholds.get_critical_threshold(metric.operation_type):
            await self._send_alert(metric)

    async def report_batch_metrics(self, metrics: list[LatencyMetric]) -> None:
        """Report critical metrics from a batch to Slack"""
        for metric in metrics:
            await self.report_metric(metric)

    async def _send_alert(self, metric: LatencyMetric) -> None:
        """Send a Slack alert for a critical metric"""
        # Check cooldown to avoid spam
        key = f"{metric.operation_type.value}/{metric.operation_name}"
        now = time.time()

        if key in self._last_alert_time:
            if now - self._last_alert_time[key] < self._alert_cooldown:
                return  # Skip, too soon since last alert

        self._last_alert_time[key] = now

        try:
            # Create alert message
            status_emoji = "🔴" if metric.status.value == "error" else "🟡"

            message = {
                "channel": self.channel,
                "username": "Latency Monitor",
                "icon_emoji": ":warning:",
                "attachments": [
                    {
                        "color": "danger" if metric.status.value == "error" else "warning",
                        "title": f"{status_emoji} High latency detected",
                        "fields": [
                            {"title": "Operation", "value": f"{metric.operation_type.value}/{metric.operation_name}", "short": True},
                            {"title": "Latency", "value": f"{metric.latency_ms:.0f}ms", "short": True},
                            {"title": "Provider", "value": metric.provider or "N/A", "short": True},
                            {"title": "Status", "value": metric.status.value, "short": True},
                            {"title": "Call SID", "value": metric.call_sid or "N/A", "short": True},
                            {"title": "Timestamp", "value": metric.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"), "short": True},
                        ],
                    }
                ],
            }

            if metric.error_message:
                message["attachments"][0]["fields"].append(
                    {
                        "title": "Error",
                        "value": metric.error_message[:500],  # Limit length
                        "short": False,
                    }
                )

            async with httpx.AsyncClient() as client:
                response = await client.post(self.webhook_url, json=message)
                response.raise_for_status()

            self.logger.info(f"Slack alert sent for {metric}")

        except Exception as e:
            self.logger.error(f"Error sending Slack alert: {e}")


class LatencyReportManager:
    """Latency reporters manager"""

    def __init__(self):
        self.reporters: list[LatencyReporter] = []
        self.logger = logging.getLogger(__name__)
        self.enabled = True

    def add_reporter(self, reporter: LatencyReporter) -> None:
        """Add a reporter"""
        self.reporters.append(reporter)
        self.logger.info(f"Reporter added: {reporter.__class__.__name__}")

    def remove_reporter(self, reporter: LatencyReporter) -> None:
        """Remove a reporter"""
        if reporter in self.reporters:
            self.reporters.remove(reporter)
            self.logger.info(f"Reporter removed: {reporter.__class__.__name__}")

    async def report_metric(self, metric: LatencyMetric) -> None:
        """Report a metric to all configured reporters"""
        if not self.enabled:
            return

        tasks = [reporter.report_metric(metric) for reporter in self.reporters]
        if tasks:
            # Execute all reporters in parallel, ignore individual errors
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log errors but don't fail the main process
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"Error in reporter {self.reporters[i].__class__.__name__}: {result}")

    async def report_batch_metrics(self, metrics: list[LatencyMetric]) -> None:
        """Report a batch of metrics to all reporters"""
        if not self.enabled or not metrics:
            return

        tasks = [reporter.report_batch_metrics(metrics) for reporter in self.reporters]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"Error in reporter {self.reporters[i].__class__.__name__}: {result}")

    def enable_reporting(self) -> None:
        """Enable reporting"""
        self.enabled = True
        self.logger.info("Latency reporting enabled")

    def disable_reporting(self) -> None:
        """Disable reporting"""
        self.enabled = False
        self.logger.info("Latency reporting disabled")


# Global manager instance
report_manager = LatencyReportManager()


# Helper to integrate reporting with the tracker
def setup_latency_reporting() -> None:
    """Configure latency reporting with the tracker"""

    def report_callback(metric: LatencyMetric) -> None:
        """Callback to report metrics automatically"""
        asyncio.create_task(report_manager.report_metric(metric))

    latency_tracker.add_alert_callback(report_callback)
