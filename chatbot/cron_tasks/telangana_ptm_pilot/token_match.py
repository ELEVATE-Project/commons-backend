import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from chatbot.cron_tasks.telangana_ptm_pilot.normalize import normalize_text

HIGH_TOKEN_SCORE = 0.70
TOP_K = 10  # candidates passed to LLM tier


def _find_duplicates(schools: list[dict]) -> set[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for s in schools:
        key = normalize_text(s["school_name"])
        if key in seen:
            dupes.add(key)
        seen.add(key)
    return dupes


class TokenMatcher:
    def __init__(self, schools: list[dict]):
        self._schools = schools
        self._duplicates = _find_duplicates(schools)
        self._norm_names = [normalize_text(s["school_name"]) for s in schools]
        self._vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1)
        self._matrix = self._vectorizer.fit_transform(self._norm_names)

    def match(
        self, message: str, translated: str = ""
    ) -> tuple[dict | None, float, list[dict]]:
        """
        Returns (best_match | None, best_score, top_k_candidates).
        top_k_candidates is always populated when there's any signal — used by LLM tier.
        """
        best_match: dict | None = None
        best_score = 0.0
        best_candidates: list[dict] = []

        for text in (message, translated):
            query = normalize_text(text)
            if not query:
                continue
            try:
                query_vec = self._vectorizer.transform([query])
            except Exception:
                continue

            scores = cosine_similarity(query_vec, self._matrix)[0]
            top_indices = np.argsort(scores)[::-1][:TOP_K]
            candidates = [
                (self._schools[idx], float(scores[idx]))
                for idx in top_indices
                if scores[idx] > 0.05
            ]

            if candidates and candidates[0][1] > best_score:
                best_score = candidates[0][1]
                best_match = candidates[0][0]
                best_candidates = [c[0] for c in candidates]

        # Duplicate school names need LLM to disambiguate across mandals
        is_duplicate = (
            best_match is not None
            and normalize_text(best_match["school_name"]) in self._duplicates
        )
        if is_duplicate:
            best_score = min(best_score, HIGH_TOKEN_SCORE - 0.01)

        method = "TOKEN_HIGH" if best_score >= HIGH_TOKEN_SCORE else "TOKEN_LOW"
        return best_match, best_score, best_candidates, method
