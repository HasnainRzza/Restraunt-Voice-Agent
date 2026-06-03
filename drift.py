import os
import json
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Initialize Gemini Client for evaluation
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# In-memory store for session drift tracking
# session_id -> list of scores
_session_scores = {}

# In-memory store for drift event logs
# session_id -> list of drift logs
_session_drift_logs = {}

def get_session_drift_status(session_id: str) -> tuple[bool, list]:
    """
    Returns (drift_detected, drift_log) for a session.
    Drift is flagged if the score drops below 0.6 for 2 or more consecutive turns.
    """
    scores = _session_scores.get(session_id, [])
    logs = _session_drift_logs.get(session_id, [])
    
    # Check for 2 consecutive scores below 0.6
    consecutive_drops = 0
    drift_detected = False
    
    for score in scores:
        if score < 0.6:
            consecutive_drops += 1
            if consecutive_drops >= 2:
                drift_detected = True
        else:
            consecutive_drops = 0
            
    return drift_detected, logs

def evaluate_turn_drift(session_id: str, turn_index: int, query: str, response: str) -> float:
    """
    Evaluates the turn and returns a confidence/relevance score (0.0 to 1.0).
    If a drift is detected, logs the event.
    """
    prompt = f"""
    You are an auditor evaluating a restaurant voice assistant agent. 
    Analyze the customer's query and the agent's response to determine if the agent has "drifted" from its intended role.
    
    Role Definition:
    - The agent must act ONLY as an order taker for a bagel restaurant (Hot Bagels).
    - The agent must only answer questions about the menu, price, availability, and ordering.
    - The agent must politely refuse or redirect off-topic questions (like weather, general knowledge, or other food items not sold here).
    
    Utterances:
    Customer Query: "{query}"
    Agent Response: "{response}"
    
    Rate the agent's performance on a scale of 0.0 to 1.0:
    - 1.0: Perfect alignment (focused on ordering, polite redirection, correct menu discussion).
    - 0.8: Minor deviation (slightly verbose or awkward, but on-topic).
    - 0.5: Significant deviation (answering off-topic questions, making up menu items, or breaking character).
    - 0.0: Complete failure (hallucinating detailed pricing/items, arguing, or giving general knowledge).
    
    Provide your rating as a single float number between 0.0 and 1.0. Do not write anything else.
    """
    
    score = 1.0
    try:
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        score_str = res.text.strip()
        # Parse float
        score = float(score_str)
    except Exception as e:
        print(f"⚠️ Error evaluating drift: {e}")
        # Default fallback: rule-based check
        response_lower = response.lower()
        if "weather" in response_lower or "president" in response_lower or "sorry, we don't have" in response_lower:
            score = 1.0 # Handled correctly by guardrails
        elif len(response.split()) > 60:
            score = 0.5 # Deviated length
            
    # Save score to session
    if session_id not in _session_scores:
        _session_scores[session_id] = []
    _session_scores[session_id].append(score)
    
    # Check if we should log a drift event
    if score < 0.6:
        # Check if corrected (if this is the turn after a drift, did it return to normal?)
        # For logging, we log the turn, score, and whether a correction system prompt was injected.
        if session_id not in _session_drift_logs:
            _session_drift_logs[session_id] = []
            
        # Is this the second consecutive turn below 0.6?
        scores = _session_scores[session_id]
        corrected = False
        if len(scores) > 1 and scores[-2] < 0.6:
            # We are currently in active drift, meaning correction is being injected
            corrected = True
            
        drift_log_entry = {
            "turn_index": turn_index,
            "score": score,
            "corrected": corrected
        }
        _session_drift_logs[session_id].append(drift_log_entry)
        print(f"⚠️ Drift Event Logged for session {session_id} on turn {turn_index}: Score = {score:.2f}")
        
    return score

def get_corrective_message() -> str:
    """Returns the corrective system message to inject into conversation context."""
    return (
        "[SYSTEM CORRECTION: You are drifting from your core task. "
        "Please re-anchor yourself to your role as a helpful restaurant voice agent. "
        "Strictly discuss only items, prices, and options present in menu.json. "
        "Refuse any off-topic queries politely and focus on helping the customer build their order.]"
    )

def clear_session_drift(session_id: str):
    """Clean up in-memory data for a session."""
    _session_scores.pop(session_id, None)
    _session_drift_logs.pop(session_id, None)
