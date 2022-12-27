from flask_login import UserMixin, current_user
from flask_security import RoleMixin
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
                       db.Column('user.id',
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
                        db.Column('client_tag_id',
                                  db.Integer,
                                  db.ForeignKey('client_tag.id'),
                                  primary_key=True))


class Tariff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True, nullable=False)
    max_locations = db.Column(db.Integer, default=1)
    max_users = db.Column(db.Integer, default=1)
    max_staff = db.Column(db.Integer, default=1)
    default = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return self.name


class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True, nullable=False)
    registration_number = db.Column(db.String(20))
    info = db.Column(db.Text)
    tariff_id = db.Column(db.ForeignKey('tariff.id'), nullable=False)
    tariff = db.relationship('Tariff', backref='companies')
    no_active = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return self.name


class CompanyConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    company = db.relationship('Company', backref='config')
    min_time_interval = db.Column(db.Integer, default=15)
    simple_mode = db.Column(db.Boolean, default=False)


class Permission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    object_name = db.Column(db.String(64), index=True, nullable=False)
    read = db.Column(db.Boolean, default=False)
    edit = db.Column(db.Boolean, default=False)
    create = db.Column(db.Boolean, default=False)
    delete = db.Column(db.Boolean, default=False)

    def __repr__(self):
        if self.read:
            read = 'r'
        else:
            read = '-'
        if self.edit:
            edit = 'e'
        else:
            edit = '-'
        if self.create:
            create = 'c'
        else:
            create = '-'
        if self.delete:
            delete = 'd'
        else:
            delete = '-'
        return f'{self.object_name} [ {read} {edit} {create} {delete} ]'


class Role(db.Model, RoleMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64),
                     index=True, unique=True, nullable=False)
    description = db.Column(db.String(255))
    permissions = db.relationship('Permission', secondary=roles_permissions,
                                  backref=db.backref('roles', lazy='dynamic'))

    def __repr__(self):
        return self.name


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    company = db.relationship('Company', backref='users')
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    no_active = db.Column(db.Boolean, default=False)
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
        read = edit = create = delete = False
        for item in permissions:
            if item.read:
                read = True
            if item.edit:
                edit = True
            if item.create:
                create = True
            if item.delete:
                delete = True
        return {'read': read,
                'edit': edit,
                'create': create,
                'delete': delete}


class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    company = db.relationship('Company', backref='staff')
    name = db.Column(db.String(64), index=True, nullable=False)
    phone = db.Column(db.String(20), index=True, unique=True, nullable=False)
    no_active = db.Column(db.Boolean, default=False)

    def __repr__(self):
        active = ''
        if self.no_active:
            active = '(no active)'
        return '{} {}'.format(self.name, active)

    def short_name(self):
        return self.name[:25]


class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    company = db.relationship('Company', backref='clients')
    name = db.Column(db.String(64), index=True, nullable=False)
    phone = db.Column(db.String(20), index=True, unique=True, nullable=False)
    info = db.Column(db.Text)
    tags = db.relationship('ClientTag', secondary=clients_tags,
                           lazy='subquery',
                           backref=db.backref('clients', lazy=True))
    no_active = db.Column(db.Boolean, default=False)

    def __repr__(self):
        active = ''
        if self.no_active:
            active = '(no active)'
        return '{} {}'.format(self.name, active)

    def short_name(self):
        return self.name[:25]


class ClientFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    client = db.relationship('Client', backref='files')
    name = db.Column(db.String(64))
    path = db.Column(db.String(128))
    hash = db.Column(db.String(64))


class ClientTag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(64), index=True, nullable=False)

    def add_tag(self, tag):
        if not self.is_service(tag):
            self.tags.append(tag)

    def remove_tag(self, tag):
        if self.is_tag(tag):
            self.tags.remove(tag)

    def is_tag(self, tag):
        return tag in self.tag


class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    company = db.relationship('Company', backref='services')
    name = db.Column(db.String(120), index=True, nullable=False)
    duration = db.Column(db.Integer)
    price = db.Column(db.Float)
    no_active = db.Column(db.Boolean, default=False)

    def __repr__(self):
        active = ''
        if self.no_active:
            active = '(no active)'
        return '{} {}'.format(self.name, active)

    def short_name(self):
        return self.name[:25]


class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    company = db.relationship('Company', backref='locations')
    name = db.Column(db.String(64), index=True, nullable=False)
    address = db.Column(db.String(120))
    phone = db.Column(db.String(20), index=True, unique=True)
    open = db.Column(db.Time)
    close = db.Column(db.Time)
    timezone = db.Column(db.Integer, default=0)
    no_active = db.Column(db.Boolean, default=False)
    services = db.relationship('Service', secondary=services_locations,
                               lazy='subquery',
                               backref=db.backref('locations', lazy=True))

    def __repr__(self):
        active = ''
        if self.no_active:
            active = '(no active)'
        return '{} {}'.format(self.name, active)

    def short_name(self):
        return self.name[:20]

    def add_service(self, service):
        if not self.is_service(service):
            self.services.append(service)

    def remove_service(self, service):
        if self.is_service(service):
            self.services.remove(service)

    def is_service(self, service):
        return service in self.services


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    company = db.relationship('Company', backref='appointments')
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
    cancel = db.Column(db.Boolean, default=False)

    def __repr__(self):
        cancel = ''
        if self.cancel:
            cancel = '(canceled)'
        return '<Appointment {} {} {}>'.format(self.location_id,
                                               self.date_time, cancel)

    def duration(self):
        duration = 0
        for service in self.services:
            duration += service.duration
        return timedelta(minutes=duration)

    def time_end(self):
        return self.date_time + self.duration()

    def add_service(self, service):
        if not self.is_service(service):
            self.services.append(service)

    def remove_service(self, service):
        if self.is_service(service):
            self.services.remove(service)

    def is_service(self, service):
        return service in self.services


class StaffSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'),
                    nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'),
                         nullable=False)
    staff = db.relationship('Staff', backref='calendar')
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'),
                            nullable=False)
    location = db.relationship('Location', backref='calendar')
    date_from = db.Column(db.Date)
    date_to = db.Column(db.Date)
    time_from = db.Column(db.Time)
    time_to = db.Column(db.Time)
    weekdays = db.Column(db.String(7))
    no_active = db.Column(db.Boolean, default=False)


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(64), index=True, nullable=False)
    description = db.Column(db.String(255))

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


class ItemFlow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'))
    location = db.relationship('Location', backref='item_flow')
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    item = db.relationship('Item', backref='item_flow')
    quantity = db.Column(db.Integer)
    sum = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow(),
                          onupdate=datetime.utcnow)


class Storage(db.Model):
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'),
                            primary_key=True)
    location = db.relationship('Location', backref='storage')
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False,
                        primary_key=True)
    item = db.relationship('Item', backref='storage')
    quantity = db.Column(db.Integer)


class CashFlow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'))
    location = db.relationship('Location', backref='cash_flow')
    description = db.Column(db.String(255))
    sum = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow(),
                          onupdate=datetime.utcnow)


class Cash(db.Model):
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'),
                            primary_key=True)
    location = db.relationship('Location', backref='cash')
    sum = db.Column(db.Float)


class TaskStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(64), index=True, nullable=False)
    description = db.Column(db.String(255))
    final = db.Column(db.Boolean, default=False)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(64), index=True, nullable=False)
    description = db.Column(db.String(255))
    deadline = db.Column(db.Date)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'),
                         nullable=False)
    staff = db.relationship('Staff', backref='tasks')
    closed = db.Column(db.Boolean, default=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    author = db.relationship('User', backref='tasks')
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow())

    def __repr__(self):
        return self.name

    def current_status(self):
        pass

    def current_staff(self):
        pass


class TaskProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    task = db.relationship('Task', backref='progress')
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'),
                         nullable=False)
    staff = db.relationship('Staff', backref='tasks_progress')
    status_id = db.Column(db.Integer, db.ForeignKey('task_status.id'),
                          nullable=False)
    status = db.relationship('TaskStatus', backref='tasks_progress')
    description = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow(),
                          onupdate=datetime.utcnow)

    def __repr__(self):
        return f'{self.task} {self.timestamp}'


class Notice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cid = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    company = db.relationship('Company', backref='notices')
    date = db.Column(db.Date, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    client = db.relationship('Client', backref='notices')
    description = db.Column(db.String(255))
    no_active = db.Column(db.Boolean, default=False)
