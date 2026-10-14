import os
import tempfile
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel

BASE_DIR = Path(__file__).parent
MAX_AUDIO_SIZE = 25 * 1024 * 1024

app = FastAPI(title="French Transcription")


@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    return WhisperModel(
        os.getenv("WHISPER_MODEL", "small"),
        device=os.getenv("WHISPER_DEVICE", "cpu"),
        compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
    )


def transcribe_audio(path: str) -> str:
    segments, _ = get_model().transcribe(
        path,
        language="fr",
        beam_size=5,
        vad_filter=True,
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict[str, str]:
    suffix = Path(audio.filename or "recording.webm").suffix or ".webm"
    temp_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            total_size = 0

            while chunk := await audio.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > MAX_AUDIO_SIZE:
                    raise HTTPException(status_code=413, detail="Recording is too large.")
                temp_file.write(chunk)

        if total_size == 0:
            raise HTTPException(status_code=400, detail="The recording is empty.")

        transcript = await run_in_threadpool(transcribe_audio, temp_path)
        return {"transcript": transcript}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail="The recording could not be transcribed.") from error
    finally:
        await audio.close()
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
