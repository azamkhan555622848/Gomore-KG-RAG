#!/usr/bin/env python3
"""
Test All Queries from CSV
Reads all inputs from column E of module3.csv and runs them through the query engine.
"""

import sys
import csv
import json
import re
from pathlib import Path
import pandas as pd

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from query_phase.graph_rag_engine import GraphRAGEngine
from shared.utils import setup_logging

def main():
    """Main test function"""
    setup_logging(level="INFO")

    print("Initializing Graph-RAG Engine...")
    try:
        engine = GraphRAGEngine()
        print("✓ Engine initialized successfully.")
    except Exception as e:
        print(f"✗ Error initializing engine: {e}")
        return

    csv_file_path = Path(__file__).parent / "documents" / "module3.csv"
    if not csv_file_path.exists():
        print(f"✗ CSV file not found at: {csv_file_path}")
        return

    print(f"Reading CSV file: {csv_file_path}")
    df = pd.read_csv(csv_file_path)

    # Find the column index for 'key_entities' and 'scenario_name'
    try:
        key_entities_col = 'key_entities'
        scenario_name_col = 'scenario_name'
        # Ensure columns exist
        if key_entities_col not in df.columns or scenario_name_col not in df.columns:
             raise ValueError("Required columns not found")
    except (ValueError, IndexError):
        print("✗ Error: Could not find 'key_entities' (Column E) or 'scenario_name' in the CSV header.")
        return


    for index, row in df.iterrows():
        scenario_name = row[scenario_name_col]
        key_entities_str = str(row[key_entities_col])

        # Use regex to find the JSON object within the string
        json_match = re.search(r'\{.*\}', key_entities_str, re.DOTALL)
        if not json_match:
            print(f"No JSON object found in 'key_entities' column for row {index+2}. Stopping as requested.")
            break

        json_str = json_match.group(0)

        try:
            key_entities_json = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Skipping row {index+2} due to JSON decode error: {e}")
            continue

        user_data = key_entities_json.get("data")
        character = key_entities_json.get("character", "mego")
        
        case = None
        if "居留證摘要" in scenario_name:
            case = "generate_residence_card"
        
        if not user_data or not case:
            print(f"Skipping row {index+2}: Not enough data in JSON to form a valid query case.")
            continue

        question = f"為 user_id {user_data.get('user_id', 'N/A')} 生成 {character} 風格的居留證"

        print(f"\n{'='*25} Testing Row {index+2} {'='*25}")
        print(f"  Scenario: {scenario_name}")
        print(f"  Character: {character}, Case: {case}")
        print(f"  Query: {question}")
        print(f"{'='*65}")


        try:
            result = engine.query(
                question=question,
                character=character,
                user_data=user_data,
                case=case
            )
            
            # Clean the placeholder from the answer
            cleaned_answer = result.answer.replace("「嘿，[用戶名稱]！", "「")

            print("\n--- Answer ---")
            print(cleaned_answer)
            print(f"  (Processing time: {result.processing_time:.2f}s)")
            print("----------------\n")
        except Exception as e:
            print(f"\n--- Error during query ---")
            print(f"  An error occurred while querying row {index+2}: {e}")
            print("--------------------------\n")

if __name__ == "__main__":
    main()
