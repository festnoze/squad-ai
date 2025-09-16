# Running the Application

This guide explains how to start and run the PIC Prospect Incoming Callbot application.

## Prerequisites

Before running the application, ensure you have:

1. Completed the [installation](installation.md) steps
2. Configured all [environment variables](configuration.md)
3. Set up your external service credentials (Twilio, Google Cloud, etc.)

## Development Server

### Using uvicorn (Recommended)
```bash
uvicorn app.api.startup:app --reload --host 0.0.0.0 --port 8080
```

### Using Python module
```bash
python -m app.api.startup
```

### Development with auto-reload
```bash
uvicorn app.api.startup:app --reload --log-level debug
```

## Production Deployment

### Using Docker
```bash
# Build the Docker image
docker build -t prospect-callbot .

# Run the container
docker run -p 8080:8080 --env-file .env prospect-callbot
```

### Using Docker Compose
```bash
docker-compose up -d
```

## Service Verification

Once the application is running, verify the services:

### Health Check
```bash
curl http://localhost:8080/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00Z",
  "version": "1.0.0"
}
```

### API Documentation
Visit the interactive API documentation:
- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc

## Testing the Phone Integration

### Twilio Webhook Configuration
Configure your Twilio phone number to point to your application:

1. **Voice Webhook URL**: `https://your-domain.com/api/callbot/incoming-call`
2. **HTTP Method**: POST

### Testing Incoming Calls
1. Call your configured Twilio phone number
2. Monitor logs for call processing
3. Check audio files in `static/incoming_audio/` and `static/outgoing_audio/`

## Monitoring and Logs

### Application Logs
```bash
# View real-time logs
tail -f outputs/logs/app.log

# View specific log level
grep "ERROR" outputs/logs/app.log
```

### Audio Processing Logs
Monitor audio file generation:
```bash
ls -la static/incoming_audio/
ls -la static/outgoing_audio/
```

### WebSocket Connections
Monitor active WebSocket connections via the logs or health endpoints.

## Common Issues

### Port Already in Use
```bash
# Find process using port 8080
lsof -i :8080

# Kill the process
kill -9 <PID>
```

### Missing Environment Variables
Check that all required environment variables are set:
```bash
python -c "from app.utils.envvar import validate_env; validate_env()"
```

### Twilio Webhook Errors
- Ensure your application is publicly accessible (use ngrok for local development)
- Verify webhook URLs in Twilio console
- Check firewall and security group settings

### Google Cloud Authentication
```bash
# Test Google Cloud credentials
gcloud auth list
gcloud auth activate-service-account --key-file=path/to/credentials.json
```

## Development Tools

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/agents/test_lead_agent.py
```

### Code Quality
```bash
# Lint the code
pylint app/

# Format the code
black app/
isort app/
```

## Debugging

### Debug Mode
Start the application in debug mode:
```bash
uvicorn app.api.startup:app --reload --log-level debug
```

### Interactive Debugging
Use Python debugger in your code:
```python
import pdb; pdb.set_trace()
```

### Performance Profiling
Monitor application performance:
```bash
# Install profiling tools
pip install py-spy

# Profile the running application
py-spy record -o profile.svg --pid <PID>
```

## Stopping the Application

### Development Server
Press `Ctrl+C` to stop the uvicorn server.

### Docker
```bash
# Stop running container
docker stop <container_id>

# Stop and remove with Docker Compose
docker-compose down
```

## Next Steps

Once your application is running successfully:

1. [Test the API endpoints](../api/endpoints.md)
2. [Configure agent behaviors](../architecture/agents.md)
3. [Set up monitoring](../development/testing.md)
4. [Deploy to production](../development/deployment.md)