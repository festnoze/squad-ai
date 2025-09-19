import os
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from utils.endpoints_api_key_required_decorator import api_key_required

logs_router = APIRouter(prefix="/logs")

@logs_router.get("/last", response_class=PlainTextResponse)
@api_key_required
def get_last_log_file(request: Request) -> str:
    log_files = os.listdir("outputs/logs")
    # Only include .log files, exclude latency_metrics.jsonl and other files
    log_files = [f for f in log_files if f.endswith('.log')]
    log_files.sort()
    if not log_files or not any(log_files):
        return "<<<No log files found.>>>"
    latest_log_file = log_files[-1]
    with open(f"outputs/logs/{latest_log_file}", encoding="utf-8") as file:
        lines = file.readlines()
        return ''.join(lines[-1000:])

@logs_router.get("/latency", response_class=PlainTextResponse)
@api_key_required
def get_latency_metrics(request: Request) -> str:
    latency_file_path = "outputs/logs/latency_metrics.jsonl"
    if not os.path.exists(latency_file_path):
        return "<<<Latency metrics file not found.>>>"
    with open(latency_file_path, encoding="utf-8") as file:
        lines = file.readlines()
        return ''.join(lines[-1000:])