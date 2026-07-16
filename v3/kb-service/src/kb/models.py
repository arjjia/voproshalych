import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from kb.db import Base


class KBChunk(Base):
    __tablename__ = "kb_chunks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace = Column(String(255), nullable=False, default="default")
    doc_id = Column(String(1024), nullable=False, index=True)
    chunk_order_index = Column(Integer, default=0)
    tokens = Column(Integer, default=0)
    content = Column(Text, nullable=False)
    source_url = Column(Text, nullable=True)
    source_type = Column(String(50), nullable=True)
    title = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, default=dict)
    file_path = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    embedding = relationship("KBEmbedding", back_populates="chunk", uselist=False, cascade="all, delete-orphan")


class KBEmbedding(Base):
    __tablename__ = "kb_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_id = Column(String, ForeignKey("kb_chunks.id", ondelete="CASCADE"), nullable=False, unique=True)
    embedding = Column(Vector(1024), nullable=False)
    model = Column(String(255), default="deepvk/USER-bge-m3")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chunk = relationship("KBChunk", back_populates="embedding")
