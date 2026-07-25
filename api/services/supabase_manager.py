import os
from supabase import create_client, Client
from typing import List, Dict, Any, Optional

class SupabaseManager:
    """Cliente Supabase de inicializacion diferida (lazy).

    Las credenciales siguen siendo obligatorias y nunca se codifican en el
    fuente, pero se resuelven en el *primer uso* y no al importar el modulo.
    Esto permite importar `api.main` (y por lo tanto ejecutar las pruebas
    unitarias del motor de reglas) en entornos sin `SUPABASE_URL` /
    `SUPABASE_KEY`; en produccion el primer acceso a la base falla igual de
    fuerte si la configuracion no existe.
    """

    _warned = False

    def __init__(self):
        self._client: Optional[Client] = None

    @property
    def is_configured(self) -> bool:
        return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"))

    def _skip_unconfigured(self) -> bool:
        """True cuando no hay credenciales; avisa una sola vez y deja que el
        llamador use su ruta de respaldo (mock / datos iniciales)."""
        if self.is_configured:
            return False
        if not SupabaseManager._warned:
            SupabaseManager._warned = True
            print(
                "SUPABASE_URL / SUPABASE_KEY no configuradas: "
                "operando en modo local (mock) sin persistencia remota."
            )
        return True

    @property
    def url(self) -> str:
        return os.environ.get("SUPABASE_URL", "")

    @property
    def key(self) -> str:
        return os.environ.get("SUPABASE_KEY", "")

    @property
    def client(self) -> Client:
        if self._client is None:
            try:
                url = os.environ["SUPABASE_URL"]
                key = os.environ["SUPABASE_KEY"]
            except KeyError as exc:
                raise RuntimeError(
                    "Supabase no esta configurado: define las variables de entorno "
                    "SUPABASE_URL y SUPABASE_KEY (ver .env.example)."
                ) from exc
            self._client = create_client(url, key)
        return self._client

    def select(self, table: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if self._skip_unconfigured():
            return []
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
        if self._skip_unconfigured():
            return None
        try:
            res = self.client.table(table).insert(row).execute()
            return {'updates': {'updatedRows': len(res.data)}}
        except Exception as e:
            print(f"Error inserting into Supabase table {table}: {e}")
            return None

    # --- Legacy sheet-shaped helpers (kept for tables not yet migrated to the relational schema) ---

    def get_sheet_values(self, sheet_name: str) -> List[List[str]]:
        if self._skip_unconfigured():
            return []
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
        if self._skip_unconfigured():
            return None
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
