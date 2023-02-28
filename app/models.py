from flask_login import UserMixin, current_user
from flask_security import RoleMixin
from sqlalchemy.orm import declared_attr
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login
from datetime import datetime, timedelta


@login.user_loader
def load_user(id):
    return User.query.get(int(id))


services_locations = db.Table('services_locations',
                              db.Column('service_id',
                                        db.Integer,
                                        db.ForeignKey('service.id'),
                                        primary_key=True),
                              db.Column('location_id',
                                        db.Integer,
                                        db.ForeignKey('location.id'),
                                        primary_key=True))

appointments_services = db.Table('appointments_services',
                                 db.Column('appointment_id',
                                           db.Integer,
                                           db.ForeignKey('appointment.id'),
                                           primary_key=True),
                                 db.Column('service_id',
                                           db.Integer,
                                           db.ForeignKey('service.id'),
                                           primary_key=True))


roles_users = db.Table('roles_users',
                       db.Column('role_id',
                                 db.Integer,
                                 db.ForeignKey('role.id'),
                                 primary_key=True),
                       db.Column('user_id',
                                 db.Integer,
                                 db.ForeignKey('user.id'),
                                 primary_key=True))


roles_permissions = db.Table('roles_permissions',
                             db.Column('role_id',
                                       db.Integer,
                                       db.ForeignKey('role.id'),
                                       primary_key=True),
                             db.Column('permission_id',
                                       db.Integer,
                                       db.ForeignKey('permission.id'),
                                       primary_key=True))


clients_tags = db.Table('clients_tags',
                        db.Column('client_id',
                                  db.Integer,
                                  db.ForeignKey('client.id'),
                                  primary_key=True),
                        db.Column('tag_id',
                                  db.Integer,
                                  db.ForeignKey('tag.id'),
                                  primary_key=True))

staff_schedules = db.Table('staff_schedules',
                           db.Column('staff_id',
                                     db.Integer,
                                     db.ForeignKey('staff.id'),
                                     primary_key=True),
                           db.Column('schedule_id',
                                     db.Integer,
                                     db.ForeignKey('schedule.id'),
                                     primary_key=True))

locations_schedules = db.Table('locations_schedules',
                               db.Column('location_id',
                                         db.Integer,
                                         db.ForeignKey('location.id'),
                                         primary_key=True),
                               db.Column('schedule_id',
                                         db.Integer,
                                         db.ForeignKey('schedule.id'),
                                         primary_key=True))


class Entity:
    sort = 'id'
    id = db.Column(db.Integer, primary_key=True)
    no_active = db.Column(db.Boolean, default=False)
    timestamp_create = db.Column(db.DateTime(), default=datetime.utcnow())
    timestamp_update = db.Column(db.DateTime(), default=datetime.utcnow(),
                                 onupdate=datetime.utcnow())

    @classmethod
    def get_subclasses(cls):
        return list(c.__name__ for c in cls.__subclasses__())

    @classmethod
    def get_items(cls, tuple_mode=False):
        items = cls.query.filter_by(no_active=False,
                                    cid=current_user.cid
                                    ).order_by(getattr(cls, cls.sort).asc())
        if tuple_mode:
            items = [(i.id, i.name) for i in items]
            items.insert(0, (0, '-Select-'))
        else:
            items = [i for i in items]
        return items

    @classmethod
    def get_object(cls, id):
        obj = cls.query.filter_by(no_active=False, cid=current_user.cid,
                                  id=id).first_or_404()
        return obj

    def item_delete(self):
        db.session.delete(self)
        db.session.commit()


class Splitter:

    @declared_attr
    def cid(self):
        return db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)


class Tariff(db.Model, Entity):
    name = db.Column(db.String(64), index=True, nullable=False)
    max_locations = db.Column(db.Integer, default=1)
    max_users = db.Column(db.Integer, default=1)
    max_staff = db.Column(db.Integer, default=1)
    default = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return self.name

    @classmethod
    def get_tariff_default(cls):
        return cls.query.filter_by(default=True).first()


class Company(db.Model, Entity):
    name = db.Column(db.String(64), index=True, nullable=False)
    registration_number = db.Column(db.String(20))
    info = db.Column(db.Text)
    config = db.relationship('CompanyConfig', backref='company',
                             uselist=False, cascade='all, delete')
    roles = db.relationship('Role', backref='company',
                            cascade='all, delete')
    users = db.relationship('User', backref='company',
                            cascade='all, delete')
    staff = db.relationship('Staff', backref='company',
                            cascade='all, delete')
    clients = db.relationship('Client', backref='company',
                              cascade='all, delete')
    services = db.relationship('Service', backref='company',
                               cascade='all, delete')
    locations = db.relationship('Location', backref='company',
                                cascade='all, delete')
    notices = db.relationship('Notice', backref='company',
                              cascade='all, delete')
    tasks = db.relationship('Task', backref='company',
                            cascade='all, delete')
    appointments = db.relationship('Appointment', backref='company',
                                   cascade='all, delete')

    def __repr__(self):
        return self.name


class CompanyConfig(db.Model, Entity, Splitter):
    min_time_interval = db.Column(db.Integer, default=15)
    simple_mode = db.Column(db.Boolean, default=True)

    @staticmethod
    def get_parameter(name):
        cfg = current_user.company.config
        if not cfg:
            return False
        return getattr(cfg, name, False)


class Permission(db.Model, Entity):
    sort = 'name'
    object_name = db.Column(db.String(64), index=True, nullable=False)
    create = db.Column(db.Boolean, default=False)
    read = db.Column(db.Boolean, default=False)
    update = db.Column(db.Boolean, default=False)
    delete = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return (f'{self.object_name} '
                f'[ {self.create} {self.read} {self.update} {self.delete} ]')


class Role(db.Model, RoleMixin, Entity, Splitter):
    sort = 'name'
    name = db.Column(db.String(64),
                     index=True, unique=True, nullable=False)
    description = db.Column(db.String(255))
    permissions = db.relationship('Permission', secondary=roles_permissions,
                                  backref=db.backref('roles', lazy='dynamic'))

    def __repr__(self):
        return self.name


class User(db.Model, UserMixin, Entity, Splitter):
    sort = 'name'
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    roles = db.relationship('Role', secondary=roles_users,
                            backref=db.backref('users', lazy='dynamic'))

    def __repr__(self):
        return self.username

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_permissions(self, object_name):
        permissions = []
        for role in self.roles:
            permissions += role.permissions
        permissions = list(filter(lambda x: x.object_name == object_name,
                           permissions))
        create = read = update = delete = False
        for item in permissions:
            if item.create:
                create = True
            if item.read:
                read = True
            if item.update:
                update = True
            if item.delete:
                delete = True
        return {'create': create,
                'read': read,
                'update': update,
                'delete': delete}


class Staff(db.Model, Entity, Splitter):
    sort = 'name'
    name = db.Column(db.String(64), index=True, nullable=False)
    phone = db.Column(db.String(16), index=True, unique=True, nullable=False)
    birthday = db.Column(db.Date)
    task_progress = db.relationship('TaskProgress', backref='staff',
                                    cascade='all, delete')
    schedules = db.relationship('Schedule', secondary=staff_schedules,
                                backref=db.backref('staff', lazy=True))

    def __repr__(self):
        active = ''
        if self.no_active:
            active = '(no active)'
        return '{} {}'.format(self.name, active)

    @property
    def main_schedule(self):
        if len(self.schedules) > 0:
            return self.schedules[0]


class Client(db.Model, Entity, Splitter):
    sort = 'name'
    name = db.Column(db.String(64), index=True, nullable=False)
    phone = db.Column(db.String(16), index=True, unique=True, nullable=False)
    birthday = db.Column(db.Date)
    info = db.Column(db.Text)
    files = db.relationship('ClientFile', backref='client', cascade='all, delete')
    tags = db.relationship('Tag', secondary=clients_tags,
                           lazy='subquery',
                           backref=db.backref('clients', lazy=True))

    def __repr__(self):
        active = ''
        if self.no_active:
            active = '(no active)'
        return '{} {}'.format(self.name, active)


class ClientFile(db.Model, Entity, Splitter):
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'),
                          nullable=False)
    name = db.Column(db.String(64))
    path = db.Column(db.String(128))
    hash = db.Column(db.String(64))


class Tag(db.Model, Entity, Splitter):
    name = db.Column(db.String(64), index=True, nullable=False)

    def add_tag(self, tag):
        if not self.is_service(tag):
            self.tags.append(tag)

    def remove_tag(self, tag):
        if self.is_tag(tag):
            self.tags.remove(tag)

    def is_tag(self, tag):
        return tag in self.tag


class Service(db.Model, Entity, Splitter):
    sort = 'name'
    name = db.Column(db.String(120), index=True, nullable=False)
    duration = db.Column(db.Integer)
    price = db.Column(db.Float)
    repeat = db.Column(db.Integer)

    def __repr__(self):
        active = ''
        if self.no_active:
            active = '(no active)'
        return '{} {}'.format(self.name, active)

    def short_name(self):
        return self.name[:25]


class Location(db.Model, Entity, Splitter):
    sort = 'name'
    name = db.Column(db.String(64), index=True, nullable=False)
    address = db.Column(db.String(120))
    phone = db.Column(db.String(20), index=True, unique=True)
    open = db.Column(db.Time)
    close = db.Column(db.Time)
    timezone = db.Column(db.Integer, default=0)
    services = db.relationship('Service', secondary=services_locations,
                               lazy='subquery',
                               backref=db.backref('locations', lazy=True))
    schedules = db.relationship('Schedule', secondary=locations_schedules,
                                backref=db.backref('locations', lazy=True))

    def __repr__(self):
        active = ''
        if self.no_active:
            active = '(no active)'
        return '{} {}'.format(self.name, active)

    @property
    def main_schedule(self):
        if len(self.schedules) > 0:
            return self.schedules[0]

    def add_service(self, service):
        if not self.is_service(service):
            self.services.append(service)

    def remove_service(self, service):
        if self.is_service(service):
            self.services.remove(service)

    def is_service(self, service):
        return service in self.services


class Appointment(db.Model, Entity, Splitter):
    sort = 'date_time'
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow(),
                          onupdate=datetime.utcnow)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'),
                            nullable=False)
    location = db.relationship('Location', backref='appointments')
    date_time = db.Column(db.DateTime, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    client = db.relationship('Client', backref='appointments')
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'))
    staff = db.relationship('Staff', backref='appointments')
    services = db.relationship('Service', secondary=appointments_services,
                               lazy='subquery',
                               backref=db.backref('appointments', lazy=True))
    info = db.Column(db.Text)
    result = db.Column(db.Text)
    payment_id = db.Column(db.Integer, db.ForeignKey('cash_flow.id'))
    payment = db.relationship('CashFlow', backref='appointment',
                              cascade='all, delete')
    cancel = db.Column(db.Boolean, default=False)

    def __repr__(self):
        cancel = ''
        if self.cancel:
            cancel = '(canceled)'
        return '<Appointment {} {} {}>'.format(self.location_id,
                                               self.date_time, cancel)

    @property
    def cost(self):
        cost = 0
        for service in self.services:
            cost += service.price
        return cost

    @property
    def duration(self):
        duration = 0
        for service in self.services:
            duration += service.duration
        return timedelta(minutes=duration)

    @property
    def date_repeat(self):
        period = min(s.repeat for s in self.services if s.repeat > 0)
        return (self.date_time + timedelta(days=period)).date()

    @property
    def time_end(self):
        return self.date_time + self.duration

    def add_service(self, service):
        if not self.is_service(service):
            self.services.append(service)

    def remove_service(self, service):
        if self.is_service(service):
            self.services.remove(service)

    def is_service(self, service):
        return service in self.services


class Schedule(db.Model, Entity, Splitter):
    sort = 'name'
    week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
            'Friday', 'Saturday', 'Sunday']
    name = db.Column(db.String(64), index=True, nullable=False)
    days = db.relationship('ScheduleDay', backref='schedule',
                           cascade='all, delete')

    def __init__(self, **kwargs):
        super(Schedule, self).__init__(**kwargs)
        hour_from = datetime.strptime('09.00', '%H.%M').time()
        hour_to = datetime.strptime('18.00', '%H.%M').time()
        for dn in range(0, 7):
            self.add_day(day_number=dn, hour_from=hour_from, hour_to=hour_to)

    def add_day(self, day_number, hour_from, hour_to):
        if day_number not in [scd.day_number for scd in self.days]:
            sd = ScheduleDay(cid=self.cid,
                             schedule_id=self.id,
                             name=self.week[day_number],
                             day_number=day_number,
                             hour_from=hour_from,
                             hour_to=hour_to)
            self.days.append(sd)

    def get_work_time(self, date):
        day_number = date.weekday()
        hour_from = hour_to = datetime.strptime('00.00', '%H.%M')
        for d in self.days:
            if d.day_number == day_number:
                hour_from = datetime.combine(date, d.hour_from)
                hour_to = datetime.combine(date, d.hour_to)
                break
        return {'hour_from': hour_from, 'hour_to': hour_to}


class ScheduleDay(db.Model, Entity, Splitter):
    name = db.Column(db.String(64), index=True, nullable=False)
    schedule_id = db.Column(db.Integer,
                            db.ForeignKey('schedule.id'), nullable=False)
    day_number = db.Column(db.Integer)
    hour_from = db.Column(db.Time)
    hour_to = db.Column(db.Time)

    @property
    def weekday(self):
        return self.name


class Item(db.Model, Entity, Splitter):
    sort = 'name'
    name = db.Column(db.String(64), index=True, nullable=False)
    description = db.Column(db.String(255))
    storage = db.relationship('Storage', backref='items', cascade='all, delete')
    item_flow = db.relationship('ItemFlow', backref='items', cascade='all, delete')

    def __repr__(self):
        return self.name

    def get_balance(self, location_id):
        return Storage.query.filter_by(cid=current_user.cid,
                                       location_id=location_id,
                                       item_id=self.id)

    def get_balance_all(self):
        counts = Storage.query.filter_by(cid=current_user.cid,
                                         item_id=self.id)
        return sum(list(map(lambda x: x.quantity, counts)))

    def get_balance_location(self, location_id):
        counts = Storage.query.filter_by(cid=current_user.cid,
                                         location_id=location_id,
                                         item_id=self.id)
        return sum(list(map(lambda x: x.quantity, counts)))


class ItemFlow(db.Model, Entity, Splitter):
    sort = 'date'
    date = db.Column(db.Date, nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'))
    location = db.relationship('Location', backref='item_flow')
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    quantity = db.Column(db.Integer)
    cost = db.Column(db.Float)


class Storage(db.Model, Entity, Splitter):
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'),
                            primary_key=True)
    location = db.relationship('Location', backref='storage')
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False,
                        primary_key=True)
    quantity = db.Column(db.Integer)


class CashFlow(db.Model, Entity, Splitter):
    sort = 'date'
    date = db.Column(db.Date, nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'))
    location = db.relationship('Location', backref='cash_flow')
    description = db.Column(db.String(255))
    cost = db.Column(db.Float)


class Cash(db.Model, Entity, Splitter):
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'),
                            primary_key=True)
    location = db.relationship('Location', backref='cash')
    cost = db.Column(db.Float)


class TaskStatus(db.Model, Entity, Splitter):
    name = db.Column(db.String(64), index=True, nullable=False)
    description = db.Column(db.String(255))
    final = db.Column(db.Boolean, default=False)
    task_progress = db.relationship('TaskProgress', backref='status', cascade='all, delete')


class Notice(db.Model, Entity, Splitter):
    sort = 'date'
    date = db.Column(db.Date, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    client = db.relationship('Client', backref='notices')
    description = db.Column(db.String(255))

    @classmethod
    def get_notices(cls, date=datetime.utcnow().date()):
        param = {'cid': current_user.cid,
                 'date': date,
                 'no_active': False}
        return cls.query.filter_by(**param)


class Task(db.Model, Entity, Splitter):
    name = db.Column(db.String(64), index=True, nullable=False)
    description = db.Column(db.String(255))
    deadline = db.Column(db.Date)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'),
                         nullable=False)
    staff = db.relationship('Staff', backref='tasks')
    closed = db.Column(db.Boolean, default=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    author = db.relationship('User', backref='tasks')
    task_progress = db.relationship('TaskProgress', backref='task', cascade='all, delete')


class TaskProgress(db.Model, Entity, Splitter):
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'),
                         nullable=False)
    status_id = db.Column(db.Integer, db.ForeignKey('task_status.id'),
                          nullable=False)
    description = db.Column(db.String(255))

    def __repr__(self):
        return f'{self.task} {self.timestamp}'
