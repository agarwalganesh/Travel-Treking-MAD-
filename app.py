
import os
import secrets
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config
from models import db, User, StaffProfile, Trek, Booking

# Initialize Flask App
app = Flask(__name__)
app.config.from_object(Config)

# Initialize Database
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'
login_manager.init_app(app)

# CSRF protection: makes every POST form require a valid token, which blocks
# Cross-Site Request Forgery attacks (Fix #3).
csrf = CSRFProtect(app)

# Rate limiter: caps how often sensitive endpoints can be hit from one IP,
# which slows down password brute-forcing and account enumeration (Fix #4, #9).
limiter = Limiter(
    key_func=get_remote_address,   # identify callers by their IP address
    app=app,
    default_limits=[]              # no global cap; limits are set per-route below
)


# ==========================================
# SECURITY HELPERS
# ==========================================

def is_password_strong(password):
    """
    Enforce a basic password policy (Fix #6).
    Returns (True, "") when the password is acceptable, otherwise
    (False, "reason") describing the first rule that failed.
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(char.isalpha() for char in password):
        return False, "Password must contain at least one letter."
    if not any(char.isdigit() for char in password):
        return False, "Password must contain at least one number."
    return True, ""


def resolve_assigned_staff_id(raw_value, approved_staff):
    """
    Safely turn the submitted 'assigned_staff_id' into a valid id (Fix #7).

    - An empty value means 'no guide assigned' and returns None.
    - A non-numeric value, or an id that is not an approved staff member,
      raises ValueError instead of crashing with an unhandled 500 error.
    """
    if not raw_value:
        return None
    try:
        staff_id = int(raw_value)
    except (TypeError, ValueError):
        raise ValueError("Invalid staff selection.")
    approved_ids = {staff.id for staff in approved_staff}
    if staff_id not in approved_ids:
        raise ValueError("Selected guide is not an approved staff member.")
    return staff_id


@login_manager.user_loader
def load_user(user_id):
    """
    Load user from DB. If user is blacklisted, we return None (or handle it
    safely) to block active sessions.
    """
    user = User.query.get(int(user_id))
    if user and user.is_blacklisted:
        return None  # Automatically logs out the user
    return user


# ==========================================
# PUBLIC ROUTES
# ==========================================

@app.route('/')
def index():
    """Public home/landing page."""
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=['POST'])   # brute-force protection (Fix #4)
def login():
    """Unified login handler for all roles."""
    if current_user.is_authenticated:
        # Redirect to respective dashboard if already logged in
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role == 'staff':
            return redirect(url_for('staff_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()

        # Validate existence & password
        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password credentials.", "danger")
            return redirect(url_for('login'))

        # Check blacklisted status
        if user.is_blacklisted:
            flash("Your account has been blacklisted by the Administrator. Access denied.", "danger")
            return redirect(url_for('login'))

        # Check Staff approval status
        if user.role == 'staff':
            profile = StaffProfile.query.filter_by(user_id=user.id).first()
            if not profile or profile.approval_status != 'Approved':
                flash(f"Login Blocked: Staff account approval status is '{profile.approval_status if profile else 'Pending'}'. Please wait for Admin approval.", "warning")
                return redirect(url_for('login'))

        # Perform login session initiation
        login_user(user)
        flash(f"Welcome back, {user.full_name}! You are signed in as {user.role.upper()}.", "success")

        # Redirect accordingly
        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif user.role == 'staff':
            return redirect(url_for('staff_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))

    return render_template('login.html')


@app.route('/register/user', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=['POST'])   # slow down enumeration/abuse (Fix #9)
def register_user():
    """Trekker registration route."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')

        # Enforce the password policy (Fix #6)
        strong, reason = is_password_strong(password)
        if not strong:
            flash(reason, "danger")
            return redirect(url_for('register_user'))

        # Duplicate check. The message is intentionally generic so it does not
        # confirm to a stranger whether an email is registered (Fix #9).
        if User.query.filter_by(email=email).first():
            flash("Registration could not be completed. If you already have an account, please sign in.", "warning")
            return redirect(url_for('register_user'))

        # Create new Trekker user
        new_user = User(
            full_name=full_name,
            email=email,
            phone=phone,
            password_hash=generate_password_hash(password),
            role='user'
        )
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! You can now sign in.", "success")
        return redirect(url_for('login'))

    return render_template('register_user.html')


@app.route('/register/staff', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=['POST'])   # slow down enumeration/abuse (Fix #9)
def register_staff():
    """Staff guide registration route."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        contact_details = request.form.get('contact_details', '').strip()
        password = request.form.get('password', '')

        # Enforce the password policy (Fix #6)
        strong, reason = is_password_strong(password)
        if not strong:
            flash(reason, "danger")
            return redirect(url_for('register_staff'))

        # Duplicate check with a generic message to avoid leaking which emails
        # are registered (Fix #9).
        if User.query.filter_by(email=email).first():
            flash("Registration could not be completed. If you already have an account, please sign in.", "warning")
            return redirect(url_for('register_staff'))

        # Create User entry
        new_staff = User(
            full_name=full_name,
            email=email,
            phone=phone,
            password_hash=generate_password_hash(password),
            role='staff'
        )
        db.session.add(new_staff)
        db.session.commit() # Commit to generate ID for staff profile link

        # Create Staff Profile (Defaults to Pending status)
        new_profile = StaffProfile(
            user_id=new_staff.id,
            contact_details=contact_details,
            approval_status='Pending'
        )
        db.session.add(new_profile)
        db.session.commit()

        flash("Application submitted successfully! Your account is pending Admin review.", "info")
        return redirect(url_for('login'))

    return render_template('register_staff.html')



@app.route('/logout')
@login_required
def logout():
    """Terminates session."""
    logout_user()
    flash("You have successfully signed out.", "info")
    return redirect(url_for('index'))


# ==========================================
# ADMIN FUNCTIONALITIES
# ==========================================

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard stats and analytics charts."""
    if current_user.role != 'admin':
        flash("Unauthorized: Admin privilege required.", "danger")
        return redirect(url_for('index'))

    # Calculate statistics values
    stats = {
        'total_treks': Trek.query.count(),
        'total_bookings': Booking.query.count(),
        'total_users': User.query.filter_by(role='user').count(),
        'total_staff': User.query.filter_by(role='staff').count(),
        'pending_staff': User.query.join(StaffProfile).filter(StaffProfile.approval_status == 'Pending').count()
    }

    # Generate Chart Data
    # 1. Popular treks (bookings per trek)
    popular_query = db.session.query(
        Trek.trek_name, db.func.count(Booking.id)
    ).join(Booking).filter(Booking.status == 'Booked').group_by(Trek.id).all()
    
    popular_labels = [row[0] for row in popular_query]
    popular_values = [row[1] for row in popular_query]

    # 2. Difficulty distribution
    difficulty_query = db.session.query(
        Trek.difficulty, db.func.count(Trek.id)
    ).group_by(Trek.difficulty).all()
    
    diff_labels = [row[0] for row in difficulty_query]
    diff_values = [row[1] for row in difficulty_query]

    chart_data = {
        'popular_treks': {
            'labels': popular_labels,
            'values': popular_values
        } if popular_labels else None,
        'trek_difficulty': {
            'labels': diff_labels,
            'values': diff_values
        } if diff_labels else None
    }

    return render_template('admin/dashboard.html', stats=stats, chart_data=chart_data)


@app.route('/admin/treks')
@login_required
def manage_treks():
    """Admin list, search, and filter view for treks."""
    if current_user.role != 'admin':
        flash("Unauthorized: Admin privilege required.", "danger")
        return redirect(url_for('index'))

    # Search & filters
    search_query = request.args.get('search', '').strip()
    filter_difficulty = request.args.get('difficulty', '').strip()
    filter_status = request.args.get('status', '').strip()
    filter_location = request.args.get('location', '').strip()

    query = Trek.query

    # Apply search filter (Name or ID)
    if search_query:
        if search_query.isdigit():
            query = query.filter(Trek.id == int(search_query))
        else:
            query = query.filter(Trek.trek_name.like(f"%{search_query}%"))

    # Apply dropdown filters
    if filter_difficulty:
        query = query.filter(Trek.difficulty == filter_difficulty)
    if filter_status:
        query = query.filter(Trek.status == filter_status)
    if filter_location:
        query = query.filter(Trek.location.like(f"%{filter_location}%"))

    treks = query.order_by(Trek.start_date.asc()).all()

    return render_template(
        'admin/treks.html',
        treks=treks,
        search_query=search_query,
        filter_difficulty=filter_difficulty,
        filter_status=filter_status,
        filter_location=filter_location
    )


@app.route('/admin/treks/create', methods=['GET', 'POST'])
@login_required
def create_trek():
    """Admin route to define a new trek expedition."""
    if current_user.role != 'admin':
        flash("Unauthorized: Admin privilege required.", "danger")
        return redirect(url_for('index'))

    # Fetch approved staff list for assignments
    approved_staff = User.query.join(StaffProfile).filter(
        User.role == 'staff',
        StaffProfile.approval_status == 'Approved'
    ).all()

    if request.method == 'POST':
        trek_name = request.form.get('trek_name', '').strip()
        location = request.form.get('location', '').strip()
        difficulty = request.form.get('difficulty')
        
        try:
            duration_days_str = request.form.get('duration_days')
            available_slots_str = request.form.get('available_slots')
            
            if not duration_days_str or not available_slots_str:
                raise ValueError("Duration and Available Slots are required.")
                
            duration_days = int(duration_days_str)
            available_slots = int(available_slots_str)

            if duration_days <= 0 or available_slots < 0:
                raise ValueError("Duration must be positive and slots cannot be negative.")

            # Parse Dates
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')
            
            if not start_date_str or not end_date_str:
                raise ValueError("Start and End dates are required.")

            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            if end_date < start_date:
                raise ValueError("End date cannot be earlier than start date.")

            # Validate the guide assignment here too, so a bad value shows a
            # friendly error instead of crashing with a 500 (Fix #7).
            assigned_staff_id = resolve_assigned_staff_id(
                request.form.get('assigned_staff_id'), approved_staff
            )
        except ValueError as e:
            flash(f"Invalid input: {str(e)}", "danger")
            return render_template('admin/trek_form.html', approved_staff=approved_staff, trek=None)

        status = request.form.get('status', 'Pending')

        # Create Trek
        new_trek = Trek(
            trek_name=trek_name,
            location=location,
            difficulty=difficulty,
            duration_days=duration_days,
            available_slots=available_slots,
            start_date=start_date,
            end_date=end_date,
            status=status,
            assigned_staff_id=assigned_staff_id
        )
        db.session.add(new_trek)
        db.session.commit()

        # Update staff's assigned trek count
        if assigned_staff_id:
            profile = StaffProfile.query.filter_by(user_id=assigned_staff_id).first()
            if profile:
                profile.assigned_trek_count = Trek.query.filter_by(assigned_staff_id=assigned_staff_id).count()
                db.session.commit()

        flash("Trek created successfully!", "success")
        return redirect(url_for('manage_treks'))

    return render_template('admin/trek_form.html', approved_staff=approved_staff, trek=None)


@app.route('/admin/treks/edit/<int:trek_id>', methods=['GET', 'POST'])
@login_required
def edit_trek(trek_id):
    """Admin route to modify trek features and guides."""
    if current_user.role != 'admin':
        flash("Unauthorized: Admin privilege required.", "danger")
        return redirect(url_for('index'))

    trek = Trek.query.get_or_404(trek_id)
    old_staff_id = trek.assigned_staff_id

    # Fetch approved staff list
    approved_staff = User.query.join(StaffProfile).filter(
        User.role == 'staff',
        StaffProfile.approval_status == 'Approved'
    ).all()

    if request.method == 'POST':
        trek.trek_name = request.form.get('trek_name', '').strip()
        trek.location = request.form.get('location', '').strip()
        trek.difficulty = request.form.get('difficulty')
        
        try:
            duration_days_str = request.form.get('duration_days')
            available_slots_str = request.form.get('available_slots')
            
            if not duration_days_str or not available_slots_str:
                raise ValueError("Duration and Available Slots are required.")
                
            duration_days = int(duration_days_str)
            available_slots = int(available_slots_str)

            if duration_days <= 0 or available_slots < 0:
                raise ValueError("Duration must be positive and slots cannot be negative.")

            # Parse dates
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')

            if not start_date_str or not end_date_str:
                raise ValueError("Start and End dates are required.")

            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            if end_date < start_date:
                raise ValueError("End date cannot be earlier than start date.")

            # Validate the guide assignment inside the try as well (Fix #7)
            new_assigned_staff_id = resolve_assigned_staff_id(
                request.form.get('assigned_staff_id'), approved_staff
            )

            trek.duration_days = duration_days
            trek.available_slots = available_slots
            trek.start_date = start_date
            trek.end_date = end_date
        except ValueError as e:
            flash(f"Invalid input: {str(e)}", "danger")
            return render_template('admin/trek_form.html', approved_staff=approved_staff, trek=trek)

        trek.status = request.form.get('status')
        trek.assigned_staff_id = new_assigned_staff_id

        db.session.commit()

        # Update old and new staff trek count trackers
        if old_staff_id:
            old_prof = StaffProfile.query.filter_by(user_id=old_staff_id).first()
            if old_prof:
                old_prof.assigned_trek_count = Trek.query.filter_by(assigned_staff_id=old_staff_id).count()
        if trek.assigned_staff_id:
            new_prof = StaffProfile.query.filter_by(user_id=trek.assigned_staff_id).first()
            if new_prof:
                new_prof.assigned_trek_count = Trek.query.filter_by(assigned_staff_id=trek.assigned_staff_id).count()
        
        db.session.commit()
        flash("Trek details updated successfully!", "success")
        return redirect(url_for('manage_treks'))

    return render_template('admin/trek_form.html', approved_staff=approved_staff, trek=trek)


@app.route('/admin/treks/delete/<int:trek_id>', methods=['POST'])
@login_required
def delete_trek(trek_id):
    """Admin route to delete a trek."""
    if current_user.role != 'admin':
        flash("Unauthorized: Admin privilege required.", "danger")
        return redirect(url_for('index'))

    trek = Trek.query.get_or_404(trek_id)
    staff_id = trek.assigned_staff_id
    
    db.session.delete(trek)
    db.session.commit()

    # Update guide assignments counter
    if staff_id:
        profile = StaffProfile.query.filter_by(user_id=staff_id).first()
        if profile:
            profile.assigned_trek_count = Trek.query.filter_by(assigned_staff_id=staff_id).count()
            db.session.commit()

    flash("Trek deleted successfully.", "success")
    return redirect(url_for('manage_treks'))


@app.route('/admin/staff')
@login_required
def manage_staff():
    """Admin view for staff approvals and blacklisting directory."""
    if current_user.role != 'admin':
        flash("Unauthorized: Admin privilege required.", "danger")
        return redirect(url_for('index'))

    search_query = request.args.get('search', '').strip()
    
    query = User.query.filter(User.role == 'staff')
    
    if search_query:
        if search_query.isdigit():
            query = query.filter(User.id == int(search_query))
        else:
            query = query.filter(User.full_name.like(f"%{search_query}%"))

    staff_list = query.all()
    return render_template('admin/staff.html', staff_list=staff_list, search_query=search_query)


@app.route('/admin/staff/approve/<int:staff_id>', methods=['POST'])
@login_required
def approve_staff(staff_id):
    """Set guide approval status to Approved."""
    if current_user.role != 'admin':
        flash("Unauthorized: Admin privilege required.", "danger")
        return redirect(url_for('index'))

    profile = StaffProfile.query.filter_by(user_id=staff_id).first_or_404()
    profile.approval_status = 'Approved'
    db.session.commit()
    
    flash(f"Staff guide approved successfully.", "success")
    return redirect(url_for('manage_staff'))


@app.route('/admin/staff/reject/<int:staff_id>', methods=['POST'])
@login_required
def reject_staff(staff_id):
    """Set guide approval status to Rejected."""
    if current_user.role != 'admin':
        flash("Unauthorized: Admin privilege required.", "danger")
        return redirect(url_for('index'))

    profile = StaffProfile.query.filter_by(user_id=staff_id).first_or_404()
    profile.approval_status = 'Rejected'
    db.session.commit()
    
    flash("Staff guide request rejected.", "warning")
    return redirect(url_for('manage_staff'))


@app.route('/admin/users')
@login_required
def manage_users():
    """Admin view for managing registered Trekkers."""
    if current_user.role != 'admin':
        flash("Unauthorized: Admin privilege required.", "danger")
        return redirect(url_for('index'))

    search_query = request.args.get('search', '').strip()
    query = User.query.filter(User.role == 'user')

    if search_query:
        if search_query.isdigit():
            query = query.filter(User.id == int(search_query))
        else:
            query = query.filter(User.full_name.like(f"%{search_query}%"))

    users = query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users, search_query=search_query)


@app.route('/admin/toggle-blacklist/<int:user_id>', methods=['POST'])
@login_required
def toggle_blacklist_user(user_id):
    """Block or unblock a user/staff account."""
    if current_user.role != 'admin':
        flash("Unauthorized: Admin privilege required.", "danger")
        return redirect(url_for('index'))

    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        flash("Action Blocked: Admins cannot blacklist other admins.", "danger")
        return redirect(url_for('index'))

    user.is_blacklisted = not user.is_blacklisted
    db.session.commit()

    status_txt = "blacklisted" if user.is_blacklisted else "unblacklisted"
    flash(f"Account for {user.full_name} has been {status_txt}.", "info")

    if user.role == 'staff':
        return redirect(url_for('manage_staff'))
    return redirect(url_for('manage_users'))


@app.route('/admin/bookings')
@login_required
def view_bookings():
    """Global bookings log sheet for admins."""
    if current_user.role != 'admin':
        flash("Unauthorized: Admin privilege required.", "danger")
        return redirect(url_for('index'))

    search_query = request.args.get('search', '').strip()
    filter_status = request.args.get('status', '').strip()

    query = Booking.query

    if search_query:
        query = query.join(User).join(Trek).filter(
            (User.full_name.like(f"%{search_query}%")) | 
            (Trek.trek_name.like(f"%{search_query}%"))
        )

    if filter_status:
        query = query.filter(Booking.status == filter_status)

    bookings = query.order_by(Booking.booking_date.desc()).all()

    # Metrics summary
    counts = {
        'booked': Booking.query.filter_by(status='Booked').count(),
        'cancelled': Booking.query.filter_by(status='Cancelled').count(),
        'completed': Booking.query.filter_by(status='Completed').count()
    }

    return render_template(
        'admin/bookings.html',
        bookings=bookings,
        search_query=search_query,
        filter_status=filter_status,
        counts=counts
    )


@app.route('/admin/bookings/cancel/<int:booking_id>', methods=['POST'])
@login_required
def admin_cancel_booking(booking_id):
    """Cancel booking directly from Admin board."""
    if current_user.role != 'admin':
        flash("Unauthorized: Admin privilege required.", "danger")
        return redirect(url_for('index'))

    booking = Booking.query.get_or_404(booking_id)
    if booking.status == 'Booked':
        booking.status = 'Cancelled'
        # Release seat
        booking.trek.available_slots += 1
        db.session.commit()
        flash("Booking cancelled successfully, slot restored.", "success")
    else:
        flash("Cannot cancel a completed or already cancelled booking.", "warning")

    return redirect(url_for('view_bookings'))


# ==========================================
# STAFF FUNCTIONALITIES
# ==========================================

@app.route('/staff/dashboard')
@login_required
def staff_dashboard():
    """Dashboard listing treks assigned to the logged-in staff member."""
    if current_user.role != 'staff':
        flash("Unauthorized: Staff role required.", "danger")
        return redirect(url_for('index'))

    # Verify approved status
    profile = StaffProfile.query.filter_by(user_id=current_user.id).first()
    if not profile or profile.approval_status != 'Approved':
        flash("Access Denied: Your staff profile is not approved yet.", "warning")
        return redirect(url_for('index'))

    assigned_treks = Trek.query.filter_by(assigned_staff_id=current_user.id).order_by(Trek.start_date.asc()).all()
    return render_template('staff/dashboard.html', assigned_treks=assigned_treks)


@app.route('/staff/treks/<int:trek_id>/update-slots', methods=['POST'])
@login_required
def staff_update_slots(trek_id):
    """Staff route to adjust available seats capacity."""
    if current_user.role != 'staff':
        flash("Unauthorized.", "danger")
        return redirect(url_for('index'))

    trek = Trek.query.get_or_404(trek_id)

    # Security check: Can only modify assigned treks
    if trek.assigned_staff_id != current_user.id:
        flash("Access Denied: You cannot modify details of treks not assigned to you.", "danger")
        return redirect(url_for('staff_dashboard'))

    try:
        new_slots = int(request.form.get('slots', 0))
        if new_slots < 0:
            raise ValueError
        trek.available_slots = new_slots
        db.session.commit()
        flash(f"Available slots for {trek.trek_name} updated to {new_slots}.", "success")
    except ValueError:
        flash("Invalid slots number.", "danger")

    return redirect(url_for('staff_dashboard'))


@app.route('/staff/treks/<int:trek_id>/change-status/<string:action_name>', methods=['POST'])
@login_required
def staff_change_status(trek_id, action_name):
    """Staff route to open, close, start, or complete an assigned trek expedition."""
    if current_user.role != 'staff':
        flash("Unauthorized.", "danger")
        return redirect(url_for('index'))

    trek = Trek.query.get_or_404(trek_id)

    # Security check
    if trek.assigned_staff_id != current_user.id:
        flash("Access Denied: You cannot modify details of treks not assigned to you.", "danger")
        return redirect(url_for('staff_dashboard'))

    if action_name == 'open':
        trek.status = 'Open'
        flash(f"Trek {trek.trek_name} bookings are now OPEN.", "success")
    elif action_name == 'close':
        trek.status = 'Closed'
        flash(f"Trek {trek.trek_name} bookings are now CLOSED.", "warning")
    elif action_name == 'start':
        trek.status = 'Started'
        flash(f"Trek {trek.trek_name} has officially STARTED! Safe travels.", "info")
    elif action_name == 'complete':
        trek.status = 'Completed'
        # Mark all active bookings for this trek as Completed as well
        bookings = Booking.query.filter_by(trek_id=trek.id, status='Booked').all()
        for b in bookings:
            b.status = 'Completed'
        flash(f"Trek {trek.trek_name} marked as COMPLETED. All bookings updated to completed.", "success")
    
    db.session.commit()
    return redirect(url_for('staff_dashboard'))


@app.route('/staff/treks/<int:trek_id>/participants')
@login_required
def staff_trek_participants(trek_id):
    """View registrant details list for an assigned trek."""
    if current_user.role != 'staff':
        flash("Unauthorized.", "danger")
        return redirect(url_for('index'))

    trek = Trek.query.get_or_404(trek_id)

    # Security check
    if trek.assigned_staff_id != current_user.id:
        flash("Access Denied.", "danger")
        return redirect(url_for('staff_dashboard'))

    bookings = Booking.query.filter_by(trek_id=trek_id).all()
    return render_template('staff/participants.html', trek=trek, bookings=bookings)


# ==========================================
# USER (TREKKER) FUNCTIONALITIES
# ==========================================

@app.route('/explorer')
@login_required
def user_dashboard():
    """Trekker dashboard where they search and filter open treks."""
    if current_user.role != 'user':
        flash("Unauthorized: Trekker view only.", "danger")
        return redirect(url_for('index'))

    search_query = request.args.get('search', '').strip()
    filter_difficulty = request.args.get('difficulty', '').strip()
    filter_location = request.args.get('location', '').strip()

    # User search: only show Open treks
    query = Trek.query.filter(Trek.status == 'Open')

    if search_query:
        query = query.filter(Trek.trek_name.like(f"%{search_query}%"))
    if filter_difficulty:
        query = query.filter(Trek.difficulty == filter_difficulty)
    if filter_location:
        query = query.filter(Trek.location.like(f"%{filter_location}%"))

    treks = query.order_by(Trek.start_date.asc()).all()

    return render_template(
        'user/dashboard.html',
        treks=treks,
        search_query=search_query,
        filter_difficulty=filter_difficulty,
        filter_location=filter_location
    )


@app.route('/trek/<int:trek_id>')
@login_required
def trek_details(trek_id):
    """Detailed profile sheet for a specific trek expedition."""
    trek = Trek.query.get_or_404(trek_id)
    
    # Query if this current user has booked this specific trek
    user_booking = Booking.query.filter_by(user_id=current_user.id, trek_id=trek_id).first()

    return render_template('user/trek_details.html', trek=trek, user_booking=user_booking)


@app.route('/trek/<int:trek_id>/book', methods=['POST'])
@login_required
def book_trek(trek_id):
    """Handles reserving a slot on a trek."""
    if current_user.role != 'user':
        flash("Unauthorized: Admins and staff cannot book treks.", "danger")
        return redirect(url_for('index'))

    # Check if blacklisted
    if current_user.is_blacklisted:
        flash("Your account is blacklisted. Booking is blocked.", "danger")
        return redirect(url_for('index'))

    # Acquire trek
    trek = Trek.query.get_or_404(trek_id)

    # Validation: Trek must be Open
    if trek.status != 'Open':
        flash("Booking Failed: Registrations are not open for this trek.", "danger")
        return redirect(url_for('trek_details', trek_id=trek.id))

    # Stop early if the trekker already holds an active booking for this trek.
    existing = Booking.query.filter_by(user_id=current_user.id, trek_id=trek.id).first()
    if existing and existing.status == 'Booked':
        flash("You have already booked this trek expedition.", "info")
        return redirect(url_for('trek_details', trek_id=trek.id))

    # Claim a seat atomically (Fix #5): this single UPDATE decrements the slot
    # count only if seats still remain. The database applies it as one locked
    # step, so two people booking the last seat at the same time can never both
    # succeed -- no overbooking, and slots can never go negative.
    seat_claimed = Trek.query.filter(
        Trek.id == trek.id,
        Trek.available_slots > 0
    ).update({Trek.available_slots: Trek.available_slots - 1}, synchronize_session=False)

    if not seat_claimed:
        db.session.rollback()
        flash("Booking Failed: No seats remaining! This expedition is fully booked.", "danger")
        return redirect(url_for('trek_details', trek_id=trek.id))

    # A seat is now reserved for us; record it by reactivating the cancelled
    # booking or creating a new one, then commit everything together.
    if existing and existing.status == 'Cancelled':
        existing.status = 'Booked'
        flash("Trek booking re-registered successfully!", "success")
    else:
        db.session.add(Booking(user_id=current_user.id, trek_id=trek.id, status='Booked'))
        flash(f"Booking successful! Your slot on {trek.trek_name} is reserved.", "success")

    db.session.commit()
    return redirect(url_for('my_bookings'))


@app.route('/booking/<int:booking_id>/cancel', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    """Enables trekkers to cancel their registrations."""
    booking = Booking.query.get_or_404(booking_id)

    # Security check: must own this booking
    if booking.user_id != current_user.id and current_user.role != 'admin':
        flash("Unauthorized cancellation request.", "danger")
        return redirect(url_for('index'))

    trek = booking.trek

    # Validation: Trek status must be Open
    if trek.status != 'Open' and current_user.role != 'admin':
        flash("Cancellation Blocked: Trek is no longer open for changes.", "danger")
        return redirect(url_for('trek_details', trek_id=trek.id))

    if booking.status == 'Booked':
        booking.status = 'Cancelled'
        # Restore available slot
        trek.available_slots += 1
        db.session.commit()
        flash("Booking cancelled successfully. Your seat has been released.", "info")
    else:
        flash("This booking has already been cancelled or completed.", "warning")

    if current_user.role == 'admin':
        return redirect(url_for('view_bookings'))
    return redirect(url_for('my_bookings'))


@app.route('/my-bookings')
@login_required
def my_bookings():
    """Trekker lists of active registrations and previous history."""
    if current_user.role != 'user':
        flash("Unauthorized view.", "danger")
        return redirect(url_for('index'))

    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.booking_date.desc()).all()
    return render_template('user/my_bookings.html', bookings=bookings)


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Trekker profile details edit endpoint."""
    if current_user.role != 'user':
        flash("Only user trekkers can access profile edits.", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()

        # Email duplicate check
        existing = User.query.filter(User.email == email, User.id != current_user.id).first()
        if existing:
            flash("This email address is already in use by another account.", "danger")
            return redirect(url_for('edit_profile'))

        # Update profile fields
        current_user.full_name = full_name
        current_user.email = email
        current_user.phone = phone
        
        db.session.commit()
        flash("Your profile has been updated successfully.", "success")
        return redirect(url_for('user_dashboard'))

    return render_template('user/edit_profile.html')


# ==========================================
# ERROR PAGES AND VIVA RUNNERS
# ==========================================

@app.errorhandler(404)
def page_not_found(e):
    # Check if request path is an API endpoint
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Resource not found'}), 404
    return render_template('index.html'), 404


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Show a friendly message instead of a raw 400 page when a CSRF token
    is missing or expired (Fix #3)."""
    flash("Your session expired or the form was invalid. Please try again.", "danger")
    return redirect(request.referrer or url_for('index'))


@app.errorhandler(429)
def handle_rate_limit(e):
    """Friendly message when a client hits a rate limit (Fix #4, #9)."""
    flash("Too many attempts. Please wait a minute and try again.", "danger")
    return redirect(request.referrer or url_for('login'))


# ==========================================
# REST API ENDPOINTS (RECOMMENDED)
# ==========================================

@app.route('/api/treks', methods=['GET'])
def api_get_treks():
    """
    Returns a list of open treks in JSON format.
    If logged in as admin, returns all treks.
    """
    is_admin = current_user.is_authenticated and current_user.role == 'admin'
    
    if is_admin:
        treks = Trek.query.all()
    else:
        treks = Trek.query.filter_by(status='Open').all()

    output = []
    for trek in treks:
        output.append({
            'id': trek.id,
            'trek_name': trek.trek_name,
            'location': trek.location,
            'difficulty': trek.difficulty,
            'duration_days': trek.duration_days,
            'available_slots': trek.available_slots,
            'status': trek.status,
            'start_date': trek.start_date.isoformat() if trek.start_date else None,
            'end_date': trek.end_date.isoformat() if trek.end_date else None
        })
    return jsonify(output), 200


@app.route('/api/treks/<int:trek_id>', methods=['GET'])
def api_get_trek(trek_id):
    """
    Returns detailed information about a single trek.
    """
    trek = Trek.query.get_or_404(trek_id)
    
    # Hide details of pending/closed/completed treks from non-admin users
    is_admin = current_user.is_authenticated and current_user.role == 'admin'
    if trek.status != 'Open' and not is_admin:
        return jsonify({'error': 'Unauthorized access or trek is not open.'}), 403

    return jsonify({
        'id': trek.id,
        'trek_name': trek.trek_name,
        'location': trek.location,
        'difficulty': trek.difficulty,
        'duration_days': trek.duration_days,
        'description': trek.description,
        'available_slots': trek.available_slots,
        'status': trek.status,
        'start_date': trek.start_date.isoformat() if trek.start_date else None,
        'end_date': trek.end_date.isoformat() if trek.end_date else None,
        'assigned_staff_id': trek.assigned_staff_id
    }), 200


@app.route('/api/bookings', methods=['GET'])
@login_required
def api_get_bookings():
    """
    Returns all booking records. Admin only.
    """
    if current_user.role != 'admin':
        return jsonify({'error': 'Admin privilege required.'}), 403

    bookings = Booking.query.order_by(Booking.booking_date.desc()).all()
    output = []
    for booking in bookings:
        output.append({
            'id': booking.id,
            'user_id': booking.user_id,
            'trek_id': booking.trek_id,
            'booking_date': booking.booking_date.isoformat(),
            'status': booking.status
        })
    return jsonify(output), 200


@app.route('/api/users', methods=['GET'])
@login_required
def api_get_users():
    """
    Returns all users. Admin only.
    """
    if current_user.role != 'admin':
        return jsonify({'error': 'Admin privilege required.'}), 403

    users = User.query.all()
    output = []
    for user in users:
        output.append({
            'id': user.id,
            'full_name': user.full_name,
            'email': user.email,
            'phone': user.phone,
            'role': user.role,
            'is_blacklisted': user.is_blacklisted,
            'created_at': user.created_at.isoformat()
        })
    return jsonify(output), 200


def init_db():
    """
    Create database tables and seed the default admin account.

    This runs at import time (see the call below) so it also works on serverless
    platforms like Vercel, where the "if __name__ == '__main__'" block never
    executes -- the platform imports the 'app' object instead of running the file.
    """
    with app.app_context():
        db.create_all()

        # Seed the default admin only if it does not exist yet.
        # The password comes from the ADMIN_PASSWORD environment variable; if
        # that is not set, a strong random one is generated and printed once, so
        # we never ship a weak, well-known default like "admin123" (Fix #4).
        # On Vercel you MUST set ADMIN_PASSWORD (and SECRET_KEY) as environment
        # variables, otherwise the admin password changes on every cold start.
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@trek.com')
        admin_password = os.environ.get('ADMIN_PASSWORD')
        admin = User.query.filter_by(email=admin_email).first()

        if not admin:
            generated = admin_password is None
            if generated:
                admin_password = secrets.token_urlsafe(12)

            db.session.add(User(
                full_name="System Administrator",
                email=admin_email,
                phone="9876543210",
                password_hash=generate_password_hash(admin_password),
                role="admin"
            ))
            db.session.commit()

            print("=" * 62)
            print("  Default admin account created")
            print(f"  Email:    {admin_email}")
            if generated:
                print(f"  Password: {admin_password}")
                print("  (Save this now. Set ADMIN_PASSWORD to choose your own.)")
            else:
                print("  Password: (from the ADMIN_PASSWORD environment variable)")
            print("=" * 62)
        elif admin_password and not check_password_hash(admin.password_hash, admin_password):
            # Keep the admin password in sync with the ADMIN_PASSWORD env var.
            # On serverless, a stale /tmp database seeded before the env var was
            # set would otherwise lock the admin out forever on that instance.
            admin.password_hash = generate_password_hash(admin_password)
            db.session.commit()
            print(f"[init_db] Admin password re-synced from ADMIN_PASSWORD for {admin_email}")


# Initialize the database as soon as this module is imported, so it works both
# locally and on serverless (Vercel). Wrapped in try/except so a database hiccup
# can never turn into an "unimportable module" 500 at deploy time.
try:
    init_db()
except Exception as exc:
    print(f"[init_db] warning: {exc}")


# Launch Script -- LOCAL DEVELOPMENT ONLY. On Vercel the platform imports the
# 'app' object above and serves it directly; app.run() is never called there.
if __name__ == '__main__':
    # Security-friendly run defaults (Fix #2):
    #   - debug is OFF unless FLASK_DEBUG=1, so the interactive debugger (which
    #     can run arbitrary code) is never exposed by accident.
    #   - host is 127.0.0.1 (localhost only) unless FLASK_HOST is set, so the
    #     app is not reachable from other machines on the network by default.
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ('1', 'true', 'yes')
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    app.run(debug=debug_mode, host=host, port=5000)
