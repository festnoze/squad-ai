"""
Tests unitaires pour le système de monitoring de latence.
"""
import asyncio
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.latency_config import latency_config
from utils.latency_decorator import measure_latency, measure_latency_context, measure_streaming_latency
from utils.latency_metric import LatencyMetric, OperationType, OperationStatus
from utils.latency_reporter import PrometheusReporter, SlackReporter, report_manager
from utils.latency_tracker import LatencyTracker, LatencyThresholds, latency_tracker

import os
from utils.latency_config import LatencyConfig

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
        latency_tracker.alert_callbacks.clear()
    
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
    
    def test_add_multiple_metrics_same_operation(self):
        """Test ajout de multiples métriques pour la même opération"""
        metrics = [
            LatencyMetric(OperationType.STT, "transcribe", 800.0, OperationStatus.SUCCESS),
            LatencyMetric(OperationType.STT, "transcribe", 1200.0, OperationStatus.SUCCESS),
            LatencyMetric(OperationType.STT, "transcribe", 900.0, OperationStatus.ERROR),
            LatencyMetric(OperationType.STT, "transcribe", 1100.0, OperationStatus.SUCCESS),
        ]
        
        for metric in metrics:
            latency_tracker.add_metric(metric)
        
        assert len(latency_tracker.metrics) == 4
        
        # Vérifier les statistiques accumulées
        key = "speech_to_text/transcribe"
        stats = latency_tracker.stats_by_operation[key]
        assert stats["count"] == 4
        assert stats["avg_time"] == 1000.0  # (800 + 1200 + 900 + 1100) / 4
        assert stats["min_time"] == 800.0
        assert stats["max_time"] == 1200.0
        assert len(stats["recent_times"]) == 4
    
    def test_metrics_deque_max_size(self):
        """Test limitation de taille du deque de métriques"""
        # Sauvegarder la taille originale
        original_maxlen = latency_tracker.metrics.maxlen
        
        # Créer un tracker avec une petite taille pour le test
        latency_tracker.metrics = deque(maxlen=3)
        
        try:
            # Ajouter plus de métriques que la taille max
            for i in range(5):
                metric = LatencyMetric(
                    operation_type=OperationType.STT,
                    operation_name=f"test_{i}",
                    latency_ms=float(i * 100),
                    status=OperationStatus.SUCCESS
                )
                latency_tracker.add_metric(metric)
            
            # Vérifier que seulement les 3 dernières métriques sont conservées
            assert len(latency_tracker.metrics) == 3
            
            # Vérifier que ce sont bien les bonnes métriques (les plus récentes)
            operation_names = [m.operation_name for m in latency_tracker.metrics]
            assert operation_names == ["test_2", "test_3", "test_4"]
        
        finally:
            # Restaurer la taille originale
            latency_tracker.metrics = deque(maxlen=original_maxlen)
    
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
    
    def test_get_recent_metrics(self):
        """Test récupération des métriques récentes"""
        # Ajouter diverses métriques
        metrics = [
            LatencyMetric(OperationType.STT, "transcribe_1", 800.0, OperationStatus.SUCCESS),
            LatencyMetric(OperationType.TTS, "synthesize_1", 600.0, OperationStatus.SUCCESS),
            LatencyMetric(OperationType.STT, "transcribe_2", 900.0, OperationStatus.ERROR),
            LatencyMetric(OperationType.RAG, "rag_query", 1200.0, OperationStatus.SUCCESS),
        ]
        
        for metric in metrics:
            latency_tracker.add_metric(metric)
        
        # Test récupération des 2 dernières
        recent = latency_tracker.get_recent_metrics(limit=2)
        assert len(recent) == 2
        assert recent[0].operation_name == "transcribe_2"
        assert recent[1].operation_name == "rag_query"
        
        # Test récupération par type d'opération
        stt_recent = latency_tracker.get_recent_metrics(limit=10, operation_type=OperationType.STT)
        assert len(stt_recent) == 2
        assert all(m.operation_type == OperationType.STT for m in stt_recent)
    
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
    
    def test_get_average_latency_no_metrics(self):
        """Test calcul de latence moyenne sans métriques"""
        avg_latency = latency_tracker.get_average_latency(OperationType.STT, minutes=5)
        assert avg_latency is None
    
    def test_get_average_latency_old_metrics(self):
        """Test calcul de latence moyenne avec métriques anciennes"""
        from datetime import datetime, timedelta, timezone
        
        # Créer une métrique ancienne (plus de 5 minutes)
        old_metric = LatencyMetric(
            operation_type=OperationType.STT,
            operation_name="test",
            latency_ms=2000.0,
            status=OperationStatus.SUCCESS
        )
        # Modifier le timestamp pour qu'il soit ancien
        old_metric.timestamp = datetime.now(timezone.utc) - timedelta(minutes=10)
        
        # Créer une métrique récente
        recent_metric = LatencyMetric(
            operation_type=OperationType.STT,
            operation_name="test",
            latency_ms=1000.0,
            status=OperationStatus.SUCCESS
        )
        
        latency_tracker.add_metric(old_metric)
        latency_tracker.add_metric(recent_metric)
        
        # Seule la métrique récente devrait être prise en compte
        avg_latency = latency_tracker.get_average_latency(OperationType.STT, minutes=5)
        assert avg_latency == 1000.0
    
    def test_threshold_checking_warning(self):
        """Test vérification des seuils d'alerte (warning)"""
        alert_triggered = []
        
        def alert_callback(metric):
            alert_triggered.append(metric)
        
        latency_tracker.add_alert_callback(alert_callback)
        
        # Créer une métrique qui dépasse le seuil warning (2000ms pour STT)
        metric = LatencyMetric(
            operation_type=OperationType.STT,
            operation_name="slow_transcribe",
            latency_ms=2500.0,  # Dépasse warning mais pas critical
            status=OperationStatus.SUCCESS
        )
        
        latency_tracker.add_metric(metric)
        
        # Vérifier que l'alerte a été déclenchée
        assert len(alert_triggered) == 1
        assert alert_triggered[0] == metric
    
    def test_threshold_checking_critical(self):
        """Test vérification des seuils d'alerte (critical)"""
        alert_triggered = []
        
        def alert_callback(metric):
            alert_triggered.append(metric)
        
        latency_tracker.add_alert_callback(alert_callback)
        
        # Créer une métrique qui dépasse le seuil critical (5000ms pour STT)
        metric = LatencyMetric(
            operation_type=OperationType.STT,
            operation_name="very_slow_transcribe",
            latency_ms=6000.0,  # Dépasse critical
            status=OperationStatus.SUCCESS
        )
        
        latency_tracker.add_metric(metric)
        
        # Vérifier que l'alerte a été déclenchée
        assert len(alert_triggered) == 1
        assert alert_triggered[0] == metric
    
    def test_threshold_checking_no_alert(self):
        """Test pas d'alerte en dessous des seuils"""
        alert_triggered = []
        
        def alert_callback(metric):
            alert_triggered.append(metric)
        
        latency_tracker.add_alert_callback(alert_callback)
        
        # Créer une métrique normale (en dessous des seuils)
        metric = LatencyMetric(
            operation_type=OperationType.STT,
            operation_name="fast_transcribe",
            latency_ms=1000.0,  # En dessous du seuil warning
            status=OperationStatus.SUCCESS
        )
        
        latency_tracker.add_metric(metric)
        
        # Vérifier qu'aucune alerte n'a été déclenchée
        assert len(alert_triggered) == 0
    
    def test_export_metrics_json(self):
        """Test export des métriques en JSON"""
        import tempfile
        import json
        
        # Ajouter quelques métriques
        metrics = [
            LatencyMetric(OperationType.STT, "transcribe", 800.0, OperationStatus.SUCCESS),
            LatencyMetric(OperationType.TTS, "synthesize", 600.0, OperationStatus.ERROR, error_message="Test error")
        ]
        
        for metric in metrics:
            latency_tracker.add_metric(metric)
        
        # Tester l'export
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            temp_path = tmp.name
        
        try:
            latency_tracker.export_metrics(temp_path, format="json")
            
            # Vérifier le contenu exporté
            with open(temp_path, 'r') as f:
                exported_data = json.load(f)
            
            assert len(exported_data) == 2
            assert exported_data[0]["operation_name"] == "transcribe"
            assert exported_data[0]["latency_ms"] == 800.0
            assert exported_data[0]["status"] == "success"
            
            assert exported_data[1]["operation_name"] == "synthesize"
            assert exported_data[1]["latency_ms"] == 600.0
            assert exported_data[1]["status"] == "error"
            assert exported_data[1]["error_message"] == "Test error"
            
        finally:
            # Nettoyer le fichier temporaire
            import os
            os.unlink(temp_path)
    
    def test_export_metrics_invalid_format(self):
        """Test export avec format invalide"""
        with pytest.raises(ValueError, match="Format non supporté"):
            latency_tracker.export_metrics("/tmp/test.xml", format="xml")
    
    def test_reset_stats(self):
        """Test remise à zéro des statistiques"""
        # Ajouter quelques métriques
        metric = LatencyMetric(
            operation_type=OperationType.STT,
            operation_name="test",
            latency_ms=1000.0,
            status=OperationStatus.SUCCESS
        )
        latency_tracker.add_metric(metric)
        
        # Vérifier qu'il y a des données
        assert len(latency_tracker.metrics) > 0
        assert len(latency_tracker.stats_by_operation) > 0
        
        # Reset
        latency_tracker.reset_stats()
        
        # Vérifier que tout est vide
        assert len(latency_tracker.metrics) == 0
        assert len(latency_tracker.stats_by_operation) == 0


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
    
    @pytest.mark.asyncio
    async def test_async_decorator_with_exception(self):
        """Test décorateur async quand une exception est levée"""
        @measure_latency(OperationType.RAG, provider="test")
        async def test_async_function_with_error():
            await asyncio.sleep(0.05)
            raise RuntimeError("Async test error")
        
        with pytest.raises(RuntimeError, match="Async test error"):
            await test_async_function_with_error()
        
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.status == OperationStatus.ERROR
        assert metric.error_message == "Async test error"
        assert 40 <= metric.latency_ms <= 100  # ~50ms avec marge
    
    def test_decorator_with_custom_operation_name(self):
        """Test décorateur avec nom d'opération personnalisé"""
        @measure_latency(OperationType.STT, operation_name="custom_transcription", provider="test")
        def test_function():
            time.sleep(0.05)
            return "done"
        
        result = test_function()
        
        assert result == "done"
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.operation_name == "custom_transcription"
        assert metric.provider == "test"
    
    def test_decorator_with_metadata(self):
        """Test décorateur avec métadonnées personnalisées"""
        custom_metadata = {"version": "1.0", "model": "gpt-4"}
        
        @measure_latency(OperationType.RAG, provider="test", metadata=custom_metadata)
        def test_function():
            time.sleep(0.02)
            return "result_with_metadata"
        
        result = test_function()
        
        assert result == "result_with_metadata"
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.metadata["version"] == "1.0"
        assert metric.metadata["model"] == "gpt-4"
    
    def test_decorator_with_call_sid_extraction(self):
        """Test extraction du call_sid depuis l'objet self"""
        class MockService:
            def __init__(self):
                self.call_sid = "CA123456789"
                self.stream_sid = "ST987654321"
            
            @measure_latency(OperationType.SALESFORCE, provider="test", 
                           call_sid_attr="call_sid", stream_sid_attr="stream_sid")
            def process_data(self):
                time.sleep(0.03)
                return "processed"
        
        service = MockService()
        result = service.process_data()
        
        assert result == "processed"
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.call_sid == "CA123456789"
        assert metric.stream_sid == "ST987654321"
    
    def test_decorator_with_missing_attributes(self):
        """Test décorateur avec attributs manquants sur self"""
        class MockService:
            def __init__(self):
                pass  # Pas d'attributs call_sid/stream_sid
            
            @measure_latency(OperationType.SALESFORCE, provider="test", 
                           call_sid_attr="call_sid", stream_sid_attr="stream_sid")
            def process_data(self):
                time.sleep(0.02)
                return "processed"
        
        service = MockService()
        result = service.process_data()
        
        assert result == "processed"
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.call_sid is None
        assert metric.stream_sid is None
    
    def test_decorator_disabled_tracking(self):
        """Test décorateur quand le tracking est désactivé"""
        latency_tracker.enabled = False
        
        @measure_latency(OperationType.STT, provider="test")
        def test_function():
            time.sleep(0.05)
            return "result"
        
        result = test_function()
        
        assert result == "result"
        assert len(latency_tracker.metrics) == 0  # Aucune métrique créée
    
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
    
    def test_context_manager_with_exception(self):
        """Test context manager avec exception"""
        with pytest.raises(KeyError, match="test_error"):
            with measure_latency_context(
                OperationType.TTS, 
                "failing_operation", 
                provider="test",
                metadata={"test": True}
            ):
                time.sleep(0.03)
                raise KeyError("test_error")
        
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.operation_name == "failing_operation"
        assert metric.status == OperationStatus.ERROR
        assert metric.error_message == "'test_error'"  # KeyError includes quotes in str()
        assert metric.metadata["test"] is True
    
    def test_context_manager_with_call_stream_ids(self):
        """Test context manager avec call_sid et stream_sid"""
        with measure_latency_context(
            OperationType.SALESFORCE, 
            "manual_operation",
            provider="test",
            call_sid="CA999888777",
            stream_sid="ST111222333"
        ):
            time.sleep(0.02)
        
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.call_sid == "CA999888777"
        assert metric.stream_sid == "ST111222333"
    
    def test_multiple_decorators_on_same_function(self):
        """Test application de multiples décorateurs (edge case)"""
        @measure_latency(OperationType.STT, provider="first")
        @measure_latency(OperationType.TTS, provider="second")  
        def test_double_decorated():
            time.sleep(0.05)
            return "double"
        
        result = test_double_decorated()
        
        assert result == "double"
        # Devrait créer 2 métriques (une pour chaque décorateur)
        assert len(latency_tracker.metrics) == 2
        
        providers = {m.provider for m in latency_tracker.metrics}
        assert "first" in providers
        assert "second" in providers


class TestLatencyConfig:
    """Tests pour la configuration de latence"""
    
    def setup_method(self):
        """Setup avant chaque test"""
        # Réinitialiser les seuils par défaut
        latency_config.thresholds = LatencyThresholds()
        latency_tracker.metrics.clear()
        latency_tracker.enabled = True
    
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

    def test_system_initialization_from_environment(self):
        """Test initialisation du système depuis les variables d'environnement"""
        # Assert
        os.environ['LATENCY_TRACKING_ENABLED'] = 'false'
        os.environ['LATENCY_LOGGING_ENABLED'] = 'true'
        os.environ['LATENCY_FILE_LOGGING_ENABLED'] = 'false'

        # Act
        config = LatencyConfig()
        config.initialize_latency_system()
        
        # Vérifier que le tracking a été désactivé
        assert not latency_tracker.enabled
        
        # Vérifier que les reporters appropriés ont été configurés
        # (Ces vérifications dépendent de l'implémentation réelle)
        assert config.is_initialized
    
    def test_default_thresholds_initialization(self):
        """Test initialisation avec les seuils par défaut"""
        # Vérifier les seuils par défaut
        default_stt_warning = latency_config.thresholds.get_warning_threshold(OperationType.STT)
        default_stt_critical = latency_config.thresholds.get_critical_threshold(OperationType.STT)
        
        assert default_stt_warning == 2000
        assert default_stt_critical == 5000
        
        default_tts_warning = latency_config.thresholds.get_warning_threshold(OperationType.TTS)
        default_tts_critical = latency_config.thresholds.get_critical_threshold(OperationType.TTS)
        
        assert default_tts_warning == 1500
        assert default_tts_critical == 3000
        
        default_rag_warning = latency_config.thresholds.get_warning_threshold(OperationType.RAG)
        default_rag_critical = latency_config.thresholds.get_critical_threshold(OperationType.RAG)
        
        assert default_rag_warning == 3000
        assert default_rag_critical == 8000
        
        default_salesforce_warning = latency_config.thresholds.get_warning_threshold(OperationType.SALESFORCE)
        default_salesforce_critical = latency_config.thresholds.get_critical_threshold(OperationType.SALESFORCE)
        
        assert default_salesforce_warning == 1000
        assert default_salesforce_critical == 3000
    
    def test_configure_invalid_thresholds(self):
        """Test configuration avec des seuils invalides"""
        # Warning supérieur à Critical
        invalid_thresholds = {
            "speech_to_text": {"warning": 5000, "critical": 3000}
        }
        
        with pytest.raises(ValueError, match="Warning threshold must be less than critical threshold"):
            latency_config.configure_custom_thresholds(invalid_thresholds)
    
    def test_configure_negative_thresholds(self):
        """Test configuration avec des seuils négatifs"""
        invalid_thresholds = {
            "speech_to_text": {"warning": -100, "critical": 1000}
        }
        
        with pytest.raises(ValueError, match="Thresholds must be positive values"):
            latency_config.configure_custom_thresholds(invalid_thresholds)
    
    def test_configure_unknown_operation_type(self):
        """Test configuration avec un type d'opération inconnu"""
        invalid_thresholds = {
            "unknown_operation": {"warning": 1000, "critical": 2000}
        }
        
        # Doit ignorer silencieusement les types d'opération inconnus
        latency_config.configure_custom_thresholds(invalid_thresholds)
        
        # Vérifier que les seuils par défaut n'ont pas changé
        stt_warning = latency_config.thresholds.get_warning_threshold(OperationType.STT)
        assert stt_warning == 2000  # Seuil par défaut
    
    @patch.dict('os.environ', {
        'LATENCY_STT_WARNING_MS': 'invalid_number',
        'LATENCY_STT_CRITICAL_MS': '5000'
    })
    def test_configure_from_environment_invalid_values(self):
        """Test configuration avec des valeurs d'environnement invalides"""
        # Ne doit pas lever d'exception, mais utiliser les valeurs par défaut
        latency_config.configure_from_environment()
        
        # Vérifier que les seuils par défaut sont conservés
        stt_warning = latency_config.thresholds.get_warning_threshold(OperationType.STT)
        stt_critical = latency_config.thresholds.get_critical_threshold(OperationType.STT)
        
        assert stt_warning == 2000  # Valeur par défaut
        assert stt_critical == 5000  # Valeur valide depuis l'environnement
    
    @patch('utils.latency_reporter.PrometheusReporter')
    @patch('utils.latency_reporter.InfluxDBReporter')
    @patch('utils.latency_reporter.SlackReporter')
    @patch.dict('os.environ', {
        'PROMETHEUS_PUSHGATEWAY_URL': 'http://localhost:9091',
        'INFLUXDB_URL': 'http://localhost:8086',
        'INFLUXDB_TOKEN': 'test_token',
        'INFLUXDB_ORG': 'test_org',
        'INFLUXDB_BUCKET': 'test_bucket',
        'SLACK_WEBHOOK_URL': 'http://test.slack.webhook',
        'SLACK_CHANNEL': '#test'
    })
    def test_initialize_external_reporters(self, mock_slack, mock_influx, mock_prometheus):
        """Test initialisation des reporters externes"""
        from utils.latency_config import LatencyConfig
        
        config = LatencyConfig()
        config.initialize_latency_system()
        
        # Vérifier que les reporters ont été créés
        mock_prometheus.assert_called_once_with('http://localhost:9091')
        mock_influx.assert_called_once_with(
            'http://localhost:8086',
            'test_token',
            'test_org',
            'test_bucket'
        )
        mock_slack.assert_called_once_with(
            'http://test.slack.webhook',
            '#test'
        )
    
    def test_threshold_manager_edge_cases(self):
        """Test cas limites du gestionnaire de seuils"""
        from utils.latency_config import ThresholdManager
        
        manager = ThresholdManager()
        
        # Test avec une opération inexistante
        unknown_warning = manager.get_warning_threshold("UNKNOWN")
        unknown_critical = manager.get_critical_threshold("UNKNOWN")
        
        assert unknown_warning is None
        assert unknown_critical is None
        
        # Test vérification de seuil pour opération inexistante
        assert not manager.exceeds_warning_threshold("UNKNOWN", 10000)
        assert not manager.exceeds_critical_threshold("UNKNOWN", 10000)


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


class TestStreamingLatencyDecorator:
    """Tests pour le décorateur de latence streaming (time to first token)"""
    
    def setup_method(self):
        """Setup avant chaque test"""
        latency_tracker.metrics.clear()
        latency_tracker.enabled = True
    
    @pytest.mark.asyncio
    async def test_async_streaming_decorator_first_token(self):
        """Test décorateur streaming sur générateur asynchrone - time to first token"""
        @measure_streaming_latency(OperationType.RAG, provider="test")
        async def test_async_streaming_function():
            await asyncio.sleep(0.1)  # Simule latence avant premier token
            yield "first_chunk"
            await asyncio.sleep(0.05)  # Simule latence entre chunks
            yield "second_chunk"
            yield "third_chunk"
        
        # Appeler la fonction directement (pas d'await) - c'est un générateur async
        generator = test_async_streaming_function()
        
        # Consommer le premier chunk
        chunks = []
        async for chunk in generator:
            chunks.append(chunk)
            if len(chunks) == 1:
                # Après le premier chunk, vérifier la métrique
                assert len(latency_tracker.metrics) == 1
                metric = latency_tracker.metrics[0]
                assert metric.operation_type == OperationType.RAG
                assert metric.operation_name == "test_async_streaming_function_first_token"
                assert metric.provider == "test"
                assert metric.status == OperationStatus.SUCCESS
                assert metric.metadata["metric_type"] == "time_to_first_token"
                assert 90 <= metric.latency_ms <= 200  # ~100ms avec marge
        
        # Vérifier que tous les chunks ont été reçus
        assert chunks == ["first_chunk", "second_chunk", "third_chunk"]
        
        # Vérifier qu'une seule métrique a été créée (pour le premier token seulement)
        assert len(latency_tracker.metrics) == 1
    
    def test_sync_streaming_decorator_first_token(self):
        """Test décorateur streaming sur générateur synchrone - time to first token"""
        @measure_streaming_latency(OperationType.RAG, provider="test")
        def test_sync_streaming_function():
            time.sleep(0.1)  # Simule latence avant premier token
            yield "first_chunk"
            time.sleep(0.05)  # Simule latence entre chunks
            yield "second_chunk"
            yield "third_chunk"
        
        generator = test_sync_streaming_function()
        
        # Consommer le premier chunk
        chunks = []
        for chunk in generator:
            chunks.append(chunk)
            if len(chunks) == 1:
                # Après le premier chunk, vérifier la métrique
                assert len(latency_tracker.metrics) == 1
                metric = latency_tracker.metrics[0]
                assert metric.operation_type == OperationType.RAG
                assert metric.operation_name == "test_sync_streaming_function_first_token"
                assert metric.provider == "test"
                assert metric.status == OperationStatus.SUCCESS
                assert metric.metadata["metric_type"] == "time_to_first_token"
                assert 90 <= metric.latency_ms <= 200  # ~100ms avec marge
        
        # Vérifier que tous les chunks ont été reçus
        assert chunks == ["first_chunk", "second_chunk", "third_chunk"]
        
        # Vérifier qu'une seule métrique a été créée
        assert len(latency_tracker.metrics) == 1
    
    @pytest.mark.asyncio
    async def test_async_streaming_decorator_with_error_before_first_token(self):
        """Test gestion d'erreur avant le premier token"""
        @measure_streaming_latency(OperationType.RAG, provider="test")
        async def test_failing_streaming_function():
            await asyncio.sleep(0.1)  # Simule latence
            raise ValueError("Error before first token")
            yield "never_reached"  # Ne sera jamais exécuté
        
        generator = test_failing_streaming_function()
        
        with pytest.raises(ValueError, match="Error before first token"):
            async for chunk in generator:
                pass  # Ne devrait jamais être atteint
        
        # Vérifier qu'une métrique d'erreur a été créée
        assert len(latency_tracker.metrics) == 1
        metric = latency_tracker.metrics[0]
        assert metric.status == OperationStatus.ERROR
        assert metric.error_message == "Error before first token"
        assert metric.metadata["metric_type"] == "time_to_first_token"
        assert 90 <= metric.latency_ms <= 200  # ~100ms avec marge
    
    @pytest.mark.asyncio
    async def test_async_streaming_decorator_with_error_after_first_token(self):
        """Test gestion d'erreur après le premier token"""
        @measure_streaming_latency(OperationType.RAG, provider="test")
        async def test_failing_after_first_streaming_function():
            await asyncio.sleep(0.1)  # Simule latence avant premier token
            yield "first_chunk"
            await asyncio.sleep(0.05)
            raise ValueError("Error after first token")
            yield "never_reached"
        
        generator = test_failing_after_first_streaming_function()
        
        chunks = []
        with pytest.raises(ValueError, match="Error after first token"):
            async for chunk in generator:
                chunks.append(chunk)
        
        # Vérifier qu'on a reçu le premier chunk
        assert chunks == ["first_chunk"]
        
        # Vérifier qu'une métrique de succès a été créée pour le premier token
        assert len(latency_tracker.metrics) == 1
        metric = latency_tracker.metrics[0]
        assert metric.status == OperationStatus.SUCCESS  # Premier token réussi
        assert metric.error_message is None
        assert metric.metadata["metric_type"] == "time_to_first_token"
    
    @pytest.mark.asyncio
    async def test_async_streaming_decorator_with_empty_generator(self):
        """Test décorateur sur générateur vide"""
        @measure_streaming_latency(OperationType.RAG, provider="test")
        async def test_empty_streaming_function():
            await asyncio.sleep(0.1)  # Simule latence
            return
            yield "never_reached"  # Ne sera jamais exécuté
        
        generator = test_empty_streaming_function()
        
        chunks = []
        async for chunk in generator:
            chunks.append(chunk)
        
        # Vérifier qu'aucun chunk n'a été reçu
        assert chunks == []
        
        # Vérifier qu'aucune métrique n'a été créée (pas de premier token)
        assert len(latency_tracker.metrics) == 0
    
    @pytest.mark.asyncio
    async def test_async_streaming_decorator_with_non_generator(self):
        """Test décorateur sur fonction qui ne retourne pas un générateur"""
        # Ce test n'est plus valide car le décorateur streaming s'attend à ce que
        # la fonction décorée soit un générateur async. Si elle n'en est pas une,
        # elle doit lever une exception. Nous testons donc ce comportement.
        @measure_streaming_latency(OperationType.RAG, provider="test")
        async def test_non_generator_function():
            await asyncio.sleep(0.1)
            return "not_a_generator"
        
        # Essayer d'utiliser la fonction comme un générateur doit lever une exception
        generator = test_non_generator_function()
        
        chunks = []
        with pytest.raises(TypeError):  # Ne peut pas itérer sur une string
            async for chunk in generator:
                chunks.append(chunk)
    
    def test_sync_streaming_decorator_with_non_generator(self):
        """Test décorateur sync sur fonction qui ne retourne pas un générateur"""
        @measure_streaming_latency(OperationType.RAG, provider="test")
        def test_sync_non_generator_function():
            time.sleep(0.1)
            return "not_a_generator"
        
        # Pour une fonction sync non-générateur, le décorateur va traiter le string comme itérable
        # ce qui va créer des caractères individuels. Ce n'est pas idéal mais c'est le comportement attendu
        result = test_sync_non_generator_function()
        
        chunks = []
        for chunk in result:
            chunks.append(chunk)
        
        # Vérifie que la string a été "streamée" caractère par caractère
        expected_chars = list("not_a_generator")
        assert chunks == expected_chars
        
        # Vérifie qu'une métrique a été créée pour le "premier token" (premier caractère)
        assert len(latency_tracker.metrics) == 1
        metric = latency_tracker.metrics[0]
        assert metric.metadata["metric_type"] == "time_to_first_token"
    
    @pytest.mark.asyncio
    async def test_streaming_decorator_with_call_sid_extraction(self):
        """Test extraction du call_sid depuis l'objet self"""
        class MockRAGClient:
            def __init__(self):
                self.call_sid = "CA123456789"
                self.stream_sid = "ST987654321"
            
            @measure_streaming_latency(OperationType.RAG, provider="test", 
                                     call_sid_attr="call_sid", stream_sid_attr="stream_sid")
            async def mock_streaming_method(self):
                await asyncio.sleep(0.05)
                yield "test_chunk"
        
        client = MockRAGClient()
        generator = client.mock_streaming_method()
        
        chunks = []
        async for chunk in generator:
            chunks.append(chunk)
        
        # Vérifier la métrique avec call_sid et stream_sid
        assert len(latency_tracker.metrics) == 1
        metric = latency_tracker.metrics[0]
        assert metric.call_sid == "CA123456789"
        assert metric.stream_sid == "ST987654321"
        assert metric.provider == "test"


@pytest.mark.asyncio 
class TestLatencySystemIntegration:
    """Tests d'intégration pour le système complet de latence"""
    
    def setup_method(self):
        """Setup avant chaque test"""
        latency_tracker.metrics.clear()
        latency_tracker.enabled = True
        latency_tracker.alert_callbacks.clear()
        # Réinitialiser les seuils par défaut
        latency_config.thresholds = LatencyThresholds()
    
    async def test_full_system_workflow_sync_function(self):
        """Test workflow complet : mesure sync -> tracker -> seuils -> export"""
        import tempfile
        import json
        
        # Configuration d'un callback d'alerte
        alerts_triggered = []
        def alert_callback(metric):
            alerts_triggered.append(metric)
        
        latency_tracker.add_alert_callback(alert_callback)
        
        # Fonction simulant une opération STT lente
        @measure_latency(OperationType.STT, provider="google", metadata={"test_mode": True})
        def slow_transcription():
            time.sleep(0.12)  # 120ms - dépasse le seuil warning par défaut (100ms dans nos tests)
            return "transcribed text"
        
        # Exécuter la fonction
        result = slow_transcription()
        
        # Vérifications
        assert result == "transcribed text"
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.operation_type == OperationType.STT
        assert metric.provider == "google"
        assert metric.metadata["test_mode"] is True
        assert metric.status == OperationStatus.SUCCESS
        assert 100 <= metric.latency_ms <= 200
        
        # Vérifier les statistiques
        stats = latency_tracker.get_stats()
        assert len(stats) == 1
        assert "speech_to_text/slow_transcription" in stats
        
        # Export vers fichier
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            temp_path = tmp.name
        
        try:
            latency_tracker.export_metrics(temp_path, format="json")
            
            # Vérifier le contenu exporté
            with open(temp_path, 'r') as f:
                exported_data = json.load(f)
            
            assert len(exported_data) == 1
            assert exported_data[0]["provider"] == "google"
            assert exported_data[0]["metadata"]["test_mode"] is True
            
        finally:
            import os
            os.unlink(temp_path)
    
    async def test_full_system_workflow_async_streaming_function(self):
        """Test workflow complet : mesure streaming async -> tracker -> time to first token"""
        # Callback pour alertes
        alerts_triggered = []
        def alert_callback(metric):
            alerts_triggered.append(metric)
        
        latency_tracker.add_alert_callback(alert_callback)
        
        # Fonction simulant une requête RAG streaming
        @measure_streaming_latency(OperationType.RAG, provider="studi_rag", 
                                 metadata={"query_type": "complex"})
        async def rag_streaming_query():
            await asyncio.sleep(0.08)  # 80ms avant premier token
            yield "Premier chunk de réponse"
            await asyncio.sleep(0.03)  # Entre les chunks
            yield "Deuxième chunk"
            yield "Troisième chunk"
        
        # Exécuter la fonction streaming
        generator = rag_streaming_query()
        chunks = []
        
        async for chunk in generator:
            chunks.append(chunk)
        
        # Vérifications
        assert chunks == ["Premier chunk de réponse", "Deuxième chunk", "Troisième chunk"]
        assert len(latency_tracker.metrics) == 1
        
        metric = latency_tracker.metrics[0]
        assert metric.operation_type == OperationType.RAG
        assert metric.operation_name == "rag_streaming_query_first_token"
        assert metric.provider == "studi_rag"
        assert metric.metadata["query_type"] == "complex"
        assert metric.metadata["metric_type"] == "time_to_first_token"
        assert metric.status == OperationStatus.SUCCESS
        assert 70 <= metric.latency_ms <= 120  # ~80ms avec marge
        
        # Vérifier les statistiques par type
        rag_stats = latency_tracker.get_stats(OperationType.RAG)
        assert len(rag_stats) == 1
        assert "rag_inference/rag_streaming_query_first_token" in rag_stats
    
    async def test_full_system_multiple_operations_with_thresholds(self):
        """Test système complet avec multiples opérations et vérification de seuils"""
        # Configurer des seuils personnalisés pour les tests
        custom_thresholds = {
            "speech_to_text": {"warning": 100, "critical": 200},
            "text_to_speech": {"warning": 80, "critical": 150},
            "rag_inference": {"warning": 200, "critical": 400}
        }
        latency_config.configure_custom_thresholds(custom_thresholds)
        
        # Callback pour capturer les alertes
        alerts_triggered = []
        def alert_callback(metric):
            alerts_triggered.append(metric)
        
        latency_tracker.add_alert_callback(alert_callback)
        
        # Créer diverses fonctions avec différentes latences
        @measure_latency(OperationType.STT, provider="google")
        def fast_transcription():
            time.sleep(0.05)  # 50ms - OK
            return "fast result"
        
        @measure_latency(OperationType.TTS, provider="openai")  
        def warning_synthesis():
            time.sleep(0.12)  # 120ms - dépasse warning (80ms) mais pas critical (150ms)
            return "warning audio"
        
        @measure_latency(OperationType.RAG, provider="test")
        def critical_rag_query():
            time.sleep(0.45)  # 450ms - dépasse critical (400ms)
            return "critical result"
        
        # Exécuter les fonctions
        result1 = fast_transcription()
        result2 = warning_synthesis()
        result3 = critical_rag_query()
        
        # Vérifications des résultats
        assert result1 == "fast result"
        assert result2 == "warning audio"  
        assert result3 == "critical result"
        
        # Vérifier qu'on a 3 métriques
        assert len(latency_tracker.metrics) == 3
        
        # Vérifier les alertes déclenchées
        # Fast transcription ne devrait pas déclencher d'alerte
        # Warning synthesis devrait déclencher une alerte warning
        # Critical RAG query devrait déclencher une alerte critical
        assert len(alerts_triggered) == 2
        
        warning_alert = next(a for a in alerts_triggered if a.operation_type == OperationType.TTS)
        critical_alert = next(a for a in alerts_triggered if a.operation_type == OperationType.RAG)
        
        assert warning_alert.provider == "openai"
        assert 100 <= warning_alert.latency_ms <= 200
        
        assert critical_alert.provider == "test"
        assert 400 <= critical_alert.latency_ms <= 500
        
        # Vérifier les statistiques globales
        all_stats = latency_tracker.get_stats()
        assert len(all_stats) == 3
        
        # Vérifier les métriques récentes par type
        stt_metrics = latency_tracker.get_recent_metrics(operation_type=OperationType.STT)
        tts_metrics = latency_tracker.get_recent_metrics(operation_type=OperationType.TTS)
        rag_metrics = latency_tracker.get_recent_metrics(operation_type=OperationType.RAG)
        
        assert len(stt_metrics) == 1
        assert len(tts_metrics) == 1
        assert len(rag_metrics) == 1
        
        # Vérifier les latences moyennes
        stt_avg = latency_tracker.get_average_latency(OperationType.STT, minutes=5)
        tts_avg = latency_tracker.get_average_latency(OperationType.TTS, minutes=5)
        rag_avg = latency_tracker.get_average_latency(OperationType.RAG, minutes=5)
        
        assert 40 <= stt_avg <= 80  # ~50ms
        assert 100 <= tts_avg <= 150  # ~120ms 
        assert 400 <= rag_avg <= 500  # ~450ms
    
    async def test_full_system_with_errors_and_recovery(self):
        """Test système complet avec gestion d'erreurs"""
        errors_caught = []
        def alert_callback(metric):
            if metric.status == OperationStatus.ERROR:
                errors_caught.append(metric)
        
        latency_tracker.add_alert_callback(alert_callback)
        
        # Fonction qui échoue
        @measure_latency(OperationType.SALESFORCE, provider="salesforce")
        def failing_salesforce_call():
            time.sleep(0.05)
            raise ConnectionError("API endpoint unavailable")
        
        # Fonction qui réussit après l'erreur
        @measure_latency(OperationType.SALESFORCE, provider="salesforce")
        def successful_salesforce_call():
            time.sleep(0.03)
            return {"status": "success", "data": "retrieved"}
        
        # Exécuter la fonction qui échoue
        with pytest.raises(ConnectionError, match="API endpoint unavailable"):
            failing_salesforce_call()
        
        # Exécuter la fonction qui réussit
        result = successful_salesforce_call()
        
        assert result["status"] == "success"
        
        # Vérifications
        assert len(latency_tracker.metrics) == 2
        assert len(errors_caught) == 1
        
        # Vérifier la métrique d'erreur
        error_metric = errors_caught[0]
        assert error_metric.operation_type == OperationType.SALESFORCE
        assert error_metric.status == OperationStatus.ERROR
        assert error_metric.error_message == "API endpoint unavailable"
        assert 40 <= error_metric.latency_ms <= 80
        
        # Vérifier la métrique de succès
        success_metrics = [m for m in latency_tracker.metrics if m.status == OperationStatus.SUCCESS]
        assert len(success_metrics) == 1
        success_metric = success_metrics[0]
        assert success_metric.error_message is None
        assert 20 <= success_metric.latency_ms <= 60
        
        # Vérifier les statistiques incluent les deux
        salesforce_stats = latency_tracker.get_stats(OperationType.SALESFORCE)
        assert len(salesforce_stats) == 2  # Une pour chaque fonction
    
    async def test_full_system_mixed_sync_async_operations(self):
        """Test système avec mélange d'opérations sync/async et streaming/non-streaming"""
        
        # Mix de toutes les opérations possibles
        @measure_latency(OperationType.STT, provider="google")
        def sync_stt():
            time.sleep(0.08)
            return "sync transcription"
        
        @measure_latency(OperationType.TTS, provider="openai")
        async def async_tts():
            await asyncio.sleep(0.06)
            return "async synthesis"
        
        @measure_streaming_latency(OperationType.RAG, provider="studi_rag")
        def sync_streaming_rag():
            time.sleep(0.1)
            yield "sync chunk 1"
            time.sleep(0.02)
            yield "sync chunk 2"
        
        @measure_streaming_latency(OperationType.RAG, provider="studi_rag")
        async def async_streaming_rag():
            await asyncio.sleep(0.12)
            yield "async chunk 1"
            await asyncio.sleep(0.03)
            yield "async chunk 2"
        
        # Exécuter toutes les opérations
        result1 = sync_stt()
        result2 = await async_tts()
        
        sync_chunks = []
        for chunk in sync_streaming_rag():
            sync_chunks.append(chunk)
        
        async_chunks = []
        async_generator = async_streaming_rag()
        async for chunk in async_generator:
            async_chunks.append(chunk)
        
        # Vérifications des résultats
        assert result1 == "sync transcription"
        assert result2 == "async synthesis"
        assert sync_chunks == ["sync chunk 1", "sync chunk 2"]
        assert async_chunks == ["async chunk 1", "async chunk 2"]
        
        # Vérifier qu'on a 4 métriques
        assert len(latency_tracker.metrics) == 4
        
        # Vérifier les types de métriques
        stt_metrics = [m for m in latency_tracker.metrics if m.operation_type == OperationType.STT]
        tts_metrics = [m for m in latency_tracker.metrics if m.operation_type == OperationType.TTS]
        rag_metrics = [m for m in latency_tracker.metrics if m.operation_type == OperationType.RAG]
        
        assert len(stt_metrics) == 1
        assert len(tts_metrics) == 1
        assert len(rag_metrics) == 2  # 2 requêtes RAG streaming
        
        # Vérifier les métriques streaming ont le bon suffixe et metadata
        for rag_metric in rag_metrics:
            assert rag_metric.operation_name.endswith("_first_token")
            assert rag_metric.metadata["metric_type"] == "time_to_first_token"
        
        # Vérifier les latences sont cohérentes
        stt_metric = stt_metrics[0]
        tts_metric = tts_metrics[0]
        
        assert 70 <= stt_metric.latency_ms <= 120  # ~80ms
        assert 50 <= tts_metric.latency_ms <= 100  # ~60ms
        
        sync_rag_metric = next(m for m in rag_metrics if "sync_streaming" in m.operation_name)
        async_rag_metric = next(m for m in rag_metrics if "async_streaming" in m.operation_name)
        
        assert 90 <= sync_rag_metric.latency_ms <= 150  # ~100ms
        assert 110 <= async_rag_metric.latency_ms <= 170  # ~120ms
    
    async def test_system_performance_with_many_metrics(self):
        """Test performance du système avec beaucoup de métriques"""
        # Générer beaucoup de métriques rapidement
        @measure_latency(OperationType.STT, provider="test")
        def fast_operation():
            time.sleep(0.001)  # 1ms
            return "fast"
        
        start_time = time.perf_counter()
        
        # Exécuter 1000 opérations
        for i in range(1000):
            fast_operation()
        
        end_time = time.perf_counter()
        total_time = (end_time - start_time) * 1000  # en ms
        
        # Vérifier que le système peut gérer 1000 métriques rapidement
        # L'overhead ne devrait pas être énorme
        assert total_time < 5000  # Moins de 5 secondes pour 1000 opérations
        
        # Vérifier qu'on a bien toutes les métriques (limité par deque maxlen=10000)
        assert len(latency_tracker.metrics) == 1000
        
        # Vérifier que les statistiques sont correctes
        stats = latency_tracker.get_stats()
        assert "speech_to_text/fast_operation" in stats
        
        # Vérifier que la latence moyenne est cohérente
        avg_latency = latency_tracker.get_average_latency(OperationType.STT, minutes=5)
        assert avg_latency is not None
        assert avg_latency < 10  # Très rapide
        
        # Vérifier que get_recent_metrics avec limite fonctionne
        recent_50 = latency_tracker.get_recent_metrics(limit=50)
        assert len(recent_50) == 50
    
    async def test_system_cleanup_and_reset(self):
        """Test nettoyage et remise à zéro du système"""
        # Ajouter quelques métriques et statistiques
        @measure_latency(OperationType.STT, provider="test")
        def test_function():
            time.sleep(0.01)
            return "test"
        
        for _ in range(5):
            test_function()
        
        # Vérifier que des données existent
        assert len(latency_tracker.metrics) == 5
        assert len(latency_tracker.get_stats()) > 0
        
        # Reset du système
        latency_tracker.reset_stats()
        
        # Vérifier que tout est nettoyé
        assert len(latency_tracker.metrics) == 0
        assert len(latency_tracker.get_stats()) == 0
        
        # Vérifier que le système continue de fonctionner après reset
        test_function()
        assert len(latency_tracker.metrics) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])