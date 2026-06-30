import json
import re


POSITIVE_WORDS = [
    "good", "great", "excellent", "amazing", "fast", "helpful", "happy",
    "love", "perfect", "resolved", "working", "reliable", "smooth",
    "easy", "improved", "best", "nice", "thank", "thanks"
]

NEGATIVE_WORDS = [
    "bad", "terrible", "awful", "slow", "broken", "issue", "problem",
    "hate", "angry", "poor", "worst", "crash", "crashing", "failed",
    "failure", "expensive", "charged", "overcharged", "no service",
    "not working", "down", "outage", "useless", "complaint", "waiting",
    "wait", "delay", "delayed", "can't", "cannot", "doesn't", "wont",
    "won't"
]


def clean_text(text):
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_keywords(keywords_raw):
    if not keywords_raw:
        return []

    try:
        keywords = json.loads(keywords_raw)
        if isinstance(keywords, list):
            return [str(keyword).lower() for keyword in keywords]
    except Exception:
        pass

    return [
        keyword.strip().lower()
        for keyword in keywords_raw.split(",")
        if keyword.strip()
    ]


def classify_service(text, services):
    """
    services expected format:
    [
        (service_id, service_name, category, description, keywords)
    ]
    """

    cleaned = clean_text(text)

    best_service = None
    best_score = 0
    matched_keywords = []

    for service in services:
        service_id, service_name, category, description, keywords_raw = service

        keywords = load_keywords(keywords_raw)

        score = 0
        current_matches = []

        for keyword in keywords:
            if keyword and keyword in cleaned:
                score += 1
                current_matches.append(keyword)

        # Give a small boost if the service name itself appears
        if service_name and service_name.lower() in cleaned:
            score += 2
            current_matches.append(service_name.lower())

        if score > best_score:
            best_score = score
            best_service = {
                "service_id": service_id,
                "service_name": service_name,
                "category": category,
                "matched_keywords": current_matches
            }
            matched_keywords = current_matches

    if not best_service:
        return {
            "service_id": None,
            "service_name": "Unclassified",
            "category": None,
            "confidence_score": 0.0,
            "matched_keywords": []
        }

    confidence_score = min(1.0, 0.35 + (best_score * 0.15))

    return {
        "service_id": best_service["service_id"],
        "service_name": best_service["service_name"],
        "category": best_service["category"],
        "confidence_score": confidence_score,
        "matched_keywords": matched_keywords
    }


def classify_sentiment(text):
    cleaned = clean_text(text)

    positive_hits = []
    negative_hits = []

    for word in POSITIVE_WORDS:
        if word in cleaned:
            positive_hits.append(word)

    for word in NEGATIVE_WORDS:
        if word in cleaned:
            negative_hits.append(word)

    positive_score = len(positive_hits)
    negative_score = len(negative_hits)

    if positive_score == 0 and negative_score == 0:
        return {
            "sentiment": "Neutral",
            "sentiment_score": 0.0,
            "matched_sentiment_words": []
        }

    if positive_score > negative_score:
        score = min(1.0, 0.4 + positive_score * 0.15)
        return {
            "sentiment": "Positive",
            "sentiment_score": score,
            "matched_sentiment_words": positive_hits
        }

    if negative_score > positive_score:
        score = min(1.0, -0.4 - negative_score * 0.15)
        return {
            "sentiment": "Negative",
            "sentiment_score": score,
            "matched_sentiment_words": negative_hits
        }

    return {
        "sentiment": "Mixed",
        "sentiment_score": 0.0,
        "matched_sentiment_words": positive_hits + negative_hits
    }


def classify_mention(text, services):
    service_result = classify_service(text, services)
    sentiment_result = classify_sentiment(text)

    overall_confidence = round(
        (
            abs(sentiment_result["sentiment_score"]) +
            service_result["confidence_score"]
        ) / 2,
        2
    )

    return {
        "service_id": service_result["service_id"],
        "service_name": service_result["service_name"],
        "category": service_result["category"],
        "sentiment": sentiment_result["sentiment"],
        "sentiment_score": sentiment_result["sentiment_score"],
        "confidence_score": overall_confidence,
        "matched_service_keywords": service_result["matched_keywords"],
        "matched_sentiment_words": sentiment_result["matched_sentiment_words"]
    }