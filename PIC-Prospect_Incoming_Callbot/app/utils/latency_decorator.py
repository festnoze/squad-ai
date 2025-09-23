import asyncio
import functools
import inspect
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
    phone_number_attr: Optional[str] = None,
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
        phone_number_attr: Nom de l'attribut contenant le phone_number dans self
        metadata: Métadonnées additionnelles à inclure dans la métrique
    
    Usage:
        @measure_latency(OperationType.STT, provider="google")
        async def function_async(self, param1: str) -> str:
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
                    
                    # Extraire call_sid, stream_sid et phone_number
                    call_sid, stream_sid, phone_number = _extract_call_stream_ids_and_phone(
                                        args, call_sid_attr, stream_sid_attr, phone_number_attr, kwargs)
                    
                    metric = LatencyMetric(
                        operation_type=operation_type,
                        operation_name=operation_name_final,
                        latency_ms=latency_ms,
                        status=status,
                        call_sid=call_sid,
                        stream_sid=stream_sid,
                        provider=provider,
                        phone_number=phone_number,
                        error_message=error_message,
                        metadata=metadata or {}
                    )
                    
                    # Calculer la criticité
                    metric.criticality = latency_tracker.calculate_criticality(metric)
                    
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
                    
                    # Extraire call_sid, stream_sid et phone_number
                    call_sid, stream_sid, phone_number = _extract_call_stream_ids_and_phone(
                        args, call_sid_attr, stream_sid_attr, phone_number_attr, kwargs)
                    
                    metric = LatencyMetric(
                        operation_type=operation_type,
                        operation_name=operation_name_final,
                        latency_ms=latency_ms,
                        status=status,
                        call_sid=call_sid,
                        stream_sid=stream_sid,
                        provider=provider,
                        phone_number=phone_number,
                        error_message=error_message,
                        metadata=metadata or {}
                    )
                    
                    # Calculer la criticité
                    metric.criticality = latency_tracker.calculate_criticality(metric)
                    
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
        phone_number: Optional[str] = None,
        metadata: Optional[dict] = None
    ):
        self.operation_type = operation_type
        self.operation_name = operation_name
        self.provider = provider
        self.call_sid = call_sid
        self.stream_sid = stream_sid
        self.phone_number = phone_number
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
            phone_number=self.phone_number,
            error_message=error_message,
            metadata=self.metadata
        )
        
        # Calculer la criticité
        metric.criticality = latency_tracker.calculate_criticality(metric)
        
        latency_tracker.add_metric(metric)


# Context manager pour usage facile
def measure_latency_context(
    operation_type: OperationType,
    operation_name: str,
    provider: Optional[str] = None,
    call_sid: Optional[str] = None,
    stream_sid: Optional[str] = None,
    phone_number: Optional[str] = None,
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
        phone_number=phone_number,
        metadata=metadata
    )


def _extract_call_stream_ids_and_phone(args, call_sid_attr, stream_sid_attr, phone_number_attr=None, kwargs=None):
    """Fonction helper pour extraire call_sid, stream_sid et phone_number depuis les arguments ou kwargs"""
    call_sid = None
    stream_sid = None
    phone_number = None
    
    # First try to get from kwargs if available
    if kwargs:
        call_sid = kwargs.get('call_sid')
        stream_sid = kwargs.get('stream_sid')
        phone_number = kwargs.get('phone_number')
    
    # If not found in kwargs, try from object attributes
    if (call_sid is None or stream_sid is None or phone_number is None) and args and hasattr(args[0], '__dict__'):
        obj = args[0]
        
        # Extraire call_sid
        if call_sid is None and call_sid_attr and hasattr(obj, call_sid_attr):
            call_sid = getattr(obj, call_sid_attr)
        
        # Extraire stream_sid
        if stream_sid is None and stream_sid_attr and hasattr(obj, stream_sid_attr):
            stream_sid = getattr(obj, stream_sid_attr)
        
        # Extraire phone_number directement ou depuis phones_by_call_sid
        if phone_number is None:
            if phone_number_attr and hasattr(obj, phone_number_attr):
                phone_number = getattr(obj, phone_number_attr)
            elif call_sid and hasattr(obj, 'phones_by_call_sid'):
                phones_by_call_sid = getattr(obj, 'phones_by_call_sid')
                if isinstance(phones_by_call_sid, dict):
                    phone_number = phones_by_call_sid.get(call_sid)
            elif hasattr(obj, 'phone_number'):
                # Fallback direct attribute
                phone_number = getattr(obj, 'phone_number')
            
    return call_sid, stream_sid, phone_number



def measure_streaming_latency(
    operation_type: OperationType,
    operation_name: Optional[str] = None,
    provider: Optional[str] = None,
    call_sid_attr: Optional[str] = None,
    stream_sid_attr: Optional[str] = None,
    phone_number_attr: Optional[str] = None,
    metadata: Optional[dict] = None
):
    """
    Décorateur spécialisé pour mesurer la latence "time to first token" 
    des générateurs et générateurs asynchrones.
    
    Ce décorateur mesure le temps écoulé entre l'appel de la fonction
    et le moment où elle yield son premier élément (time to first token).
    
    Args:
        operation_type: Type d'opération (STT, TTS, SALESFORCE, RAG)
        operation_name: Nom de l'opération (par défaut utilise le nom de la méthode)
        provider: Nom du fournisseur de service (e.g., "google", "openai")
        call_sid_attr: Nom de l'attribut contenant le call_sid dans self
        stream_sid_attr: Nom de l'attribut contenant le stream_sid dans self
        metadata: Métadonnées additionnelles à inclure dans la métrique
    
    Usage:
        @measure_streaming_latency(OperationType.RAG, provider="studi_rag")
        async def rag_query_stream_async(self, ...):
            # Code qui yield des chunks
            async for chunk in response:
                yield chunk
    """
    def decorator(func: Callable) -> Callable:
        operation_name_final = operation_name or func.__name__
        
        if inspect.isasyncgenfunction(func) or asyncio.iscoroutinefunction(func):
            # Le décorateur doit créer une fonction async generator
            @functools.wraps(func)
            async def async_generator_wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                first_chunk_yielded = False
                status = OperationStatus.SUCCESS
                error_message = None
                
                try:
                    # Appeler la fonction originale qui est un async generator
                    async for chunk in func(*args, **kwargs):
                        if not first_chunk_yielded:
                            # Mesurer le time to first token
                            end_time = time.perf_counter()
                            latency_ms = (end_time - start_time) * 1000
                            
                            # Extraire les métadonnées
                            call_sid, stream_sid, phone_number = _extract_call_stream_ids_and_phone(
                                args, call_sid_attr, stream_sid_attr, phone_number_attr, kwargs
                            )
                            
                            metric = LatencyMetric(
                                operation_type=operation_type,
                                operation_name=f"{operation_name_final}_first_token",
                                latency_ms=latency_ms,
                                status=status,
                                call_sid=call_sid,
                                stream_sid=stream_sid,
                                provider=provider,
                                phone_number=phone_number,
                                error_message=error_message,
                                metadata={**(metadata or {}), "metric_type": "time_to_first_token"}
                            )
                            
                            # Calculer la criticité
                            metric.criticality = latency_tracker.calculate_criticality(metric)
                            
                            latency_tracker.add_metric(metric)
                            first_chunk_yielded = True
                        
                        yield chunk
                        
                except Exception as e:
                    if not first_chunk_yielded:
                        # Erreur avant le premier chunk
                        end_time = time.perf_counter()
                        latency_ms = (end_time - start_time) * 1000
                        status = OperationStatus.ERROR
                        error_message = str(e)
                        
                        call_sid, stream_sid, phone_number = _extract_call_stream_ids_and_phone(
                            args, call_sid_attr, stream_sid_attr, phone_number_attr, kwargs
                        )
                        
                        metric = LatencyMetric(
                            operation_type=operation_type,
                            operation_name=f"{operation_name_final}_first_token",
                            latency_ms=latency_ms,
                            status=status,
                            call_sid=call_sid,
                            stream_sid=stream_sid,
                            provider=provider,
                            phone_number=phone_number,
                            error_message=error_message,
                            metadata={**(metadata or {}), "metric_type": "time_to_first_token"}
                        )
                        
                        # Calculer la criticité
                        metric.criticality = latency_tracker.calculate_criticality(metric)
                        
                        latency_tracker.add_metric(metric)
                    raise
            
            return async_generator_wrapper
            
        else:
            # Version synchrone pour les générateurs sync
            @functools.wraps(func)
            def sync_generator_wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                first_chunk_yielded = False
                status = OperationStatus.SUCCESS
                error_message = None
                
                try:
                    # Appeler la fonction originale qui est un generator
                    for chunk in func(*args, **kwargs):
                        if not first_chunk_yielded:
                            end_time = time.perf_counter()
                            latency_ms = (end_time - start_time) * 1000
                            
                            call_sid, stream_sid, phone_number = _extract_call_stream_ids_and_phone(
                            args, call_sid_attr, stream_sid_attr, phone_number_attr, kwargs
                        )
                            
                            metric = LatencyMetric(
                                operation_type=operation_type,
                                operation_name=f"{operation_name_final}_first_token",
                                latency_ms=latency_ms,
                                status=status,
                                call_sid=call_sid,
                                stream_sid=stream_sid,
                                provider=provider,
                                phone_number=phone_number,
                                error_message=error_message,
                                metadata={**(metadata or {}), "metric_type": "time_to_first_token"}
                            )
                            
                            # Calculer la criticité
                            metric.criticality = latency_tracker.calculate_criticality(metric)
                            
                            latency_tracker.add_metric(metric)
                            first_chunk_yielded = True
                        
                        yield chunk
                        
                except Exception as e:
                    if not first_chunk_yielded:
                        end_time = time.perf_counter()
                        latency_ms = (end_time - start_time) * 1000
                        status = OperationStatus.ERROR
                        error_message = str(e)
                        
                        call_sid, stream_sid, phone_number = _extract_call_stream_ids_and_phone(
                            args, call_sid_attr, stream_sid_attr, phone_number_attr, kwargs
                        )
                        
                        metric = LatencyMetric(
                            operation_type=operation_type,
                            operation_name=f"{operation_name_final}_first_token",
                            latency_ms=latency_ms,
                            status=status,
                            call_sid=call_sid,
                            stream_sid=stream_sid,
                            provider=provider,
                            phone_number=phone_number,
                            error_message=error_message,
                            metadata={**(metadata or {}), "metric_type": "time_to_first_token"}
                        )
                        
                        # Calculer la criticité
                        metric.criticality = latency_tracker.calculate_criticality(metric)
                        
                        latency_tracker.add_metric(metric)
                    raise
            
            return sync_generator_wrapper
    
    return decorator