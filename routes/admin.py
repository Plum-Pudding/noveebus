import csv
import io
from datetime import date, datetime, timedelta
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, jsonify, abort, make_response)
from flask_login import login_required, current_user
from models import Route, Stop, Shift, Schedule, Booking, User, DriverLocation
from extensions import db

admin_bp = Blueprint('admin', __name__)


def require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ─── Dashboard ────────────────────────────────────────────────────────────────

@admin_bp.route('/')
@login_required
@require_admin
def dashboard():
    today = date.today()
    total_bookings_today = (Booking.query.join(Schedule)
                            .filter(Schedule.date == today,
                                    Booking.status.in_(['booked', 'checked_in'])).count())
    active_trips = Schedule.query.filter_by(date=today, status='active').count()
    schedules_today = Schedule.query.filter_by(date=today).count()

    # Utilization
    capacity_today = 0
    booked_today = 0
    for s in Schedule.query.filter_by(date=today).all():
        capacity_today += s.route.capacity
        booked_today += s.booked_count
    utilization = round(booked_today / capacity_today * 100, 1) if capacity_today else 0

    # Active driver locations (latest per schedule)
    active_schedules = Schedule.query.filter_by(date=today, status='active').all()
    driver_positions = []
    for s in active_schedules:
        loc = (DriverLocation.query
               .filter_by(schedule_id=s.id)
               .order_by(DriverLocation.timestamp.desc())
               .first())
        if loc:
            driver_positions.append({
                'schedule_id': s.id,
                'route': s.route.name,
                'lat': loc.lat,
                'lon': loc.lon
            })

    routes = Route.query.filter_by(active=True).all()
    return render_template('admin/dashboard.html',
                           today=today,
                           total_bookings_today=total_bookings_today,
                           active_trips=active_trips,
                           schedules_today=schedules_today,
                           utilization=utilization,
                           driver_positions=driver_positions,
                           routes=routes)


# ─── Routes & Stops ───────────────────────────────────────────────────────────

@admin_bp.route('/routes')
@login_required
@require_admin
def routes():
    all_routes = Route.query.all()
    return render_template('admin/routes.html', routes=all_routes)


@admin_bp.route('/routes/add', methods=['POST'])
@login_required
@require_admin
def add_route():
    import json
    name = request.form.get('name', '').strip()
    origin = request.form.get('origin', '').strip()
    destination = request.form.get('destination', '').strip()
    capacity = request.form.get('capacity', 45, type=int)
    active_days = request.form.getlist('active_days', type=int)

    if not all([name, origin, destination]):
        flash('Name, origin and destination are required.', 'warning')
        return redirect(url_for('admin.routes'))

    route = Route(name=name, origin=origin, destination=destination,
                  capacity=capacity)
    route.active_days = active_days or [0, 1, 2, 3, 4]
    db.session.add(route)
    db.session.commit()
    flash(f'Route "{name}" added.', 'success')
    return redirect(url_for('admin.routes'))


@admin_bp.route('/routes/edit/<int:route_id>', methods=['POST'])
@login_required
@require_admin
def edit_route(route_id):
    route = Route.query.get_or_404(route_id)
    route.name = request.form.get('name', route.name).strip()
    route.origin = request.form.get('origin', route.origin).strip()
    route.destination = request.form.get('destination', route.destination).strip()
    route.capacity = request.form.get('capacity', route.capacity, type=int)
    active_days = request.form.getlist('active_days', type=int)
    route.active_days = active_days or [0, 1, 2, 3, 4]
    route.active = request.form.get('active') == 'on'
    db.session.commit()
    flash(f'Route "{route.name}" updated.', 'success')
    return redirect(url_for('admin.routes'))


@admin_bp.route('/routes/delete/<int:route_id>', methods=['POST'])
@login_required
@require_admin
def delete_route(route_id):
    route = Route.query.get_or_404(route_id)
    route.active = False
    db.session.commit()
    flash(f'Route "{route.name}" deactivated.', 'info')
    return redirect(url_for('admin.routes'))


@admin_bp.route('/routes/<int:route_id>/stops/add', methods=['POST'])
@login_required
@require_admin
def add_stop(route_id):
    route = Route.query.get_or_404(route_id)
    name = request.form.get('name', '').strip()
    lat = request.form.get('lat', type=float)
    lon = request.form.get('lon', type=float)
    pickup_time = request.form.get('pickup_time', '').strip()
    order_index = len(route.stops) + 1

    if not all([name, lat, lon]):
        flash('Stop name, lat, lon required.', 'warning')
        return redirect(url_for('admin.routes'))

    stop = Stop(route_id=route_id, name=name, lat=lat, lon=lon,
                order_index=order_index, pickup_time=pickup_time)
    db.session.add(stop)
    db.session.commit()
    flash(f'Stop "{name}" added.', 'success')
    return redirect(url_for('admin.routes'))


@admin_bp.route('/routes/stops/delete/<int:stop_id>', methods=['POST'])
@login_required
@require_admin
def delete_stop(stop_id):
    stop = Stop.query.get_or_404(stop_id)
    db.session.delete(stop)
    db.session.commit()
    flash('Stop removed.', 'info')
    return redirect(url_for('admin.routes'))


# ─── Schedules ────────────────────────────────────────────────────────────────

@admin_bp.route('/schedules')
@login_required
@require_admin
def schedules():
    filter_date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    try:
        filter_date = datetime.strptime(filter_date_str, '%Y-%m-%d').date()
    except ValueError:
        filter_date = date.today()

    scheds = (Schedule.query
              .filter_by(date=filter_date)
              .order_by(Schedule.route_id)
              .all())
    routes = Route.query.filter_by(active=True).all()
    shifts = Shift.query.all()
    drivers = User.query.filter_by(role='driver', active=True).all()
    return render_template('admin/schedules.html',
                           schedules=scheds,
                           routes=routes,
                           shifts=shifts,
                           drivers=drivers,
                           filter_date=filter_date)


@admin_bp.route('/schedules/generate', methods=['POST'])
@login_required
@require_admin
def generate_schedules():
    start_str = request.form.get('start_date')
    end_str = request.form.get('end_date')
    route_ids = request.form.getlist('route_ids', type=int)
    shift_ids = request.form.getlist('shift_ids', type=int)

    try:
        start = datetime.strptime(start_str, '%Y-%m-%d').date()
        end = datetime.strptime(end_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        flash('Invalid date range.', 'danger')
        return redirect(url_for('admin.schedules'))

    if not route_ids:
        route_ids = [r.id for r in Route.query.filter_by(active=True).all()]
    if not shift_ids:
        shift_ids = [s.id for s in Shift.query.all()]

    created = 0
    current = start
    while current <= end:
        for route_id in route_ids:
            route = Route.query.get(route_id)
            if not route:
                continue
            if current.weekday() not in route.active_days:
                continue
            for shift_id in shift_ids:
                existing = Schedule.query.filter_by(
                    route_id=route_id, shift_id=shift_id, date=current
                ).first()
                if not existing:
                    s = Schedule(route_id=route_id, shift_id=shift_id, date=current)
                    db.session.add(s)
                    created += 1
        current += timedelta(days=1)

    db.session.commit()
    flash(f'Generated {created} schedules.', 'success')
    return redirect(url_for('admin.schedules'))


@admin_bp.route('/schedules/assign/<int:schedule_id>', methods=['POST'])
@login_required
@require_admin
def assign_driver(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    driver_id = request.form.get('driver_id', type=int)
    schedule.driver_id = driver_id or None
    db.session.commit()
    flash('Driver assigned.', 'success')
    return redirect(url_for('admin.schedules', date=schedule.date.strftime('%Y-%m-%d')))


@admin_bp.route('/schedules/cancel/<int:schedule_id>', methods=['POST'])
@login_required
@require_admin
def cancel_schedule(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    schedule.status = 'cancelled'
    # Cancel all bookings
    Booking.query.filter_by(schedule_id=schedule_id, status='booked').update({'status': 'cancelled'})
    Booking.query.filter_by(schedule_id=schedule_id, status='waitlisted').update({'status': 'cancelled'})
    db.session.commit()
    flash('Schedule cancelled.', 'info')
    return redirect(url_for('admin.schedules', date=schedule.date.strftime('%Y-%m-%d')))


# ─── Users ────────────────────────────────────────────────────────────────────

@admin_bp.route('/users')
@login_required
@require_admin
def users():
    all_users = User.query.order_by(User.role, User.name).all()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/users/add', methods=['POST'])
@login_required
@require_admin
def add_user():
    employee_id = request.form.get('employee_id', '').strip()
    name = request.form.get('name', '').strip()
    role = request.form.get('role', 'employee')
    password = request.form.get('password', '').strip()

    if not all([employee_id, name, password]):
        flash('All fields required.', 'warning')
        return redirect(url_for('admin.users'))

    if User.query.filter_by(employee_id=employee_id).first():
        flash(f'Employee ID "{employee_id}" already exists.', 'danger')
        return redirect(url_for('admin.users'))

    user = User(employee_id=employee_id, name=name, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f'User "{name}" created.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/edit/<int:user_id>', methods=['POST'])
@login_required
@require_admin
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    user.name = request.form.get('name', user.name).strip()
    user.role = request.form.get('role', user.role)
    user.active = request.form.get('active') == 'on'
    new_pw = request.form.get('password', '').strip()
    if new_pw:
        user.set_password(new_pw)
    db.session.commit()
    flash(f'User "{user.name}" updated.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/deactivate/<int:user_id>', methods=['POST'])
@login_required
@require_admin
def deactivate_user(user_id):
    user = User.query.get_or_404(user_id)
    user.active = False
    db.session.commit()
    flash(f'User "{user.name}" deactivated.', 'info')
    return redirect(url_for('admin.users'))


# ─── Ridership ────────────────────────────────────────────────────────────────

@admin_bp.route('/ridership')
@login_required
@require_admin
def ridership():
    routes = Route.query.all()
    shifts = Shift.query.all()

    route_id = request.args.get('route_id', type=int)
    shift_id = request.args.get('shift_id', type=int)
    start_str = request.args.get('start', (date.today() - timedelta(days=7)).strftime('%Y-%m-%d'))
    end_str = request.args.get('end', date.today().strftime('%Y-%m-%d'))

    try:
        start = datetime.strptime(start_str, '%Y-%m-%d').date()
        end = datetime.strptime(end_str, '%Y-%m-%d').date()
    except ValueError:
        start = date.today() - timedelta(days=7)
        end = date.today()

    query = (Booking.query
             .join(Schedule)
             .filter(Schedule.date >= start, Schedule.date <= end,
                     Booking.status.in_(['booked', 'checked_in', 'no_show'])))
    if route_id:
        query = query.filter(Schedule.route_id == route_id)
    if shift_id:
        query = query.filter(Schedule.shift_id == shift_id)

    bookings = query.all()

    # Build daily trend data
    from collections import defaultdict
    daily = defaultdict(int)
    route_count = defaultdict(int)
    for b in bookings:
        daily[b.schedule.date.strftime('%Y-%m-%d')] += 1
        route_count[b.schedule.route.name] += 1

    chart_dates = sorted(daily.keys())
    chart_counts = [daily[d] for d in chart_dates]
    route_names = list(route_count.keys())
    route_vals = [route_count[r] for r in route_names]

    return render_template('admin/ridership.html',
                           bookings=bookings,
                           routes=routes,
                           shifts=shifts,
                           route_id=route_id,
                           shift_id=shift_id,
                           start=start_str,
                           end=end_str,
                           chart_dates=chart_dates,
                           chart_counts=chart_counts,
                           route_names=route_names,
                           route_vals=route_vals)


# ─── Reports ──────────────────────────────────────────────────────────────────

@admin_bp.route('/reports')
@login_required
@require_admin
def reports():
    return render_template('admin/reports.html',
                           today=date.today().strftime('%Y-%m-%d'))


@admin_bp.route('/reports/export')
@login_required
@require_admin
def export_csv():
    start_str = request.args.get('start', date.today().strftime('%Y-%m-%d'))
    end_str = request.args.get('end', date.today().strftime('%Y-%m-%d'))
    try:
        start = datetime.strptime(start_str, '%Y-%m-%d').date()
        end = datetime.strptime(end_str, '%Y-%m-%d').date()
    except ValueError:
        start = end = date.today()

    bookings = (Booking.query.join(Schedule)
                .filter(Schedule.date >= start, Schedule.date <= end)
                .order_by(Schedule.date)
                .all())

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Route', 'Shift', 'Employee ID', 'Name',
                     'Status', 'Recurring', 'Created At'])
    for b in bookings:
        writer.writerow([
            b.schedule.date.strftime('%Y-%m-%d'),
            b.schedule.route.name,
            b.schedule.shift.name,
            b.user.employee_id,
            b.user.name,
            b.status,
            b.recurring,
            b.created_at.strftime('%Y-%m-%d %H:%M') if b.created_at else ''
        ])

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=noveebus_report_{start_str}_{end_str}.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response


# ─── API: Latest driver positions ─────────────────────────────────────────────

@admin_bp.route('/api/positions')
@login_required
@require_admin
def api_positions():
    today = date.today()
    active_schedules = Schedule.query.filter_by(date=today, status='active').all()
    positions = []
    for s in active_schedules:
        loc = (DriverLocation.query
               .filter_by(schedule_id=s.id)
               .order_by(DriverLocation.timestamp.desc())
               .first())
        if loc:
            positions.append({
                'schedule_id': s.id,
                'route': s.route.name,
                'lat': loc.lat,
                'lon': loc.lon,
                'timestamp': loc.timestamp.isoformat()
            })
    return jsonify(positions)
