from flask_login import current_user
from sqlalchemy import func

from app.models import *


def check_permission(object_name, access_level):
    if not current_user.is_authenticated:
        return False
    return current_user.get_permissions(object_name).get(access_level, False)


def get_company_config():
    cfg = CompanyConfig.query.filter_by(
        cid=current_user.cid).first()
    return cfg


def get_config_parameter(name):
    cfg = get_company_config()
    if not cfg:
        return False
    return getattr(cfg, name, False)


def get_active_companies(queryset=False):
    role = current_user.role
    if role.superadmin:
        items = Company.query.filter_by(no_active=False).all()
    else:
        items = Company.query.filter_by(no_active=False,
                                        id=current_user.cid).all()
    if queryset:
        return items
    if len(items) == 1:
        list_items = []
    else:
        list_items = [(0, '-Select-')]
    for item in items:
        list_items.append((item.id, item.name))
    return list_items


def get_tariff_limit(parameter):
    if parameter == 'location':
        limit = current_user.company.tariff.max_locations
        count = Location.query.filter_by(cid=current_user.cid).count()
        return max(0, limit-count)
    elif parameter == 'user':
        limit = current_user.company.tariff.max_users
        count = User.query.filter_by(cid=current_user.cid).count()
        return max(0, limit - count)
    elif parameter == 'staff':
        limit = current_user.company.tariff.max_staff
        count = Staff.query.filter_by(cid=current_user.cid).count()
        return max(0, limit - count)


def get_active_locations(queryset=False, multi=False):
    items = Location.query.filter_by(no_active=False,
                                     cid=current_user.cid
                                     ).order_by(Location.name).all()
    if queryset:
        return items
    if multi:
        list_items = []
    else:
        list_items = [(0, '-Select-')]
    for item in items:
        list_items.append((item.id, item.name))
    return list_items


def get_active_clients(queryset=False):
    list_items = [(0, '-Select-')]
    items = Client.query.filter_by(no_active=False,
                                   cid=current_user.cid
                                   ).order_by(Client.name).all()
    if queryset:
        return items
    for item in items:
        list_items.append((item.id, item.name))
    return list_items


def get_active_staff(queryset=False):
    items = Staff.query.filter_by(no_active=False,
                                  cid=current_user.cid
                                  ).order_by(Staff.name).all()
    if queryset:
        return items
    list_items = [(0, '-Select-')]
    for item in items:
        list_items.append((item.id, item.name))
    return list_items


def get_staff_schedule(staff_id, location_id, date):
    staff = Staff.query.get(staff_id)
    items = StaffSchedule.query.filter(StaffSchedule.id.in_(
        [x.id for x in staff.calendar]), StaffSchedule.date_from <= date,
        StaffSchedule.date_to >= date).filter_by(location_id=location_id,
                                                 no_active=False,
                                                 cid=current_user.cid).all()
    list_items = []
    for item in items:
        time_from = datetime.combine(date, item.time_from)
        time_to = datetime.combine(date, item.time_to)
        list_items.append((time_from, time_to))
    list_items.sort(key=lambda x: (x[0].hour, x[0].minute))
    print(list_items)
    return list_items


def get_active_services(location_id=None, queryset=False, multi=False):
    if location_id:
        location = Location.query.get(location_id)
        items = Service.query.filter(
            Service.id.in_([x.id for x in location.services])).filter_by(
            no_active=False, cid=current_user.cid).order_by(Service.name)
    else:
        items = Service.query.filter_by(no_active=False,
                                        cid=current_user.cid
                                        ).order_by(Service.name).all()
    if queryset:
        return items
    if multi:
        list_items = []
    else:
        list_items = [(0, '-Select-')]
    for item in items:
        list_items.append(
            (item.id, '{} ({} min)'.format(item.name, item.duration)))
    return list_items


def get_duration(services):
    duration = 0
    for service_id in services:
        service = Service.query.get_or_404(service_id)
        duration += service.duration
    return timedelta(minutes=duration)


def get_active_items(queryset=False, multi=False):
    items = Item.query.filter_by(cid=current_user.cid
                                 ).order_by(Item.name).all()
    if queryset:
        return items
    if multi:
        list_items = []
    else:
        list_items = [(0, '-Select-')]
    for item in items:
        list_items.append((item.id, item.name))
    return list_items


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
                            fix_date=False, except_id=None):
    staff_intervals = get_staff_schedule(staff_id, location_id, date)
    location = Location.query.get_or_404(location_id)
    time_open = datetime.combine(date, location.open)
    time_close = datetime.combine(date, location.close)
    staff = Staff.query.get_or_404(staff_id)
    timetable = Appointment.query.filter_by(
        cid=current_user.cid, location_id=location.id, cancel=False).filter(
        func.date(Appointment.date_time) == date,
        Appointment.id != except_id).filter_by(
        staff=staff).order_by(Appointment.date_time)
    intervals = []
    time_from = max(time_open, datetime.now())
    for appointment in timetable:
        if appointment.time_end() < datetime.now():
            continue
        time_to = appointment.date_time
        interval = time_to - time_from
        if interval >= duration:
            intervals.append((time_from, time_to - duration))
        time_from = appointment.time_end()
    interval = time_close - time_from
    if interval >= duration:
        intervals.append((time_from, time_close - duration))
    if len(intervals) > 0 or fix_date:
        if get_config_parameter('simple_mode'):
            return intervals
        else:
            free_intervals = get_interval_intersection(intervals,
                                                       staff_intervals)
            return free_intervals
    else:
        return get_free_time_intervals(location_id, date + timedelta(days=1),
                                       staff_id, duration, fix_date,
                                       except_id)
