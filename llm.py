import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load env variables immediately
load_dotenv()

# Initialize the Gemini Client
# It automatically picks up GEMINI_API_KEY from environment
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def route_input(query: str, chat_history: list) -> dict:
    """
    Classifies the user query.
    Returns a dict with:
      - 'action': 'respond' or 'search'
      - 'reply': Conversational response if 'respond'
      - 'search_query': Phrase to search in menu if 'search'
    """
    history_str = ""
    for turn in chat_history[-5:]:
        history_str += f"{turn['speaker'].upper()}: {turn['text']}\n"
        
    prompt = f"""
    You are an AI routing agent for a restaurant voice assistant. Your job is to classify the USER's latest utterance.
    
    Here is the recent conversation history:
    {history_str}
    
    USER's latest utterance: "{query}"
    
    Classify the utterance into one of two actions:
    1. "respond": Use this if the user is making small talk, greeting you, checking if you can hear them (e.g. "hi", "hello", "can you hear me"), asking general non-menu questions, or asking to finalize/checkout.
    2. "search": Use this if the user is asking about specific food items, prices, ingredients, availability, or expressing a desire to order/add something to their cart.
    
    Return your classification as a JSON object with the following schema:
    {{
        "action": "respond" | "search",
        "reply": "If action is 'respond', provide a polite, natural, and extremely concise conversational response here (under 15 words). Otherwise leave empty.",
        "search_query": "If action is 'search', provide the extracted food item name or phrase to look up in the menu database here. Otherwise leave empty."
    }}
    
    Ensure your response is valid JSON and nothing else. Do not include markdown code block formatting.
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"⚠️ Error in LLM routing: {e}")
        return {"action": "search", "reply": "", "search_query": query}

def generate_grounded_response(query: str, chat_history: list, search_results: list) -> str:
    """
    Generates a friendly voice response grounded only on the menu search results.
    Enforces strict guardrails against hallucinating items, prices, or availability from training data.
    """
    history_str = ""
    for turn in chat_history[-5:]:
        history_str += f"{turn['speaker'].upper()}: {turn['text']}\n"
        
    results_str = ""
    for item, score in search_results:
        results_str += f"- Name: {item['name']}, Price: ${item['price']:.2f}, Category: {item['category']}, Description: {item['description']}\n"
        
    prompt = f"""
    You are a friendly, natural voice ordering agent for a restaurant.
    Respond to the USER's query based ONLY on the provided menu search results.
    
    Strict Guardrails & Rules:
    - Keep your response brief, spoken-language-appropriate, and under 25 words (suitable for a phone call).
    - NEVER answer a price, availability, or item question from your training data alone. You must rely ONLY on the 'Menu Search Results' provided below.
    - If the 'Menu Search Results' are empty, or if they do not contain the exact item the user asked about, you MUST politely refuse to answer or redirect them (e.g. "I'm sorry, we don't have that item on our menu. Is there anything else I can find for you?").
    - Never assume or make up prices, ingredients, or availability. If the item is not present in the 'Menu Search Results', treat it as unavailable.
    
    Conversation History:
    {history_str}
    
    Menu Search Results:
    {results_str if search_results else "No matching items found in the menu."}
    
    USER's query: "{query}"
    
    Write your response now (adhering strictly to the rules above):
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ Error in LLM response generation: {e}")
        if search_results:
            best_match = search_results[0][0]
            return f"Yes, we have {best_match['name']} for ${best_match['price']:.2f}."
        return "I'm sorry, we don't have that item on our menu. Can I help you find something else?"