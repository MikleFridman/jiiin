import datetime
import os
from datetime import datetime, timedelta

from flask_login import current_user
from flask_mail import Message
from sqlalchemy import func

from app import app, mail
from .models import Location, User, Staff, Service, Appointment, CompanyConfig


def get_languages():
    languages = [('', '-Select-')]
    for language, description in app.config['LANGUAGES'].items():
        languages.append((language, description))
    return languages


def allowed_file_ext(filename):
    allow_ext = app.config['UPLOAD_EXTENSIONS']
    return '.' in filename and os.path.splitext(filename)[1] in allow_ext


def get_tariff_limit(parameter):
    if parameter == 'location':
        limit = current_user.company.tariff.max_locations
        count = Location.query.filter_by(cid=current_user.cid).count()
        return max(0, limit - count)
    elif parameter == 'user':
        limit = current_user.company.tariff.max_users
        count = User.query.filter_by(cid=current_user.cid).count()
        return max(0, limit - count)
    elif parameter == 'staff':
        limit = current_user.company.tariff.max_staff
        count = Staff.query.filter_by(cid=current_user.cid).count()
        return max(0, limit - count)


def get_duration(services):
    duration = 0
    for service_id in services:
        service = Service.get_object(service_id)
        duration += service.duration
    return timedelta(minutes=duration)


def get_interval_intersection(list_1, list_2):
    if len(list_1) == 0 or len(list_2) == 0:
        return []
    time_list = []
    for item in list_1:
        time_list.append(('start', item[0]))
        time_list.append(('end', item[1]))
    for item in list_2:
        time_list.append(('start', item[0]))
        time_list.append(('end', item[1]))
    time_list.sort(key=lambda x: x[1])
    intervals = []
    flag = ''
    for time in time_list:
        if time[0] == flag:
            prev_time = time
        else:
            flag = time[0]
            if flag == 'start':
                prev_time = time
            else:
                intervals.append((prev_time[1], time[1]))
    return intervals


def get_free_time_intervals(location_id, date, staff_id, duration,
                            except_id=None):
    if not location_id or not date or not staff_id or not duration:
        return []
    location = Location.query.get_or_404(location_id)
    time_open = datetime.strptime('00.00', '%H.%M')
    time_close = datetime.strptime('00.00', '%H.%M')
    if location.main_schedule:
        wt = location.main_schedule.get_work_time(date)
        time_open = wt['hour_from']
        time_close = wt['hour_to']
    staff_intervals = []
    staff = Staff.query.get_or_404(staff_id)
    if staff.main_schedule:
        wts = staff.main_schedule.get_work_time(date)
        if wts['hour_from'] == wts['hour_to']:
            staff_intervals = []
        else:
            staff_intervals = [(wts['hour_from'], wts['hour_to'])]
    timetable = Appointment.query.filter_by(
        cid=current_user.cid, location_id=location.id, cancel=False).filter(
        func.date(Appointment.date_time) == date,
        Appointment.id != except_id).filter_by(
        staff=staff).order_by(Appointment.date_time)
    intervals = []
    time_from = max(time_open, datetime.now())
    for appointment in timetable:
        if appointment.time_end < datetime.now():
            continue
        time_to = appointment.date_time
        interval = time_to - time_from
        if interval >= duration:
            intervals.append((time_from, time_to - duration))
        time_from = appointment.time_end
    interval = time_close - time_from
    if interval >= duration:
        intervals.append((time_from, time_close - duration))
    if CompanyConfig.get_parameter('simple_mode'):
        return intervals
    else:
        free_intervals = get_interval_intersection(intervals, staff_intervals)
        return free_intervals


def send_mail_from_site(sender, subject, text):
    msg = Message(subject=subject,
                  sender=sender,
                  recipients=[app.config['MAIL_USERNAME']])
    msg.body = text
    mail.send(msg)
