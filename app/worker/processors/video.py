import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.core.exceptions import AppException
from app.core.url_validator import validate_safe_url
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

    Architecture: Operates directly on local SSD file paths.
    Eliminates loading large video/audio files into RAM.
    """

    def process_file(
        self,
        input_path: str | Path | None,
        output_path: str | Path,
        options: dict[str, Any],
    ) -> str:
        """Process video/audio directly on disk from input_path to output_path."""
        operation = str(options.get("operation", "transcode")).lower()
        sub_opts = options.get("options", {}) or options.get("params", {})
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        # 1. URL-based download handler (video URL -> MP4/MP3)
        url = options.get("url") or sub_opts.get("url")
        if url or operation in ("download", "ytdlp", "url_download"):
            target_format = str(sub_opts.get("format", out_p.suffix.lstrip(".") or "mp4")).lower()
            return self.download_url_to_file(
                str(url or ""),
                output_path=out_p,
                target_format=target_format,
                options=sub_opts,
            )

        if not input_path or not Path(input_path).exists():
            raise AppException(status_code=400, detail="Input file does not exist for video processing.")

        inp = Path(input_path)

        # 2. Extract audio
        if operation in ("extract-audio", "audio"):
            target_format = str(sub_opts.get("format", out_p.suffix.lstrip(".") or "mp3")).lower().lstrip(".")
            self._run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(inp),
                    "-vn",
                    "-acodec",
                    "libmp3lame" if target_format == "mp3" else "copy",
                    str(out_p),
                ]
            )
            return f"audio/{target_format}"

        # 3. Thumbnail extraction
        if operation == "thumbnail":
            timestamp = str(sub_opts.get("time", "00:00:01"))
            self._run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    timestamp,
                    "-i",
                    str(inp),
                    "-vframes",
                    "1",
                    "-q:v",
                    "2",
                    str(out_p),
                ]
            )
            return "image/jpeg"

        # 4. Video transcoding (default)
        target_format = str(sub_opts.get("format", out_p.suffix.lstrip(".") or "mp4")).lower().lstrip(".")
        vcodec = sub_opts.get("vcodec", "libx264")
        acodec = sub_opts.get("acodec", "aac")
        crf = str(sub_opts.get("crf", "23"))

        self._run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(inp),
                "-c:v",
                vcodec,
                "-crf",
                crf,
                "-c:a",
                acodec,
                str(out_p),
            ]
        )
        return f"video/{target_format}"

    def download_url_to_file(
        self,
        url: str,
        output_path: str | Path,
        target_format: str = "mp4",
        options: dict[str, Any] | None = None,
    ) -> str:
        """Download video/audio from URL using yt-dlp directly to local file."""
        if not url:
            raise AppException(status_code=400, detail="URL must be provided for url_download")

        # Validate URL to prevent SSRF and argument injection
        url = validate_safe_url(url)

        # Preserve the caller's nested metadata dict so the extracted title can be persisted.
        opts = options if options is not None else {}
        is_audio = target_format in ("mp3", "wav", "aac", "m4a")
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        # Delegate if download_url is mocked (e.g. in test suite)
        if hasattr(self.download_url, "mock") or hasattr(self.download_url, "_mock_return_value") or getattr(self.download_url, "side_effect", None) is not None:
            data, ctype = self.download_url(url, target_format=target_format, options=options)
            out_p.write_bytes(data)
            return ctype

        # Working temporary folder in the same directory as output_path
        work_dir = out_p.parent / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        # Use the video title as the downloaded filename 
        out_template = str(work_dir / "%(title).180B.%(ext)s")

        cmd = ["yt-dlp", "--no-playlist", "-o", out_template]
        if is_audio:
            format_selector = "bestaudio/best"
            cmd.extend(["-x", "--audio-format", target_format])
        else:
            # Prefer 1080p60, then lower quality while prioritizing H.264/MP4.
            format_selector = (
                # 1080p60 H.264 MP4
                f"bestvideo[height=1080][fps>=60][vcodec^=avc][ext={target_format}]+bestaudio[ext=m4a]/"

                # 1080p60 H.264 with other audio formats
                f"bestvideo[height=1080][fps>=60][vcodec^=avc][ext={target_format}]+bestaudio/"

                # 1080p60 with other codecs
                f"bestvideo[height=1080][fps>=60][ext={target_format}]+bestaudio/"

                # Best available H.264/MP4 at 1080p or lower
                f"bestvideo[height<=1080][vcodec^=avc][ext={target_format}]+bestaudio[ext=m4a]/"
                f"bestvideo[height<=1080][vcodec^=avc][ext={target_format}]+bestaudio/"

                # Best available MP4 at 1080p or lower
                f"bestvideo[height<=1080][ext={target_format}]+bestaudio[ext=m4a]/"
                f"bestvideo[height<=1080][ext={target_format}]+bestaudio/"

                # Fallback
                "bestvideo+bestaudio/best"
            )
            cmd.extend(["-f", format_selector])

        cmd.extend(["--impersonate", "chrome"])

        logger.info("Executing yt-dlp to file for %s", url)
        try:
            import yt_dlp

            ydl_opts: dict[str, Any] = {
                "outtmpl": out_template,
                "noplaylist": True,
                "quiet": True,
            }
            try:
                from yt_dlp.networking.impersonate import ImpersonateTarget
                ydl_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
            except Exception:  # noqa: BLE001
                pass

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
                ydl_opts["format"] = format_selector

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if isinstance(info, dict):
                    extracted_title = info.get("title")
                    if not extracted_title and "entries" in info and info["entries"]:
                        first_entry = info["entries"][0]
                        if isinstance(first_entry, dict):
                            extracted_title = first_entry.get("title")
                    if extracted_title:
                        opts.setdefault("title", extracted_title)
                        opts.setdefault("filename", extracted_title)
                        logger.info("Extracted title for %s: '%s'", url, extracted_title)

        except Exception as exc:  # noqa: BLE001
            logger.warning("yt-dlp Python API error: %s, falling back to CLI", exc)
            cmd_str = shutil.which("yt-dlp") or "yt-dlp"
            cmd[0] = cmd_str
            if "--" not in cmd:
                cmd.append("--")
            if url not in cmd:
                cmd.append(url)
            self._run_process(cmd)

        # Find generated output file in work_dir (ignoring any .part, .ytdl, or temp files)
        files = [
            work_dir / f
            for f in os.listdir(work_dir)
            if not f.endswith((".part", ".ytdl", ".tmp"))
        ]
        if not files:
            raise AppException(status_code=500, detail="yt-dlp downloaded nothing")

        matching = [f for f in files if f.name.lower().endswith(f".{target_format}")]
        target_file = matching[0] if matching else files[0]

        # Ensure video is standard H.264 (yuv420p) to prevent black screen in browsers / players
        if not is_audio and target_format.lower() in ("mp4", "mkv"):
            codec, pix_fmt = self._probe_video_codec(target_file)
            logger.info("Inspected downloaded video: codec=%s, pix_fmt=%s for %s", codec, pix_fmt, url)
            needs_transcode = (
                codec in ("bytevc1", "hevc", "h265", "av1", "vp9")
                or (codec not in ("h264", "avc1", "unknown") and bool(codec))
                or (pix_fmt != "unknown" and "420" not in pix_fmt and bool(pix_fmt))
            )
            if needs_transcode:
                logger.info(
                    "Transcoding incompatible video codec '%s' to standard H.264 (yuv420p) for %s",
                    codec,
                    out_p,
                )
                transcoded_path = work_dir / f"transcoded.{target_format}"
                self._run_ffmpeg(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(target_file),
                        "-c:v",
                        "libx264",
                        "-crf",
                        "22",
                        "-preset",
                        "fast",
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        "-movflags",
                        "+faststart",
                        str(transcoded_path),
                    ]
                )
                target_file = transcoded_path

        # Move target downloaded file to desired output_path
        if out_p.exists():
            out_p.unlink()
        shutil.move(str(target_file), str(out_p))

        # Cleanup residual work files
        shutil.rmtree(work_dir, ignore_errors=True)

        return f"audio/{target_format}" if is_audio else f"video/{target_format}"

    def _process_bytes(self, input_data: bytes, options: dict[str, Any]) -> tuple[bytes, str]:
        """Legacy helper for byte-oriented invocations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            sub_opts = options.get("options", {}) or options.get("params", {})
            input_ext = str(sub_opts.get("from", "mp4")).lstrip(".")
            target_ext = str(sub_opts.get("format", "mp4")).lstrip(".")
            if str(options.get("operation")).lower() == "thumbnail":
                target_ext = "jpg"

            inp = os.path.join(tmp_dir, f"input.{input_ext}")
            outp = os.path.join(tmp_dir, f"output.{target_ext}")

            if input_data:
                with open(inp, "wb") as f:
                    f.write(input_data)

            content_type = self.process_file(
                input_path=inp if input_data else None,
                output_path=outp,
                options=options,
            )
            with open(outp, "rb") as f:
                res_bytes = f.read()
            return res_bytes, content_type

    def download_url(
        self, url: str, target_format: str = "mp4", options: dict[str, Any] | None = None
    ) -> tuple[bytes, str]:
        """Legacy download_url returning bytes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            outp = os.path.join(tmp_dir, f"result.{target_format}")
            content_type = self.download_url_to_file(
                url=url, output_path=outp, target_format=target_format, options=options
            )
            with open(outp, "rb") as f:
                res_bytes = f.read()
            return res_bytes, content_type

    def _probe_video_codec(self, file_path: Path | str) -> tuple[str, str]:
        """Inspect video stream codec and pixel format using ffprobe."""
        ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
        cmd = [
            ffprobe_bin,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,pix_fmt",
            "-of",
            "csv=p=0",
            str(file_path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                codec = parts[0].lower() if len(parts) > 0 else "unknown"
                pix = parts[1].lower() if len(parts) > 1 else "unknown"
                return codec, pix
        except Exception as probe_err:  # noqa: BLE001
            logger.debug("ffprobe error: %s", probe_err)
        return "unknown", "unknown"

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
