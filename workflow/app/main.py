"""Reusable, file-defined workflow engine with tenant and role checks."""

import hmac
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import DateTime, ForeignKey, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./workflow.db")
INTERNAL_SECRET = os.getenv("INTERNAL_GATEWAY_SECRET", "")
DEFINITIONS_DIR = Path(os.getenv("DEFINITIONS_DIR", "/service/definitions"))


class Transition(BaseModel):
    action: str = Field(min_length=1)
    from_state: str
    to_state: str
    roles: list[str] = Field(min_length=1)


class Definition(BaseModel):
    key: str = Field(min_length=1)
    name: str
    initial_state: str
    states: list[str] = Field(min_length=1)
    transitions: list[Transition]

    @model_validator(mode="after")
    def valid_graph(self):
        states = set(self.states)
        if len(states) != len(self.states) or self.initial_state not in states:
            raise ValueError("Invalid workflow states")
        edges = set()
        for transition in self.transitions:
            if transition.from_state not in states or transition.to_state not in states:
                raise ValueError("Transition uses an unknown state")
            edge = transition.from_state, transition.action
            if edge in edges:
                raise ValueError("Duplicate action from the same state")
            edges.add(edge)
        return self


def load_definitions(directory: Path) -> dict[str, Definition]:
    definitions = {}
    for path in directory.glob("*.json"):
        definition = Definition.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if definition.key in definitions:
            raise ValueError(f"Duplicate workflow key: {definition.key}")
        definitions[definition.key] = definition
    if not definitions:
        raise ValueError("At least one workflow definition is required")
    return definitions


def permitted_transition(definition: Definition, state: str, action: str, roles: set[str]) -> Transition:
    for transition in definition.transitions:
        if transition.from_state == state and transition.action == action:
            if roles.isdisjoint(transition.roles):
                raise HTTPException(status_code=403, detail="Role cannot perform this action")
            return transition
    raise HTTPException(status_code=409, detail="Action is not valid in the current state")


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Instance(Base):
    __tablename__ = "workflow_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    definition_key: Mapped[str] = mapped_column(String(128))
    reference_id: Mapped[str] = mapped_column(String(128), index=True)
    state: Mapped[str] = mapped_column(String(128))
    started_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Event(Base):
    __tablename__ = "workflow_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflow_instances.id"), index=True)
    action: Mapped[str] = mapped_column(String(128))
    from_state: Mapped[str | None] = mapped_column(String(128))
    to_state: Mapped[str] = mapped_column(String(128))
    actor: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InstanceCreate(BaseModel):
    definition_key: str
    reference_id: str = Field(min_length=1, max_length=128)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.definitions = load_definitions(DEFINITIONS_DIR)
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="DX-OS Workflow API", docs_url=None, redoc_url=None, lifespan=lifespan)


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


def instance_dict(instance: Instance) -> dict:
    return {
        "id": instance.id,
        "definition_key": instance.definition_key,
        "reference_id": instance.reference_id,
        "state": instance.state,
        "started_by": instance.started_by,
        "created_at": instance.created_at,
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "workflow"}


@app.get("/definitions")
def list_definitions(identity: tuple[str, str, set[str]] = Depends(caller)) -> list[dict]:
    return [definition.model_dump() for definition in app.state.definitions.values()]


@app.post("/instances", status_code=201)
def start_instance(
    body: InstanceCreate,
    identity: tuple[str, str, set[str]] = Depends(caller),
    db: Session = Depends(db_session),
) -> dict:
    user, tenant, _ = identity
    definition = app.state.definitions.get(body.definition_key)
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    now = datetime.now(timezone.utc)
    instance = Instance(
        id=str(uuid4()), tenant_id=tenant, definition_key=definition.key,
        reference_id=body.reference_id, state=definition.initial_state,
        started_by=user, created_at=now,
    )
    db.add(instance)
    db.flush()  # Parent row must exist before inserting its history event.
    db.add(Event(
        id=str(uuid4()), instance_id=instance.id, action="start",
        from_state=None, to_state=instance.state, actor=user, created_at=now,
    ))
    db.commit()
    return instance_dict(instance)


@app.get("/instances")
def list_instances(
    identity: tuple[str, str, set[str]] = Depends(caller),
    db: Session = Depends(db_session),
) -> list[dict]:
    user, tenant, roles = identity
    statement = select(Instance).where(Instance.tenant_id == tenant)
    if not roles & {"operator", "admin"}:
        statement = statement.where(Instance.started_by == user)
    return [instance_dict(row) for row in db.scalars(statement.order_by(Instance.created_at.desc()))]


@app.get("/instances/{instance_id}")
def get_instance(
    instance_id: str,
    identity: tuple[str, str, set[str]] = Depends(caller),
    db: Session = Depends(db_session),
) -> dict:
    user, tenant, roles = identity
    instance = db.get(Instance, instance_id)
    if not instance or instance.tenant_id != tenant or (
        instance.started_by != user and not roles & {"operator", "admin"}
    ):
        raise HTTPException(status_code=404, detail="Workflow instance not found")
    events = db.scalars(
        select(Event).where(Event.instance_id == instance.id).order_by(Event.created_at, Event.id)
    )
    return {
        **instance_dict(instance),
        "history": [
            {"action": event.action, "from_state": event.from_state,
             "to_state": event.to_state, "actor": event.actor,
             "created_at": event.created_at}
            for event in events
        ],
    }


@app.post("/instances/{instance_id}/actions/{action}")
def take_action(
    instance_id: str,
    action: str,
    identity: tuple[str, str, set[str]] = Depends(caller),
    db: Session = Depends(db_session),
) -> dict:
    user, tenant, roles = identity
    instance = db.scalar(select(Instance).where(Instance.id == instance_id).with_for_update())
    if not instance or instance.tenant_id != tenant:
        raise HTTPException(status_code=404, detail="Workflow instance not found")
    definition = app.state.definitions[instance.definition_key]
    transition = permitted_transition(definition, instance.state, action, roles)
    old_state = instance.state
    instance.state = transition.to_state
    db.add(Event(
        id=str(uuid4()), instance_id=instance.id, action=action,
        from_state=old_state, to_state=instance.state,
        actor=user, created_at=datetime.now(timezone.utc),
    ))
    db.commit()
    return instance_dict(instance)

