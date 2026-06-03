import os
import io
import uuid
import datetime
import asyncio
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request, status, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

# Import our decoupled layers
from db import (
    start_session, end_session, get_session, list_sessions,
    create_user, get_user, update_user_otp, activate_user, update_user_password
)
from auth import (
    hash_password, verify_password, generate_jwt, verify_jwt,
    generate_otp, is_otp_valid
)
from stt import transcribe_audio
from tts import (
    synthesize_speech, generate_silent_wav,
    synthesize_speech_pcm, play_pcm_locally, speak_locally
)
from llm import route_input, generate_grounded_response
from guardrails import enforce_guardrails
from drift import evaluate_turn_drift, get_session_drift_status, get_corrective_message, clear_session_drift
from menu_search import load_menu, search_menu

app = FastAPI(
    title="Restaurant Voice Agent Orchestrator API",
    description="Production-grade FastAPI server orchestrating call sessions, STT, TTS, LLM (Gemini), Guardrails, and SQLite persistence."
)

security = HTTPBearer()

# In-memory store for active call sessions context and tasks
_active_sessions = {}
_active_recording_tasks = {}

# Menu data loaded once at startup
MENU_ITEMS = load_menu()

# Pydantic request models
class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str

class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

class StartCallRequest(BaseModel):
    caller_id: str
    audio_route: Optional[str] = "server"

class EndCallRequest(BaseModel):
    session_id: str

# Helper dependency for authentication
def get_current_user_email(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = credentials.credentials
    email = verify_jwt(token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token"
        )
    return email

# Background task for microphone recording & orchestrating conversation
async def mic_recording_loop(session_id: str):
    import sounddevice as sd
    import numpy as np
    from deepgram import AsyncDeepgramClient
    from deepgram.core.events import EventType

    SAMPLE_RATE = 16000
    CHANNELS = 1
    
    session_ctx = _active_sessions[session_id]
    client = AsyncDeepgramClient(api_key=os.getenv("DEEPGRAM_API_KEY"))
    is_playing_tts = False
    
    loop = asyncio.get_running_loop()

    async def process_user_turn(user_transcript: str):
        nonlocal is_playing_tts
        is_playing_tts = True
        try:
            print(f"\n🧠 Thinking...", flush=True)
            session_ctx["turn_index"] += 1
            
            # Append user statement to history
            session_ctx["transcript_history"].append({
                "speaker": "user",
                "text": user_transcript,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
            
            # Check if we have drift correction prompt to inject
            drift_detected, _ = get_session_drift_status(session_id)
            current_history = session_ctx["transcript_history"].copy()
            if drift_detected:
                current_history.append({
                    "speaker": "system",
                    "text": get_corrective_message(),
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
                
            # LLM Agent Routing
            routing = route_input(user_transcript, current_history)
            action = routing.get("action", "respond")
            
            # Handle routing and execute tools if required
            if action == "respond":
                raw_reply = routing.get("reply", "Okay, how can I help you?")
            else:
                search_query = routing.get("search_query", user_transcript)
                print(f"🔍 Searching menu for: '{search_query}'", flush=True)
                
                # Execute search tool using the existing logic in menu_search.py
                matches = search_menu(search_query, MENU_ITEMS)
                
                # Generate grounded response
                raw_reply = generate_grounded_response(user_transcript, current_history, matches)
                
                # Auto-extract order items if confidence is high (>= 0.75)
                if matches:
                    for item, score in matches:
                        if score >= 0.75:
                            quantity = 1
                            words = user_transcript.lower().split()
                            for word in words:
                                if word in ["one", "1"]: quantity = 1
                                elif word in ["two", "2"]: quantity = 2
                                elif word in ["three", "3"]: quantity = 3
                                elif word in ["four", "4"]: quantity = 4
                                elif word in ["five", "5"]: quantity = 5
                                
                            # Add or update item in active session order
                            existing = next((x for x in session_ctx["session_order"]["items"] if x["name"] == item["name"]), None)
                            if existing:
                                existing["quantity"] += quantity
                                existing["total"] = existing["quantity"] * existing["price"]
                            else:
                                session_ctx["session_order"]["items"].append({
                                    "name": item["name"],
                                    "quantity": quantity,
                                    "price": item["price"],
                                    "total": quantity * item["price"]
                                })
                            
                            session_ctx["session_order"]["total"] = sum(x["total"] for x in session_ctx["session_order"]["items"])
                            print(f"🛒 Added to order: {item['name']} x{quantity}. Total: ${session_ctx['session_order']['total']:.2f}", flush=True)
                            
            # Enforce Safety Guardrails
            reply = enforce_guardrails(raw_reply, user_transcript)
            print(f"🤖 Agent reply: {reply}", flush=True)
            
            # Append assistant statement to history
            session_ctx["transcript_history"].append({
                "speaker": "assistant",
                "text": reply,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
            
            # Evaluate Model Drift
            evaluate_turn_drift(session_id, session_ctx["turn_index"], user_transcript, reply)
            
            # Text-to-Speech (TTS)
            # Try to synthesize using ElevenLabs PCM
            pcm_bytes = await synthesize_speech_pcm(reply)
            if pcm_bytes:
                print("🔊 Playing ElevenLabs TTS locally...", flush=True)
                await asyncio.to_thread(play_pcm_locally, pcm_bytes)
            else:
                print("🔊 ElevenLabs PCM unavailable. Playing TTS locally via PowerShell...", flush=True)
                await asyncio.to_thread(speak_locally, reply)
                
        except Exception as e:
            print(f"❌ Error during local voice turn processing: {e}", flush=True)
        finally:
            is_playing_tts = False
            print("\n🎙️ Listening... Speak into your microphone.\n", flush=True)

    try:
        # Connect to Deepgram's live transcription API
        async with client.listen.v2.connect(
            model="flux-general-en",
            encoding="linear16",
            sample_rate=str(SAMPLE_RATE)
        ) as connection:

            def on_message(message) -> None:
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

                if transcript.strip():
                    if event == "EndOfTurn":
                        print(f"🎤 (Final) {transcript}", flush=True)
                    else:
                        print(f"🎤 {transcript}", flush=True)

                if event == "EndOfTurn" and transcript.strip():
                    # Process user turn without blocking on Deepgram message callback thread
                    asyncio.run_coroutine_threadsafe(process_user_turn(transcript.strip()), loop)

            # Set up event handlers
            connection.on(EventType.OPEN, lambda _: print("\n✅ Connected to Deepgram! Speak into your microphone...\n", flush=True))
            connection.on(EventType.MESSAGE, on_message)
            connection.on(EventType.CLOSE, lambda _: print("\n❌ Deepgram connection closed", flush=True))
            connection.on(EventType.ERROR, lambda error: print(f"\n⚠️ Deepgram error: {error}", flush=True))

            # Start listening task in the background
            deepgram_task = asyncio.create_task(connection.start_listening())

            def mic_callback(indata, frames, time, status):
                if status:
                    print(f"Sounddevice status: {status}", flush=True)
                if is_playing_tts:
                    return
                # Convert float32 samples to int16 PCM bytes
                pcm_data = (indata * 32767).astype('int16').tobytes()
                coro = connection.send_media(pcm_data)
                asyncio.run_coroutine_threadsafe(coro, loop)

            # Start recording from default microphone
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='float32',
                                blocksize=2048, callback=mic_callback):
                print("🎙️ Microphone active.", flush=True)
                # Play greeting on call start
                greeting = "Hello! Welcome to Hot Bagels. How can I help you today?"
                
                # Append greeting to history
                session_ctx["transcript_history"].append({
                    "speaker": "assistant",
                    "text": greeting,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
                
                # Play greeting
                is_playing_tts = True
                try:
                    pcm_bytes = await synthesize_speech_pcm(greeting)
                    if pcm_bytes:
                        await asyncio.to_thread(play_pcm_locally, pcm_bytes)
                    else:
                        await asyncio.to_thread(speak_locally, greeting)
                finally:
                    is_playing_tts = False
                    print("\n🎙️ Listening... Speak into your microphone.\n", flush=True)

                while True:
                    await asyncio.sleep(0.5)

    except asyncio.CancelledError:
        print(f"🛑 Call session {session_id} mic loop cancelled.", flush=True)
    except Exception as e:
        print(f"⚠️ Error in mic loop: {e}", flush=True)
    finally:
        print(f"🧹 Closed mic stream and Deepgram connection for session {session_id}", flush=True)

async def end_active_session_helper(session_id: str):
    # Cancel the mic background task
    task = _active_recording_tasks.pop(session_id, None)
    if task:
        task.cancel()
        try:
            await task
        except Exception:
            pass
            
    # Retrieve and pop session context
    session_ctx = _active_sessions.pop(session_id, None)
    if session_ctx:
        drift_detected, drift_log = get_session_drift_status(session_id)
        end_session(
            session_id,
            session_ctx["transcript_history"],
            session_ctx["session_order"],
            drift_detected,
            drift_log
        )
        clear_session_drift(session_id)
        print(f"💾 Automatically ended and persisted session {session_id} to SQLite", flush=True)

@app.on_event("shutdown")
async def shutdown_event():
    # End all active calls on server shutdown to free devices
    active_ids = list(_active_recording_tasks.keys())
    for active_id in active_ids:
        await end_active_session_helper(active_id)

# ==========================================
# 1. WEBHOOK ENDPOINTS (CALL LIFECYCLE)
# ==========================================

@app.post("/webhook/call/start")
async def start_call_session(payload: StartCallRequest):
    """
    Initiate a new voice call session.
    Registers started_at in SQLite and sets up the active call context.
    Starts the microphone capture stream and deepgram listener loop in a background task if audio_route is "server".
    """
    # Release mic/speakers if there is any running session
    active_ids = list(_active_recording_tasks.keys())
    for active_id in active_ids:
        print(f"⚠️ Ending existing active call session {active_id} before starting a new one.", flush=True)
        await end_active_session_helper(active_id)

    session_id = str(uuid.uuid4())
    caller_id = payload.caller_id
    audio_route = payload.audio_route or "server"
    
    # Store session state in memory
    _active_sessions[session_id] = {
        "caller_id": caller_id,
        "transcript_history": [],
        "session_order": {
            "items": [],
            "total": 0.0
        },
        "turn_index": 0,
        "audio_route": audio_route
    }
    
    # Persist session start in SQLite
    start_session(session_id, caller_id)
    print(f"📞 Call started: Session {session_id} for Caller {caller_id} (Route: {audio_route})", flush=True)
    
    # Spawn background mic capture and deepgram streaming loop only for server routing
    if audio_route == "server":
        _active_recording_tasks[session_id] = asyncio.create_task(mic_recording_loop(session_id))
    
    return {"session_id": session_id}

@app.post("/webhook/call/audio")
async def process_call_audio(session_id: str = Query(...), request: Request = None):
    """
    Receive a chunk of caller audio.
    Processes the audio chunk using STT -> LLM Router -> Search Tool -> LLM Grounding -> Guardrails -> TTS.
    Returns synthesised agent response audio.
    """
    if session_id not in _active_sessions:
        raise HTTPException(status_code=404, detail="Call session not found or inactive")
        
    audio_bytes = await request.body()
    if not audio_bytes:
        # Return tiny silent wave if no audio sent
        return StreamingResponse(io.BytesIO(generate_silent_wav(1.0)), media_type="audio/wav")
        
    session_ctx = _active_sessions[session_id]
    
    try:
        # 1. Speech-to-Text (STT)
        user_transcript = await transcribe_audio(audio_bytes)
        user_transcript = user_transcript.strip()
        
        if not user_transcript:
            # Silent user chunk, return silent response
            return StreamingResponse(io.BytesIO(generate_silent_wav(1.0)), media_type="audio/wav")
            
        print(f"🎤 [{session_id}] User said: {user_transcript}", flush=True)
        session_ctx["turn_index"] += 1
        
        # Append user statement to history
        session_ctx["transcript_history"].append({
            "speaker": "user",
            "text": user_transcript,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
        
        # Check if we have drift correction prompt to inject
        drift_detected, _ = get_session_drift_status(session_id)
        current_history = session_ctx["transcript_history"].copy()
        if drift_detected:
            # Inject corrective system prompt into conversation context
            current_history.append({
                "speaker": "system",
                "text": get_corrective_message(),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
            
        # 2. LLM Agent Routing
        routing = route_input(user_transcript, current_history)
        action = routing.get("action", "respond")
        
        # 3. Handle routing and execute tools if required
        if action == "respond":
            raw_reply = routing.get("reply", "Okay, how can I help you?")
        else:
            search_query = routing.get("search_query", user_transcript)
            print(f"🔍 [{session_id}] Searching menu for: '{search_query}'", flush=True)
            
            # Execute search tool using the existing logic in menu_search.py
            matches = search_menu(search_query, MENU_ITEMS)
            
            # Generate grounded response
            raw_reply = generate_grounded_response(user_transcript, current_history, matches)
            
            # Auto-extract order items if confidence is high (>= 0.75)
            if matches:
                for item, score in matches:
                    if score >= 0.75:
                        quantity = 1
                        words = user_transcript.lower().split()
                        for word in words:
                            if word in ["one", "1"]: quantity = 1
                            elif word in ["two", "2"]: quantity = 2
                            elif word in ["three", "3"]: quantity = 3
                            elif word in ["four", "4"]: quantity = 4
                            elif word in ["five", "5"]: quantity = 5
                            
                        # Add or update item in active session order
                        existing = next((x for x in session_ctx["session_order"]["items"] if x["name"] == item["name"]), None)
                        if existing:
                            existing["quantity"] += quantity
                            existing["total"] = existing["quantity"] * existing["price"]
                        else:
                            session_ctx["session_order"]["items"].append({
                                "name": item["name"],
                                "quantity": quantity,
                                "price": item["price"],
                                "total": quantity * item["price"]
                            })
                        
                        session_ctx["session_order"]["total"] = sum(x["total"] for x in session_ctx["session_order"]["items"])
                        print(f"🛒 [{session_id}] Added to order: {item['name']} x{quantity}. Total: ${session_ctx['session_order']['total']:.2f}", flush=True)
                        
        # 4. Enforce Safety Guardrails
        reply = enforce_guardrails(raw_reply, user_transcript)
        print(f"🤖 [{session_id}] Agent reply: {reply}", flush=True)
        
        # Append assistant statement to history
        session_ctx["transcript_history"].append({
            "speaker": "assistant",
            "text": reply,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
        
        # 5. Evaluate Model Drift
        evaluate_turn_drift(session_id, session_ctx["turn_index"], user_transcript, reply)
        
        # 6. Text-to-Speech (TTS)
        synthesised_audio = await synthesize_speech(reply)
        
        return StreamingResponse(io.BytesIO(synthesised_audio), media_type="audio/mpeg")
        
    except Exception as e:
        print(f"❌ Error processing audio chunk: {e}", flush=True)
        # Return tiny silent wave to prevent client crash
        return StreamingResponse(io.BytesIO(generate_silent_wav(2.0)), media_type="audio/wav")

@app.post("/webhook/call/end")
async def end_call_session(payload: EndCallRequest):
    """
    Close the session, finalise transcript, extract order, and persist everything to DB.
    """
    session_id = payload.session_id
    if session_id not in _active_sessions:
        # Check if already closed
        session_db = get_session(session_id)
        if session_db:
            return {"status": "already_closed", "session_id": session_id}
        raise HTTPException(status_code=404, detail="Call session not found or active")
        
    await end_active_session_helper(session_id)
    return {"status": "success", "session_id": session_id}


# ==========================================
# 2. DASHBOARD DATA API (JWT SECURED)
# ==========================================

@app.get("/api/calls")
async def list_call_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    email: str = Depends(get_current_user_email)
):
    """
    List all call sessions (paginated). Requires authentication token.
    """
    all_sessions = list_sessions()
    
    # Calculate offset
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_sessions = all_sessions[start_idx:end_idx]
    
    return {
        "page": page,
        "limit": limit,
        "total_calls": len(all_sessions),
        "calls": paginated_sessions
    }

@app.get("/api/calls/{session_id}")
async def get_call_session_details(
    session_id: str,
    email: str = Depends(get_current_user_email)
):
    """
    Retrieve full details for a single call session. Requires authentication token.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    return session


# ==========================================
# 3. AUTHENTICATION & SECURITY ENDPOINTS
# ==========================================

@app.post("/api/auth/signup")
async def auth_signup(payload: SignupRequest):
    """
    Register a new user; triggers a mock OTP email.
    """
    email = payload.email.lower()
    existing_user = get_user(email)
    if existing_user and existing_user["is_active"]:
        raise HTTPException(status_code=400, detail="Email is already registered and active")
        
    password_hash = hash_password(payload.password)
    otp, otp_expires = generate_otp()
    
    # Create or replace inactive user
    create_user(email, password_hash, payload.display_name, otp, otp_expires)
    
    # Mock sending OTP email to console and payload
    print(f"\n==============================================", flush=True)
    print(f"[MOCK EMAIL to {email}]", flush=True)
    print(f"Subject: Verify Your Account OTP Code", flush=True)
    print(f"Body: Hello {payload.display_name}, your activation OTP is: {otp}", flush=True)
    print(f"==============================================\n", flush=True)
    
    return {
        "message": "Registration successful. Please verify the OTP sent to your email.",
        "email": email,
        "otp_code": otp # Returned in payload for easy manual testing
    }

@app.post("/api/auth/verify-otp")
async def auth_verify_otp(payload: VerifyOtpRequest):
    """
    Verify OTP and activate account.
    """
    email = payload.email.lower()
    user = get_user(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user["is_active"]:
        return {"message": "Account is already active."}
        
    if is_otp_valid(user["otp"], user["otp_expires"], payload.otp):
        activate_user(email)
        return {"message": "Account activated successfully. You can now log in."}
    else:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP code")

@app.post("/api/auth/login")
async def auth_login(payload: LoginRequest):
    """
    Exchange credentials for JWT.
    """
    email = payload.email.lower()
    user = get_user(email)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=400, detail="Incorrect email or account is inactive")
        
    if not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Incorrect password")
        
    token = generate_jwt(email)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "email": user["email"],
            "display_name": user["display_name"]
        }
    }

@app.post("/api/auth/forgot-password")
async def auth_forgot_password(payload: ForgotPasswordRequest):
    """
    Send OTP to registered email for password reset.
    """
    email = payload.email.lower()
    user = get_user(email)
    if not user or not user["is_active"]:
        # Do not leak that email doesn't exist, return 200 standard response
        return {"message": "If the account exists, an OTP has been sent."}
        
    otp, otp_expires = generate_otp()
    update_user_otp(email, otp, otp_expires)
    
    print(f"\n==============================================", flush=True)
    print(f"[MOCK EMAIL to {email}]", flush=True)
    print(f"Subject: Reset Your Password OTP Code", flush=True)
    print(f"Body: Hello, your password reset OTP is: {otp}", flush=True)
    print(f"==============================================\n", flush=True)
    
    return {
        "message": "If the account exists, an OTP has been sent.",
        "otp_code": otp # Returned in payload for easy manual testing
    }

@app.post("/api/auth/reset-password")
async def auth_reset_password(payload: ResetPasswordRequest):
    """
    Verify OTP and update password.
    """
    email = payload.email.lower()
    user = get_user(email)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=404, detail="User not found")
        
    if is_otp_valid(user["otp"], user["otp_expires"], payload.otp):
        new_hash = hash_password(payload.new_password)
        update_user_password(email, new_hash)
        return {"message": "Password reset successfully. You can now log in."}
    else:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP code")

# Serve the static frontend
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Ensure static folder exists
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(static_dir, "index.html"))

