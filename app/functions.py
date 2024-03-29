import os
from datetime import datetime, timedelta
from threading import Thread

from flask import flash, session
from flask_mail import Message
from flask_babel import lazy_gettext as _l, _
from sqlalchemy import func, inspect

from app import app, mail
from .models import Location, Staff, Service, Appointment, CompanyConfig


def get_languages():
    languages = [('', _l('-Select-'))]
    for language, description in app.config['LANGUAGES'].items():
        languages.append((language, description))
    return languages


def allowed_file_ext(filename):
    allow_ext = app.config['UPLOAD_EXTENSIONS']
    return '.' in filename and os.path.splitext(filename)[1] in allow_ext


def get_duration(services):
    duration = 0
    if not services:
        return timedelta(minutes=duration)
    for service_id in services:
        service = Service.get_object(service_id)
        duration += service.duration
    return timedelta(minutes=duration)


def get_interval_intersection(list_1, list_2):
    if len(list_1) == 0 or len(list_2) == 0:
        return []
    time_list = []
    for item in list_1:
        time_list.append(('start', item[0], 1))
        time_list.append(('end', item[1], 1))
    for item in list_2:
        time_list.append(('start', item[0], 2))
        time_list.append(('end', item[1], 2))
    time_list.sort(key=lambda x: x[1])
    intervals = []
    flag = ''
    check = check_sum = 0
    for time in time_list:
        if not check:
            check = time[2]
        if not time[2] == check:
            check = time[2]
            check_sum += 1
        if time[0] == flag:
            prev_time = time
        else:
            flag = time[0]
            if flag == 'start':
                prev_time = time
            else:
                intervals.append((prev_time[1], time[1]))
    if check_sum == 1:
        return []
    return intervals


def get_free_time_intervals(location_id, date, staff_id, duration,
                            appointment_id=None):
    if not location_id or not date or not staff_id or not duration:
        return []
    if not isinstance(duration, type(timedelta(minutes=1))):
        flash(_('Something went wrong...'))
        return []
    location = Location.get_object(location_id)
    time_open = datetime.strptime('00.00', '%H.%M')
    time_close = datetime.strptime('00.00', '%H.%M')
    if location.main_schedule:
        wt = location.main_schedule.get_work_time(date)
        time_open = wt['hour_from']
        time_close = wt['hour_to']
    staff_intervals = []
    staff = Staff.get_object(staff_id)
    if staff.main_schedule:
        wts = staff.main_schedule.get_work_time(date)
        if wts['hour_from'] == wts['hour_to']:
            staff_intervals = []
        else:
            staff_from = max(wts['hour_from'], datetime.now())
            staff_intervals = [(staff_from, wts['hour_to'])]
    ht = staff.get_holiday_time(date)
    if ht:
        if ht['hour_from'] == ht['hour_to']:
            staff_intervals = []
        else:
            staff_intervals = [(ht['hour_from'], ht['hour_to'])]
    filter_param = dict(staff_id=staff_id, cancel=False,
                        allow_booking_this_time=False)
    search_param = [func.date(Appointment.date_time) == date]
    if appointment_id:
        search_param.append(Appointment.id != appointment_id)
    timetable = Appointment.get_items(False, filter_param, search_param)
    timetable.sort(key=lambda x: x.date_time)
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
    intervals.sort(key=lambda x: x[0])
    if CompanyConfig.get_parameter('simple_mode'):
        return intervals
    else:
        free_intervals = get_interval_intersection(intervals, staff_intervals)
        return free_intervals


def time_in_intervals(dt, intervals):
    for interval in intervals:
        time_from = interval[0]
        time_to = interval[1]
        if time_from <= dt <= time_to:
            return True
    return False


def send_acync_mail(msg):
    with app.app_context():
        mail.send(msg)


def send_mail_from_site(sender, subject, text):
    msg = Message(subject=subject,
                  sender=sender,
                  recipients=[app.config['ADMINS'][0]])
    msg.body = text
    Thread(target=send_acync_mail, args=(msg,)).start()


def send_mail(sender, subject, recipients, text_body, html_body=None):
    msg = Message(subject=subject,
                  sender=sender,
                  recipients=recipients)
    msg.body = text_body
    msg.html = html_body
    Thread(target=send_acync_mail, args=(msg,)).start()


def get_attr_inspect(name, class_object):
    relationships = [rel.__str__().split('.')[1] for rel in
                     inspect(class_object).relationships]
    search_name = name.split('_id')[0]
    if search_name in relationships:
        return search_name
    return name


def phone_number_plus(number):
    number = str(number).strip()
    if not number[0] == '+':
        number = '+' + number
    return number


def get_calendar(days=None, data_filter=None, day_start=None):
    if not day_start:
        current_day = (datetime.now().date() +
                       timedelta(days=-datetime.now().isoweekday()))
    else:
        if day_start.isoweekday() == 7:
            current_day = day_start
        else:
            current_day = day_start + timedelta(days=-day_start.isoweekday())
    if not days:
        day_end = current_day + timedelta(days=31)
    else:
        day_end = current_day + timedelta(days=days)
    calendar = {}
    while current_day < day_end:
        data_search = [func.date(Appointment.date_time) == current_day]
        appointments = Appointment.get_items(False, data_filter=data_filter,
                                             data_search=data_search)
        appointments_list = (
            [(a.date_time, a.date_time + a.duration, a.staff) for a in appointments])
        appointments_list.sort(key=lambda x: x[0])
        day = {'count': len(appointments_list),
               'appointments': appointments_list}
        calendar[current_day] = day
        current_day += timedelta(days=1)
    return calendar


def clear_session():
    session.pop('services', None)
    session.pop('location', None)
    session.pop('staff', None)
    session.pop('client', None)
    session.pop('date', None)
    session.pop('time', None)
