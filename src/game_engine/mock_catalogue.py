"""
Mock data for testing - only mocks the catalogue service.
Database operations use real repositories with in-memory SQLite.
"""
import json
import os
from typing import Dict, List

# Mock card catalogue (loaded from cards.json)
MOCK_CARD_CATALOGUE = {}


def _load_mock_cards():
    """
    Loads cards from cards/cards.json into the MOCK_CARD_CATALOGUE.
    """
    global MOCK_CARD_CATALOGUE
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir) # Adjust if mocks.py is deeper
    file_path = os.path.join(project_root, "cards", "cards.json")
    
    print(f"[mock_catalogue] Loading from: {file_path}", flush=True)

    if not os.path.exists(file_path):
         print(f"[mock_catalogue] ERROR: File not found at {file_path}", flush=True)
         return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Reset catalogue
        MOCK_CARD_CATALOGUE = {}

        # --- NEW LOGIC FOR YOUR SPECIFIC JSON ---
        if isinstance(data, dict):
            # 1. Sort keys to ensure deterministic IDs (Abruzzo = 1, Basilicata = 2...)
            sorted_keys = sorted(data.keys())
            
            for idx, key in enumerate(sorted_keys):
                card_data = data[key]
                
                # 2. Assign ID starting from 1
                card_id = idx + 1
                
                # 3. Create the card object
                card = dict(card_data)
                card["id"] = card_id
                
                # Optional: Keep the original key (e.g. 'abruzzo') just in case
                card["region_id"] = key 

                MOCK_CARD_CATALOGUE[card_id] = card

            print(f"[mock_catalogue] Success! Loaded {len(MOCK_CARD_CATALOGUE)} regions.", flush=True)
            
            # Debug: Print the first card to verify
            print(f"[mock_catalogue] Card 1 is: {MOCK_CARD_CATALOGUE[1]['name']}", flush=True)

        else:
            print(f"[mock_catalogue] ERROR: JSON must be a dictionary, got {type(data)}", flush=True)

    except Exception as e:
        print(f"[mock_catalogue] CRITICAL ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()

# Load immediately
_load_mock_cards()


def mock_fetch_card_stats(card_ids: List[int]) -> Dict:
    """
    Mock version of _fetch_card_stats_from_ids.
    Returns card data from MOCK_CARD_CATALOGUE which is populated from JSON.
    This replaces the HTTP call to the catalogue service.
    """
    result = {}
    for card_id in card_ids:
        if card_id not in MOCK_CARD_CATALOGUE:
            raise ValueError(f"Card {card_id} not found in catalogue")
        result[card_id] = MOCK_CARD_CATALOGUE[card_id].copy()
    return result
