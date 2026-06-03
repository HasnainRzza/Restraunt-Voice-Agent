# For more Python SDK migration guides, visit:
# https://github.com/deepgram/deepgram-python-sdk/tree/main/docs

import time
import wave

from deepgram import (
    DeepgramClient,
)
from deepgram.core.events import EventTypes
from deepgram.speak.v1.types import SpeakV1Text

AUDIO_FILE = "output.wav"
TTS_TEXT = "Hello, this is a text to speech example using Deepgram. How are you doing today? I am fine thanks for asking."

def main():
    try:
        # use default config
        deepgram: DeepgramClient = DeepgramClient()

        # Generate a generic WAV container header
        # since we don't support containerized audio, we need to generate a header
        header = wave.open(AUDIO_FILE, "wb")
        header.setnchannels(1)  # Mono audio
        header.setsampwidth(2)  # 16-bit audio
        header.setframerate(16000)  # Sample rate of 16000 Hz
        header.close()

        # Create a websocket connection to Deepgram
        with deepgram.speak.v1.connect(
            model="aura-2-thalia-en",
            encoding="linear16",
            sample_rate=16000
        ) as connection:
            def on_message(message) -> None:
                if isinstance(message, bytes):
                    print("Received binary data")
                    with open(AUDIO_FILE, "ab") as f:
                        f.write(message)
                        f.flush()
                else:
                    msg_type = getattr(message, "type", "Unknown")
                    print(f"Received {msg_type} event")

            connection.on(EventType.OPEN, lambda _: print("Connection opened"))
            connection.on(EventType.MESSAGE, on_message)
            connection.on(EventType.CLOSE, lambda _: print("Connection closed"))
            connection.on(EventType.ERROR, lambda error: print(f"Error: {error}"))

            connection.start_listening()

            # Send text to be converted to speech
            connection.send_text(SpeakV1Text(text=TTS_TEXT))

            # Flush to generate the audio
            connection.send_flush()

            # Indicate that we've finished
            time.sleep(7)
            print("\n\nPress Enter to stop...\n\n")
            input()

            connection.send_close()

            print("Finished")

    except ValueError as e:
        print(f"Invalid value encountered: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
