from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = logging.currentframe()
        depth = 2

        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.bind(logger_name=record.name).opt(
            depth=depth,
            exception=record.exc_info,
        ).log(level, record.getMessage())


def _json_serializer(record: dict[str, Any]) -> str:
    payload = {
        "ts": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "module": record["module"],
        "name": record["name"],
        "function": record["function"],
        "line": record["line"],
        "process_id": record["process"].id,
        "thread_id": record["thread"].id,
        "extra": record["extra"],
    }

    if record["exception"] is not None:
        payload["exception"] = {
            "type": record["exception"].type.__name__
            if record["exception"].type
            else None,
            "value": str(record["exception"].value)
            if record["exception"].value
            else None,
            "traceback": str(record["exception"]),
        }

    return json.dumps(payload, ensure_ascii=False)


def _patch_record(record: dict[str, Any]) -> None:
    extra = record["extra"]
    extra.setdefault("service", os.getenv("APP_NAME", "app"))
    extra.setdefault("env", os.getenv("APP_ENV", "prod"))
    extra.setdefault("version", os.getenv("APP_VERSION", "-"))
    extra.setdefault("request_id", "-")
    extra.setdefault("trace_id", "-")
    extra.setdefault("user_id", "-")
    extra.setdefault("chat_id", "-")
    extra.setdefault("job_id", "-")
    extra.setdefault("component", "-")
    extra.setdefault("logger_name", record["name"])


def _console_format(record: dict[str, Any]) -> str:
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[service]}</cyan> | "
        "<yellow>{extra[component]}</yellow> | "
        "rid=<magenta>{extra[request_id]}</magenta> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>\n"
    )


def _json_file_format(record: dict[str, Any]) -> str:
    record["extra"]["serialized"] = _json_serializer(record)
    return "{extra[serialized]}\n"


def setup_logger(
    *,
    app_name: str,
    env: str = "prod",
    level: str = "INFO",
    log_dir: str | Path = "logs",
    log_json: bool = True,
    log_to_file: bool = True,
    intercept_std_logging: bool = True,
) -> None:
    os.environ["APP_NAME"] = app_name
    os.environ["APP_ENV"] = env

    log_path = Path(log_dir).expanduser().resolve()
    print(log_path)
    log_path.mkdir(parents=True, exist_ok=True)

    logger.remove()

    logger.configure(
        extra={
            "service": app_name,
            "env": env,
            "version": os.getenv("APP_VERSION", "-"),
            "request_id": "-",
            "trace_id": "-",
            "user_id": "-",
            "chat_id": "-",
            "job_id": "-",
            "component": "-",
            "logger_name": "-",
        },
        patcher=_patch_record,
    )

    logger.add(
        sys.stderr,
        level=level.upper(),
        format=_console_format,
        colorize=True,
        backtrace=True,
        diagnose=True,
        enqueue=True,
        catch=True,
    )

    if log_to_file:
        app_log_file = log_path / "app.log"
        error_log_file = log_path / "error.log"
        json_log_file = log_path / "app.jsonl"

        logger.add(
            app_log_file,
            level=level.upper(),
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{extra[service]} | "
                "{extra[component]} | "
                "rid={extra[request_id]} | "
                "{name}:{function}:{line} - {message}\n"
            ),
            encoding="utf-8",
            enqueue=True,
            catch=True,
            backtrace=True,
            diagnose=False,
            rotation="100 MB",
            retention="30 days",
            compression="gz",
        )

        logger.add(
            error_log_file,
            level="ERROR",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{extra[service]} | "
                "{extra[component]} | "
                "rid={extra[request_id]} | "
                "{name}:{function}:{line} - {message}\n{exception}\n"
            ),
            encoding="utf-8",
            enqueue=True,
            catch=True,
            backtrace=True,
            diagnose=False,
            rotation="50 MB",
            retention="60 days",
            compression="gz",
        )

        if log_json:
            logger.add(
                json_log_file,
                level=level.upper(),
                format=_json_file_format,
                encoding="utf-8",
                enqueue=True,
                catch=True,
                backtrace=False,
                diagnose=False,
                rotation="100 MB",
                retention="14 days",
                compression="gz",
            )

    if intercept_std_logging:
        intercept_handler = InterceptHandler()
        logging.basicConfig(handlers=[intercept_handler], level=0, force=True)

    logger.bind(component="bootstrap").info("Logger configured: log_dir={}", log_path)


def get_logger(*, component: str | None = None, **extra):
    log = logger
    if component is not None:
        log = log.bind(component=component)
    if extra:
        log = log.bind(**extra)
    return log
