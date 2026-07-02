import os
import sys
from datetime import datetime, date, timezone

# Add current directory to path to ensure imports work
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app import app, db
from models import User, StaffProfile, Trek, Booking
from werkzeug.security import generate_password_hash

def seed_db():
    print("Initializing database...")
    try:
        with app.app_context():
            db.create_all()

            # 1. Create Default Admin
            admin_email = "admin@trek.com"
            admin = User.query.filter_by(email=admin_email).first()
            if not admin:
                admin = User(
                    full_name="System Administrator",
                    email=admin_email,
                    phone="9876543210",
                    password_hash=generate_password_hash("admin123"),
                    role="admin",
                    is_blacklisted=False
                )
                db.session.add(admin)
                db.session.commit()
                print("Default admin created: admin@trek.com / admin123")
            else:
                print("Default admin already exists.")

            # 2. Check if we already have sample data to prevent duplicate seeding
            if User.query.filter(User.role != 'admin').first():
                print("Sample data already exists. Seeding skipped.")
                return

            print("Seeding sample data...")

            # 3. Create Staff Members with their profiles
            staff1 = User(
                full_name="John Doe",
                email="john@trek.com",
                phone="9876543211",
                password_hash=generate_password_hash("staff123"),
                role="staff",
                is_blacklisted=False
            )
            db.session.add(staff1)
            db.session.flush()

            profile1 = StaffProfile(
                user_id=staff1.id,
                contact_details="Certified Wilderness First Responder (WFR). 8 years of alpine guiding experience.",
                approval_status="Approved",
                assigned_trek_count=2
            )
            db.session.add(profile1)

            staff2 = User(
                full_name="Jane Smith",
                email="jane@trek.com",
                phone="9876543212",
                password_hash=generate_password_hash("staff123"),
                role="staff",
                is_blacklisted=False
            )
            db.session.add(staff2)
            db.session.flush()

            profile2 = StaffProfile(
                user_id=staff2.id,
                contact_details="Experienced trek leader. Specialized in rock climbing and high-altitude rescues.",
                approval_status="Pending",
                assigned_trek_count=0
            )
            db.session.add(profile2)
            db.session.commit()

            # 4. Create Regular Users (Trekkers)
            user1 = User(
                full_name="Alice Brown",
                email="alice@gmail.com",
                phone="9876543220",
                password_hash=generate_password_hash("user123"),
                role="user",
                is_blacklisted=False
            )
            db.session.add(user1)

            user2 = User(
                full_name="Bob Miller",
                email="bob@gmail.com",
                phone="9876543221",
                password_hash=generate_password_hash("user123"),
                role="user",
                is_blacklisted=False
            )
            db.session.add(user2)

            user3 = User(
                full_name="Charlie Green (Blacklisted)",
                email="charlie@gmail.com",
                phone="9876543222",
                password_hash=generate_password_hash("user123"),
                role="user",
                is_blacklisted=True
            )
            db.session.add(user3)
            db.session.commit()

            # 5. Create Treks
            trek1 = Trek(
                trek_name="Himalayan Valley Trek",
                location="Himachal Pradesh",
                difficulty="Moderate",
                duration_days=5,
                description="Explore the beautiful lush green valleys, snow-capped peaks, and crystal-clear rivers of the Himachal region. Ideal for beginners and intermediate trekkers.",
                available_slots=9,
                start_date=date(2026, 7, 10),
                end_date=date(2026, 7, 15),
                status="Open",
                assigned_staff_id=staff1.id
            )
            db.session.add(trek1)

            trek2 = Trek(
                trek_name="Western Ghats Trail",
                location="Maharashtra",
                difficulty="Easy",
                duration_days=2,
                description="A beautiful weekend trail through misty mountains, historic fort ruins, and cascading seasonal waterfalls. Perfect for a quick escape.",
                available_slots=15,
                start_date=date(2026, 8, 1),
                end_date=date(2026, 8, 3),
                status="Open",
                assigned_staff_id=staff1.id
            )
            db.session.add(trek2)

            trek3 = Trek(
                trek_name="Everest Base Camp Expedition",
                location="Nepal",
                difficulty="Hard",
                duration_days=12,
                description="The ultimate bucket-list adventure. Trek to the base of the world's tallest mountain, experiencing Sherpa culture and stunning Himalayan glaciers.",
                available_slots=5,
                start_date=date(2026, 9, 10),
                end_date=date(2026, 9, 22),
                status="Approved",
                assigned_staff_id=None
            )
            db.session.add(trek3)
            db.session.commit()

            # 6. Create Bookings
            booking1 = Booking(
                user_id=user1.id,
                trek_id=trek1.id,
                booking_date=datetime.now(timezone.utc),
                status="Booked"
            )
            db.session.add(booking1)

            booking2 = Booking(
                user_id=user2.id,
                trek_id=trek2.id,
                booking_date=datetime.now(timezone.utc),
                status="Cancelled"
            )
            db.session.add(booking2)
            db.session.commit()

            print("Database successfully seeded with mock data!")
    except Exception as e:
        db.session.rollback()
        print(f"Error seeding database: {str(e)}")
        raise

if __name__ == "__main__":
    seed_db()
