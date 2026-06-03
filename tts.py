import os
import io
import wave
import httpx
from dotenv import load_dotenv

load_dotenv()

def generate_silent_wav(duration_seconds=2.0) -> bytes:
    """Generate a tiny silent 8-bit mono WAV file to use as a fallback."""
    num_samples = int(8000 * duration_seconds)
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(1)
        wav_file.setframerate(8000)
        # 128 is the silence value for 8-bit PCM
        wav_file.writeframes(bytes([128] * num_samples))
    return wav_io.getvalue()

async def synthesize_speech(text: str) -> bytes:
    """
    Synthesize text to speech using Deepgram TTS REST API (defaulting to MP3).
    Falls back to a silent WAV buffer if the API fails.
    """
    api_key = os.getenv("DEEPGRAM_TTS")
    if not api_key:
        print("⚠️ DEEPGRAM_TTS is not set. Using silent WAV fallback.", flush=True)
        return generate_silent_wav()
        
    try:
        url = "https://api.deepgram.com/v1/speak"
        params = {
            "model": "aura-2-thalia-en",
            "encoding": "mp3"
        }
        headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "text": text
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, headers=headers, json=data)
            if response.status_code == 200:
                return response.content
            else:
                print(f"⚠️ Deepgram TTS failed: {response.text}", flush=True)
                return generate_silent_wav()
                
    except Exception as e:
        print(f"⚠️ Deepgram TTS failed: {e}. Using silent WAV fallback.", flush=True)
        return generate_silent_wav()

async def synthesize_speech_pcm(text: str) -> bytes:
    """
    Synthesize text to speech using Deepgram in raw PCM format (16000Hz, 16-bit, mono) for direct sounddevice playback.
    Returns None if the API fails.
    """
    api_key = os.getenv("DEEPGRAM_TTS")
    if not api_key:
        print("⚠️ DEEPGRAM_TTS is not set.", flush=True)
        return None
        
    try:
        url = "https://api.deepgram.com/v1/speak"
        params = {
            "model": "aura-2-thalia-en",
            "encoding": "linear16",
            "sample_rate": "16000"
        }
        headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "text": text
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, headers=headers, json=data)
            if response.status_code == 200:
                return response.content
            else:
                print(f"⚠️ Deepgram PCM TTS failed: {response.text}", flush=True)
                return None
                
    except Exception as e:
        print(f"⚠️ Deepgram PCM TTS failed: {e}", flush=True)
        return None

def play_pcm_locally(pcm_bytes: bytes):
    """
    Play 16-bit mono PCM bytes at 16000Hz locally using sounddevice.
    """
    import sounddevice as sd
    import numpy as np
    try:
        pcm_data = np.frombuffer(pcm_bytes, dtype=np.int16)
        sd.play(pcm_data, samplerate=16000)
        sd.wait()
    except Exception as e:
        print(f"⚠️ Local PCM playback failed: {e}", flush=True)

def speak_locally(text: str):
    """
    Speak text locally using native Windows SpeechSynthesizer via PowerShell.
    """
    import subprocess
    clean_text = text.replace('"', '""').replace("`", "``")
    ps_cmd = f'Add-Type -AssemblyName System.Speech; $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; $synth.Speak("{clean_text}")'
    try:
        subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, check=True)
    except Exception as e:
        print(f"⚠️ Local TTS failed: {e}", flush=True)
