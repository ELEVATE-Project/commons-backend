from rapidfuzz import process, fuzz
from chatbot.cron_tasks.telangana_ptm_pilot.normalize import normalize_text

HIGH_CONFIDENCE = 85
LOW_CONFIDENCE = 60


def _find_duplicates(schools: list[dict]) -> set[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for s in schools:
        key = normalize_text(s["school_name"])
        if key in seen:
            dupes.add(key)
        seen.add(key)
    return dupes


class FuzzyMatcher:
    def __init__(self, schools: list[dict]):
        self._schools = schools
        self._duplicates = _find_duplicates(schools)
        self._choices = [normalize_text(s["school_name"]) for s in schools]

    def _best_match(self, query: str) -> tuple[dict | None, float]:
        if not query:
            return None, 0.0
        result = process.extractOne(
            query, self._choices, scorer=fuzz.WRatio, score_cutoff=LOW_CONFIDENCE
        )
        if result is None:
            return None, 0.0
        matched_name, score, idx = result
        school = self._schools[idx]
        # Defer duplicates to LLM regardless of score
        if normalize_text(school["school_name"]) in self._duplicates:
            return school, score * 0.5  # artificially lower to trigger Tier 3
        return school, score

    def match(self, message: str, translated: str = "") -> tuple[dict | None, float, str]:
        """Returns (school_row | None, score, method_label)."""
        best_school, best_score = None, 0.0

        for text in (message, translated):
            query = normalize_text(text)
            school, score = self._best_match(query)
            if score > best_score:
                best_school, best_score = school, score

        if best_school is None:
            return None, 0.0, "FUZZY_LOW"

        method = "FUZZY_HIGH" if best_score >= HIGH_CONFIDENCE else "FUZZY_LOW"
        return best_school, best_score, method
