import json
from datetime import datetime
from extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='employee')  # employee/driver/admin/contractor
    password_hash = db.Column(db.String(256), nullable=False)
    telegram_chat_id = db.Column(db.String(50), nullable=True)
    telegram_link_token = db.Column(db.String(64), nullable=True)
    active = db.Column(db.Boolean, default=True)

    bookings = db.relationship('Booking', backref='user', lazy=True, foreign_keys='Booking.user_id')
    driven_schedules = db.relationship('Schedule', backref='driver', lazy=True, foreign_keys='Schedule.driver_id')
    locations = db.relationship('DriverLocation', backref='driver_user', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.employee_id}>'


class Route(db.Model):
    __tablename__ = 'routes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    origin = db.Column(db.String(200), nullable=False)
    destination = db.Column(db.String(200), nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=45)
    active_days_json = db.Column(db.Text, default='[0,1,2,3,4]')  # 0=Mon..6=Sun
    active = db.Column(db.Boolean, default=True)

    stops = db.relationship('Stop', backref='route', lazy=True, order_by='Stop.order_index', cascade='all, delete-orphan')
    schedules = db.relationship('Schedule', backref='route', lazy=True)

    @property
    def active_days(self):
        return json.loads(self.active_days_json or '[]')

    @active_days.setter
    def active_days(self, value):
        self.active_days_json = json.dumps(value)

    def __repr__(self):
        return f'<Route {self.name}>'


class Stop(db.Model):
    __tablename__ = 'stops'
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    order_index = db.Column(db.Integer, nullable=False)
    pickup_time = db.Column(db.String(10), nullable=True)  # HH:MM

    def __repr__(self):
        return f'<Stop {self.name}>'


class Shift(db.Model):
    __tablename__ = 'shifts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # Morning/Afternoon/Night/OT
    departure_time = db.Column(db.String(10), nullable=False)  # HH:MM

    schedules = db.relationship('Schedule', backref='shift', lazy=True)

    def __repr__(self):
        return f'<Shift {self.name} {self.departure_time}>'


class Schedule(db.Model):
    __tablename__ = 'schedules'
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id'), nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), default='scheduled')  # scheduled/active/completed/cancelled

    bookings = db.relationship('Booking', backref='schedule', lazy=True)
    locations = db.relationship('DriverLocation', backref='schedule', lazy=True)

    @property
    def booked_count(self):
        return Booking.query.filter_by(schedule_id=self.id, status='booked').count() + \
               Booking.query.filter_by(schedule_id=self.id, status='checked_in').count()

    @property
    def seats_remaining(self):
        return self.route.capacity - self.booked_count

    def __repr__(self):
        return f'<Schedule {self.route_id} {self.date}>'


class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedules.id'), nullable=False)
    status = db.Column(db.String(20), default='booked')  # booked/checked_in/no_show/cancelled/waitlisted
    qr_token = db.Column(db.String(36), unique=True, nullable=False)
    recurring = db.Column(db.Boolean, default=False)
    recur_days_json = db.Column(db.Text, default='[]')  # [0,1,2,3,4]
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def recur_days(self):
        return json.loads(self.recur_days_json or '[]')

    @recur_days.setter
    def recur_days(self, value):
        self.recur_days_json = json.dumps(value)

    def __repr__(self):
        return f'<Booking {self.id} {self.status}>'


class DriverLocation(db.Model):
    __tablename__ = 'driver_locations'
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedules.id'), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DriverLocation {self.driver_id} {self.timestamp}>'


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    channel = db.Column(db.String(20), default='app')  # app/telegram

    def __repr__(self):
        return f'<Notification {self.id}>'
