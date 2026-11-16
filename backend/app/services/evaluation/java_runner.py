from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, settings

_JAVA_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*\Z")


@dataclass(frozen=True)
class ProcessResult:
    returncode: int | None
    stdout: str
    stderr: str
    elapsed_ns: int
    timed_out: bool = False

    @property
    def elapsed_ms(self) -> int:
        return self.elapsed_ns // 1_000_000


class JavaRunner:
    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or settings

    def validate_class_name(self, class_name: str) -> None:
        if not _JAVA_IDENTIFIER.fullmatch(class_name):
            raise ValueError("Java class name must be a simple Java identifier.")

    def compile(
        self,
        source_code: str,
        work_dir: Path,
        class_name: str,
    ) -> ProcessResult:
        self.validate_class_name(class_name)
        source_path = work_dir / f"{class_name}.java"
        source_path.write_text(source_code, encoding="utf-8")
        return self._run(
            [self.config.JAVA_COMPILER, "-encoding", "UTF-8", source_path.name],
            work_dir,
            timeout=self.config.JAVA_COMPILATION_TIMEOUT_SECONDS,
        )

    def execute(
        self,
        work_dir: Path,
        class_name: str,
        input_data: str,
        timeout: float,
    ) -> ProcessResult:
        self.validate_class_name(class_name)
        return self._run(
            [self.config.JAVA_RUNTIME, "-cp", str(work_dir), class_name],
            work_dir,
            timeout=timeout,
            input_data=input_data,
        )

    @staticmethod
    def _run(
        command: list[str],
        work_dir: Path,
        timeout: float,
        input_data: str | None = None,
    ) -> ProcessResult:
        started = time.perf_counter_ns()
        try:
            completed = subprocess.run(
                command,
                cwd=work_dir,
                input=input_data,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_ns = time.perf_counter_ns() - started
            return ProcessResult(
                returncode=None,
                stdout=_to_text(exc.stdout),
                stderr=_to_text(exc.stderr),
                elapsed_ns=elapsed_ns,
                timed_out=True,
            )

        elapsed_ns = time.perf_counter_ns() - started
        return ProcessResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            elapsed_ns=elapsed_ns,
        )


def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
