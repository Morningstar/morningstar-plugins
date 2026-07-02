"""Tool for querying pillar rating input data IDs."""

import os
from typing import List, Literal
import pandas as pd


def get_pillar_data_id(
    pillar: Literal["parent", "people", "process"],
    manage_type: Literal["active", "passive"]
) -> List[str]:
    """
    Query pillar rating input data and return matching IDs.

    Args:
        pillar: The pillar type (parent, people, or process)
        manage_type: The management type (active or passive)

    Returns:
        List of matching data point IDs
    """
    # Get the path to the Excel file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    excel_path = os.path.join(
        os.path.dirname(current_dir),
        'pillar_rating_input_data.xlsx'
    )

    # Read the Excel file
    try:
        df = pd.read_excel(excel_path, engine="openpyxl")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"pillar_rating_input_data.xlsx not found at {excel_path}. "
            "Ensure the file is present alongside the skill package."
        ) from exc
    except ImportError as exc:
        raise ImportError(
            "Reading pillar_rating_input_data.xlsx requires openpyxl. Install with: pip install openpyxl"
        ) from exc

    # Normalize inputs for case-insensitive matching
    pillar_normalized = pillar.lower().capitalize()
    manage_type_normalized = manage_type.lower().capitalize()

    # Parent inputs are shared across active and passive vehicles.
    if pillar_normalized == "Parent":
        filtered_df = df[df['Pillar'] == pillar_normalized]
    # Filter data based on pillar and manage_type.
    # Handle both exact matches and "Passive/Active" entries for passive queries.
    elif manage_type_normalized == "Passive":
        filtered_df = df[
            (df['Pillar'] == pillar_normalized) &
            ((df['Active/Passive'] == manage_type_normalized) |
             (df['Active/Passive'] == 'Passive/Active'))
        ]
    else:
        filtered_df = df[
            (df['Pillar'] == pillar_normalized) &
            (df['Active/Passive'] == manage_type_normalized)
        ]

    # Extract IDs and clean them (remove tabs and whitespace)
    ids = filtered_df['ID'].astype(str).str.strip().tolist()

    return ids
