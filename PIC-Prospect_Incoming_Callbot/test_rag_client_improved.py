#!/usr/bin/env python3
import asyncio
import os
from dotenv import load_dotenv
from app.api_client.studi_rag_inference_api_client import StudiRAGInferenceApiClient

async def test_improved_rag_client():
    # Load environment variables
    load_dotenv()
    
    print("=== Testing improved RAG client ===")
    print(f"RAG_API_HOST: {os.getenv('RAG_API_HOST')}")
    print(f"RAG_API_PORT: {os.getenv('RAG_API_PORT')}")
    print(f"RAG_API_IS_SSH: {os.getenv('RAG_API_IS_SSH')}")
    print(f"RAG_API_TEST_TIMEOUT: {os.getenv('RAG_API_TEST_TIMEOUT', 'default: 10.0')}")
    print(f"RAG_API_CONNECT_TIMEOUT: {os.getenv('RAG_API_CONNECT_TIMEOUT', 'default: 10.0')}")
    print(f"RAG_API_READ_TIMEOUT: {os.getenv('RAG_API_READ_TIMEOUT', 'default: 80.0')}")
    
    # Test with default timeouts
    print("\n--- Testing with default timeouts ---")
    client = StudiRAGInferenceApiClient()
    print(f"Client URL: {client.host_base_url}")
    print(f"Connect timeout: {client.connect_timeout}s")
    print(f"Read timeout: {client.read_timeout}s") 
    print(f"Test timeout: {client.test_timeout}s")
    
    try:
        result = await client.test_client_connection_async()
        print(f"SUCCESS: {result}")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await client.close_client_async()
    
    # Test with custom short timeout
    print("\n--- Testing with short timeout (2s) ---")
    client_short = StudiRAGInferenceApiClient(connect_timeout=2.0, read_timeout=2.0)
    client_short.test_timeout = 2.0
    
    try:
        result = await client_short.test_client_connection_async()
        print(f"SUCCESS: {result}")
    except Exception as e:
        print(f"EXPECTED TIMEOUT: {e}")
    finally:
        await client_short.close_client_async()

if __name__ == "__main__":
    asyncio.run(test_improved_rag_client())
