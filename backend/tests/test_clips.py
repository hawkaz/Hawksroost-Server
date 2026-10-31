import asyncio
import shutil
import subprocess

import pytest

from app import config
from app.services import clips

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


class FakeStream:
    def __init__(self, data: bytes):
        self.data = data

    async def iter_chunked(self, n):
        for i in range(0, len(self.data), n):
            yield self.data[i:i + n]


class FakeVod:
    def __init__(self, data):
        self.stream, self.length, self.closed = FakeStream(data), len(data), False

    def close(self):
        self.closed = True


def test_clip_cut(tmp_path, monkeypatch):
    src = tmp_path / "long.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=20:size=320x180:rate=10",
                    "-c:v", "libx264", "-g", "10", str(src)], check=True)
    data = src.read_bytes()

    async def fake_download(cam_id, name, start_id, end_id, stream):
        return FakeVod(data)

    monkeypatch.setattr(clips.manager, "download", fake_download)
    config.CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    async def run():
        job = clips.start(1, "Porch", "Rec/file.mp4", "a", "b", "sub", 5, 6, "test")
        for _ in range(100):
            if job.status in ("ready", "failed"):
                break
            await asyncio.sleep(0.1)
        return job

    job = asyncio.run(run())
    assert job.status == "ready", job.error
    out = clips.clip_path(job)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                               capture_output=True, text=True).stdout)
    assert 5 <= dur <= 7.5
    assert job.filename == "Porch-test.mp4"
