from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone

# Initialize SQLAlchemy
db = SQLAlchemy()

class User(db.Model, UserMixin):
    """
    User model representing Admins, Trek Staff, and Users (Trekkers).
    """
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(15), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user', nullable=False) # admin, staff, user
    is_blacklisted = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    # One User can have many Bookings
    bookings = db.relationship('Booking', backref='user', cascade='all, delete-orphan', lazy=True)
    # One User (with staff role) can have one StaffProfile
    staff_profile = db.relationship('StaffProfile', backref='user_profile', uselist=False, cascade='all, delete-orphan')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class StaffProfile(db.Model):
    """
    Staff Profile model storing contact and approval details for trekking staff.
    One-to-One relationship with User.
    """
    __tablename__ = 'staff_profile'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    contact_details = db.Column(db.Text, nullable=True)
    approval_status = db.Column(db.String(20), default='Pending', nullable=False) # Pending, Approved, Rejected
    specializations = db.Column(db.String(255), nullable=True) # Comma-separated list of certs/specializations
    assigned_trek_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<StaffProfile for User ID {self.user_id} Status: {self.approval_status}>"


class Trek(db.Model):
    """
    Trek model containing details of treks, their difficulty, duration, and slots.
    """
    __tablename__ = 'trek'

    id = db.Column(db.Integer, primary_key=True)
    trek_name = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False) # Easy, Moderate, Hard
    duration_days = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=True)
    available_slots = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Pending', nullable=False) # Pending, Approved, Open, Closed, Completed
    
    # Staff assigned to this trek (foreign key points to user.id of role 'staff')
    assigned_staff_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    # One Trek can have many Bookings
    bookings = db.relationship('Booking', backref='trek', cascade='all, delete-orphan', lazy=True)
    # A Trek points back to the User who is the assigned staff member
    assigned_staff = db.relationship('User', backref='assigned_treks', foreign_keys=[assigned_staff_id])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<Trek {self.trek_name} ({self.location})>"



class Booking(db.Model):
    """
    Booking model tracking which users (trekkers) have booked which treks.
    """
    __tablename__ = 'booking'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    trek_id = db.Column(db.Integer, db.ForeignKey('trek.id'), nullable=False)
    booking_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    status = db.Column(db.String(20), default='Booked', nullable=False) # Booked, Cancelled, Completed

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<Booking User ID {self.user_id} -> Trek ID {self.trek_id} ({self.status})>"


class Review(db.Model):
    """
    Review model representing a Trekker's rating and feedback for a trek.
    """
    __tablename__ = 'review'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    trek_id = db.Column(db.Integer, db.ForeignKey('trek.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False) # 1 to 5 stars
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = db.relationship('User', backref='reviews')
    trek = db.relationship('Trek', backref='reviews')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<Review User ID {self.user_id} -> Trek ID {self.trek_id} ({self.rating} stars)>"