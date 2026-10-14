# French Transcription

A local web app that records French speech in the browser and transcribes it with `faster-whisper`.

## Run

```powershell
uv sync
uv run python main.py
```

Open <http://127.0.0.1:8000>, allow microphone access, and press **Record**. The first transcription downloads the Whisper model and can take longer than later requests.

The app uses the `small` model on CPU by default. You can change the model or runtime with environment variables:

```powershell
$env:WHISPER_MODEL = "medium"
$env:WHISPER_DEVICE = "cuda"
$env:WHISPER_COMPUTE_TYPE = "float16"
uv run python main.py
```
