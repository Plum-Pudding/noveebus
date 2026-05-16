"""
init_db.py — Seed the NoveeBus database with demo data.
Run: python init_db.py
"""
import os
import sys
import uuid
from datetime import date, datetime, timedelta

# Set default DB path for local init
if 'DATABASE_URL' not in os.environ:
    _basedir = os.path.abspath(os.path.dirname(__file__))
    os.environ['DATABASE_URL'] = f'sqlite:///{_basedir}/data/noveebus.db'
if 'SECRET_KEY' not in os.environ:
    os.environ['SECRET_KEY'] = 'dev-seed-key'

from app import create_app
from extensions import db
from models import User, Route, Stop, Shift, Schedule, Booking

app = create_app()

with app.app_context():
    print('Creating tables...')
    db.create_all()

    # ── Users ────────────────────────────────────────────────────────────────

    def make_user(eid, name, role, password):
        u = User.query.filter_by(employee_id=eid).first()
        if not u:
            u = User(employee_id=eid, name=name, role=role)
            u.set_password(password)
            db.session.add(u)
            print(f'  Created user: {eid} ({role})')
        return u

    admin = make_user('admin', 'System Admin', 'admin', 'admin123')
    d1 = make_user('driver01', 'Ahmad Razif', 'driver', 'driver01')
    d2 = make_user('driver02', 'Siti Norzahra', 'driver', 'driver02')
    d3 = make_user('driver03', 'Rajan Krishnan', 'driver', 'driver03')
    e1 = make_user('emp001', 'Wei Ling Tan', 'employee', 'emp001')
    e2 = make_user('emp002', 'Priya Nair', 'employee', 'emp002')
    e3 = make_user('emp003', 'James Lim', 'employee', 'emp003')
    e4 = make_user('emp004', 'Nur Farhana', 'employee', 'emp004')
    e5 = make_user('emp005', 'David Chua', 'employee', 'emp005')
    db.session.flush()

    # ── Shifts ───────────────────────────────────────────────────────────────

    def make_shift(name, departure_time):
        s = Shift.query.filter_by(name=name).first()
        if not s:
            s = Shift(name=name, departure_time=departure_time)
            db.session.add(s)
            print(f'  Created shift: {name} @ {departure_time}')
        return s

    morning = make_shift('Morning', '07:00')
    afternoon = make_shift('Afternoon', '13:00')
    night = make_shift('Night', '21:00')
    ot = make_shift('OT', '18:00')
    db.session.flush()

    # ── Routes & Stops ───────────────────────────────────────────────────────
    # Singapore Jurong/Tuas area coordinates

    def make_route(name, origin, destination, capacity, active_days):
        r = Route.query.filter_by(name=name).first()
        if not r:
            r = Route(name=name, origin=origin, destination=destination, capacity=capacity)
            r.active_days = active_days
            db.session.add(r)
            db.session.flush()
            print(f'  Created route: {name}')
        return r

    def make_stop(route, name, lat, lon, order_index, pickup_time=None):
        s = Stop.query.filter_by(route_id=route.id, name=name).first()
        if not s:
            s = Stop(route_id=route.id, name=name, lat=lat, lon=lon,
                     order_index=order_index, pickup_time=pickup_time)
            db.session.add(s)
        return s

    # Route A: Jurong East MRT → Tuas
    rA = make_route(
        'Route A',
        'Jurong East MRT',
        'Tuas Industrial Estate',
        45,
        [0, 1, 2, 3, 4]  # Mon–Fri
    )
    make_stop(rA, 'Jurong East MRT (Bus Bay)',    1.3329, 103.7436, 1, '06:50')
    make_stop(rA, 'Jurong West Ave 5 Stop',       1.3447, 103.7034, 2, '07:00')
    make_stop(rA, 'Pioneer MRT',                  1.3380, 103.6974, 3, '07:10')
    make_stop(rA, 'Tuas Industrial Estate Gate',  1.3213, 103.6435, 4, '07:25')

    # Route B: Boon Lay MRT → Pioneer Road
    rB = make_route(
        'Route B',
        'Boon Lay MRT',
        'Pioneer Road North',
        40,
        [0, 1, 2, 3, 4]
    )
    make_stop(rB, 'Boon Lay MRT (Pickup)',        1.3384, 103.7059, 1, '06:55')
    make_stop(rB, 'Jurong Point Mall',            1.3401, 103.7059, 2, '07:05')
    make_stop(rB, 'Pioneer Road North Jct',       1.3280, 103.6990, 3, '07:15')
    make_stop(rB, 'Pioneer Road North Gate',      1.3192, 103.6920, 4, '07:25')

    # Route C: Clementi MRT → Joo Koon
    rC = make_route(
        'Route C',
        'Clementi MRT',
        'Joo Koon MRT',
        35,
        [0, 1, 2, 3, 4, 5]  # Mon–Sat
    )
    make_stop(rC, 'Clementi MRT',                 1.3152, 103.7651, 1, '06:45')
    make_stop(rC, 'Dover MRT',                    1.3113, 103.7786, 2, '06:55')
    make_stop(rC, 'Buona Vista MRT',              1.3072, 103.7902, 3, '07:05')
    make_stop(rC, 'Joo Koon MRT',                1.3278, 103.6780, 4, '07:20')

    db.session.flush()

    # ── Schedules ────────────────────────────────────────────────────────────

    routes = [rA, rB, rC]
    shifts = [morning, afternoon]
    drivers_list = [d1, d2, d3]
    driver_idx = 0

    today = date.today()
    created_schedules = []

    print('  Generating schedules for next 7 days...')
    for day_offset in range(7):
        target_date = today + timedelta(days=day_offset)
        for route in routes:
            if target_date.weekday() not in route.active_days:
                continue
            for shift in shifts:
                existing = Schedule.query.filter_by(
                    route_id=route.id, shift_id=shift.id, date=target_date
                ).first()
                if not existing:
                    driver = drivers_list[driver_idx % len(drivers_list)]
                    sched = Schedule(
                        route_id=route.id,
                        shift_id=shift.id,
                        date=target_date,
                        driver_id=driver.id,
                        status='scheduled'
                    )
                    db.session.add(sched)
                    created_schedules.append(sched)
                    driver_idx += 1

    db.session.flush()
    print(f'  Created {len(created_schedules)} schedules')

    # ── Sample bookings ───────────────────────────────────────────────────────

    employees = [e1, e2, e3, e4, e5]
    booking_count = 0

    # Get first 10 schedules and book employees into them
    schedules_to_book = Schedule.query.filter(Schedule.date >= today).limit(15).all()
    for i, sched in enumerate(schedules_to_book):
        for j, emp in enumerate(employees[:3]):  # 3 employees per schedule
            existing = Booking.query.filter_by(
                user_id=emp.id, schedule_id=sched.id
            ).first()
            if not existing:
                b = Booking(
                    user_id=emp.id,
                    schedule_id=sched.id,
                    status='booked',
                    qr_token=str(uuid.uuid4()),
                    recurring=False
                )
                db.session.add(b)
                booking_count += 1

    db.session.commit()
    print(f'  Created {booking_count} sample bookings')
    print()
    print('=' * 50)
    print('Database initialized successfully!')
    print('=' * 50)
    print()
    print('Login credentials:')
    print('  Admin:   admin / admin123')
    print('  Driver:  driver01 / driver01')
    print('  Driver:  driver02 / driver02')
    print('  Driver:  driver03 / driver03')
    print('  Emp:     emp001 / emp001  (Wei Ling Tan)')
    print('  Emp:     emp002 / emp002  (Priya Nair)')
    print('  Emp:     emp003 / emp003  (James Lim)')
    print('  Emp:     emp004 / emp004  (Nur Farhana)')
    print('  Emp:     emp005 / emp005  (David Chua)')
    print()
    print(f'  Routes: {Route.query.count()}')
    print(f'  Shifts: {Shift.query.count()}')
    print(f'  Schedules: {Schedule.query.count()}')
    print(f'  Bookings: {Booking.query.count()}')
