"""Pipeline worker thread for CutPilot UI.

Runs the video processing pipeline in a QThread to avoid freezing the GUI.
Communicates with the main window via Qt signals.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.config import CutPilotConfig
from core.models import ProcessResult
from core.pipeline import process_video

logger = logging.getLogger(__name__)


class PipelineWorker(QThread):
    """Background worker that processes videos through the pipeline.

    Signals:
        progress(str, int): Stage label and percentage (0-100).
        video_done(str, ProcessResult): Video filename and its result.
        all_done(): All videos have been processed.
        error(str): Fatal error message.
    """

    progress = Signal(str, int)
    video_done = Signal(str, object)  # (filename, ProcessResult)
    all_done = Signal()
    error = Signal(str)

    def __init__(
        self,
        video_paths: list[Path],
        config: CutPilotConfig,
        hotwords: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._video_paths = list(video_paths)
        self._config = config
        self._hotwords = hotwords
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation (checked between videos)."""
        self._cancelled = True

    def run(self) -> None:
        """Process all videos sequentially in this thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            for i, video_path in enumerate(self._video_paths):
                if self._cancelled:
                    logger.info("Worker cancelled")
                    break

                base_pct = int(i / len(self._video_paths) * 100)
                filename = video_path.name

                def on_progress(label: str, pct: int) -> None:
                    scaled = base_pct + int(pct / len(self._video_paths))
                    self.progress.emit(f"{filename}: {label}", scaled)

                self.progress.emit(f"处理中: {filename}", base_pct)

                result = loop.run_until_complete(
                    process_video(
                        video_path,
                        self._config,
                        on_progress=on_progress,
                        hotwords=self._hotwords,
                    )
                )

                self.video_done.emit(filename, result)

            self.progress.emit("全部完成", 100)
            self.all_done.emit()

        except Exception as exc:
            logger.exception("Pipeline worker failed")
            self.error.emit(str(exc))
        finally:
            loop.close()
