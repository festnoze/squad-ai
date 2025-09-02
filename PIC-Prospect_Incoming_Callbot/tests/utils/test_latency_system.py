"""
Tests unitaires pour le système de monitoring de latence.
"""
import asyncio
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.latency_config import latency_config
from utils.latency_decorator import measure_latency, measure_latency_context
from utils.latency_metric import LatencyMetric, OperationType, OperationStatus
from utils.latency_reporter import PrometheusReporter, SlackReporter, report_manager
from utils.latency_tracker import LatencyTracker, latency_tracker


class TestLatencyMetric:
    """Tests pour la classe LatencyMetric"""
    
    def test_create_metric(self):
        """Test création d'une métrique de latence"""
        metric = LatencyMetric(
            operation_type=OperationType.STT,
            operation_name="transcribe_audio_async",
            latency_ms=1500.0,
            status=OperationStatus.SUCCESS,
            provider="google",
            call_sid="CA123456789",
            stream_sid="ST987654321"
        )
        
        assert metric.operation_type == OperationType.STT
        assert metric.operation_name == "transcribe_audio_async"
        assert metric.latency_ms == 1500.0
        assert metric.status == OperationStatus.SUCCESS
        assert metric.provider == "google"
        assert metric.call_sid == "CA123456789"
        assert metric.stream_sid == "ST987654321"
        assert metric.timestamp is not None
    
    def test_to_dict(self):
        """Test conversion en dictionnaire"""
        metric = LatencyMetric(
            operation_type=OperationType.TTS,
            operation_name="synthesize_speech",
            latency_ms=800.0,
            status=OperationStatus.SUCCESS
        )
        
        metric_dict = metric.to_dict()
        
        assert metric_dict["operation_type"] == "text_to_speech"
        assert metric_dict["operation_name"] == "synthesize_speech"
        assert metric_dict["latency_ms"] == 800.0
        assert metric_dict["status"] == "success"
        assert "timestamp" in metric_dict
    
    def test_from_dict(self):
        """Test création depuis un dictionnaire"""
        metric_dict = {
            "operation_type": "salesforce_api",
            "operation_name": "schedule_appointment",
            "latency_ms": 2500.0,
            "status": "success",
            "timestamp": "2025-01-01T12:00:00+00:00",
            "provider": "salesforce",
            "call_sid": "CA123",
            "metadata": {"test": True}
        }
        
        metric = LatencyMetric.from_dict(metric_dict)
        
        assert metric.operation_type == OperationType.SALESFORCE
        assert metric.operation_name == "schedule_appointment"
        assert metric.latency_ms == 2500.0
        assert metric.provider == "salesforce"
        assert metric.call_sid == "CA123"
        assert metric.metadata["test"] is True
    
    def test_is_above_threshold(self):
        """Test vérification de seuil"""
        metric = LatencyMetric(
            operation_type=OperationType.STT,
            operation_name="test",
            latency_ms=1500.0,
            status=OperationStatus.SUCCESS
        )
        
        assert metric.is_above_threshold(1000.0) is True
        assert metric.is_above_threshold(2000.0) is False


class TestLatencyTracker:
    """Tests pour la classe LatencyTracker"""
    
    def setup_method(self):
        """Setup avant chaque test"""
        # Réinitialiser le tracker pour les tests
        latency_tracker.metrics.clear()
        latency_tracker.stats_by_operation.clear()
        latency_tracker.enabled = True
    
    def test_singleton_pattern(self):
        """Test que LatencyTracker est bien un singleton"""
        tracker1 = LatencyTracker()
        tracker2 = LatencyTracker()
        assert tracker1 is tracker2
    
    def test_add_metric(self):
        """Test ajout d'une métrique"""
        metric = LatencyMetric(
            operation_type=OperationType.STT,
            operation_name="test_method",
            latency_ms=1000.0,
            status=OperationStatus.SUCCESS
        )
        
        latency_tracker.add_metric(metric)
        
        assert len(latency_tracker.metrics) == 1
        assert latency_tracker.metrics[0] == metric
        
        # Vérifier les stats
        key = "speech_to_text/test_method"
        stats = latency_tracker.stats_by_operation[key]
        assert stats["count"] == 1
        assert stats["avg_time"] == 1000.0
        assert stats["min_time"] == 1000.0
        assert stats["max_time"] == 1000.0
    
    def test_disabled_tracking(self):
        """Test que le tracking peut être désactivé"""
        latency_tracker.enabled = False
        
        metric = LatencyMetric(
            operation_type=OperationType.STT,
            operation_name="test_method",
            latency_ms=1000.0,
            status=OperationStatus.SUCCESS
        )
        
        latency_tracker.add_metric(metric)
        
        assert len(latency_tracker.metrics) == 0
    
    def test_get_stats_by_operation_type(self):
        """Test récupération des stats par type d'opération"""
        # Ajouter quelques métriques
        stt_metric = LatencyMetric(
            operation_type=OperationType.STT,
            operation_name="transcribe",
            latency_ms=1000.0,
            status=OperationStatus.SUCCESS
        )
        
        tts_metric = LatencyMetric(
            operation_type=OperationType.TTS,
            operation_name="synthesize",
            latency_ms=800.0,
            status=OperationStatus.SUCCESS
        )
        
        latency_tracker.add_metric(stt_metric)
        latency_tracker.add_metric(tts_metric)
        
        # Tester récupération par type
        stt_stats = latency_tracker.get_stats(OperationType.STT)
        assert len(stt_stats) == 1
        assert "speech_to_text/transcribe" in stt_stats
        
        all_stats = latency_tracker.get_stats()
        assert len(all_stats) == 2
    
    def test_get_average_latency(self):
        """Test calcul de latence moyenne"""
        # Ajouter quelques métriques récentes
        for latency in [1000, 1500, 800]:
            metric = LatencyMetric(
                operation_type=OperationType.STT,
                operation_name="test",
                latency_ms=latency,
                status=OperationStatus.SUCCESS
            )
            latency_tracker.add_metric(metric)
        
        avg_latency = latency_tracker.get_average_latency(OperationType.STT, minutes=5)
        assert avg_latency == 1100.0  # (1000 + 1500 + 800) / 3


class TestLatencyDecorator:
    """Tests pour le décorateur de mesure de latence"""
    
    def setup_method(self):
        """Setup avant chaque test"""
        latency_tracker.metrics.clear()
        latency_tracker.enabled = True
    
    def test_sync_decorator(self):
        """Test décorateur sur méthode synchrone"""
        @measure_latency(OperationType.STT, provider="test")
        def test_sync_function():
            time.sleep(0.1)  # 100ms
            return "result"
        
        result = test_sync_function()
        
        assert result == "result"
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.operation_type == OperationType.STT
        assert metric.operation_name == "test_sync_function"
        assert metric.provider == "test"
        assert metric.status == OperationStatus.SUCCESS
        assert 90 <= metric.latency_ms <= 200  # ~100ms avec marge
    
    @pytest.mark.asyncio
    async def test_async_decorator(self):
        """Test décorateur sur méthode asynchrone"""
        @measure_latency(OperationType.TTS, provider="test")
        async def test_async_function():
            await asyncio.sleep(0.1)  # 100ms
            return "async_result"
        
        result = await test_async_function()
        
        assert result == "async_result"
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.operation_type == OperationType.TTS
        assert metric.operation_name == "test_async_function"
        assert metric.provider == "test"
        assert metric.status == OperationStatus.SUCCESS
        assert 90 <= metric.latency_ms <= 200  # ~100ms avec marge
    
    def test_decorator_with_exception(self):
        """Test décorateur quand une exception est levée"""
        @measure_latency(OperationType.SALESFORCE, provider="test")
        def test_function_with_error():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError, match="Test error"):
            test_function_with_error()
        
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.status == OperationStatus.ERROR
        assert metric.error_message == "Test error"
    
    def test_context_manager(self):
        """Test context manager pour mesure de latence"""
        with measure_latency_context(
            OperationType.RAG, 
            "custom_operation", 
            provider="test"
        ):
            time.sleep(0.05)  # 50ms
        
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.operation_type == OperationType.RAG
        assert metric.operation_name == "custom_operation"
        assert metric.provider == "test"
        assert metric.status == OperationStatus.SUCCESS
        assert 40 <= metric.latency_ms <= 100  # ~50ms avec marge


class TestLatencyConfig:
    """Tests pour la configuration de latence"""
    
    def test_configure_custom_thresholds(self):
        """Test configuration de seuils personnalisés"""
        custom_thresholds = {
            "speech_to_text": {"warning": 3000, "critical": 6000},
            "text_to_speech": {"warning": 2000, "critical": 4000}
        }
        
        latency_config.configure_custom_thresholds(custom_thresholds)
        
        # Vérifier que les seuils ont été mis à jour
        stt_warning = latency_config.thresholds.get_warning_threshold(OperationType.STT)
        stt_critical = latency_config.thresholds.get_critical_threshold(OperationType.STT)
        
        assert stt_warning == 3000
        assert stt_critical == 6000
        
        tts_warning = latency_config.thresholds.get_warning_threshold(OperationType.TTS)
        tts_critical = latency_config.thresholds.get_critical_threshold(OperationType.TTS)
        
        assert tts_warning == 2000
        assert tts_critical == 4000
    
    @patch.dict('os.environ', {
        'LATENCY_STT_WARNING_MS': '2500',
        'LATENCY_STT_CRITICAL_MS': '5500',
        'LATENCY_TTS_WARNING_MS': '1800',
        'LATENCY_TTS_CRITICAL_MS': '3500'
    })
    def test_configure_from_environment(self):
        """Test configuration depuis les variables d'environnement"""
        latency_config.configure_from_environment()
        
        stt_warning = latency_config.thresholds.get_warning_threshold(OperationType.STT)
        stt_critical = latency_config.thresholds.get_critical_threshold(OperationType.STT)
        
        assert stt_warning == 2500
        assert stt_critical == 5500
        
        tts_warning = latency_config.thresholds.get_warning_threshold(OperationType.TTS)
        tts_critical = latency_config.thresholds.get_critical_threshold(OperationType.TTS)
        
        assert tts_warning == 1800
        assert tts_critical == 3500


@pytest.mark.asyncio
class TestLatencyReporters:
    """Tests pour les reporters de latence"""
    
    def test_prometheus_reporter_format(self):
        """Test formatage Prometheus"""
        reporter = PrometheusReporter("http://localhost:9091", "test_job")
        
        metric = LatencyMetric(
            operation_type=OperationType.STT,
            operation_name="transcribe",
            latency_ms=1500.0,
            status=OperationStatus.SUCCESS,
            provider="google",
            call_sid="CA123"
        )
        
        formatted = reporter._format_metric_for_prometheus(metric)
        
        assert "latency_ms{" in formatted
        assert 'operation_type="speech_to_text"' in formatted
        assert 'operation_name="transcribe"' in formatted
        assert 'status="success"' in formatted
        assert 'provider="google"' in formatted
        assert 'call_sid="CA123"' in formatted
        assert "1500.0" in formatted
    
    async def test_slack_reporter_cooldown(self):
        """Test cooldown des alertes Slack"""
        with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            
            reporter = SlackReporter("http://test.webhook", "#test")
            reporter._alert_cooldown = 1  # 1 seconde pour le test
            
            # Créer une métrique critique
            metric = LatencyMetric(
                operation_type=OperationType.STT,
                operation_name="test",
                latency_ms=10000.0,  # Dépasse le seuil critique
                status=OperationStatus.SUCCESS
            )
            
            # Premier appel doit envoyer l'alerte
            await reporter.report_metric(metric)
            assert mock_post.call_count == 1
            
            # Deuxième appel immédiat ne doit pas envoyer (cooldown)
            await reporter.report_metric(metric)
            assert mock_post.call_count == 1  # Pas d'appel supplémentaire
            
            # Attendre la fin du cooldown
            time.sleep(1.1)
            
            # Troisième appel doit envoyer l'alerte
            await reporter.report_metric(metric)
            assert mock_post.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])