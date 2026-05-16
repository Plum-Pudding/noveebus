import uuid
import io
from datetime import date, datetime, timedelta
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, send_file, abort)
from flask_login import login_required, current_user
from models import Route, Shift, Schedule, Booking, Stop
from extensions import db

employee_bp = Blueprint('employee', __name__)


def require_employee(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role not in ('employee', 'contractor'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


@employee_bp.route('/')
@login_required
@require_employee
def dashboard():
    today = date.today()
    bookings = (Booking.query
                .join(Schedule)
                .filter(Booking.user_id == current_user.id,
                        Schedule.date == today,
                        Booking.status.in_(['booked', 'checked_in', 'waitlisted']))
                .all())
    upcoming = (Booking.query
                .join(Schedule)
                .filter(Booking.user_id == current_user.id,
                        Schedule.date >= today,
                        Booking.status.in_(['booked', 'waitlisted']))
                .order_by(Schedule.date)
                .limit(5)
                .all())
    return render_template('employee/dashboard.html',
                           bookings=bookings,
                           upcoming=upcoming,
                           today=today)


@employee_bp.route('/book', methods=['GET', 'POST'])
@login_required
@require_employee
def book():
    routes = Route.query.filter_by(active=True).all()
    shifts = Shift.query.all()

    if request.method == 'POST':
        route_id = request.form.get('route_id', type=int)
        shift_id = request.form.get('shift_id', type=int)
        book_date_str = request.form.get('book_date')
        recurring = request.form.get('recurring') == 'on'
        recur_days = request.form.getlist('recur_days', type=int)

        if not all([route_id, shift_id, book_date_str]):
            flash('Please fill in all fields.', 'warning')
            return redirect(url_for('employee.book'))

        try:
            book_date = datetime.strptime(book_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format.', 'danger')
            return redirect(url_for('employee.book'))

        if book_date < date.today():
            flash('Cannot book a past date.', 'warning')
            return redirect(url_for('employee.book'))

        if recurring and recur_days:
            # Create bookings for next 4 weeks for each selected day
            created = 0
            for week in range(4):
                for day in recur_days:
                    target = book_date + timedelta(weeks=week)
                    # Find the next occurrence of this weekday from target
                    days_ahead = day - target.weekday()
                    if days_ahead < 0:
                        days_ahead += 7
                    target_date = target + timedelta(days=days_ahead)

                    sched = Schedule.query.filter_by(
                        route_id=route_id, shift_id=shift_id, date=target_date
                    ).first()
                    if not sched:
                        continue

                    # Check not already booked
                    existing = Booking.query.filter_by(
                        user_id=current_user.id, schedule_id=sched.id
                    ).filter(Booking.status.in_(['booked', 'waitlisted', 'checked_in'])).first()
                    if existing:
                        continue

                    status = 'booked' if sched.seats_remaining > 0 else 'waitlisted'
                    booking = Booking(
                        user_id=current_user.id,
                        schedule_id=sched.id,
                        status=status,
                        qr_token=str(uuid.uuid4()),
                        recurring=True,
                        recur_days_json=str(recur_days)
                    )
                    db.session.add(booking)
                    created += 1

            db.session.commit()
            _send_booking_telegram(current_user, f'{created} recurring bookings')
            flash(f'Created {created} recurring bookings!', 'success')
            return redirect(url_for('employee.my_bookings'))
        else:
            # Single booking
            sched = Schedule.query.filter_by(
                route_id=route_id, shift_id=shift_id, date=book_date
            ).first()

            if not sched:
                flash('No schedule found for that route/shift/date.', 'warning')
                return redirect(url_for('employee.book'))

            existing = Booking.query.filter_by(
                user_id=current_user.id, schedule_id=sched.id
            ).filter(Booking.status.in_(['booked', 'waitlisted', 'checked_in'])).first()
            if existing:
                flash('You already have a booking for this schedule.', 'warning')
                return redirect(url_for('employee.my_bookings'))

            status = 'booked' if sched.seats_remaining > 0 else 'waitlisted'
            booking = Booking(
                user_id=current_user.id,
                schedule_id=sched.id,
                status=status,
                qr_token=str(uuid.uuid4()),
                recurring=False
            )
            db.session.add(booking)
            db.session.commit()

            _send_booking_telegram(current_user, sched)
            if status == 'waitlisted':
                flash('Seat full — you have been added to the waitlist.', 'info')
            else:
                flash('Booking confirmed!', 'success')
            return redirect(url_for('employee.qr_code', booking_id=booking.id))

    # GET: compute seats remaining for display
    today = date.today()
    return render_template('employee/book.html',
                           routes=routes,
                           shifts=shifts,
                           today=today,
                           min_date=today.strftime('%Y-%m-%d'),
                           max_date=(today + timedelta(days=30)).strftime('%Y-%m-%d'))


@employee_bp.route('/bookings')
@login_required
@require_employee
def my_bookings():
    today = date.today()
    bookings = (Booking.query
                .join(Schedule)
                .filter(Booking.user_id == current_user.id,
                        Schedule.date >= today)
                .order_by(Schedule.date)
                .all())
    past = (Booking.query
            .join(Schedule)
            .filter(Booking.user_id == current_user.id,
                    Schedule.date < today)
            .order_by(Schedule.date.desc())
            .limit(20)
            .all())
    return render_template('employee/my_bookings.html',
                           bookings=bookings,
                           past=past,
                           today=today)


@employee_bp.route('/cancel/<int:booking_id>', methods=['POST'])
@login_required
@require_employee
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        abort(403)
    if booking.status in ('booked', 'waitlisted'):
        booking.status = 'cancelled'
        db.session.commit()
        flash('Booking cancelled.', 'info')
    else:
        flash('Cannot cancel this booking.', 'warning')
    return redirect(url_for('employee.my_bookings'))


@employee_bp.route('/qr/<int:booking_id>')
@login_required
def qr_code(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id and current_user.role not in ('admin', 'driver'):
        abort(403)
    return render_template('employee/my_bookings.html',
                           show_qr=booking,
                           bookings=[],
                           past=[],
                           today=date.today())


@employee_bp.route('/qr/image/<int:booking_id>')
@login_required
def qr_image(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id and current_user.role not in ('admin', 'driver'):
        abort(403)

    import qrcode
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(booking.qr_token)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


@employee_bp.route('/live/<int:schedule_id>')
@login_required
def live_map(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    # Check user has a booking for this schedule or is admin
    if current_user.role not in ('admin',):
        booking = Booking.query.filter_by(
            user_id=current_user.id,
            schedule_id=schedule_id
        ).filter(Booking.status.in_(['booked', 'checked_in', 'waitlisted'])).first()
        if not booking:
            flash('You do not have a booking for this schedule.', 'warning')
            return redirect(url_for('employee.dashboard'))

    stops = schedule.route.stops
    return render_template('employee/live_map.html',
                           schedule=schedule,
                           stops=stops)


def _send_booking_telegram(user, schedule_info):
    """Send Telegram confirmation if user has chat_id."""
    import os
    import requests
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if not token or not user.telegram_chat_id:
        return
    if isinstance(schedule_info, str):
        msg = f'✅ NoveeBus: Booking confirmed — {schedule_info}'
    else:
        msg = (f'✅ NoveeBus: Booking confirmed!\n'
               f'Route: {schedule_info.route.name}\n'
               f'Shift: {schedule_info.shift.name} at {schedule_info.shift.departure_time}\n'
               f'Date: {schedule_info.date.strftime("%d %b %Y")}')
    try:
        requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': user.telegram_chat_id, 'text': msg},
            timeout=5
        )
    except Exception:
        pass


@employee_bp.route('/seats')
@login_required
def seats_remaining():
    """AJAX endpoint: return seats remaining for a given schedule."""
    from flask import jsonify
    route_id = request.args.get('route_id', type=int)
    shift_id = request.args.get('shift_id', type=int)
    book_date_str = request.args.get('date')
    if not all([route_id, shift_id, book_date_str]):
        return jsonify({'seats': None})
    try:
        book_date = datetime.strptime(book_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'seats': None})
    sched = Schedule.query.filter_by(
        route_id=route_id, shift_id=shift_id, date=book_date
    ).first()
    if not sched:
        return jsonify({'seats': None, 'message': 'No schedule'})
    return jsonify({'seats': sched.seats_remaining, 'capacity': sched.route.capacity})


@employee_bp.route('/link_telegram')
@login_required
def link_telegram():
    """Generate a one-time token and redirect to Telegram bot to link the account."""
    import os, secrets
    from flask import jsonify, redirect
    from models import User
    token = secrets.token_urlsafe(32)
    current_user.telegram_link_token = token
    db.session.commit()
    bot_username = os.environ.get('TELEGRAM_BOT_USERNAME', 'NoveeBusBot')
    tg_url = f'https://t.me/{bot_username}?start={token}'
    return redirect(tg_url)


@employee_bp.route('/unlink_telegram', methods=['POST'])
@login_required
def unlink_telegram():
    """Unlink Telegram from this account."""
    current_user.telegram_chat_id = None
    current_user.telegram_link_token = None
    db.session.commit()
    flash('Telegram account unlinked.', 'info')
    return redirect(url_for('employee.dashboard'))
