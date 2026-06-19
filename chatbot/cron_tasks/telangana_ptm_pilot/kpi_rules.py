import json
import re


def load_keywords(dynamic_context_str) -> dict:
    if isinstance(dynamic_context_str, dict):
        return dynamic_context_str
    # Strip invalid control characters that break json.loads (e.g. bare \t inside string values)
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', dynamic_context_str)
    return json.loads(cleaned)


def _norm(text: str) -> str:
    text = text.lower()
    # Keep Telugu Unicode block (0900-097F Devanagari, 0C00-0C7F Telugu)
    text = re.sub(r'[^\w\s\u0C00-\u0C7F\u0900-\u097F]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _hit(text: str, keywords: list) -> bool:
    for kw in keywords:
        if _norm(kw) in text:
            return True
    return False


def classify_sentiment(text: str, kw: dict) -> tuple:
    t = _norm(text)
    sk = kw.get('sentiment', {})
    pos = _hit(t, sk.get('positive', []))
    neg = _hit(t, sk.get('negative', []))
    neu = _hit(t, sk.get('neutral', []))

    if pos and neg:
        return {'sentiment': 'mixed'}, 0.85
    if pos:
        return {'sentiment': 'positive'}, 0.9
    if neg:
        return {'sentiment': 'negative'}, 0.9
    if neu:
        return {'sentiment': 'neutral'}, 0.85
    return None, 0.0


def classify_ptm_scheduling(text: str, kw: dict) -> tuple:
    t = _norm(text)
    sk = kw.get('ptm_scheduling', {})

    result = {}

    for dim, keywords_map in [('frequency', sk.get('frequency', {})),
                                ('day', sk.get('day', {})),
                                ('time', sk.get('time', {}))]:
        matched = 'unspecified'
        for label, keywords in keywords_map.items():
            if _hit(t, keywords):
                matched = label
                break
        result[dim] = matched

    if all(v == 'unspecified' for v in result.values()):
        return None, 0.0
    return result, 0.85


def classify_resource_availability(text: str, kw: dict) -> tuple:
    t = _norm(text)
    sk = kw.get('resource_availability', {})

    pos = _hit(t, sk.get('received_positive', []))
    neg = _hit(t, sk.get('received_negative', []))

    if pos and neg:
        return None, 0.0

    if pos:
        materials = [
            label for label, keywords in sk.get('materials', {}).items()
            if _hit(t, keywords)
        ]
        return {'received': 'yes', 'materials': materials}, 0.9

    if neg:
        return {'received': 'no', 'materials': []}, 0.9

    return None, 0.0


def classify_programme_awareness(text: str, kw: dict) -> tuple:
    t = _norm(text)
    sk = kw.get('programme_awareness', {})

    pos = _hit(t, sk.get('aware_positive', []))
    neg = _hit(t, sk.get('aware_negative', []))

    if pos and neg:
        return None, 0.0

    if pos:
        programmes = [
            label for label, keywords in sk.get('programmes', {}).items()
            if _hit(t, keywords)
        ]
        return {'aware': 'yes', 'programmes': programmes}, 0.9

    if neg:
        return {'aware': 'no', 'programmes': []}, 0.9

    return None, 0.0


def classify_school_reputation(text: str, kw: dict) -> tuple:
    t = _norm(text)
    sk = kw.get('school_reputation', {})

    pos = _hit(t, sk.get('recommend_positive', []))
    neg = _hit(t, sk.get('recommend_negative', []))

    if pos and neg:
        return None, 0.0
    if pos:
        return {'recommend': 'yes'}, 0.9
    if neg:
        return {'recommend': 'no'}, 0.9
    return None, 0.0


STAGE_CLASSIFIERS = {
    'PTM_SCHEDULING_PREFERENCE': ('ptm_scheduling',        classify_ptm_scheduling),
    'RESOURCE_AVAILABILITY':     ('resource_availability', classify_resource_availability),
    'PROGRAM_AWARENESS':         ('programme_awareness',   classify_programme_awareness),
    'SCHOOL_REPUTATION':         ('school_reputation',     classify_school_reputation),
}

CONFIDENCE_THRESHOLD = 0.8
