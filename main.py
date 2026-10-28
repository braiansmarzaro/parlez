import os
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).parent
MAX_AUDIO_SIZE = 25 * 1024 * 1024
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="Transcription en français")

DELF_B2_INSTRUCTION = """
Tu es un examinateur et coach expert du DELF B2, spécialisé dans la production orale.
Tu reçois exclusivement la transcription en français d'une prise de parole. La transcription
automatique peut contenir des mots mal reconnus, des omissions et une ponctuation imprécise :
ne sanctionne pas comme faute du candidat ce qui semble probablement venir de la transcription,
et signale clairement toute incertitude.

Évalue le discours selon les attentes officielles du niveau DELF B2 : accomplissement de la tâche,
présentation et défense d'un point de vue, cohérence et cohésion, aisance, étendue et maîtrise du
lexique, correction grammaticale. N'évalue pas la prononciation à partir du texte seul.

Analyse réellement le texte au lieu de donner des conseils génériques. Adopte un ton direct,
exigeant et factuel. Commence par les faiblesses qui pénaliseraient le plus une production orale
DELF B2. Ne cherche pas à équilibrer chaque critique par un compliment et ne félicite le candidat
que lorsqu'un point fort précis mérite d'être conservé.

Réponds uniquement en français et en texte brut. N'utilise aucun format Markdown : aucun titre
préfixé par #, aucune liste avec des tirets, des astérisques ou des numéros, aucun texte en gras,
aucun tableau et aucun bloc de code. Utilise seulement de courts paragraphes séparés par une ligne
vide, introduits par ces libellés simples : Diagnostic, Critiques, Améliorations, Reformulations,
Priorité de travail.

Dans Critiques, cite de courts extraits problématiques et explique précisément pourquoi ils sont
faibles, imprécis, répétitifs, incorrects ou insuffisants pour le niveau B2. Dans Améliorations,
indique concrètement quoi changer et l'effet attendu. Dans Reformulations, présente chaque extrait
original suivi d'une version plus naturelle, plus précise ou mieux argumentée. Ne réécris pas tout
le discours, ne donne pas de conseils génériques et ne prétends pas attribuer une note officielle.
""".strip()


class AnalysisRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=30_000)


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


def analyze_transcript(transcript: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        raise RuntimeError("GEMINI_API_KEY n'est pas configurée.")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", GEMINI_MODEL),
        contents=transcript,
        config=types.GenerateContentConfig(
            system_instruction=DELF_B2_INSTRUCTION,
            temperature=0.35,
        ),
    )
    if not response.text:
        raise RuntimeError("Gemini n'a retourné aucune analyse.")
    return response.text.strip()


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
                    raise HTTPException(status_code=413, detail="L'enregistrement est trop volumineux.")
                temp_file.write(chunk)

        if total_size == 0:
            raise HTTPException(status_code=400, detail="L'enregistrement est vide.")

        transcript = await run_in_threadpool(transcribe_audio, temp_path)
        return {"transcript": transcript}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail="L'enregistrement n'a pas pu être transcrit.") from error
    finally:
        await audio.close()
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


def convert_audio_to_mp3(audio: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as directory:
        input_path = Path(directory) / "recording"
        output_path = Path(directory) / "recording.mp3"
        input_path.write_bytes(audio)
        try:
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-y", "-i", str(input_path), "-map", "0:a:0", "-vn",
                    "-codec:a", "libmp3lame", "-b:a", "128k", str(output_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=503,
                detail="La conversion en MP3 nécessite FFmpeg. Installez-le et ajoutez-le au PATH, puis redémarrez le serveur.",
            ) from error
        except subprocess.TimeoutExpired as error:
            raise HTTPException(status_code=504, detail="Le délai de conversion en MP3 a été dépassé.") from error
        except subprocess.CalledProcessError as error:
            raise HTTPException(status_code=422, detail="L'enregistrement n'a pas pu être converti en MP3.") from error
        return output_path.read_bytes()


@app.post("/api/recording/mp3")
async def download_mp3(audio: Annotated[UploadFile, File()]) -> Response:
    try:
        recording = await audio.read(MAX_AUDIO_SIZE + 1)
        if len(recording) > MAX_AUDIO_SIZE:
            raise HTTPException(status_code=413, detail="L'enregistrement est trop volumineux.")
        if not recording:
            raise HTTPException(status_code=400, detail="L'enregistrement est vide.")
        mp3 = await run_in_threadpool(convert_audio_to_mp3, recording)
        return Response(
            content=mp3,
            media_type="audio/mpeg",
            headers={"Content-Disposition": 'attachment; filename="parlez-enregistrement.mp3"'},
        )
    finally:
        await audio.close()


@app.post("/api/analyze")
async def analyze(request: AnalysisRequest) -> dict[str, str]:
    transcript = request.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="La transcription est vide.")

    try:
        analysis = await run_in_threadpool(analyze_transcript, transcript)
        return {"analysis": analysis}
    except RuntimeError as error:
        status_code = 503 if "GEMINI_API_KEY" in str(error) else 502
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="L'analyse Gemini a échoué. Veuillez réessayer.",
        ) from error


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
