import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)


class PatrimonialImport(TimestampMixin, db.Model):
    """Archivo íntegro de procedencia, sin convertir exclusiones en activos."""
    __tablename__ = 'patrimonial_imports'
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_data: Mapped[dict] = mapped_column(JSON, nullable=False)


class PatrimonialSourceChunk(db.Model):
    __tablename__ = 'patrimonial_source_chunks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    import_hash: Mapped[str] = mapped_column(ForeignKey('patrimonial_imports.sha256'), nullable=False)
    sheet: Mapped[str] = mapped_column(String(100), nullable=False)
    first_row: Mapped[int] = mapped_column(Integer, nullable=False)
    rows: Mapped[list] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint('import_hash', 'sheet', 'first_row'),)


class User(TimestampMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    session_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __table_args__ = (CheckConstraint("role IN ('ADMIN','INVENTORY','RESEARCHER','ASSET_MANAGER','VIEWER')", name='ck_users_role'),)

    def public(self):
        return {"id": self.id, "username": self.username, "email": self.email, "fullName": self.full_name,
                "role": self.role, "active": self.active, "mustChangePassword": self.must_change_password}


class Asset(TimestampMixin, db.Model):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __mapper_args__ = {'version_id_col': version}
    sbn: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    internal_code: Mapped[str | None] = mapped_column(String(100))
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(250), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100)); model: Mapped[str | None] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(150), index=True)
    executing_unit: Mapped[str | None] = mapped_column(String(30))
    site: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    building: Mapped[str | None] = mapped_column(String(100)); floor: Mapped[str | None] = mapped_column(String(50))
    room: Mapped[str | None] = mapped_column(String(250)); organizational_unit: Mapped[str | None] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(20), default="OPERATIVO", nullable=False, index=True)
    condition: Mapped[str] = mapped_column(String(20), default="BUENO", nullable=False)
    responsible_person: Mapped[str | None] = mapped_column(String(500)); third_party_user: Mapped[str | None] = mapped_column(String(500))
    processor: Mapped[str | None] = mapped_column(String(500)); memory: Mapped[str | None] = mapped_column(String(500))
    storage: Mapped[str | None] = mapped_column(String(500)); operating_system: Mapped[str | None] = mapped_column(String(500))
    installed_software: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    record_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    record_consistent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    correctly_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    record_updated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    barcode_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    movements = relationship("Movement", cascade="all, delete-orphan", back_populates="asset")
    group_membership = relationship("AssetGroupMember", cascade="all, delete-orphan", back_populates="asset", uselist=False)
    __table_args__ = (CheckConstraint("LENGTH(sbn) = 12"),)

    def api_dict(self):
        return {"id": self.id, "version": self.version, "sbn": self.sbn, "internalCode": self.internal_code, "assetType": self.asset_type,
                "description": self.description, "brand": self.brand, "model": self.model, "serialNumber": self.serial_number,
                "executingUnit": self.executing_unit, "site": self.site, "building": self.building, "floor": self.floor,
                "room": self.room, "organizationalUnit": self.organizational_unit, "status": self.status, "condition": self.condition,
                "responsiblePerson": self.responsible_person, "thirdPartyUser": self.third_party_user, "processor": self.processor,
                "memory": self.memory, "storage": self.storage, "operatingSystem": self.operating_system,
                "installedSoftware": self.installed_software or [], "notes": self.notes, "recordComplete": self.record_complete,
                "recordConsistent": self.record_consistent, "correctlyRegistered": self.correctly_registered,
                "recordUpdated": self.record_updated, "barcodeVerified": self.barcode_verified,
                "lastVerifiedAt": self.last_verified_at.isoformat() if self.last_verified_at else None,
                "createdAt": self.created_at.isoformat(), "updatedAt": self.updated_at.isoformat(),
                "grouping": self.group_membership.api_dict() if self.group_membership else None,
                "groupingAlert": self.asset_type in {"MONITOR", "KEYBOARD", "CPU", "ALL_IN_ONE", "TYPE_1", "TYPE_2", "TYPE_3"} and not self.group_membership}


class AssetGroup(TimestampMixin, db.Model):
    __tablename__ = "asset_groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    group_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    site: Mapped[str] = mapped_column(String(150), nullable=False)
    responsible_person: Mapped[str | None] = mapped_column(String(500))
    members = relationship("AssetGroupMember", cascade="all, delete-orphan", back_populates="group")

    def api_dict(self):
        required = {"ALL_IN_ONE": {"INTEGRATED_UNIT", "KEYBOARD"}, "TYPE_2": {"MONITOR", "KEYBOARD", "CPU"},
                    "TYPE_3": {"MONITOR", "KEYBOARD", "CPU"}}.get(self.group_type, set())
        present = {member.component_role for member in self.members}
        return {"id": self.id, "code": self.code, "groupType": self.group_type, "name": self.name, "site": self.site,
                "responsiblePerson": self.responsible_person, "complete": required.issubset(present),
                "missingRoles": sorted(required - present), "members": [member.api_dict(include_group=False) for member in self.members]}


class AssetGroupMember(db.Model):
    __tablename__ = "asset_group_members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    group_id: Mapped[str] = mapped_column(ForeignKey("asset_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), unique=True, nullable=False)
    component_role: Mapped[str] = mapped_column(String(30), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    group = relationship("AssetGroup", back_populates="members")
    asset = relationship("Asset", back_populates="group_membership")
    __table_args__ = (UniqueConstraint("group_id", "component_role"),)

    def api_dict(self, include_group=True):
        result = {"id": self.id, "groupId": self.group_id, "assetId": self.asset_id, "componentRole": self.component_role,
                  "sbn": self.asset.sbn, "description": self.asset.description, "assetType": self.asset.asset_type}
        if include_group:
            result["group"] = {"id": self.group.id, "code": self.group.code, "groupType": self.group.group_type,
                               "name": self.group.name}
        return result


class Movement(db.Model):
    __tablename__ = "movements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    movement_type: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_site: Mapped[str | None] = mapped_column(String(150)); new_site: Mapped[str | None] = mapped_column(String(150))
    previous_responsible: Mapped[str | None] = mapped_column(String(500)); new_responsible: Mapped[str | None] = mapped_column(String(500))
    reason: Mapped[str] = mapped_column(String(1000), nullable=False); support_document: Mapped[str | None] = mapped_column(String(500))
    performed_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="REQUESTED", nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    asset = relationship("Asset", back_populates="movements")


class Observation(db.Model):
    __tablename__ = "observations"
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __mapper_args__ = {'version_id_col': version}
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    phase: Mapped[str] = mapped_column(String(10), nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    record_complete: Mapped[bool] = mapped_column(Boolean, nullable=False); record_consistent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    correctly_identified: Mapped[bool] = mapped_column(Boolean, nullable=False); identification_method: Mapped[str] = mapped_column(String(100), nullable=False)
    identification_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False); correctly_registered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    record_updated: Mapped[bool] = mapped_column(Boolean, nullable=False); notes: Mapped[str | None] = mapped_column(String(1000))
    observed_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (UniqueConstraint("phase", "asset_id"), CheckConstraint("identification_duration_ms >= 0"))


class ResearchSample(db.Model):
    __tablename__ = "research_sample"
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    sample_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    stratum: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    selected_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class ResearchSettings(db.Model):
    __tablename__ = "research_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    target_size: Mapped[int] = mapped_column(Integer, default=361, nullable=False)
    population_size: Mapped[int] = mapped_column(Integer, default=5958, nullable=False)
    selection_seed: Mapped[str | None] = mapped_column(String(100)); site_filter: Mapped[str | None] = mapped_column(String(150))
    executing_units: Mapped[list] = mapped_column(JSON, default=lambda: ["024", "026", "116"], nullable=False)
    asset_types: Mapped[list] = mapped_column(JSON, default=lambda: ["TYPE_1", "TYPE_2", "TYPE_3", "PRINTER"], nullable=False)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id")); updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ReportTrial(db.Model):
    __tablename__ = "report_trials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    measurement_code: Mapped[str] = mapped_column(String(50), nullable=False); phase: Mapped[str] = mapped_column(String(10), nullable=False)
    report_type: Mapped[str] = mapped_column(String(100), nullable=False); duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    measured_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (UniqueConstraint("measurement_code", "phase"), CheckConstraint("duration_ms >= 0"))


class InventorySession(db.Model):
    __tablename__ = "inventory_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid); name: Mapped[str] = mapped_column(String(150), nullable=False)
    phase: Mapped[str] = mapped_column(String(10), nullable=False); site: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(10), default="OPEN", nullable=False); created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False); closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InventoryCheck(db.Model):
    __tablename__ = "inventory_checks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid); session_id: Mapped[str] = mapped_column(ForeignKey("inventory_sessions.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False); result: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __mapper_args__ = {'version_id_col': version}
    checked_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    scanned_sbn: Mapped[str | None] = mapped_column(String(12)); notes: Mapped[str | None] = mapped_column(String(1000))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)
    __table_args__ = (UniqueConstraint("session_id", "asset_id"),)


class InventoryAssignment(db.Model):
    __tablename__ = 'inventory_assignments'
    session_id: Mapped[str] = mapped_column(ForeignKey('inventory_sessions.id'), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)


class ResearchPhase(db.Model):
    __tablename__ = 'research_phases'
    phase: Mapped[str] = mapped_column(String(10), primary_key=True)
    status: Mapped[str] = mapped_column(String(10), default='OPEN', nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str | None] = mapped_column(String(1000))


class CensusSnapshot(db.Model):
    __tablename__ = 'census_snapshots'
    asset_id: Mapped[str] = mapped_column(ForeignKey('assets.id'), primary_key=True)
    sample_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class Evidence(db.Model):
    __tablename__ = 'evidence'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    check_id: Mapped[str] = mapped_column(ForeignKey('inventory_checks.id'), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    filename: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class LoginThrottle(db.Model):
    __tablename__ = 'login_throttles'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started: Mapped[int] = mapped_column(Integer, nullable=False)
    blocked_until: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GuideStudy(TimestampMixin, db.Model):
    __tablename__ = 'guide_studies'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    source_cells: Mapped[dict] = mapped_column(JSON, nullable=False)
    guides: Mapped[dict] = mapped_column(JSON, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)


class GuideAsset(db.Model):
    __tablename__ = 'guide_assets'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    study_id: Mapped[str] = mapped_column(ForeignKey('guide_studies.id'), nullable=False, index=True)
    sample_code: Mapped[str] = mapped_column(String(20), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    pre: Mapped[dict] = mapped_column(JSON, nullable=False)
    post: Mapped[dict] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint('study_id', 'sample_code'),)


class Catalog(db.Model):
    __tablename__ = "catalogs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid); category: Mapped[str] = mapped_column(String(80), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False); label: Mapped[str] = mapped_column(String(150), nullable=False); active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("category", "code"),)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid); user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), nullable=False); entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100)); details: Mapped[dict | None] = mapped_column(JSON); ip_address: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
