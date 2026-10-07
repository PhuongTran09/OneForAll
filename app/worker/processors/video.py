import os
import shutil
import subprocess
import tempfile
from typing import Any

from app.core.exceptions import AppException
from app.utils.logger import logger
from app.worker.processors.base import BaseProcessor


class VideoAudioProcessor(BaseProcessor):
    """
    Video & Audio processor handling:
    - transcode (MP4/MKV/AVI/WEBM transcoding via ffmpeg)
    - extract-audio (extract MP3/WAV/AAC from video)
    - audio conversion (convert audio between formats)
    - thumbnail (capture frame at specific timestamp)
    - url-download (download video/audio from URL using yt-dlp)
    """

    def process(self, input_data: bytes, options: dict[str, Any]) -> tuple[bytes, str]:
        operation = str(options.get("operation", "transcode")).lower()
        sub_opts = options.get("options", {}) or options.get("params", {})

        # URL-based download handler (video URL -> MP4/MP3)
        url = options.get("url") or sub_opts.get("url")
        if url or operation in ("download", "ytdlp", "url_download"):
            target_format = str(sub_opts.get("format", "mp4")).lower()
            return self.download_url(str(url or ""), target_format=target_format, options=sub_opts)

        # File-based processing
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_ext = str(sub_opts.get("from", "mp4")).lstrip(".")
            input_path = os.path.join(tmp_dir, f"input.{input_ext}")
            with open(input_path, "wb") as f:
                f.write(input_data)

            if operation in ("extract-audio", "audio"):
                target_format = str(sub_opts.get("format", "mp3")).lower().lstrip(".")
                output_path = os.path.join(tmp_dir, f"output.{target_format}")
                self._run_ffmpeg(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        input_path,
                        "-vn",
                        "-acodec",
                        "libmp3lame" if target_format == "mp3" else "copy",
                        output_path,
                    ]
                )
                with open(output_path, "rb") as f:
                    content = f.read()
                return content, f"audio/{target_format}"

            elif operation == "thumbnail":
                timestamp = str(sub_opts.get("time", "00:00:01"))
                output_path = os.path.join(tmp_dir, "thumb.jpg")
                self._run_ffmpeg(
                    [
                        "ffmpeg",
                        "-y",
                        "-ss",
                        timestamp,
                        "-i",
                        input_path,
                        "-vframes",
                        "1",
                        "-q:v",
                        "2",
                        output_path,
                    ]
                )
                with open(output_path, "rb") as f:
                    content = f.read()
                return content, "image/jpeg"

            else:
                # Default video transcode
                target_format = str(sub_opts.get("format", "mp4")).lower().lstrip(".")
                output_path = os.path.join(tmp_dir, f"output.{target_format}")
                vcodec = sub_opts.get("vcodec", "libx264")
                acodec = sub_opts.get("acodec", "aac")
                crf = str(sub_opts.get("crf", "23"))

                self._run_ffmpeg(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        input_path,
                        "-c:v",
                        vcodec,
                        "-crf",
                        crf,
                        "-c:a",
                        acodec,
                        output_path,
                    ]
                )
                with open(output_path, "rb") as f:
                    content = f.read()
                return content, f"video/{target_format}"

    def download_url(
        self, url: str, target_format: str = "mp4", options: dict[str, Any] | None = None
    ) -> tuple[bytes, str]:
        """Download video/audio from URL using yt-dlp."""
        if not url:
            raise AppException(status_code=400, detail="URL must be provided for url_download")

        opts = options or {}
        is_audio = target_format in ("mp3", "wav", "aac", "m4a")

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_template = os.path.join(tmp_dir, "media.%(ext)s")
            cmd = ["yt-dlp", "--no-playlist", "-o", out_template]

            if is_audio:
                cmd.extend(["-x", "--audio-format", target_format])
            else:
                cmd.extend(["-f", f"bestvideo[ext={target_format}]+bestaudio/best[ext={target_format}]/best"])

            logger.info("Executing yt-dlp command for %s", url)
            try:
                # Use Python yt_dlp package directly if installed
                import yt_dlp

                ydl_opts: dict[str, Any] = {
                    "outtmpl": out_template,
                    "noplaylist": True,
                    "quiet": True,
                }
                if is_audio:
                    ydl_opts["format"] = "bestaudio/best"
                    ydl_opts["postprocessors"] = [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": target_format,
                            "preferredquality": opts.get("quality", "192"),
                        }
                    ]
                else:
                    ydl_opts["format"] = f"bestvideo[ext={target_format}]+bestaudio/best[ext={target_format}]/best"

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

            except Exception as exc:  # noqa: BLE001
                logger.warning("yt-dlp Python API error: %s, falling back to CLI", exc)
                cmd_str = shutil.which("yt-dlp") or "yt-dlp"
                cmd[0] = cmd_str
                self._run_process(cmd)

            # Find generated output file in tmp_dir
            files = [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)]
            if not files:
                raise AppException(status_code=500, detail="yt-dlp downloaded nothing")

            target_file = files[0]
            with open(target_file, "rb") as f:
                content = f.read()

            content_type = f"audio/{target_format}" if is_audio else f"video/{target_format}"
            return content, content_type

    def _run_ffmpeg(self, cmd: list[str]) -> None:
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        cmd[0] = ffmpeg_bin
        self._run_process(cmd)

    def _run_process(self, cmd: list[str]) -> None:
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=300,
            )
            logger.debug("Process stdout: %s", res.stdout)
        except subprocess.CalledProcessError as exc:
            logger.error("Process failed with code %s: %s", exc.returncode, exc.stderr)
            raise AppException(status_code=500, detail=f"Processing failed: {exc.stderr}") from exc
        except Exception as exc:
            logger.error("Failed to execute process %s: %s", cmd, exc)
            raise AppException(status_code=500, detail=f"Execution error: {exc!s}") from exc


video_audio_processor = VideoAudioProcessor()
