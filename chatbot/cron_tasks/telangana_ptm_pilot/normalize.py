import io
import re
import pandas as pd


def normalize_text(text: str) -> str:
    """Uppercase, strip punctuation (except hyphens), collapse whitespace."""
    if not text or text.strip().lower() in ("nan", "none", ""):
        return ""
    text = text.upper()
    text = re.sub(r"[^\w\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_schools_df(df) -> list[dict]:
    df.columns = ["district", "mandal", "school_name", "udise_code"]
    df["district"] = df["district"].str.upper().str.strip()
    df["mandal"] = df["mandal"].str.upper().str.strip()
    df["school_name"] = df["school_name"].str.strip()
    df["udise_code"] = df["udise_code"].astype(str).str.strip()
    return df.to_dict("records")


def load_schools(csv_path: str) -> list[dict]:
    return _parse_schools_df(pd.read_csv(csv_path))


def load_schools_from_string(csv_content: str) -> list[dict]:
    return _parse_schools_df(pd.read_csv(io.StringIO(csv_content)))


UNMATCHED_ROW = {
    "district": "",
    "mandal": "",
    "school_name": "UNMATCHED",
    "udise_code": "",
}


class Normalizer:
    def __init__(self, schools: list[dict]):
        self._lookup: dict[str, dict] = {}
        self._duplicates: set[str] = set()
        for school in schools:
            key = normalize_text(school["school_name"])
            if key in self._lookup:
                self._duplicates.add(key)
            self._lookup[key] = school

    def match(self, message: str, translated: str = "") -> dict | None:
        for text in (message, translated):
            key = normalize_text(text)
            if not key:
                continue
            if key in self._lookup and key not in self._duplicates:
                return self._lookup[key]
        return None
