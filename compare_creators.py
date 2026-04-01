from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMON = ROOT / "services" / "common"
if str(COMMON) not in sys.path:
    sys.path.insert(0, str(COMMON))

from adobe_influencer.core.config import AppSettings
from adobe_influencer.core.logging import configure_logging, get_logger
from adobe_influencer.core.models import (
    AudienceInsight,
    CommentRecord,
    ContentRecord,
    ContentType,
    CreatorProfile,
    SourcePlatform,
)
from adobe_influencer.ingestion.seeds import load_creator_seeds
from adobe_influencer.nlp.pipeline import (
    build_quality_scorecard,
    classify_comments,
    detect_product_signals,
    detect_themes,
)
from adobe_influencer.scoring.engine import PersonaAnalyzer, RecommendationScorer
from adobe_influencer.storage.analytics import AnalyticsStore
from adobe_influencer.storage.database import DatabaseManager
from adobe_influencer.storage.repositories import Repository
from adobe_influencer.storage.vector_store import VectorStore
from datetime import UTC, datetime

logger = get_logger(__name__)


class RealCreatorAdapter:
    """Adapter to read pre-existing raw_lake data for real creators"""
    
    def __init__(self, raw_lake_dir: Path):
        self.raw_lake_dir = raw_lake_dir
    
    def ingest(self, seeds):
        creators = []
        content_items = []
        comments = []
        
        for seed in seeds:
            profile_path = self.raw_lake_dir / f"{seed.creator_id}_profile.json"
            posts_path = self.raw_lake_dir / f"{seed.creator_id}_posts.json"
            
            if not profile_path.exists() or not posts_path.exists():
                logger.warning(f"Missing data files for {seed.creator_id}")
                continue
            
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            posts = json.loads(posts_path.read_text(encoding="utf-8"))
            
            creators.append(self._normalize_creator(seed, profile, posts))
            content_items.extend(self._normalize_content(seed, posts))
            comments.extend(self._normalize_comments(seed, posts))
            
        logger.info(f"Loaded data for {len(creators)} creators")
        return creators, content_items, comments
    
    def _normalize_creator(self, seed, profile, posts):
        # Calculate averages from recent posts
        recent_posts = posts[:5] if len(posts) >= 5 else posts
        avg_likes = int(sum((post.get("likesCount", 0) or 0) for post in recent_posts) / max(len(recent_posts), 1))
        avg_comments = int(sum((post.get("commentsCount", 0) or 0) for post in recent_posts) / max(len(recent_posts), 1))
        
        return CreatorProfile(
            creator_id=seed.creator_id,
            handle=profile.get("username", seed.handle),
            display_name=profile.get("full_name", seed.display_name),
            primary_platform=SourcePlatform.instagram,
            profile_url=str(seed.profile_url),
            youtube_channel_url=None,
            website_url=profile.get("external_url"),
            niche=seed.niche,
            bio=profile.get("biography", seed.bio),
            followers=profile.get("followers", 0),
            avg_likes=avg_likes,
            avg_comments=avg_comments,
            posts_last_30_days=len([p for p in posts if self._is_recent(p.get("timestamp"))]),
            audience_persona=seed.audience_persona,
        )
    
    def _is_recent(self, timestamp):
        if not timestamp:
            return False
        try:
            # Handle both ISO string and Unix timestamp
            if isinstance(timestamp, str):
                post_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                post_time = datetime.fromtimestamp(timestamp, UTC)
            days_ago = (datetime.now(UTC) - post_time).days
            return days_ago <= 30
        except:
            return False
    
    def _normalize_content(self, seed, posts):
        records = []
        for post in posts[:15]:  # Process top 15 posts
            content_type = ContentType.video if post.get("type") == "Video" else ContentType.post
            
            # Parse timestamp
            posted_at = datetime.now(UTC)
            if post.get("timestamp"):
                try:
                    # Try ISO format first (string)
                    if isinstance(post["timestamp"], str):
                        posted_at = datetime.fromisoformat(post["timestamp"].replace('Z', '+00:00'))
                    else:
                        # Unix timestamp (integer)
                        posted_at = datetime.fromtimestamp(post["timestamp"], UTC)
                except:
                    posted_at = datetime.now(UTC)
            
            post_url = post.get("url", f"https://www.instagram.com/p/{post.get('shortCode', '')}/")
            
            records.append(
                ContentRecord(
                    content_id=f"ig_{post.get('id')}",
                    creator_id=seed.creator_id,
                    platform=SourcePlatform.instagram,
                    content_type=content_type,
                    source_url=post_url,
                    title=None,
                    caption=post.get("caption", ""),
                    published_at=posted_at,
                    likes=post.get("likesCount", 0),
                    comments_count=post.get("commentsCount", 0),
                    views=post.get("videoViewCount") or post.get("playCount") or 0,
                    raw_payload_path=f"{seed.creator_id}_posts.json",
                )
            )
        return records
    
    def _normalize_comments(self, seed, posts):
        comments = []
        for post in posts[:10]:  # Get comments from first 10 posts
            post_comments = post.get("latestComments", [])
            for comment in post_comments[:5]:  # Top 5 comments per post
                # Parse timestamp
                posted_at = datetime.now(UTC)
                if comment.get("timestamp"):
                    try:
                        # Try ISO format first (string)
                        if isinstance(comment["timestamp"], str):
                            posted_at = datetime.fromisoformat(comment["timestamp"].replace('Z', '+00:00'))
                        else:
                            # Unix timestamp (integer)
                            posted_at = datetime.fromtimestamp(comment["timestamp"], UTC)
                    except:
                        posted_at = datetime.now(UTC)
                
                comments.append(
                    CommentRecord(
                        comment_id=f"ig_comment_{comment.get('id', len(comments))}",
                        content_id=f"ig_{post.get('id')}",
                        creator_id=seed.creator_id,
                        author_name=comment.get("ownerUsername", "unknown"),
                        text=comment.get("text", ""),
                        likes=comment.get("likesCount", 0),
                        published_at=posted_at,
                        source_url=None,
                    )
                )
        return comments


def main():
    settings = AppSettings()
    settings.ensure_paths()
    configure_logging(settings.log_level)
    
    # Initialize storage
    db = DatabaseManager(settings.database_url)
    db.create_all()
    repo = Repository(db)
    analytics_store = AnalyticsStore(settings.duckdb_path)
    vector_store = VectorStore(str(settings.vector_store_path), settings.chroma_collection)
    
    # Load creator seeds
    live_seed_path = settings.imports_dir / "live_creator_seeds.json"
    seeds = load_creator_seeds(live_seed_path)
    
    # Ingest using existing raw data
    adapter = RealCreatorAdapter(settings.raw_lake_dir)
    creators, content, comments = adapter.ingest(seeds)
    
    # Store in database
    repo.upsert_creators(creators)
    repo.upsert_content(content)
    repo.upsert_comments(comments)
    
    # Run analysis pipeline
    quality = build_quality_scorecard(creators, content, [])
    themes = detect_themes(creators, content, [])
    audience = classify_comments(comments)
    
    # Fill in missing audience insights
    for creator in creators:
        if creator.creator_id not in audience:
            audience[creator.creator_id] = AudienceInsight(
                creator_id=creator.creator_id,
                sentiment_summary="No detailed audience comments available in this analysis.",
                sentiment_distribution={"positive": 0, "neutral": 0, "negative": 0},
                intents={
                    "question": 0,
                    "tutorial_request": 0,
                    "tool_comparison": 0,
                    "workflow_pain_point": 0,
                    "unmet_need": 0,
                },
                recurring_questions=[],
            )
    
    product = detect_product_signals(creators, content, comments, [])
    personas = PersonaAnalyzer().analyze({creator.creator_id: creator.audience_persona for creator in creators})
    
    # Score and rank
    scorer = RecommendationScorer(settings.configs_dir / "scoring_weights.yaml")
    recommendations = scorer.score(
        creator_lookup={creator.creator_id: {"display_name": creator.display_name, "handle": creator.handle} for creator in creators},
        quality=quality,
        themes=themes,
        audience=audience,
        product=product,
        personas=personas,
    )
    
    # Store results
    repo.replace_recommendations(recommendations)
    analytics_store.persist_recommendations(recommendations)
    
    # Generate detailed comparison report
    output_path = settings.output_dir / "real_creators_comparison.md"
    generate_comparison_report(creators, recommendations, content, comments, themes, audience, product, output_path)
    
    # Also save JSON
    json_path = settings.output_dir / "real_creators_comparison.json"
    json_data = {
        "creators": [
            {
                "creator_id": rec.creator_id,
                "handle": rec.handle,
                "display_name": rec.creator_name,
                "overall_score": rec.overall_brand_fit,
                "acrobat_score": rec.acrobat_fit,
                "creative_cloud_score": rec.creative_cloud_fit,
                "audience_sentiment": rec.audience_sentiment_summary,
                "campaign_angle": rec.recommended_campaign_angle,
                "risk_flags": rec.risk_flags,
                "recurring_questions": rec.recurring_audience_questions,
                "evidence": rec.evidence_snippets[:10],
            }
            for rec in recommendations
        ]
    }
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")
    
    logger.info(f"✅ Analysis complete for {len(recommendations)} creators")
    logger.info(f"📊 Comparison report: {output_path}")
    logger.info(f"📄 JSON data: {json_path}")
    
    print(f"\n✅ Analysis complete!")
    print(f"📊 Detailed comparison: {output_path}")
    print(f"📄 JSON data: {json_path}")


def generate_comparison_report(creators, recommendations, content, comments, themes, audience, product, output_path):
    """Generate a detailed comparison report with descriptions and citations"""
    
    # Sort by overall score
    sorted_recs = sorted(recommendations, key=lambda x: x.overall_brand_fit, reverse=True)
    
    lines = []
    lines.append("# Real Creator Comparison Analysis")
    lines.append(f"\n**Analysis Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"\n**Creators Analyzed:** {len(creators)}")
    lines.append("\n---\n")
    
    # Executive Summary
    lines.append("## Executive Summary\n")
    lines.append("This report compares three Instagram creators for Adobe brand partnership potential, ")
    lines.append("analyzing their content themes, audience engagement, Adobe product signals, and overall brand fit.\n")
    
    # Rankings Table
    lines.append("\n## Overall Rankings\n")
    lines.append("| Rank | Creator | Handle | Overall Score | Acrobat Fit | Creative Cloud Fit | Followers |")
    lines.append("|------|---------|--------|---------------|-------------|-------------------|-----------|")
    for i, rec in enumerate(sorted_recs, 1):
        creator = next(c for c in creators if c.creator_id == rec.creator_id)
        lines.append(
            f"| {i} | {rec.creator_name} | @{rec.handle} | "
            f"**{rec.overall_brand_fit:.1f}** | {rec.acrobat_fit:.1f} | "
            f"{rec.creative_cloud_fit:.1f} | {creator.followers:,} |"
        )
    
    # Detailed Analysis for Each Creator
    lines.append("\n---\n")
    lines.append("## Detailed Creator Analysis\n")
    
    for i, rec in enumerate(sorted_recs, 1):
        creator = next(c for c in creators if c.creator_id == rec.creator_id)
        creator_content = [c for c in content if c.creator_id == rec.creator_id]
        creator_comments = [c for c in comments if c.creator_id == rec.creator_id]
        
        lines.append(f"\n### {i}. {rec.creator_name} (@{rec.handle})\n")
        lines.append(f"**Profile:** [{creator.profile_url}]({creator.profile_url})\n")
        
        # Overview
        lines.append("#### Overview\n")
        lines.append(f"- **Niche:** {creator.niche}")
        lines.append(f"- **Bio:** {creator.bio}")
        lines.append(f"- **Followers:** {creator.followers:,}")
        lines.append(f"- **Average Likes:** {creator.avg_likes:,}")
        lines.append(f"- **Average Comments:** {creator.avg_comments:,}")
        lines.append(f"- **Posts (Last 30 Days):** {creator.posts_last_30_days}")
        if creator.website_url:
            lines.append(f"- **Website:** {creator.website_url}")
        lines.append("")
        
        # Scores
        lines.append("#### Adobe Brand Fit Scores\n")
        lines.append(f"- **Overall Brand Fit:** {rec.overall_brand_fit:.2f}/100")
        lines.append(f"- **Adobe Acrobat Fit:** {rec.acrobat_fit:.2f}/100")
        lines.append(f"- **Adobe Creative Cloud Fit:** {rec.creative_cloud_fit:.2f}/100")
        lines.append("")
        
        # Content Analysis
        lines.append("#### Content Analysis\n")
        lines.append(f"**Total Posts Analyzed:** {len(creator_content)}")
        
        video_count = sum(1 for c in creator_content if c.content_type == ContentType.video)
        image_count = len(creator_content) - video_count
        lines.append(f"- Video Posts: {video_count}")
        lines.append(f"- Image Posts: {image_count}")
        
        if creator_content:
            total_likes = sum(c.likes for c in creator_content)
            total_comments = sum(c.comments_count for c in creator_content)
            lines.append(f"- Total Engagement: {total_likes:,} likes, {total_comments:,} comments")
            lines.append(f"- Engagement Rate: ~{(total_likes / creator.followers * 100):.2f}%")
        lines.append("")
        
        # Themes
        if rec.creator_id in themes:
            theme_data = themes[rec.creator_id]
            lines.append("#### Content Themes\n")
            if hasattr(theme_data, 'themes') and theme_data.themes:
                for theme in theme_data.themes[:5]:
                    lines.append(f"- **{theme}**")
            lines.append("")
        
        # Audience Insights
        lines.append("#### Audience Insights\n")
        lines.append(f"**Sentiment:** {rec.audience_sentiment_summary}\n")
        
        if rec.recurring_audience_questions:
            lines.append("**Recurring Questions:**")
            for q in rec.recurring_audience_questions:
                lines.append(f"- _{q}_")
            lines.append("")
        
        # Adobe Product Signals
        if rec.creator_id in product:
            prod_signals = product[rec.creator_id]
            lines.append("#### Adobe Product Signals\n")
            if hasattr(prod_signals, 'acrobat_signals') and prod_signals.acrobat_signals:
                lines.append(f"**Acrobat Mentions:** {len(prod_signals.acrobat_signals)} signals detected")
                for signal in prod_signals.acrobat_signals[:3]:
                    lines.append(f"- {signal}")
            if hasattr(prod_signals, 'creative_cloud_signals') and prod_signals.creative_cloud_signals:
                lines.append(f"\n**Creative Cloud Mentions:** {len(prod_signals.creative_cloud_signals)} signals detected")
                for signal in prod_signals.creative_cloud_signals[:3]:
                    lines.append(f"- {signal}")
            lines.append("")
        
        # Campaign Strategy
        lines.append("#### Recommended Campaign Strategy\n")
        lines.append(f"**Campaign Angle:** {rec.recommended_campaign_angle}\n")
        
        if rec.risk_flags:
            risk_str = ', '.join(rec.risk_flags) if isinstance(rec.risk_flags, list) else rec.risk_flags
            lines.append(f"**⚠️ Risk Flags:** {risk_str}\n")
        
        # Evidence Snippets (Citations)
        lines.append("#### Evidence & Citations\n")
        lines.append("*Sample content demonstrating Adobe product fit:*\n")
        for j, evidence in enumerate(rec.evidence_snippets[:5], 1):
            # Clean and truncate evidence
            clean_evidence = evidence.replace('\n', ' ').strip()
            if len(clean_evidence) > 200:
                clean_evidence = clean_evidence[:200] + "..."
            lines.append(f"{j}. \"{clean_evidence}\"")
        lines.append("")
        
        # Sample Posts
        if creator_content:
            lines.append("#### Top Performing Posts\n")
            top_posts = sorted(creator_content, key=lambda x: x.likes, reverse=True)[:3]
            for post in top_posts:
                caption = post.caption[:150].replace('\n', ' ') if post.caption else "No caption"
                lines.append(f"- **{post.content_type.value.title()}** ({post.likes:,} likes) - \"{caption}...\"")
                if post.source_url:
                    lines.append(f"  - Link: {post.source_url}")
            lines.append("")
        
        lines.append("---\n")
    
    # Comparative Analysis
    lines.append("\n## Comparative Analysis\n")
    lines.append("### Strengths & Differentiation\n")
    
    for rec in sorted_recs:
        creator = next(c for c in creators if c.creator_id == rec.creator_id)
        lines.append(f"\n**{rec.creator_name}:**")
        
        if rec.overall_brand_fit >= 75:
            lines.append(f"- ✅ **Strong overall fit** ({rec.overall_brand_fit:.1f}/100)")
        elif rec.overall_brand_fit >= 60:
            lines.append(f"- ⚠️ **Moderate fit** ({rec.overall_brand_fit:.1f}/100)")
        else:
            lines.append(f"- ⚠️ **Needs evaluation** ({rec.overall_brand_fit:.1f}/100)")
        
        if rec.acrobat_fit > 80:
            lines.append("- Strong Acrobat product alignment")
        if rec.creative_cloud_fit > 80:
            lines.append("- Strong Creative Cloud alignment")
        
        if creator.followers > 400000:
            lines.append(f"- Large audience reach ({creator.followers:,} followers)")
        elif creator.followers > 100000:
            lines.append(f"- Mid-tier audience reach ({creator.followers:,} followers)")
        
        lines.append(f"- Niche: {creator.niche}")
    
    # Recommendations
    lines.append("\n\n## Final Recommendations\n")
    lines.append(f"1. **Top Priority:** {sorted_recs[0].creator_name} (@{sorted_recs[0].handle}) - ")
    lines.append(f"Highest overall score ({sorted_recs[0].overall_brand_fit:.1f}) with {sorted_recs[0].recommended_campaign_angle.lower()}")
    
    if len(sorted_recs) > 1:
        lines.append(f"\n2. **Secondary Option:** {sorted_recs[1].creator_name} (@{sorted_recs[1].handle}) - ")
        lines.append(f"Strong alternative ({sorted_recs[1].overall_brand_fit:.1f}) with {sorted_recs[1].recommended_campaign_angle.lower()}")
    
    if len(sorted_recs) > 2:
        lines.append(f"\n3. **Tertiary Option:** {sorted_recs[2].creator_name} (@{sorted_recs[2].handle}) - ")
        lines.append(f"Consider for specific campaigns ({sorted_recs[2].overall_brand_fit:.1f})")
    
    lines.append("\n\n---")
    lines.append("\n*Report generated by Adobe Influencer Intelligence System*")
    
    output_path.write_text('\n'.join(lines), encoding='utf-8')


if __name__ == "__main__":
    main()
