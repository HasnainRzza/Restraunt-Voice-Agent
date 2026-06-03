import os
import uuid
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from .env file immediately
load_dotenv()

import sounddevice as sd
import numpy as np
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType

# Import menu functions from the search module
from menu_search import load_menu, search_menu
# Import database persistence functions
from db import start_session, end_session
# Import LLM agent routing & response generation functions
from llm import route_input, generate_grounded_response

# Audio settings
SAMPLE_RATE = 16000
CHANNELS = 1

async def main():
    # Load menu items first
    menu_items = load_menu()
    if not menu_items:
        print("❌ Could not load menu items. Exiting.", flush=True)
        return
    print(f"📖 Loaded {len(menu_items)} items from menu.json successfully.", flush=True)

    # Initialize call session details
    session_id = str(uuid.uuid4())
    caller_id = "terminal-user"
    transcript_history = []
    session_order = {
        "items": [],
        "total": 0.0
    }
    
    # Start session in database
    start_session(session_id, caller_id)
    print(f"\n📞 Starting call session (ID: {session_id})", flush=True)

    # Create the Deepgram async client passing the API key explicitly
    client = AsyncDeepgramClient(api_key=os.getenv("DEEPGRAM_API_KEY"))

    try:
        # Connect to Deepgram's live transcription API
        # We specify encoding as linear16 and sample_rate as 16000
        async with client.listen.v2.connect(
            model="flux-general-en",
            encoding="linear16",
            sample_rate=str(SAMPLE_RATE)
        ) as connection:

            # Define message handler function
            def on_message(message) -> None:
                nonlocal transcript_history, session_order
                transcript = ""
                event = ""
                if isinstance(message, dict):
                    msg_type = message.get("type")
                    if msg_type == "TurnInfo":
                        transcript = message.get("transcript", "")
                        event = message.get("event", "")
                    elif msg_type == "Results":
                        transcript = message.get("channel", {}).get("alternatives", [{}])[0].get("transcript", "")
                else:
                    transcript = getattr(message, "transcript", "")
                    event = getattr(message, "event", "")
                    if not transcript and hasattr(message, "channel"):
                        try:
                            transcript = message.channel.alternatives[0].transcript
                        except Exception:
                            pass

                # If there's an update, print it
                if transcript.strip():
                    # Check if it's the final turn event or an update
                    if event == "EndOfTurn":
                        print(f"🎤 (Final) {transcript}", flush=True)
                    else:
                        print(f"🎤 {transcript}", flush=True)

                # When the user stops speaking (EndOfTurn event detected)
                if event == "EndOfTurn" and transcript.strip():
                    # Append to session transcript
                    transcript_history.append({
                        "speaker": "user",
                        "text": transcript.strip(),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    
                    print("\n🧠 Thinking...", flush=True)
                    routing = route_input(transcript.strip(), transcript_history)
                    action = routing.get("action", "respond")
                    
                    if action == "respond":
                        reply = routing.get("reply", "Okay, got it.")
                        print(f"🤖 {reply}", flush=True)
                        transcript_history.append({
                            "speaker": "assistant",
                            "text": reply,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                    elif action == "search":
                        search_q = routing.get("search_query", transcript.strip())
                        print(f"🔍 Searching menu for: '{search_q}'...", flush=True)
                        matches = search_menu(search_q, menu_items)
                        
                        # Generate natural grounded response
                        reply = generate_grounded_response(transcript.strip(), transcript_history, matches)
                        print(f"🤖 {reply}", flush=True)
                        transcript_history.append({
                            "speaker": "assistant",
                            "text": reply,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                        
                        if matches:
                            print("✨ Best Menu Match(es):", flush=True)
                            for item, score in matches:
                                print(f"   • [{item['category']}] {item['name']} - ${item['price']:.2f} (Match Confidence: {score:.1%})", flush=True)
                                if item['description']:
                                    print(f"     Description: {item['description']}", flush=True)
                                
                                # Auto-add matching items to the session order if confidence is high (e.g. >= 0.75)
                                if score >= 0.75:
                                    quantity = 1
                                    words = transcript.lower().split()
                                    for idx, word in enumerate(words):
                                        if word in ["one", "1"]: quantity = 1
                                        elif word in ["two", "2"]: quantity = 2
                                        elif word in ["three", "3"]: quantity = 3
                                        elif word in ["four", "4"]: quantity = 4
                                        elif word in ["five", "5"]: quantity = 5
                                    
                                    existing_item = next((x for x in session_order["items"] if x["name"] == item["name"]), None)
                                    if existing_item:
                                        existing_item["quantity"] += quantity
                                        existing_item["total"] = existing_item["quantity"] * existing_item["price"]
                                    else:
                                        session_order["items"].append({
                                            "name": item["name"],
                                            "quantity": quantity,
                                            "price": item["price"],
                                            "total": quantity * item["price"]
                                        })
                                    
                                    session_order["total"] = sum(x["total"] for x in session_order["items"])
                                    print(f"🛒 Added to order: {item['name']} x{quantity}. Current Total: ${session_order['total']:.2f}", flush=True)
                        else:
                            print("❌ No matching menu items found.", flush=True)
                    print("\n🎙️ Listening... Speak into your microphone.\n", flush=True)

            # Set up event handlers
            connection.on(EventType.OPEN, lambda _: print("\n✅ Connected to Deepgram! Speak into your microphone...\n", flush=True))
            connection.on(EventType.MESSAGE, on_message)
            connection.on(EventType.CLOSE, lambda _: print("\n❌ Connection closed", flush=True))
            connection.on(EventType.ERROR, lambda error: print(f"\n⚠️ Caught error: {error}", flush=True))

            # Start listening task in the background
            deepgram_task = asyncio.create_task(connection.start_listening())

            # Define sounddevice callback to capture microphone input
            loop = asyncio.get_running_loop()

            def callback(indata, frames, time, status):
                if status:
                    print(f"Sounddevice status: {status}", flush=True)
                
                # Convert float32 samples to int16 PCM bytes
                pcm_data = (indata * 32767).astype('int16').tobytes()
                # Run send_media asynchronously in the main loop thread-safely
                coro = connection.send_media(pcm_data)
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                
                # Check for errors in the coroutine thread-safely
                def done_callback(fut):
                    try:
                        fut.result()
                    except Exception as err:
                        # Only print if it's not a normal connection close error
                        if "closed" not in str(err).lower():
                            print(f"⚠️ Error sending audio chunk: {err}", flush=True)
                future.add_done_callback(done_callback)

            # Start recording from the default input device (microphone)
            # blocksize of 2048 frames = ~128ms of audio at 16kHz
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='float32',
                               blocksize=2048, callback=callback):
                print("🎙️ Microphone active. Press Ctrl+C to stop recording.")
                while True:
                    await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Caught error: {e}")
    finally:
        # Save session to SQLite database on end
        if 'session_id' in locals():
            print(f"\n💾 Saving call session data to SQLite (ID: {session_id})...", flush=True)
            end_session(session_id, transcript_history, session_order, drift_detected=False, drift_log=[])
            print("✅ Call session persisted successfully!", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
