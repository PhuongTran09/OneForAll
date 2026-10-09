from abc import ABC
from pathlib import Path
from typing import Any


class BaseProcessor(ABC):
    """Abstract base class for all conversion and media processors."""

    def process_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        options: dict[str, Any],
    ) -> str:
        """
        Process file on disk without loading entire payload into RAM.
        Args:
            input_path: Local filesystem path to input file.
            output_path: Local filesystem path where processed result must be written.
            options: Dictionary of parameters (operation, formats, quality, etc.)
        Returns:
            str: MIME content-type of the output file.
        """
        raise NotImplementedError

    def process(
        self,
        input_data: bytes | None = None,
        options: dict[str, Any] | None = None,
        *,
        input_path: str | Path | None = None,
        output_path: str | Path | None = None,
        **kwargs: Any,
    ) -> tuple[bytes, str] | str:
        """
        Unified processor method supporting both file-path processing
        and legacy in-memory processing.
        """
        opts = options or {}
        if input_path is not None and output_path is not None:
            return self.process_file(input_path, output_path, opts)

        if input_data is not None:
            return self._process_bytes(input_data, opts)

        raise ValueError("Either (input_path, output_path) or input_data must be provided.")

    def _process_bytes(self, input_data: bytes, options: dict[str, Any]) -> tuple[bytes, str]:
        """Fallback for in-memory processing."""
        raise NotImplementedError
