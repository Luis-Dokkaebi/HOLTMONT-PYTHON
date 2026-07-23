import os
from supabase import create_client, Client
from typing import List, Dict, Any, Optional

class SupabaseManager:
    def __init__(self):
        self.url = os.environ["SUPABASE_URL"]
        self.key = os.environ["SUPABASE_KEY"]
        self.client: Client = create_client(self.url, self.key)

    def select(self, table: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            page_size = 1000
            rows: List[Dict[str, Any]] = []
            offset = 0
            while True:
                query = self.client.table(table).select("*").range(offset, offset + page_size - 1)
                if filters:
                    for col, val in filters.items():
                        query = query.eq(col, val)
                page = query.execute().data or []
                rows.extend(page)
                if len(page) < page_size:
                    break
                offset += page_size
            return rows
        except Exception as e:
            print(f"Error fetching from Supabase table {table}: {e}")
            return []

    def insert(self, table: str, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            res = self.client.table(table).insert(row).execute()
            return {'updates': {'updatedRows': len(res.data)}}
        except Exception as e:
            print(f"Error inserting into Supabase table {table}: {e}")
            return None

    # --- Legacy sheet-shaped helpers (kept for tables not yet migrated to the relational schema) ---

    def get_sheet_values(self, sheet_name: str) -> List[List[str]]:
        try:
            response = self.client.table(sheet_name).select("*").execute()
            data = response.data

            if not data:
                return []

            headers = list(data[0].keys())
            values = [headers]
            for row in data:
                values.append([str(row.get(col, "")) if row.get(col) is not None else "" for col in headers])

            return values

        except Exception as e:
            print(f"Error fetching from Supabase table {sheet_name}: {e}")
            return []

    def append_row(self, sheet_name: str, values: List[str]) -> Optional[Dict[str, Any]]:
        try:
            response = self.client.table(sheet_name).select("*").limit(1).execute()
            if not response.data:
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
