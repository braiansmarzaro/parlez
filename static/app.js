const recordButton = document.querySelector("#record-button");
const recordLabel = document.querySelector("#record-label");
const statusText = document.querySelector("#status");
const timer = document.querySelector("#timer");
const transcript = document.querySelector("#transcript");
const copyButton = document.querySelector("#copy-button");
const downloadButton = document.querySelector("#download-button");
const analyzeButton = document.querySelector("#analyze-button");
const analysisSection = document.querySelector("#analysis-section");
const analysisStatus = document.querySelector("#analysis-status");
const analysisOutput = document.querySelector("#analysis-output");

let mediaRecorder;
let audioChunks = [];
let timerInterval;
let startedAt;
let recordingBlob;

function setStatus(message) {
  statusText.textContent = message;
}

function updateTimer() {
  const elapsedSeconds = Math.floor((Date.now() - startedAt) / 1000);
  const minutes = String(Math.floor(elapsedSeconds / 60)).padStart(2, "0");
  const seconds = String(elapsedSeconds % 60).padStart(2, "0");
  timer.textContent = `${minutes}:${seconds}`;
}

function getAudioExtension(mimeType) {
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("mp4")) return "m4a";
  if (mimeType.includes("wav")) return "wav";
  return "webm";
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setStatus("Ce navigateur ne prend pas en charge l'enregistrement audio.");
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const preferredType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "";

    mediaRecorder = new MediaRecorder(stream, preferredType ? { mimeType: preferredType } : undefined);
    audioChunks = [];
    recordingBlob = undefined;
    downloadButton.disabled = true;
    mediaRecorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) audioChunks.push(event.data);
    });
    mediaRecorder.addEventListener("stop", () => submitRecording(stream), { once: true });
    mediaRecorder.start();

    startedAt = Date.now();
    timer.textContent = "00:00";
    timerInterval = window.setInterval(updateTimer, 1000);
    document.body.classList.add("is-recording");
    recordLabel.textContent = "Arrêter";
    recordButton.setAttribute("aria-label", "Arrêter l'enregistrement");
    setStatus("Écoute en français...");
  } catch (error) {
    setStatus(error.name === "NotAllowedError" ? "L'accès au microphone a été refusé." : "Impossible d'accéder à votre microphone.");
  }
}

function stopRecording() {
  window.clearInterval(timerInterval);
  document.body.classList.remove("is-recording");
  recordButton.disabled = true;
  recordLabel.textContent = "Patientez";
  setStatus("Transcription de votre enregistrement en cours...");
  mediaRecorder.stop();
}

async function submitRecording(stream) {
  stream.getTracks().forEach((track) => track.stop());
  const mimeType = mediaRecorder.mimeType || "audio/webm";
  const recordingExtension = getAudioExtension(mimeType);
  const recording = new Blob(audioChunks, { type: mimeType });
  recordingBlob = recording;
  downloadButton.disabled = false;
  const formData = new FormData();
  formData.append("audio", recording, `recording.${recordingExtension}`);

  try {
    const response = await fetch("/api/transcribe", { method: "POST", body: formData });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "La transcription a échoué.");

    transcript.value = result.transcript;
    copyButton.disabled = !result.transcript;
    analyzeButton.disabled = !result.transcript;
    setStatus(result.transcript ? "Transcription prête" : "Aucune parole détectée. Veuillez réessayer.");
  } catch (error) {
    setStatus(error instanceof TypeError || error instanceof SyntaxError ? "La transcription a échoué. Vérifiez votre connexion et réessayez." : error.message || "La transcription a échoué. Veuillez réessayer.");
  } finally {
    recordButton.disabled = false;
    recordLabel.textContent = "Enregistrer";
    recordButton.setAttribute("aria-label", "Démarrer l'enregistrement");
  }
}

recordButton.addEventListener("click", () => {
  if (mediaRecorder?.state === "recording") stopRecording();
  else startRecording();
});

copyButton.addEventListener("click", async () => {
  await navigator.clipboard.writeText(transcript.value);
  copyButton.textContent = "Copié";
  window.setTimeout(() => { copyButton.textContent = "Copier"; }, 1400);
});

transcript.addEventListener("input", () => {
  const hasTranscript = Boolean(transcript.value.trim());
  copyButton.disabled = !hasTranscript;
  analyzeButton.disabled = !hasTranscript;
});

analyzeButton.addEventListener("click", async () => {
  const text = transcript.value.trim();
  if (!text) return;

  analysisSection.hidden = false;
  analysisOutput.textContent = "";
  analysisStatus.textContent = "Analyse en cours...";
  analyzeButton.disabled = true;
  analyzeButton.textContent = "Analyse en cours...";

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript: text }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "L'analyse a échoué.");

    analysisOutput.textContent = result.analysis;
    analysisStatus.textContent = "Analyse terminée";
    analysisSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    analysisStatus.textContent = "Analyse indisponible";
    analysisOutput.textContent = error instanceof TypeError || error instanceof SyntaxError ? "L'analyse a échoué. Vérifiez votre connexion et réessayez." : error.message || "L'analyse a échoué. Veuillez réessayer.";
  } finally {
    analyzeButton.disabled = false;
    analyzeButton.textContent = "Analyser à nouveau";
  }
});

downloadButton.addEventListener("click", async () => {
  if (!recordingBlob) return;

  const recording = recordingBlob;
  const formData = new FormData();
  formData.append("audio", recording, `recording.${getAudioExtension(recording.type)}`);
  downloadButton.disabled = true;
  downloadButton.textContent = "Conversion en cours...";

  try {
    const response = await fetch("/api/recording/mp3", { method: "POST", body: formData });
    if (!response.ok) {
      const result = await response.json();
      throw new Error(result.detail || "La conversion en MP3 a échoué.");
    }

    const recordingUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    const timestamp = new Date().toISOString().replaceAll(":", "-").replace(".", "-");
    link.href = recordingUrl;
    link.download = `parlez-enregistrement-${timestamp}.mp3`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(recordingUrl), 60_000);
  } catch (error) {
    setStatus(error instanceof TypeError || error instanceof SyntaxError ? "Le téléchargement du MP3 a échoué. Vérifiez votre connexion et réessayez." : error.message || "Le téléchargement du MP3 a échoué. Veuillez réessayer.");
  } finally {
    if (recordingBlob === recording) downloadButton.disabled = false;
    downloadButton.textContent = "Télécharger le MP3";
  }
});