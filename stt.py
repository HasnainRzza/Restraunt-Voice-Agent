import os
import httpx
from dotenv import load_dotenv

load_dotenv()

async def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Transcribe a chunk of audio bytes using Deepgram's REST API.
    Supports audio formats like WAV, MP3, etc.
    """
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY environment variable is not set")
        
    async with httpx.AsyncClient() as client:
        # We auto-detect formatting and use nova-2 for fast, high-quality transcription
        response = await client.post(
            "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true",
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/octet-stream"
            },
            content=audio_bytes,
            timeout=15.0
        )
        
        if response.status_code == 200:
            data = response.json()
            try:
                transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
                return transcript
            except (KeyError, IndexError):
                return ""
        else:
            raise Exception(f"Deepgram STT error: HTTP {response.status_code} - {response.text}")
