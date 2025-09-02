import asyncio
import functools
import time
from typing import Any, Callable, Optional, Union

from utils.latency_metric import LatencyMetric, OperationType, OperationStatus
from utils.latency_tracker import latency_tracker


def measure_latency(
    operation_type: OperationType,
    operation_name: Optional[str] = None,
    provider: Optional[str] = None,
    call_sid_attr: Optional[str] = None,
    stream_sid_attr: Optional[str] = None,
    metadata: Optional[dict] = None
):
    """
    Décorateur pour mesurer la latence des méthodes synchrones et asynchrones.
    
    Args:
        operation_type: Type d'opération (STT, TTS, SALESFORCE, RAG)
        operation_name: Nom de l'opération (par défaut utilise le nom de la méthode)
        provider: Nom du fournisseur de service (e.g., "google", "openai")
        call_sid_attr: Nom de l'attribut contenant le call_sid dans self
        stream_sid_attr: Nom de l'attribut contenant le stream_sid dans self
        metadata: Métadonnées additionnelles à inclure dans la métrique
    
    Usage:
        @measure_latency(OperationType.STT, provider="google")
        async def transcribe_audio_async(self, file_name: str) -> str:
            ...
    """
    def decorator(func: Callable) -> Callable:
        operation_name_final = operation_name or func.__name__
        
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                start_time = time.perf_counter()
                status = OperationStatus.SUCCESS
                error_message = None
                
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    status = OperationStatus.ERROR
                    error_message = str(e)
                    raise
                finally:
                    end_time = time.perf_counter()
                    latency_ms = (end_time - start_time) * 1000
                    
                    # Extraire call_sid et stream_sid si disponibles
                    call_sid = None
                    stream_sid = None
                    if args and hasattr(args[0], '__dict__'):  # Premier argument est généralement 'self'
                        obj = args[0]
                        if call_sid_attr and hasattr(obj, call_sid_attr):
                            call_sid = getattr(obj, call_sid_attr)
                        if stream_sid_attr and hasattr(obj, stream_sid_attr):
                            stream_sid = getattr(obj, stream_sid_attr)
                    
                    metric = LatencyMetric(
                        operation_type=operation_type,
                        operation_name=operation_name_final,
                        latency_ms=latency_ms,
                        status=status,
                        call_sid=call_sid,
                        stream_sid=stream_sid,
                        provider=provider,
                        error_message=error_message,
                        metadata=metadata or {}
                    )
                    
                    latency_tracker.add_metric(metric)
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                start_time = time.perf_counter()
                status = OperationStatus.SUCCESS
                error_message = None
                
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    status = OperationStatus.ERROR
                    error_message = str(e)
                    raise
                finally:
                    end_time = time.perf_counter()
                    latency_ms = (end_time - start_time) * 1000
                    
                    # Extraire call_sid et stream_sid si disponibles
                    call_sid = None
                    stream_sid = None
                    if args and hasattr(args[0], '__dict__'):  # Premier argument est généralement 'self'
                        obj = args[0]
                        if call_sid_attr and hasattr(obj, call_sid_attr):
                            call_sid = getattr(obj, call_sid_attr)
                        if stream_sid_attr and hasattr(obj, stream_sid_attr):
                            stream_sid = getattr(obj, stream_sid_attr)
                    
                    metric = LatencyMetric(
                        operation_type=operation_type,
                        operation_name=operation_name_final,
                        latency_ms=latency_ms,
                        status=status,
                        call_sid=call_sid,
                        stream_sid=stream_sid,
                        provider=provider,
                        error_message=error_message,
                        metadata=metadata or {}
                    )
                    
                    latency_tracker.add_metric(metric)
            
            return sync_wrapper
    
    return decorator


class LatencyContextManager:
    """Context manager pour mesurer la latence d'un bloc de code"""
    
    def __init__(
        self,
        operation_type: OperationType,
        operation_name: str,
        provider: Optional[str] = None,
        call_sid: Optional[str] = None,
        stream_sid: Optional[str] = None,
        metadata: Optional[dict] = None
    ):
        self.operation_type = operation_type
        self.operation_name = operation_name
        self.provider = provider
        self.call_sid = call_sid
        self.stream_sid = stream_sid
        self.metadata = metadata or {}
        self.start_time: Optional[float] = None
    
    def __enter__(self) -> "LatencyContextManager":
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.start_time is None:
            return
        
        end_time = time.perf_counter()
        latency_ms = (end_time - self.start_time) * 1000
        
        status = OperationStatus.SUCCESS if exc_type is None else OperationStatus.ERROR
        error_message = str(exc_val) if exc_val else None
        
        metric = LatencyMetric(
            operation_type=self.operation_type,
            operation_name=self.operation_name,
            latency_ms=latency_ms,
            status=status,
            call_sid=self.call_sid,
            stream_sid=self.stream_sid,
            provider=self.provider,
            error_message=error_message,
            metadata=self.metadata
        )
        
        latency_tracker.add_metric(metric)


# Context manager pour usage facile
def measure_latency_context(
    operation_type: OperationType,
    operation_name: str,
    provider: Optional[str] = None,
    call_sid: Optional[str] = None,
    stream_sid: Optional[str] = None,
    metadata: Optional[dict] = None
) -> LatencyContextManager:
    """
    Créer un context manager pour mesurer la latence.
    
    Usage:
        with measure_latency_context(OperationType.SALESFORCE, "complex_operation"):
            # code à mesurer
            pass
    """
    return LatencyContextManager(
        operation_type=operation_type,
        operation_name=operation_name,
        provider=provider,
        call_sid=call_sid,
        stream_sid=stream_sid,
        metadata=metadata
    )