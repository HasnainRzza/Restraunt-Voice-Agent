import os
import json
import difflib

def load_menu():
    """Load and parse menu.json items from the project root."""
    menu_path = os.path.join(os.path.dirname(__file__), "..", "menu.json")
    try:
        with open(menu_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        items = []
        categories = data.get("menu", {}).get("categories", [])
        for category in categories:
            cat_name = category.get("name", "General")
            for item in category.get("items", []):
                items.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description", ""),
                    "price": item.get("base_price"),
                    "category": cat_name,
                    "available": item.get("available", True)
                })
        return items
    except Exception as e:
        print(f"⚠️ Error loading menu.json: {e}", flush=True)
        return []

def search_menu(query: str, menu_items: list, threshold: float = 0.65) -> list:
    """Smarter and stricter menu item matching to prevent false positives."""
    query_clean = query.lower().replace("?", "").replace(".", "").replace(",", "").strip()
    if not query_clean:
        return []
        
    query_words = [w for w in query_clean.split() if w not in {"do", "you", "have", "want", "get", "with", "please", "can", "i", "the", "a", "an", "any", "some"}]
    if not query_words:
        query_words = query_clean.split()
        
    results = []
    for item in menu_items:
        item_name = item["name"].lower()
        item_words = item_name.split()
        
        # 1. Exact Substring Match
        if item_name in query_clean:
            results.append((item, 1.0))
            continue
            
        # 2. Prevent false positives (e.g. "cheeseburger" matching "donut" or "bagel")
        # Require that at least one keyword in the query has a high similarity (>= 0.75) 
        # to a word in the item name.
        has_similar_word = False
        for qw in query_words:
            for iw in item_words:
                ratio = difflib.SequenceMatcher(None, qw, iw).ratio()
                if ratio >= 0.75:
                    has_similar_word = True
                    break
            if has_similar_word:
                break
                
        if not has_similar_word:
            continue
            
        # 3. Overall name similarity match using a sliding window
        window_size = len(item_words)
        best_fuzzy = 0.0
        query_word_list = query_clean.split()
        for i in range(len(query_word_list) - window_size + 1):
            sub_query = " ".join(query_word_list[i:i+window_size])
            sub_score = difflib.SequenceMatcher(None, sub_query, item_name).ratio()
            if sub_score > best_fuzzy:
                best_fuzzy = sub_score
                
        # 4. Description overlap check (only if we have word similarity)
        desc_score = 0.0
        if item["description"]:
            desc_clean = item["description"].lower().replace(".", "").replace(",", "").replace("(", "").replace(")", "")
            desc_words = set(desc_clean.split())
            overlap = set(query_words).intersection(desc_words)
            if overlap:
                desc_score = len(overlap) / len(query_words)
                
        combined_score = best_fuzzy * 0.8 + desc_score * 0.2
        final_score = max(best_fuzzy, combined_score)
        
        if final_score >= threshold:
            results.append((item, final_score))
            
    # Sort results by score descending
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:3] # Return top 3 matches
