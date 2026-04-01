from __future__ import annotations

from collections import Counter
from urllib.parse import parse_qs, urlparse

from adobe_influencer.core.models import AudienceInsight, CommentRecord, ContentRecord, CreatorProfile, ProductSignalResult, QualityScorecard, ThemeResult, TranscriptSegment
from adobe_influencer.core.text import chunk_text, keyword_counts, normalize_text

POSITIVE_TERMS = {"love", "great", "helpful", "amazing", "perfect", "useful", "clear", "best"}
NEGATIVE_TERMS = {"bad", "confusing", "slow", "expensive", "annoying", "bug", "hate", "broken"}
QUESTION_TERMS = {"how", "what", "why", "can", "does", "where", "which"}
TUTORIAL_TERMS = {"tutorial", "walkthrough", "show", "explain", "teach"}
WORKFLOW_PAIN_TERMS = {"slow", "manual", "friction", "messy", "confusing", "versioning", "formatting"}
COMPARISON_TERMS = {"vs", "versus", "compare", "alternative", "better", "than"}
UNMET_NEED_TERMS = {"wish", "need", "missing", "can't", "cannot"}

THEME_KEYWORDS = {
    "design_education": {"design", "layout", "brand", "photoshop", "illustrator", "color"},
    "video_workflows": {"video", "premiere", "after", "effects", "editing", "b-roll"},
    "productivity_docs": {"pdf", "document", "sign", "client", "proposal", "review"},
    "creator_business": {"client", "freelance", "pricing", "workflow", "brief", "revision"},
}

ADOBE_PRODUCTS = {
    "photoshop": ["photoshop", " ps "],
    "illustrator": ["illustrator"],
    "premiere_pro": ["premiere", "premiere pro"],
    "after_effects": ["after effects", " ae "],
    "lightroom": ["lightroom"],
    "indesign": ["indesign"],
    "adobe_express": ["adobe express"],
    "acrobat": ["acrobat", "pdf", "sign", "e-sign", "review", "annotate", "convert"],
}

COMPETITORS = {
    "canva": ["canva"],
    "figma": ["figma"],
    "capcut": ["capcut"],
    "docusign": ["docusign"],
    "notion": ["notion"],
}


def build_quality_scorecard(creators: list[CreatorProfile], content: list[ContentRecord], analytics_rows: list[dict] | None = None) -> dict[str, QualityScorecard]:
    analytics_map = {row.get("creator_id"): row for row in analytics_rows or []}
    by_creator: dict[str, list[ContentRecord]] = {}
    for item in content:
        by_creator.setdefault(item.creator_id, []).append(item)

    results: dict[str, QualityScorecard] = {}
    for creator in creators:
        items = by_creator.get(creator.creator_id, [])
        engagement_rate = 0.0
        comment_like_ratio = 0.0
        if creator.followers and items:
            engagement_rate = sum((item.likes + item.comments_count) / creator.followers for item in items) / len(items)
        if items:
            comment_like_ratio = sum(item.comments_count / max(item.likes, 1) for item in items) / len(items)
        posting_consistency = min(1.0, creator.posts_last_30_days / 12)
        growth_trend = float(analytics_map.get(creator.creator_id, {}).get("growth_trend", 0.55))
        imported = [analytics_map[creator.creator_id]["source"]] if creator.creator_id in analytics_map else []
        results[creator.creator_id] = QualityScorecard(
            creator_id=creator.creator_id,
            engagement_rate=round(engagement_rate * 100, 2),
            comment_like_ratio=round(comment_like_ratio, 3),
            posting_consistency=round(posting_consistency, 3),
            growth_trend=growth_trend,
            imported_analytics_sources=imported,
        )
    return results


def clean_corpus(*text_groups: list[str]) -> list[str]:
    cleaned: list[str] = []
    for group in text_groups:
        for text in group:
            normalized = normalize_text(text)
            if normalized:
                cleaned.append(normalized)
    return cleaned


def detect_themes(creators: list[CreatorProfile], content: list[ContentRecord], transcripts: list[TranscriptSegment]) -> dict[str, ThemeResult]:
    text_map: dict[str, list[str]] = {creator.creator_id: [creator.bio] for creator in creators}
    for item in content:
        text_map.setdefault(item.creator_id, []).append(item.caption)
        if item.title:
            text_map[item.creator_id].append(item.title)
    for transcript in transcripts:
        text_map.setdefault(transcript.creator_id, []).append(transcript.text)

    output: dict[str, ThemeResult] = {}
    for creator in creators:
        texts = clean_corpus(text_map.get(creator.creator_id, []))
        keyword_list = keyword_counts(texts, top_k=12)
        joined = " ".join(texts).lower()
        theme_rows = []
        for theme_name, lexicon in THEME_KEYWORDS.items():
            hits = sum(joined.count(term) for term in lexicon)
            if hits:
                theme_rows.append(
                    {
                        "theme": theme_name,
                        "share": round(min(1.0, hits / 10), 2),
                        "evidence_terms": [term for term in keyword_list if term in lexicon][:4],
                    }
                )
        theme_rows.sort(key=lambda row: row["share"], reverse=True)
        output[creator.creator_id] = ThemeResult(creator_id=creator.creator_id, themes=theme_rows, keywords=keyword_list)
    return output


def classify_comments(comments: list[CommentRecord]) -> dict[str, AudienceInsight]:
    grouped: dict[str, list[CommentRecord]] = {}
    for comment in comments:
        grouped.setdefault(comment.creator_id, []).append(comment)

    insights: dict[str, AudienceInsight] = {}
    for creator_id, creator_comments in grouped.items():
        sentiment = Counter({"positive": 0, "neutral": 0, "negative": 0})
        intents = Counter({
            "question": 0,
            "tutorial_request": 0,
            "tool_comparison": 0,
            "workflow_pain_point": 0,
            "unmet_need": 0,
        })
        recurring_questions: list[str] = []
        for comment in creator_comments:
            text = normalize_text(comment.text).lower()
            tokens = set(text.split())
            if tokens & POSITIVE_TERMS:
                sentiment["positive"] += 1
            elif tokens & NEGATIVE_TERMS:
                sentiment["negative"] += 1
            else:
                sentiment["neutral"] += 1
            if "?" in comment.text or tokens & QUESTION_TERMS:
                intents["question"] += 1
                recurring_questions.append(comment.text)
            if tokens & TUTORIAL_TERMS:
                intents["tutorial_request"] += 1
            if tokens & COMPARISON_TERMS:
                intents["tool_comparison"] += 1
            if tokens & WORKFLOW_PAIN_TERMS:
                intents["workflow_pain_point"] += 1
            if tokens & UNMET_NEED_TERMS:
                intents["unmet_need"] += 1
        dominant = sentiment.most_common(1)[0][0]
        summary = f"Mostly {dominant} audience response with {intents['question']} question-led comments and {intents['workflow_pain_point']} workflow pain-point mentions."
        insights[creator_id] = AudienceInsight(
            creator_id=creator_id,
            sentiment_summary=summary,
            sentiment_distribution=dict(sentiment),
            intents=dict(intents),
            recurring_questions=recurring_questions[:5],
        )
    return insights


def detect_product_signals(creators: list[CreatorProfile], content: list[ContentRecord], comments: list[CommentRecord], transcripts: list[TranscriptSegment]) -> dict[str, ProductSignalResult]:
    text_map: dict[str, list[str]] = {creator.creator_id: [creator.bio] for creator in creators}
    content_lookup = {item.content_id: item for item in content}
    for item in content:
        text_map.setdefault(item.creator_id, []).append(item.caption)
        if item.title:
            text_map[item.creator_id].append(item.title)
    for comment in comments:
        text_map.setdefault(comment.creator_id, []).append(comment.text)
    for transcript in transcripts:
        text_map.setdefault(transcript.creator_id, []).append(transcript.text)

    results: dict[str, ProductSignalResult] = {}
    for creator in creators:
        corpus = " ".join(clean_corpus(text_map.get(creator.creator_id, [])))
        joined = f" {corpus.lower()} "
        adobe_mentions = {name: sum(joined.count(term) for term in terms) for name, terms in ADOBE_PRODUCTS.items()}
        competitor_mentions = {name: sum(joined.count(term) for term in terms) for name, terms in COMPETITORS.items()}
        creative_cloud_signal = sum(adobe_mentions[name] for name in ("photoshop", "illustrator", "premiere_pro", "after_effects", "lightroom", "indesign", "adobe_express"))
        acrobat_signal = adobe_mentions["acrobat"]
        creative_cloud_fit = min(100.0, 35 + creative_cloud_signal * 8 + joined.count("design") * 1.5)
        acrobat_fit = min(100.0, 25 + acrobat_signal * 7 + joined.count("client") * 1.2 + joined.count("review") * 2)
        evidence_snippets = _build_evidence_snippets(creator.creator_id, content, comments, transcripts, content_lookup)
        risk_flags: list[str] = []
        if competitor_mentions.get("canva", 0) >= 3:
            risk_flags.append("Heavy Canva usage may dilute Adobe Creative Cloud positioning.")
        if competitor_mentions.get("capcut", 0) >= 2:
            risk_flags.append("CapCut is a recurring video workflow comparison point.")
        if "sponsor" not in joined and "affiliate" not in joined:
            risk_flags.append("Limited historical sponsored-content evidence in sample corpus.")
        campaign_angle = (
            "Show Adobe Creative Cloud as the backbone for creator ideation, editing, and client-ready deliverables."
            if creative_cloud_fit >= acrobat_fit
            else "Position Adobe Acrobat as the fastest path from creator draft to signed-off client document and feedback cycle."
        )
        results[creator.creator_id] = ProductSignalResult(
            creator_id=creator.creator_id,
            acrobat_fit=round(acrobat_fit, 2),
            creative_cloud_fit=round(creative_cloud_fit, 2),
            adobe_mentions=adobe_mentions,
            competitor_mentions=competitor_mentions,
            evidence_snippets=evidence_snippets,
            risk_flags=risk_flags,
            recommended_campaign_angle=campaign_angle,
        )
    return results


def _build_evidence_snippets(
    creator_id: str,
    content: list[ContentRecord],
    comments: list[CommentRecord],
    transcripts: list[TranscriptSegment],
    content_lookup: dict[str, ContentRecord],
) -> list[str]:
    target_terms = ("pdf", "acrobat", "photoshop", "illustrator", "premiere", "after effects", "review", "client", "design")
    snippets: list[str] = []
    seen: set[str] = set()

    def maybe_add(kind: str, text: str, source_url: str | None, content_id: str | None = None) -> None:
        normalized = normalize_text(text)
        if not normalized:
            return
        lowered = normalized.lower()
        if not any(term in lowered for term in target_terms):
            return
        quote = chunk_text(normalized, max_words=24)[0]
        source = _resolve_evidence_source_url(creator_id, source_url, content_id, content_lookup)
        snippet = f"[{kind}] {quote}"
        if source:
            snippet = f"{snippet} (source: {source})"
        key = snippet.lower()
        if key not in seen:
            snippets.append(snippet)
            seen.add(key)

    for item in content:
        if item.creator_id != creator_id:
            continue
        maybe_add("caption", f"{item.title or ''} {item.caption}".strip(), item.source_url, item.content_id)

    for comment in comments:
        if comment.creator_id != creator_id:
            continue
        maybe_add("comment", comment.text, comment.source_url, comment.content_id)

    for transcript in transcripts:
        if transcript.creator_id != creator_id:
            continue
        maybe_add("transcript", transcript.text, None, transcript.content_id)

    return snippets[:6]


def _resolve_evidence_source_url(
    creator_id: str,
    source_url: str | None,
    content_id: str | None,
    content_lookup: dict[str, ContentRecord],
) -> str | None:
    candidates: list[str] = []
    if content_id and content_id in content_lookup:
        content = content_lookup[content_id]
        if content.creator_id == creator_id and content.source_url:
            candidates.append(content.source_url)
    if source_url:
        candidates.append(source_url)

    for candidate in candidates:
        normalized = _normalize_supported_source_url(candidate)
        if normalized:
            return normalized
    return None


def _normalize_supported_source_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]

    if host == "instagram.com":
        segments = [segment for segment in parsed.path.split("/") if segment]
        if not segments:
            return None
        if segments[0] in {"p", "reel", "tv"} and len(segments) >= 2:
            return f"https://www.instagram.com/{segments[0]}/{segments[1]}/"
        if len(segments) == 1:
            return f"https://www.instagram.com/{segments[0]}/"
        return None

    if host == "youtube.com":
        segments = [segment for segment in parsed.path.split("/") if segment]
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"
            return None
        if segments and segments[0] == "shorts" and len(segments) >= 2:
            return f"https://www.youtube.com/shorts/{segments[1]}"
        if segments and segments[0].startswith("@"):
            return f"https://www.youtube.com/{segments[0]}"
        if segments and segments[0] in {"channel", "user", "c"} and len(segments) >= 2:
            return f"https://www.youtube.com/{segments[0]}/{segments[1]}"
        return None

    if host == "youtu.be":
        segments = [segment for segment in parsed.path.split("/") if segment]
        if segments:
            return f"https://www.youtube.com/watch?v={segments[0]}"

    return None
