# Système de Monitoring de Latence

Ce document décrit le système de monitoring de latence implémenté pour mesurer et surveiller les performances des opérations critiques du Prospect Incoming Callbot.

## Vue d'ensemble

Le système mesure automatiquement la latence des opérations suivantes :
- **STT (Speech-to-Text)** : Transcription audio via Google, OpenAI ou Hybrid
- **TTS (Text-to-Speech)** : Synthèse vocale via Google ou OpenAI
- **Salesforce API** : Toutes les opérations API Salesforce
- **RAG (AI Inference)** : Requêtes d'inférence IA

## Architecture

### Composants principaux

1. **LatencyMetric** : Modèle de données pour une mesure de latence
2. **LatencyTracker** : Service central de collecte et analyse des métriques
3. **LatencyDecorator** : Décorateur pour marquer les méthodes à mesurer automatiquement
4. **LatencyReporter** : Export vers systèmes de monitoring externes
5. **LatencyConfig** : Configuration et initialisation du système

### Flux de données

```
Méthode décorée → LatencyDecorator → LatencyMetric → LatencyTracker → LatencyReporter → Monitoring externe
```

## Configuration

### Variables d'environnement

Ajoutez ces variables à votre fichier `.env` :

```bash
# Activation du monitoring
LATENCY_TRACKING_ENABLED=true
LATENCY_LOGGING_ENABLED=true
LATENCY_FILE_LOGGING_ENABLED=true
LATENCY_METRICS_FILE_PATH=outputs/logs/latency_metrics.jsonl

# Seuils de latence (millisecondes)
LATENCY_STT_WARNING_MS=2000
LATENCY_STT_CRITICAL_MS=5000
LATENCY_TTS_WARNING_MS=1500
LATENCY_TTS_CRITICAL_MS=3000
LATENCY_SALESFORCE_WARNING_MS=1000
LATENCY_SALESFORCE_CRITICAL_MS=3000
LATENCY_RAG_WARNING_MS=3000
LATENCY_RAG_CRITICAL_MS=8000

# Systèmes de monitoring externes (optionnel)
PROMETHEUS_PUSHGATEWAY_URL=http://localhost:9091
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your_token
INFLUXDB_ORG=your_org
INFLUXDB_BUCKET=latency_metrics
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK
SLACK_CHANNEL=#alerts
```

### Seuils par défaut

| Opération | Warning (ms) | Critical (ms) |
|-----------|--------------|---------------|
| STT       | 2000         | 5000          |
| TTS       | 1500         | 3000          |
| Salesforce| 1000         | 3000          |
| RAG       | 3000         | 8000          |

## Utilisation

### Automatique

Le système est automatiquement initialisé au démarrage de l'application et les décorateurs sont déjà appliqués aux méthodes critiques.

### Décorateur manuel

Pour mesurer une nouvelle méthode :

```python
from utils.latency_decorator import measure_latency
from utils.latency_metric import OperationType

@measure_latency(OperationType.SALESFORCE, provider="salesforce")
async def my_salesforce_method(self):
    # Votre code ici
    pass
```

### Context manager

Pour mesurer un bloc de code spécifique :

```python
from utils.latency_decorator import measure_latency_context
from utils.latency_metric import OperationType

with measure_latency_context(OperationType.RAG, "custom_operation"):
    # Code à mesurer
    result = complex_operation()
```

### Accès aux métriques

```python
from utils.latency_tracker import latency_tracker

# Obtenir les statistiques
stats = latency_tracker.get_stats()

# Obtenir les métriques récentes
recent_metrics = latency_tracker.get_recent_metrics(limit=50)

# Obtenir la latence moyenne sur les 5 dernières minutes
avg_latency = latency_tracker.get_average_latency(OperationType.STT, minutes=5)

# Exporter toutes les métriques
latency_tracker.export_metrics("latency_export.json")
```

## Monitoring externe

### Prometheus

Le système peut exporter les métriques vers Prometheus via un pushgateway :

```python
from utils.latency_reporter import PrometheusReporter, report_manager

reporter = PrometheusReporter("http://prometheus-pushgateway:9091")
report_manager.add_reporter(reporter)
```

### InfluxDB

Export vers InfluxDB :

```python
from utils.latency_reporter import InfluxDBReporter, report_manager

reporter = InfluxDBReporter(
    influxdb_url="http://influxdb:8086",
    token="your_token",
    org="your_org",
    bucket="latency_metrics"
)
report_manager.add_reporter(reporter)
```

### Alertes Slack

Configuration des alertes Slack pour les dépassements critiques :

```python
from utils.latency_reporter import SlackReporter, report_manager

reporter = SlackReporter(
    webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK",
    channel="#alerts"
)
report_manager.add_reporter(reporter)
```

## Format des métriques

### Structure JSON

```json
{
  "operation_type": "speech_to_text",
  "operation_name": "transcribe_audio_async",
  "latency_ms": 1500.0,
  "status": "success",
  "timestamp": "2025-01-01T12:00:00Z",
  "call_sid": "CA123456789",
  "stream_sid": "ST987654321",
  "provider": "google",
  "error_message": null,
  "metadata": {}
}
```

### Champs disponibles

- `operation_type` : Type d'opération (speech_to_text, text_to_speech, salesforce_api, rag_inference)
- `operation_name` : Nom de la méthode/opération
- `latency_ms` : Temps d'exécution en millisecondes
- `status` : Statut (success, error, timeout)
- `timestamp` : Horodatage UTC
- `call_sid` : Identifiant d'appel Twilio (si disponible)
- `stream_sid` : Identifiant de stream Twilio (si disponible)
- `provider` : Fournisseur de service (google, openai, salesforce, etc.)
- `error_message` : Message d'erreur (si status = error)
- `metadata` : Métadonnées additionnelles

## Alertes

### Seuils d'alerte

- **Warning** : Latence élevée, monitoring nécessaire
- **Critical** : Latence très élevée, action immédiate requise

### Actions automatiques

Quand un seuil critique est dépassé :
1. Log d'alerte dans les journaux
2. Notification Slack (si configuré)
3. Export vers systèmes de monitoring
4. Métriques sauvegardées dans le fichier de métriques

## Fichiers de logs

### Fichier principal

Les métriques sont sauvegardées en JSONL dans :
```
outputs/logs/latency_metrics.jsonl
```

Chaque ligne est une métrique JSON.

### Logs applicatifs

Les alertes et informations sont également dans les logs standards de l'application.

## Performance

### Impact sur les performances

- Overhead négligeable (~0.1ms par mesure)
- Mesures asynchrones pour éviter les blocages
- Mémoire limitée (10K métriques max en mémoire)

### Optimisations

- Cache des calculs statistiques
- Export en batch vers les systèmes externes
- Cooldown des alertes pour éviter le spam

## Dépannage

### Problèmes courants

1. **Métriques non collectées**
   - Vérifier `LATENCY_TRACKING_ENABLED=true`
   - Vérifier que les décorateurs sont appliqués

2. **Pas d'alertes Slack**
   - Vérifier la configuration du webhook
   - Vérifier les seuils critiques

3. **Erreurs d'export**
   - Vérifier la connectivité aux systèmes externes
   - Vérifier les credentials InfluxDB/Prometheus

### Debug

Activer les logs de debug :

```python
import logging
logging.getLogger("utils.latency_tracker").setLevel(logging.DEBUG)
logging.getLogger("utils.latency_reporter").setLevel(logging.DEBUG)
```

## Tests

Exécuter les tests unitaires :

```bash
pytest tests/utils/test_latency_system.py -v
```

## Maintenance

### Rotation des logs

Les fichiers de métriques peuvent grossir rapidement. Configurez une rotation :

```bash
# Exemple de rotation quotidienne
logrotate -f latency_metrics.conf
```

### Nettoyage périodique

```python
# Réinitialiser les statistiques
latency_tracker.reset_stats()

# Nettoyer les anciennes métriques
latency_tracker.metrics.clear()
```

## Évolutions futures

- Dashboard web temps réel
- Analyse de tendances automatique
- Prédiction de performance
- Intégration avec plus de systèmes de monitoring
- Alertes personnalisées par règles métier