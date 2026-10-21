"""Tenant-scoped structured records and S3-compatible object storage."""

import hmac
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, ForeignKey, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")
INTERNAL_SECRET = os.getenv("INTERNAL_GATEWAY_SECRET", "")
S3_BUCKET = os.getenv("S3_BUCKET", "dxos-objects")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Record(Base):
    __tablename__ = "records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StoredObject(Base):
    __tablename__ = "stored_objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    record_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("records.id"))
    object_key: Mapped[str] = mapped_column(String(256), unique=True)
    content_type: Mapped[str] = mapped_column(String(128))
    size: Mapped[int]
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecordCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=128)
    payload: dict


class RecordPatch(BaseModel):
    payload: dict


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://localhost:9000"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY", ""),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY", ""),
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )


def ensure_bucket(client) -> None:
    try:
        client.head_bucket(Bucket=S3_BUCKET)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code not in {"404", "NoSuchBucket"}:
            raise
        client.create_bucket(Bucket=S3_BUCKET)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="DX-OS Data API", docs_url=None, redoc_url=None, lifespan=lifespan)


def db_session():
    with SessionLocal() as db:
        yield db


def caller(
    x_internal_secret: str | None = Header(default=None),
    x_dxos_user: str | None = Header(default=None),
    x_dxos_tenant: str | None = Header(default=None),
    x_dxos_roles: str = Header(default=""),
) -> tuple[str, str, set[str]]:
    if not INTERNAL_SECRET or not x_internal_secret or not hmac.compare_digest(
        x_internal_secret, INTERNAL_SECRET
    ):
        raise HTTPException(status_code=403, detail="Gateway access required")
    if not x_dxos_user or not x_dxos_tenant:
        raise HTTPException(status_code=403, detail="Identity context required")
    return x_dxos_user, x_dxos_tenant, set(x_dxos_roles.split(","))


def may_read(owner: str, user: str, roles: set[str]) -> bool:
    return owner == user or bool(roles & {"operator", "admin"})


def record_dict(record: Record) -> dict:
    return {
        "id": record.id,
        "kind": record.kind,
        "payload": record.payload,
        "created_by": record.created_by,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "data"}


@app.post("/records", status_code=201)
def create_record(
    body: RecordCreate,
    identity: tuple[str, str, set[str]] = Depends(caller),
    db: Session = Depends(db_session),
) -> dict:
    user, tenant, _ = identity
    now = datetime.now(timezone.utc)
    record = Record(
        id=str(uuid4()), tenant_id=tenant, kind=body.kind, payload=body.payload,
        created_by=user, created_at=now, updated_at=now,
    )
    db.add(record)
    db.commit()
    return record_dict(record)


@app.get("/records")
def list_records(
    identity: tuple[str, str, set[str]] = Depends(caller),
    db: Session = Depends(db_session),
) -> list[dict]:
    user, tenant, roles = identity
    statement = select(Record).where(Record.tenant_id == tenant)
    if not roles & {"operator", "admin"}:
        statement = statement.where(Record.created_by == user)
    return [record_dict(row) for row in db.scalars(statement.order_by(Record.created_at.desc()))]


@app.get("/records/{record_id}")
def get_record(
    record_id: str,
    identity: tuple[str, str, set[str]] = Depends(caller),
    db: Session = Depends(db_session),
) -> dict:
    user, tenant, roles = identity
    record = db.get(Record, record_id)
    if not record or record.tenant_id != tenant or not may_read(record.created_by, user, roles):
        raise HTTPException(status_code=404, detail="Record not found")
    return record_dict(record)


@app.patch("/records/{record_id}")
def update_record(
    record_id: str,
    body: RecordPatch,
    identity: tuple[str, str, set[str]] = Depends(caller),
    db: Session = Depends(db_session),
) -> dict:
    user, tenant, roles = identity
    record = db.get(Record, record_id)
    if not record or record.tenant_id != tenant or not may_read(record.created_by, user, roles):
        raise HTTPException(status_code=404, detail="Record not found")
    record.payload = body.payload
    record.updated_at = datetime.now(timezone.utc)
    db.commit()
    return record_dict(record)


@app.post("/objects", status_code=201)
def upload_object(
    file: UploadFile = File(...),
    record_id: str | None = None,
    identity: tuple[str, str, set[str]] = Depends(caller),
    db: Session = Depends(db_session),
) -> dict:
    user, tenant, roles = identity
    if record_id:
        record = db.get(Record, record_id)
        if not record or record.tenant_id != tenant or not may_read(record.created_by, user, roles):
            raise HTTPException(status_code=404, detail="Record not found")
    contents = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Maximum upload size is 10 MiB")
    object_id = str(uuid4())
    key = f"{tenant}/{object_id}"
    content_type = file.content_type or "application/octet-stream"
    try:
        client = s3_client()
        ensure_bucket(client)
        client.put_object(Bucket=S3_BUCKET, Key=key, Body=contents, ContentType=content_type)
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=503, detail="Object storage unavailable") from exc
    item = StoredObject(
        id=object_id, tenant_id=tenant, record_id=record_id, object_key=key,
        content_type=content_type, size=len(contents), created_by=user,
        created_at=datetime.now(timezone.utc),
    )
    db.add(item)
    db.commit()
    return {"id": item.id, "record_id": item.record_id, "size": item.size,
            "content_type": item.content_type}


@app.get("/objects/{object_id}")
def download_object(
    object_id: str,
    identity: tuple[str, str, set[str]] = Depends(caller),
    db: Session = Depends(db_session),
):
    user, tenant, roles = identity
    item = db.get(StoredObject, object_id)
    if not item or item.tenant_id != tenant or not may_read(item.created_by, user, roles):
        raise HTTPException(status_code=404, detail="Object not found")
    try:
        source = s3_client().get_object(Bucket=S3_BUCKET, Key=item.object_key)["Body"]
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=503, detail="Object storage unavailable") from exc
    return StreamingResponse(source.iter_chunks(), media_type=item.content_type)

