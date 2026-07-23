import os
import requests
from supabase import create_client, Client
from typing import List, Dict, Any, Optional

class SupabaseManager:
    def __init__(self):
        self.url = os.environ.get("SUPABASE_URL", "https://zurbtyxhkylnlvcobefy.supabase.co")
        self.key = os.environ.get("SUPABASE_KEY", "sb_secret_wdmpdp9g0QMgHa9ff9eiKg_iLzXK-e_")
        self.client: Client = create_client(self.url, self.key)
        
    def get_sheet_values(self, sheet_name: str) -> List[List[str]]:
        try:
            response = self.client.table(sheet_name).select("*").execute()
            data = response.data
            
            if not data:
                return []
                
            # Extract headers from the first dictionary
            headers = list(data[0].keys())
            
            # Convert dictionaries to list of lists
            values = [headers]
            for row in data:
                values.append([str(row.get(col, "")) if row.get(col) is not None else "" for col in headers])
                
            return values
            
        except Exception as e:
            print(f"Error fetching from Supabase table {sheet_name}: {e}")
            return []

    def append_row(self, sheet_name: str, values: List[str]) -> Optional[Dict[str, Any]]:
        try:
            # First need to get the headers to map the list to a dict
            response = self.client.table(sheet_name).select("*").limit(1).execute()
            if not response.data:
                # If table is empty, we don't know the headers. We'll return None for now.
                print(f"Table {sheet_name} is empty, cannot append row safely without knowing column names.")
                return None
                
            headers = list(response.data[0].keys())
            
            row_dict = {}
            for i, val in enumerate(values):
                if i < len(headers):
                    row_dict[headers[i]] = val
                    
            res = self.client.table(sheet_name).insert(row_dict).execute()
            return {'updates': {'updatedRows': len(res.data)}}
        except Exception as e:
            print(f"Error inserting into Supabase table {sheet_name}: {e}")
            return None

sb_manager = SupabaseManager()
