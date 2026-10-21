# French Transcription

A local web app that records French speech in the browser and transcribes it with `faster-whisper`.

## Run

```powershell
uv sync
uv run python main.py
```

Open <http://127.0.0.1:8000>, allow microphone access, and press **Record**. The first transcription downloads the Whisper model and can take longer than later requests.

To enable the French DELF B2 speaking analysis, add your Gemini API key to `.env`:

```dotenv
GEMINI_API_KEY=your_api_key_here
```

After a transcription, you can correct recognition errors and select **Analyser avec Gemini**. The coach treats the text as an error-prone transcription, follows DELF B2 oral-production criteria, and responds only in French. The default model is `gemini-2.5-flash`; set `GEMINI_MODEL` in `.env` to use another Gemini model.

The app uses the `small` model on CPU by default. You can change the model or runtime with environment variables:

```powershell
$env:WHISPER_MODEL = "medium"
$env:WHISPER_DEVICE = "cuda"
$env:WHISPER_COMPUTE_TYPE = "float16"
uv run python main.py
```
