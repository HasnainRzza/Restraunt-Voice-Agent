import re
from menu_search import load_menu

# Load menu items for verification
menu_items = load_menu()
valid_prices = {item["price"] for item in menu_items if item["price"] is not None}
valid_names = {item["name"].lower() for item in menu_items}

def sanitise_text(text: str) -> str:
    """Remove markdown, code blocks, and other non-spoken characters from the text."""
    # Remove code blocks
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    # Remove single line code markers
    text = re.sub(r'`.*?`', '', text)
    # Remove bold/italic markdown markers
    text = text.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
    # Remove bullet points/hyphens at start of lines
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    # Remove any extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def enforce_guardrails(llm_response: str, user_query: str) -> str:
    """
    Enforces strict safety guardrails on the generated LLM response.
    Returns the sanitized response or a fallback refusal message if a guardrail is breached.
    """
    # 1. Enforce length limit (maximum 60 words)
    words = llm_response.split()
    if len(words) > 60:
        print(f"⚠️ Guardrail Triggered: Response length exceeded 60 words ({len(words)} words). Truncating.")
        # Truncate to 50 words and add a polite ending
        llm_response = " ".join(words[:50]) + ". Please let me know how you'd like to proceed."
        
    # Sanitise output
    clean_response = sanitise_text(llm_response)
    
    # 2. Block off-topic responses (e.g., weather, politics, general knowledge)
    off_topic_indicators = [
        r'\b(weather|temperature|forecast|rain|sunny|snow)\b',
        r'\b(capital of|president|prime minister|politics|election)\b',
        r'\b(math|calculate|derive|solve for)\b',
        r'\b(scientific|science|history of|who is the author of)\b'
    ]
    
    response_lower = clean_response.lower()
    for pattern in off_topic_indicators:
        if re.search(pattern, response_lower):
            print(f"⚠️ Guardrail Triggered: Detected off-topic keywords matching pattern '{pattern}'.")
            return "I'm sorry, I can only assist you with our restaurant menu, pricing, and placing your order."

    # 3. Block hallucinated prices or items not present in menu.json
    # Extract any dollar amounts in response (e.g., $4.10, $5, $12.99)
    prices_found = re.findall(r'\$\s*(\d+(?:\.\d{2})?)', clean_response)
    for price_str in prices_found:
        price_val = float(price_str)
        # Check if the mentioned price matches any price in our menu.json
        if price_val not in valid_prices:
            print(f"⚠️ Guardrail Triggered: Mentioned price ${price_val:.2f} is not valid in menu.json.")
            return "I'm sorry, I can only provide information about items and prices available on our menu. Can I help you find something else?"

    # Check if the response names an item that is definitely not in the menu
    # This is a soft check: if the user query mentioned something off-topic (e.g. "pizza"),
    # and the response is discussing it as if it exists on the menu, we block it.
    menu_words = set()
    for name in valid_names:
        menu_words.update(name.split())
        
    # If the user queried about an item and the LLM responds talking about it but it's not in the menu
    # we double check. To avoid over-blocking, we check if the response asserts availability of items not present.
    invalid_food_items = ["pizza", "burger", "sushi", "pasta", "taco", "ramen", "steak"]
    for food in invalid_food_items:
        if food in response_lower and food not in valid_names:
            # Check if we are confirming we sell it
            if any(confirm in response_lower for confirm in ["have", "serve", "offer", "order", "price", "cost"]):
                print(f"⚠️ Guardrail Triggered: Confirmed off-menu item '{food}'.")
                return "I'm sorry, we do not have that item on our menu. Would you like to check out our bagels or salads?"

    return clean_response
