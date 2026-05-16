from datetime import date
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, jsonify, abort)
from flask_login import login_required, current_user
from models import Schedule, Booking, DriverLocation
from extensions import db

driver_bp = Blueprint('driver', __name__)


def require_driver(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role != 'driver':
            abort(403)
        return f(*args, **kwargs)
    return decorated


@driver_bp.route('/')
@login_required
@require_driver
def dashboard():
    today = date.today()
    schedules = (Schedule.query
                 .filter_by(driver_id=current_user.id)
                 .filter(Schedule.date == today)
                 .filter(Schedule.status.in_(['scheduled', 'active']))
                 .all())
    return render_template('driver/dashboard.html',
                           schedules=schedules,
                           today=today)


@driver_bp.route('/trip/<int:schedule_id>')
@login_required
@require_driver
def trip(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    if schedule.driver_id != current_user.id:
        abort(403)

    bookings = (Booking.query
                .filter_by(schedule_id=schedule_id)
                .filter(Booking.status.in_(['booked', 'checked_in', 'no_show', 'waitlisted']))
                .all())
    stops = schedule.route.stops

    return render_template('driver/manifest.html',
                           schedule=schedule,
                           bookings=bookings,
                           stops=stops)


@driver_bp.route('/trip/<int:schedule_id>/start', methods=['POST'])
@login_required
@require_driver
def start_trip(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    if schedule.driver_id != current_user.id:
        abort(403)
    if schedule.status == 'scheduled':
        schedule.status = 'active'
        db.session.commit()
        flash('Trip started!', 'success')
    return redirect(url_for('driver.trip', schedule_id=schedule_id))


@driver_bp.route('/trip/<int:schedule_id>/end', methods=['POST'])
@login_required
@require_driver
def end_trip(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    if schedule.driver_id != current_user.id:
        abort(403)
    if schedule.status == 'active':
        schedule.status = 'completed'
        # Mark unchecked booked passengers as no_show
        Booking.query.filter_by(
            schedule_id=schedule_id, status='booked'
        ).update({'status': 'no_show'})
        db.session.commit()
        flash('Trip completed.', 'success')
    return redirect(url_for('driver.dashboard'))


@driver_bp.route('/noshow/<int:booking_id>', methods=['POST'])
@login_required
@require_driver
def mark_noshow(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    schedule = Schedule.query.get(booking.schedule_id)
    if schedule.driver_id != current_user.id:
        abort(403)
    booking.status = 'no_show'
    db.session.commit()
    return jsonify({'ok': True, 'status': 'no_show'})


@driver_bp.route('/checkin', methods=['POST'])
@login_required
@require_driver
def checkin():
    data = request.get_json(force=True)
    token = data.get('token', '').strip()
    if not token:
        return jsonify({'ok': False, 'message': 'No token provided'}), 400

    booking = Booking.query.filter_by(qr_token=token).first()
    if not booking:
        return jsonify({'ok': False, 'message': 'Invalid QR code'}), 404

    schedule = Schedule.query.get(booking.schedule_id)
    if schedule.driver_id != current_user.id:
        return jsonify({'ok': False, 'message': 'Not your schedule'}), 403

    if booking.status == 'checked_in':
        return jsonify({'ok': True, 'message': f'{booking.user.name} already checked in',
                        'name': booking.user.name, 'status': 'already'})

    if booking.status not in ('booked', 'waitlisted'):
        return jsonify({'ok': False, 'message': f'Booking status: {booking.status}'}), 400

    booking.status = 'checked_in'
    db.session.commit()
    return jsonify({'ok': True, 'message': f'Checked in: {booking.user.name}',
                    'name': booking.user.name, 'booking_id': booking.id})
