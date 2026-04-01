from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class CreatorORM(Base):
    __tablename__ = "creators"

    creator_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    handle: Mapped[str] = mapped_column(String(128), index=True)
    display_name: Mapped[str] = mapped_column(String(256))
    primary_platform: Mapped[str] = mapped_column(String(64))
    profile_url: Mapped[str] = mapped_column(Text)
    youtube_channel_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    niche: Mapped[str] = mapped_column(String(256))
    bio: Mapped[str] = mapped_column(Text)
    followers: Mapped[int] = mapped_column(Integer, default=0)
    avg_likes: Mapped[int] = mapped_column(Integer, default=0)
    avg_comments: Mapped[int] = mapped_column(Integer, default=0)
    posts_last_30_days: Mapped[int] = mapped_column(Integer, default=0)
    audience_persona: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    contents: Mapped[list["ContentORM"]] = relationship(back_populates="creator")


class ContentORM(Base):
    __tablename__ = "content"

    content_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    creator_id: Mapped[str] = mapped_column(ForeignKey("creators.creator_id"), index=True)
    platform: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    raw_payload_path: Mapped[str] = mapped_column(Text)

    creator: Mapped[CreatorORM] = relationship(back_populates="contents")
    comments: Mapped[list["CommentORM"]] = relationship(back_populates="content")
    transcripts: Mapped[list["TranscriptORM"]] = relationship(back_populates="content")


class CommentORM(Base):
    __tablename__ = "comments"

    comment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("content.content_id"), index=True)
    creator_id: Mapped[str] = mapped_column(String(64), index=True)
    author_name: Mapped[str] = mapped_column(String(256))
    text: Mapped[str] = mapped_column(Text)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime] = mapped_column(DateTime)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    content: Mapped[ContentORM] = relationship(back_populates="comments")


class TranscriptORM(Base):
    __tablename__ = "transcripts"

    transcript_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("content.content_id"), index=True)
    creator_id: Mapped[str] = mapped_column(String(64), index=True)
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)

    content: Mapped[ContentORM] = relationship(back_populates="transcripts")


class CreatorScoreORM(Base):
    __tablename__ = "creator_scores"

    creator_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    overall_brand_fit: Mapped[float] = mapped_column(Float)
    acrobat_fit: Mapped[float] = mapped_column(Float)
    creative_cloud_fit: Mapped[float] = mapped_column(Float)
    audience_sentiment_summary: Mapped[str] = mapped_column(Text)
    recurring_audience_questions: Mapped[list] = mapped_column(JSON, default=list)
    content_theme_map: Mapped[list] = mapped_column(JSON, default=list)
    evidence_snippets: Mapped[list] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    recommended_campaign_angle: Mapped[str] = mapped_column(Text)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DatabaseManager:
    def __init__(self, database_url: str) -> None:
        connect_args = {}
        if database_url.startswith("sqlite:///"):
            sqlite_path = Path(database_url.replace("sqlite:///", "", 1))
            if sqlite_path.name != ":memory:":
                sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            connect_args["check_same_thread"] = False
        self.engine = create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def close(self) -> None:
        """Close the database engine and dispose of the connection pool"""
        if hasattr(self, 'engine') and self.engine:
            self.engine.dispose()

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator:
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
