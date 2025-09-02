import asyncio
import logging
import time
from abc import ABC, abstractmethod
import httpx
from utils.latency_metric import LatencyMetric
from utils.latency_tracker import latency_tracker


class LatencyReporter(ABC):
    """Interface abstraite pour reporter les métriques de latence vers des systèmes externes"""
    
    @abstractmethod
    async def report_metric(self, metric: LatencyMetric) -> None:
        """Reporte une métrique de latence vers le système externe"""
        pass
    
    @abstractmethod
    async def report_batch_metrics(self, metrics: list[LatencyMetric]) -> None:
        """Reporte un batch de métriques vers le système externe"""
        pass

class PrometheusReporter(LatencyReporter):
    """Reporter pour Prometheus via pushgateway"""
    
    def __init__(self, pushgateway_url: str, job_name: str = "prospect_callbot"):
        self.pushgateway_url = pushgateway_url.rstrip("/")
        self.job_name = job_name
        self.logger = logging.getLogger(__name__)
    
    async def report_metric(self, metric: LatencyMetric) -> None:
        """Reporte une métrique unique vers Prometheus"""
        metrics_text = self._format_metric_for_prometheus(metric)
        await self._push_to_prometheus(metrics_text)
    
    async def report_batch_metrics(self, metrics: list[LatencyMetric]) -> None:
        """Reporte un batch de métriques vers Prometheus"""
        if not metrics:
            return
        
        metrics_text = "\n".join(self._format_metric_for_prometheus(m) for m in metrics)
        await self._push_to_prometheus(metrics_text)
    
    def _format_metric_for_prometheus(self, metric: LatencyMetric) -> str:
        """Formate une métrique au format Prometheus"""
        labels = {
            "operation_type": metric.operation_type.value,
            "operation_name": metric.operation_name,
            "status": metric.status.value
        }
        
        if metric.provider:
            labels["provider"] = metric.provider
        if metric.call_sid:
            labels["call_sid"] = metric.call_sid
        if metric.stream_sid:
            labels["stream_sid"] = metric.stream_sid
        
        labels_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        timestamp_ms = int(metric.timestamp.timestamp() * 1000)
        
        return f'latency_ms{{{labels_str}}} {metric.latency_ms} {timestamp_ms}'
    
    async def _push_to_prometheus(self, metrics_text: str) -> None:
        """Pousse les métriques vers Prometheus pushgateway"""
        try:
            url = f"{self.pushgateway_url}/metrics/job/{self.job_name}"
            headers = {"Content-Type": "text/plain"}
            
            async with httpx.AsyncClient() as client:
                response = await client.put(url, content=metrics_text, headers=headers)
                response.raise_for_status()
                
            self.logger.debug(f"Métriques envoyées à Prometheus: {len(metrics_text.split(chr(10)))} métriques")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi vers Prometheus: {e}")


class InfluxDBReporter(LatencyReporter):
    """Reporter pour InfluxDB"""
    
    def __init__(self, influxdb_url: str, token: str, org: str, bucket: str):
        self.influxdb_url = influxdb_url.rstrip("/")
        self.token = token
        self.org = org
        self.bucket = bucket
        self.logger = logging.getLogger(__name__)
    
    async def report_metric(self, metric: LatencyMetric) -> None:
        """Reporte une métrique unique vers InfluxDB"""
        line = self._format_metric_for_influxdb(metric)
        await self._write_to_influxdb(line)
    
    async def report_batch_metrics(self, metrics: list[LatencyMetric]) -> None:
        """Reporte un batch de métriques vers InfluxDB"""
        if not metrics:
            return
        
        lines = "\n".join(self._format_metric_for_influxdb(m) for m in metrics)
        await self._write_to_influxdb(lines)
    
    def _format_metric_for_influxdb(self, metric: LatencyMetric) -> str:
        """Formate une métrique au format InfluxDB line protocol"""
        tags = {
            "operation_type": metric.operation_type.value,
            "operation_name": metric.operation_name,
            "status": metric.status.value
        }
        
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
        """Écrit les données vers InfluxDB"""
        try:
            url = f"{self.influxdb_url}/api/v2/write?org={self.org}&bucket={self.bucket}"
            headers = {
                "Authorization": f"Token {self.token}",
                "Content-Type": "text/plain"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, content=data, headers=headers)
                response.raise_for_status()
                
            self.logger.debug(f"Métriques envoyées à InfluxDB: {len(data.split(chr(10)))} métriques")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi vers InfluxDB: {e}")


class SlackReporter(LatencyReporter):
    """Reporter pour envoyer des alertes Slack"""
    
    def __init__(self, webhook_url: str, channel: str = "#alerts"):
        self.webhook_url = webhook_url
        self.channel = channel
        self.logger = logging.getLogger(__name__)
        
        # Éviter le spam : limite une alerte par minute par type d'opération
        self._last_alert_time: dict[str, float] = {}
        self._alert_cooldown = 60  # secondes
    
    async def report_metric(self, metric: LatencyMetric) -> None:
        """Reporte une métrique critique vers Slack"""
        # Ne reporte que les métriques qui dépassent les seuils critiques
        from utils.latency_tracker import LatencyThresholds
        thresholds = LatencyThresholds()
        
        if metric.latency_ms > thresholds.get_critical_threshold(metric.operation_type):
            await self._send_alert(metric)
    
    async def report_batch_metrics(self, metrics: list[LatencyMetric]) -> None:
        """Reporte les métriques critiques d'un batch vers Slack"""
        for metric in metrics:
            await self.report_metric(metric)
    
    async def _send_alert(self, metric: LatencyMetric) -> None:
        """Envoie une alerte Slack pour une métrique critique"""
        # Vérifier le cooldown pour éviter le spam
        key = f"{metric.operation_type.value}/{metric.operation_name}"
        now = time.time()
        
        if key in self._last_alert_time:
            if now - self._last_alert_time[key] < self._alert_cooldown:
                return  # Skip, trop tôt depuis la dernière alerte
        
        self._last_alert_time[key] = now
        
        try:
            # Créer le message d'alerte
            status_emoji = "🔴" if metric.status.value == "error" else "🟡"
            
            message = {
                "channel": self.channel,
                "username": "Latency Monitor",
                "icon_emoji": ":warning:",
                "attachments": [
                    {
                        "color": "danger" if metric.status.value == "error" else "warning",
                        "title": f"{status_emoji} Latence élevée détectée",
                        "fields": [
                            {
                                "title": "Opération",
                                "value": f"{metric.operation_type.value}/{metric.operation_name}",
                                "short": True
                            },
                            {
                                "title": "Latence",
                                "value": f"{metric.latency_ms:.0f}ms",
                                "short": True
                            },
                            {
                                "title": "Provider",
                                "value": metric.provider or "N/A",
                                "short": True
                            },
                            {
                                "title": "Status",
                                "value": metric.status.value,
                                "short": True
                            },
                            {
                                "title": "Call SID",
                                "value": metric.call_sid or "N/A",
                                "short": True
                            },
                            {
                                "title": "Timestamp",
                                "value": metric.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
                                "short": True
                            }
                        ]
                    }
                ]
            }
            
            if metric.error_message:
                message["attachments"][0]["fields"].append({
                    "title": "Error",
                    "value": metric.error_message[:500],  # Limiter la longueur
                    "short": False
                })
            
            async with httpx.AsyncClient() as client:
                response = await client.post(self.webhook_url, json=message)
                response.raise_for_status()
                
            self.logger.info(f"Alerte Slack envoyée pour {metric}")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi de l'alerte Slack: {e}")


class LatencyReportManager:
    """Gestionnaire des reporters de latence"""
    
    def __init__(self):
        self.reporters: list[LatencyReporter] = []
        self.logger = logging.getLogger(__name__)
        self.enabled = True
    
    def add_reporter(self, reporter: LatencyReporter) -> None:
        """Ajoute un reporter"""
        self.reporters.append(reporter)
        self.logger.info(f"Reporter ajouté: {reporter.__class__.__name__}")
    
    def remove_reporter(self, reporter: LatencyReporter) -> None:
        """Supprime un reporter"""
        if reporter in self.reporters:
            self.reporters.remove(reporter)
            self.logger.info(f"Reporter supprimé: {reporter.__class__.__name__}")
    
    async def report_metric(self, metric: LatencyMetric) -> None:
        """Reporte une métrique vers tous les reporters configurés"""
        if not self.enabled:
            return
        
        tasks = [reporter.report_metric(metric) for reporter in self.reporters]
        if tasks:
            # Exécuter tous les reporters en parallèle, ignorer les erreurs individuelles
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log les erreurs mais ne pas faire échouer le processus principal
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"Erreur dans reporter {self.reporters[i].__class__.__name__}: {result}")
    
    async def report_batch_metrics(self, metrics: list[LatencyMetric]) -> None:
        """Reporte un batch de métriques vers tous les reporters"""
        if not self.enabled or not metrics:
            return
        
        tasks = [reporter.report_batch_metrics(metrics) for reporter in self.reporters]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"Erreur dans reporter {self.reporters[i].__class__.__name__}: {result}")
    
    def enable_reporting(self) -> None:
        """Active le reporting"""
        self.enabled = True
        self.logger.info("Reporting de latence activé")
    
    def disable_reporting(self) -> None:
        """Désactive le reporting"""
        self.enabled = False
        self.logger.info("Reporting de latence désactivé")


# Instance globale du manager
report_manager = LatencyReportManager()


# Helper pour intégrer le reporting avec le tracker
def setup_latency_reporting() -> None:
    """Configure le reporting de latence avec le tracker"""
    
    def report_callback(metric: LatencyMetric) -> None:
        """Callback pour reporter les métriques automatiquement"""
        asyncio.create_task(report_manager.report_metric(metric))
    
    latency_tracker.add_alert_callback(report_callback)