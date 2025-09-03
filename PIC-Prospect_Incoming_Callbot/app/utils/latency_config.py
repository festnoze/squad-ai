"""
Configuration module for latency monitoring system.

This module provides configuration management for latency thresholds, 
reporting settings, and alerting rules.
"""
import os
from typing import Dict, Optional

from utils.envvar import EnvHelper
from utils.latency_metric import OperationType
from utils.latency_reporter import (
    InfluxDBReporter,
    LatencyReportManager,
    PrometheusReporter,
    SlackReporter,
    report_manager,
    setup_latency_reporting,
)
from utils.latency_tracker import LatencyThresholds, latency_tracker


class ThresholdManager:
    """Manager for threshold operations with string-based operation types"""
    
    def __init__(self, thresholds: Optional[LatencyThresholds] = None):
        # Use provided thresholds or get from global latency tracker
        self.thresholds = thresholds or latency_tracker.thresholds
    
    def get_warning_threshold(self, operation_name: str) -> Optional[float]:
        """Get warning threshold for an operation by string name"""
        try:
            operation_type = OperationType(operation_name.lower())
            return self.thresholds.get_warning_threshold(operation_type)
        except ValueError:
            return None
    
    def get_critical_threshold(self, operation_name: str) -> Optional[float]:
        """Get critical threshold for an operation by string name"""
        try:
            operation_type = OperationType(operation_name.lower())
            return self.thresholds.get_critical_threshold(operation_type)
        except ValueError:
            return None
    
    def exceeds_warning_threshold(self, operation_name: str, latency_ms: float) -> bool:
        """Check if latency exceeds warning threshold for an operation"""
        warning_threshold = self.get_warning_threshold(operation_name)
        if warning_threshold is None:
            return False
        return latency_ms > warning_threshold
    
    def exceeds_critical_threshold(self, operation_name: str, latency_ms: float) -> bool:
        """Check if latency exceeds critical threshold for an operation"""
        critical_threshold = self.get_critical_threshold(operation_name)
        if critical_threshold is None:
            return False
        return latency_ms > critical_threshold
    
    def calculate_criticality(self, operation_name: str, latency_ms: float) -> str:
        """Calculate criticality level (normal/warning/critical) for string-based operation names"""
        if self.exceeds_critical_threshold(operation_name, latency_ms):
            return "critical"
        elif self.exceeds_warning_threshold(operation_name, latency_ms):
            return "warning"
        else:
            return "normal"


class LatencyConfig:
    """Gestionnaire de configuration pour le système de monitoring de latence"""
    
    def __init__(self):
        self.thresholds = LatencyThresholds()
        self.configured = False
        self.is_initialized = False
    
    def configure_custom_thresholds(self, custom_thresholds: Dict[str, Dict[str, float]]) -> None:
        """
        Configure des seuils personnalisés pour la latence.
        
        Args:
            custom_thresholds: Dict avec la structure:
                {
                    "speech_to_text": {"warning": 2000, "critical": 5000},
                    "text_to_speech": {"warning": 1500, "critical": 3000},
                    "salesforce_api": {"warning": 1000, "critical": 3000},
                    "rag_inference": {"warning": 3000, "critical": 8000}
                }
        """
        for operation_type_str, thresholds in custom_thresholds.items():
            try:
                # Validate thresholds
                warning = thresholds.get("warning")
                critical = thresholds.get("critical")
                
                if warning is not None and warning < 0:
                    raise ValueError("Thresholds must be positive values")
                if critical is not None and critical < 0:
                    raise ValueError("Thresholds must be positive values")
                if warning is not None and critical is not None and warning >= critical:
                    raise ValueError("Warning threshold must be less than critical threshold")
                
                operation_type = OperationType(operation_type_str.lower())
                if warning is not None:
                    self.thresholds.thresholds[operation_type]["warning"] = float(warning)
                if critical is not None:
                    self.thresholds.thresholds[operation_type]["critical"] = float(critical)
            except ValueError as e:
                if "must be" in str(e):
                    raise  # Re-raise validation errors
                print(f"Type d'opération inconnu: {operation_type_str}")
        
        # Sync configured thresholds to the latency tracker
        latency_tracker.thresholds = self.thresholds
    
    def configure_from_environment(self) -> None:
        """Configure le système depuis les variables d'environnement"""
        try:
            # Configuration des seuils depuis l'environnement
            custom_thresholds = {}
            
            # STT thresholds
            stt_warning = os.getenv("LATENCY_STT_WARNING_MS")
            stt_critical = os.getenv("LATENCY_STT_CRITICAL_MS")
            if stt_warning or stt_critical:
                custom_thresholds["speech_to_text"] = {}
                if stt_warning:
                    custom_thresholds["speech_to_text"]["warning"] = float(stt_warning)
                if stt_critical:
                    custom_thresholds["speech_to_text"]["critical"] = float(stt_critical)
            
            # TTS thresholds
            tts_warning = os.getenv("LATENCY_TTS_WARNING_MS")
            tts_critical = os.getenv("LATENCY_TTS_CRITICAL_MS")
            if tts_warning or tts_critical:
                custom_thresholds["text_to_speech"] = {}
                if tts_warning:
                    custom_thresholds["text_to_speech"]["warning"] = float(tts_warning)
                if tts_critical:
                    custom_thresholds["text_to_speech"]["critical"] = float(tts_critical)
            
            # Salesforce thresholds
            sf_warning = os.getenv("LATENCY_SALESFORCE_WARNING_MS")
            sf_critical = os.getenv("LATENCY_SALESFORCE_CRITICAL_MS")
            if sf_warning or sf_critical:
                custom_thresholds["salesforce_api"] = {}
                if sf_warning:
                    custom_thresholds["salesforce_api"]["warning"] = float(sf_warning)
                if sf_critical:
                    custom_thresholds["salesforce_api"]["critical"] = float(sf_critical)
            
            # RAG thresholds
            rag_warning = os.getenv("LATENCY_RAG_WARNING_MS")
            rag_critical = os.getenv("LATENCY_RAG_CRITICAL_MS")
            if rag_warning or rag_critical:
                custom_thresholds["rag_inference"] = {}
                if rag_warning:
                    custom_thresholds["rag_inference"]["warning"] = float(rag_warning)
                if rag_critical:
                    custom_thresholds["rag_inference"]["critical"] = float(rag_critical)
            
            if custom_thresholds:
                self.configure_custom_thresholds(custom_thresholds)
            
        except Exception as e:
            print(f"Erreur lors de la configuration des seuils depuis l'environnement: {e}")
    
    def setup_prometheus_reporter(
        self, 
        pushgateway_url: Optional[str] = None, 
        job_name: str = "prospect_callbot"
    ) -> None:
        """Configure un reporter Prometheus"""
        url = pushgateway_url or os.getenv("PROMETHEUS_PUSHGATEWAY_URL")
        if url:
            reporter = PrometheusReporter(url, job_name)
            report_manager.add_reporter(reporter)
            print(f"Reporter Prometheus configuré: {url}")
    
    def setup_influxdb_reporter(
        self,
        influxdb_url: Optional[str] = None,
        token: Optional[str] = None,
        org: Optional[str] = None,
        bucket: Optional[str] = None
    ) -> None:
        """Configure un reporter InfluxDB"""
        url = influxdb_url or os.getenv("INFLUXDB_URL")
        token = token or os.getenv("INFLUXDB_TOKEN")
        org = org or os.getenv("INFLUXDB_ORG")
        bucket = bucket or os.getenv("INFLUXDB_BUCKET")
        
        if url and token and org and bucket:
            reporter = InfluxDBReporter(url, token, org, bucket)
            report_manager.add_reporter(reporter)
            print(f"Reporter InfluxDB configuré: {url}")
    
    def setup_slack_reporter(
        self,
        webhook_url: Optional[str] = None,
        channel: str = "#alerts"
    ) -> None:
        """Configure un reporter Slack pour les alertes"""
        url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        channel = os.getenv("SLACK_CHANNEL", channel)
        
        if url:
            reporter = SlackReporter(url, channel)
            report_manager.add_reporter(reporter)
            print(f"Reporter Slack configuré: {channel}")
    
    def initialize_latency_system(self) -> None:
        """Initialize le système de monitoring de latence complet"""
        if self.configured:
            return
        
        print("Initialisation du système de monitoring de latence...")
        
        # Configurer les seuils depuis l'environnement
        self.configure_from_environment()
        
        # Mettre à jour les seuils du tracker
        latency_tracker.thresholds = self.thresholds
        
        # Update tracker configuration from environment
        latency_tracker.enabled = EnvHelper.get_latency_tracking_enabled()
        latency_tracker.log_metrics = EnvHelper.get_latency_logging_enabled()
        latency_tracker.save_to_file = EnvHelper.get_latency_file_logging_enabled()
        
        # Configurer les reporters depuis l'environnement
        self.setup_prometheus_reporter()
        self.setup_influxdb_reporter()
        self.setup_slack_reporter()
        
        # Connecter le reporting au tracker
        setup_latency_reporting()
        
        self.configured = True
        self.is_initialized = True
        print("Système de monitoring de latence initialisé avec succès")
        
        # Afficher la configuration
        self.print_configuration()
    
    def print_configuration(self) -> None:
        """Affiche la configuration actuelle"""
        print("\n=== Configuration du monitoring de latence ===")
        print(f"Tracking activé: {latency_tracker.enabled}")
        print(f"Logging activé: {latency_tracker.log_metrics}")
        print(f"Sauvegarde fichier: {latency_tracker.save_to_file}")
        
        if latency_tracker.save_to_file:
            print(f"Fichier de métriques: {latency_tracker.metrics_file_path}")
        
        print("\nSeuils de latence (ms):")
        for op_type, thresholds in self.thresholds.thresholds.items():
            print(f"  {op_type.value}:")
            print(f"    Warning: {thresholds['warning']}ms")
            print(f"    Critical: {thresholds['critical']}ms")
        
        print(f"\nReporters configurés: {len(report_manager.reporters)}")
        for reporter in report_manager.reporters:
            print(f"  - {reporter.__class__.__name__}")
        
        print("=" * 50 + "\n")
    
    def get_threshold_manager(self) -> ThresholdManager:
        """Get a ThresholdManager that uses the current configuration"""
        return ThresholdManager(self.thresholds)
    
    def get_current_stats(self) -> Dict:
        """Retourne les statistiques actuelles de latence"""
        return {
            "total_metrics": len(latency_tracker.metrics),
            "stats_by_operation": dict(latency_tracker.stats_by_operation),
            "thresholds": {
                op_type.value: thresholds 
                for op_type, thresholds in self.thresholds.thresholds.items()
            }
        }


# Instance globale de configuration
latency_config = LatencyConfig()


def get_threshold_manager() -> ThresholdManager:
    """Get a ThresholdManager that uses the global latency tracker's thresholds"""
    return ThresholdManager()