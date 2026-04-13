from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)


class DeviceHistory(db.Model):
    __tablename__ = "device_history"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    username = db.Column(db.String(80), nullable=False) 
    action = db.Column(db.String, nullable=False)


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)


class DeviceType(db.Model):
    __tablename__ = "device_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)


class Status(db.Model):
    __tablename__ = "statuses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)


class Crew(db.Model):
    __tablename__ = "crews"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)


class DeactivationReason(db.Model):
    __tablename__ = "deactivation_reasons"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)


class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)

    base_number = db.Column(db.Integer, nullable=False)
    suffix = db.Column(db.Integer, default=0)
    full_number = db.Column(db.String, unique=True, nullable=False)

    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"))
    device_type_id = db.Column(db.Integer, db.ForeignKey("device_types.id"), nullable=False)
    status_id = db.Column(db.Integer, db.ForeignKey("statuses.id"), nullable=False)
    crew_id = db.Column(db.Integer, db.ForeignKey("crews.id"))

    manufacture_date = db.Column(db.Date)
    install_date = db.Column(db.Date)

    location = db.Column(db.String)

    deactivation_date = db.Column(db.Date)
    deactivation_reason_id = db.Column(db.Integer, db.ForeignKey("deactivation_reasons.id"))

    comment = db.Column(db.String)

    is_archived = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)

    department = db.relationship("Department")
    device_type = db.relationship("DeviceType")
    status = db.relationship("Status")
    crew = db.relationship("Crew")
    deactivation_reason = db.relationship("DeactivationReason")
    
    history = db.relationship("DeviceHistory", backref="device", lazy=True, cascade="all, delete-orphan")

    def generate_full_number(self):
        self.full_number = f"{self.base_number:03d}-{self.suffix:02d}"
