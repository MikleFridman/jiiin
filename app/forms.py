import string
from datetime import datetime, timedelta

import phonenumbers
from flask import flash
from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm, RecaptchaField
from sqlalchemy import func
from wtforms import (StringField, PasswordField, BooleanField,
                     SubmitField, TextAreaField, TelField, IntegerField,
                     FloatField, SelectField, DateField, TimeField,
                     SelectMultipleField, FileField, HiddenField, EmailField, URLField)
from wtforms.validators import (DataRequired, Email, EqualTo,
                                ValidationError, Length, Optional, NumberRange)

import config
from .functions import get_languages, get_free_time_intervals, get_interval_intersection
from .models import Item, Week, Client, User, Staff, Location, Service, Appointment, ScheduleDay


# global validators
def validate_phone_global(form, field):
    try:
        p = phonenumbers.parse(field.data)
        if not phonenumbers.is_valid_number(p):
            raise ValueError()
    except (phonenumbers.phonenumberutil.NumberParseException, ValueError):
        flash(_l('Invalid phone number'))
        raise ValidationError(_l('Invalid phone number'))


def validate_username_global(form, field):
    if len(field.data.strip()) < 8:
        msg = _l('Min length username is 8 characters')
        flash(msg)
        raise ValidationError(msg)
    abc = string.ascii_letters + string.digits + '_'
    for s in field.data:
        if s not in abc:
            msg = _l('Username can contain only latin letters and numbers')
            flash(msg)
            raise ValidationError(msg)


def validate_name_global(form, field):
    cyrillic_lower_letters = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
    cyrillic_letters = cyrillic_lower_letters + cyrillic_lower_letters.upper()
    if len(field.data.strip()) < 8:
        msg = _l('Min length field "%(fn)s" is 8 characters', fn=field.label)
        flash(msg)
        raise ValidationError(msg)
    abc = string.ascii_letters + string.digits + string.whitespace
    abc += '_' + cyrillic_letters
    for s in field.data:
        if s not in abc:
            msg = _l('Field "%(fn)s" can contain only latin letters and numbers',
                     fn=field.label)
            flash(msg)
            raise ValidationError(msg)


def validate_birthday_global(form, field):
    if (not isinstance(field.data, type(datetime.now().date())) or
            field.data >= datetime.now().date()):
        flash(_l('Invalid birthday date'))
        raise ValidationError(_l('Invalid birthday date'))


class RegisterForm(FlaskForm):
    company = StringField(_l('Company'),
                          validators=[DataRequired(), validate_name_global])
    username = StringField(_l('Username'),
                           validators=[DataRequired(), validate_username_global])
    email = EmailField(_l('E-mail'), validators=[DataRequired(), Email()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    password2 = PasswordField(_l('Repeat password'),
                              validators=[DataRequired(), EqualTo('password')])
    recaptcha = RecaptchaField()
    submit = SubmitField(_l('Submit'))

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            flash(_l('Please use a different username'))
            raise ValidationError(_l('Please use a different username'))

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            flash(_l('Please use a different email'))
            raise ValidationError(_l('Please use a different email'))


class LoginForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    remember_me = BooleanField(_l('Remember me'))
    submit = SubmitField(_l('Submit'))


class UserForm(RegisterForm):
    company = None
    recaptcha = None


class UserFormEdit(UserForm):
    language = SelectField(_l('Language'), choices=get_languages(), coerce=str,
                           validators=[Optional()])
    start_page = SelectField(_l('Start page'),
                             choices=[('', _l('-Select-')),
                                      ('appointments_table', _l('Timetable')),
                                      ('clients_table', _l('Clients')),
                                      ('notices_table', _l('Notices'))],
                             coerce=str, validators=[Optional()])
    password_old = PasswordField(_l('Password'))
    password = PasswordField(_l('Password new'))
    password2 = PasswordField(_l('Repeat password new'),
                              validators=[EqualTo('password')])

    def __init__(self, original_username, original_email, *args, **kwargs):
        super(UserFormEdit, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email

    def validate_username(self, username):
        if username.data != self.original_username:
            if User.find_object({'username': username.data}):
                flash(_l('Please use a different username'))
                raise ValidationError(_l('Please use a different username'))

    def validate_email(self, email):
        if email.data != self.original_email:
            if User.find_object({'email': email.data}):
                flash(_l('Please use a different email'))
                raise ValidationError(_l('Please use a different email'))


class ResetPasswordRequestForm(FlaskForm):
    email = EmailField(_l('E-mail'), validators=[DataRequired(), Email()])
    submit = SubmitField(_l('Submit'))


class ResetPasswordForm(FlaskForm):
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    password2 = PasswordField(_l('Repeat password'),
                              validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField(_l('Submit'))


class CompanyForm(FlaskForm):
    name = StringField(_l('Company name'), validators=[DataRequired(),
                                                       validate_name_global])
    registration_number = StringField(_l('Registration number'))
    default_time_from = TimeField(_l('Open from (default)'))
    default_time_to = TimeField(_l('Open until (default)'))
    choices = [(5, '5'), (10, '10'), (15, '15'), (30, '30'), (45, '45'),
               (60, '60')]
    min_time_interval = SelectField(_l('Time interval (min)'), choices=choices,
                                    coerce=int)
    simple_mode = BooleanField(_l('Not use staff schedules'))
    show_quick_start = BooleanField(_l('Show quick start'))
    delete_account = URLField(_l('Delete account'))
    # info = TextAreaField(_l('Info'), validators=[Length(max=200)])
    submit = SubmitField(_l('Submit'))


class DeleteAccountForm(FlaskForm):
    reason = TextAreaField(_l('Reason'), validators=[DataRequired(),
                                                     Length(min=10, max=200)])
    confirm_delete = BooleanField(_l('Confirm deletion account and all data'),
                                  validators=[DataRequired()])
    submit = SubmitField(_l('Submit'))


class StaffForm(FlaskForm):
    required_fields = ['name', 'phone']
    name = StringField(_l('Name'), validators=[DataRequired(),
                                               validate_name_global])
    phone = TelField(_l('Phone'), validators=[DataRequired(),
                                              validate_phone_global])
    birthday = DateField(_l('Birthday'), validators=[Optional(),
                                                     validate_birthday_global])
    schedule = SelectField(_l('Schedule'), choices=[], coerce=int,
                           validate_choice=False)
    submit = SubmitField(_l('Submit'))

    def __init__(self, source_phone=None, *args, **kwargs):
        super(StaffForm, self).__init__(*args, **kwargs)
        self.source_phone = source_phone

    def validate_phone(self, field):
        if field.data != self.source_phone:
            if Staff.find_object({'phone': field.data}):
                flash(_l('Please use a different phone'))
                raise ValidationError(_l('Please use a different phone'))

    def validate_schedule(self, field):
        if not self.schedule.data:
            flash(_l('Please select schedule'))
            raise ValidationError(_l('Please select schedule'))


class StaffFormSimple(StaffForm):
    schedule = None


class ScheduleForm(FlaskForm):
    name = StringField(_l('Title'), validators=[DataRequired(),
                                                validate_name_global])
    submit = SubmitField(_l('Submit'))


class ScheduleDayForm(FlaskForm):
    choices = Week.get_items(True)
    weekday = SelectField(_l('Weekday'), choices=[*choices], coerce=int)
    hour_from = TimeField(_l('From hour'))
    hour_to = TimeField(_l('To hour'))
    submit = SubmitField(_l('Submit'))

    def __init__(self, schedule=None, schedule_day=None, *args, **kwargs):
        super(ScheduleDayForm, self).__init__(*args, **kwargs)
        self.schedule = schedule
        self.schedule_day = schedule_day

    def validate_hour_from(self, field):
        if not self.hour_from.data:
            flash(_l('Please select time'))
            raise ValidationError(_l('Please select time'))
        if (datetime.combine(datetime.now(), self.hour_to.data) -
                datetime.combine(datetime.now(), field.data) < timedelta(seconds=0)):
            flash(_l('Incorrect time interval'))
            raise ValidationError(_l('Incorrect time interval'))

    def validate_hour_to(self, field):
        if not self.hour_to.data:
            flash(_l('Please select time'))
            raise ValidationError(_l('Please select time'))

    def validate_weekday(self, field):
        filter_param = dict(schedule_id=self.schedule.id, day_number=field.data)
        search_param = []
        if self.schedule_day:
            search_param.append(ScheduleDay.id != self.schedule_day.id)
        days = ScheduleDay.get_items(data_filter=filter_param,
                                     data_search=search_param)
        if days:
            flash(_l('Incorrect weekday'))
            raise ValidationError(_l('Incorrect weekday'))


class ClientForm(FlaskForm):
    name = StringField(_l('Name'), validators=[DataRequired(),
                                               validate_name_global])
    phone = TelField(_l('Phone'), validators=[DataRequired(),
                                              validate_phone_global])
    birthday = DateField(_l('Birthday'), validators=[Optional(),
                                                     validate_birthday_global])
    info = TextAreaField(_l('Info'), validators=[Length(max=200)])
    submit = SubmitField(_l('Submit'))

    def __init__(self, source_phone=None, *args, **kwargs):
        super(ClientForm, self).__init__(*args, **kwargs)
        self.source_phone = source_phone

    def validate_phone(self, field):
        if field.data != self.source_phone:
            if Client.find_object({'phone': field.data}):
                flash(_l('Please use a different phone'))
                raise ValidationError(_l('Please use a different phone'))


class ClientFileForm(FlaskForm):
    file = FileField('')
    submit = SubmitField(_l('Submit'))


class ClientTagForm(FlaskForm):
    tags = SelectMultipleField(_l('Tags'), choices=[], coerce=int)
    submit = SubmitField(_l('Submit'))


class TagForm(FlaskForm):
    name = StringField(_l('Title'), validators=[DataRequired()])
    submit = SubmitField(_l('Submit'))

    def validate_name(self, field):
        self.name.data = self.name.data.strip().replace(' ', '_').lower()


class ServiceForm(FlaskForm):
    name = StringField(_l('Title'), validators=[DataRequired(),
                                                validate_name_global])
    duration = IntegerField(_l('Duration'), default=0,
                            validators=[NumberRange(min=0, max=365)])
    price = FloatField(_l('Price'), default=0,
                       validators=[NumberRange(min=0, max=1000000)])
    repeat = IntegerField(_l('Repeat'), default=0,
                          validators=[NumberRange(min=0, max=365)])
    location = SelectMultipleField(_l('Locations'), choices=[],
                                   validate_choice=False, coerce=int)
    submit = SubmitField(_l('Submit'))

    def validate_location(self, field):
        if not self.location.data:
            flash(_l('Please select location'))
            raise ValidationError(_l('Please select location'))

    def validate_price(self, field):
        max_price = config.Config.MAX_PRICE
        if self.price.data > max_price:
            flash(_l('Price cannot exceed %(mp)s', mp=max_price))
            raise ValidationError(_l('Price cannot exceed %(mp)s', mp=max_price))


class LocationForm(FlaskForm):
    name = StringField(_l('Title'), validators=[DataRequired(),
                                                validate_name_global])
    phone = TelField(_l('Phone'), validators=[DataRequired(),
                                              validate_phone_global])
    address = StringField(_l('Address'), validators=[DataRequired()])
    schedule = SelectField(_l('Schedule'), choices=[], coerce=int,
                           validate_choice=False)
    add_services = URLField(_l('Add all services'))
    delete_services = URLField(_l('Delete all services'))
    submit = SubmitField(_l('Submit'))

    def __init__(self, source_phone=None, *args, **kwargs):
        super(LocationForm, self).__init__(*args, **kwargs)
        self.source_phone = source_phone

    def validate_phone(self, field):
        if field.data != self.source_phone:
            if Location.find_object({'phone': field.data}, overall=True):
                flash(_l('Please use a different phone'))
                raise ValidationError(_l('Please use a different phone'))

    def validate_schedule(self, field):
        if not self.schedule.data:
            flash(_l('Please select schedule'))
            raise ValidationError(_l('Please select schedule'))


class LocationFormCreate(LocationForm):
    add_services = None
    delete_services = None


class AppointmentForm(FlaskForm):
    location = SelectField(_l('Location'), choices=[], coerce=int)
    date = DateField(_l('Date'), validators=[], format='%Y-%m-%d')
    time = SelectField(_l('Time'), choices=[], validate_choice=False)
    client = SelectField(_l('Client'), choices=[], coerce=int)
    staff = SelectField(_l('Worker'), choices=[], coerce=int)
    service = SelectMultipleField(_l('Services'), choices=[],
                                  validate_choice=False, coerce=int)
    duration = HiddenField(_l('Duration'), default=0)
    services = HiddenField(_l('Services'), default='')
    no_check_duration = BooleanField(_l('Not control duration'))
    info = TextAreaField(_l('Info'), validators=[Length(max=200)])
    submit = SubmitField(_l('Submit'))

    def __init__(self, appointment=None, *args, **kwargs):
        super(AppointmentForm, self).__init__(*args, **kwargs)
        self.appointment = appointment

    def validate_location(self, field):
        if not self.location.data:
            flash(_l('Please select location'))
            raise ValidationError(_l('Please select location'))

    def validate_services(self, field):
        if len(field.data) == 0:
            flash(_l('Please select services'))
            raise ValidationError(_l('Please select services'))
        else:
            if not self.location.data:
                raise ValidationError(_l('Please select location'))
            location = Location.query.get_or_404(self.location.data)
            services_id = [x.id for x in location.services]
            for s in field.data.split(','):
                if int(s) not in services_id:
                    service = Service.get_object(s)
                    msg = _l('Service %(sn)s unavailable in select location',
                             sn=service.name)
                    flash(msg)
                    raise ValidationError(msg)

    def validate_client(self, field):
        if not self.client.data:
            flash(_l('Please select client'))
            raise ValidationError(_l('Please select client'))
        if self.date.data and self.time.data:
            filter_param = dict(client_id=self.client.data)
            search_param = [func.date(Appointment.date_time) == self.date.data]
            if self.appointment:
                search_param.append(Appointment.id != self.appointment.id)
            appointments = Appointment.get_items(data_filter=filter_param,
                                                 data_search=search_param)
            client_intervals = []
            current_date_time = datetime.combine(self.date.data,
                                                 datetime.strptime(self.time.data,
                                                                   '%H:%M').time())
            current_interval = [(current_date_time,
                                 current_date_time + self.duration.data)]
            for ap in appointments:
                client_intervals.append((ap.date_time, ap.date_time + ap.duration))
            if get_interval_intersection(client_intervals, current_interval):
                flash(_l('Client is busy at this time'))
                raise ValidationError(_l('Client is busy at this time'))

    def validate_staff(self, field):
        if not self.staff.data:
            flash(_l('Please select staff'))
            raise ValidationError(_l('Please select staff'))

    def validate_date(self, field):
        if not self.date.data:
            flash(_l('Please select date'))
            raise ValidationError(_l('Please select date'))

    def validate_time(self, field):
        if not field.data:
            flash(_l('Please select time'))
            raise ValidationError(_l('Please select time'))
        time = datetime.strptime(field.data, '%H:%M').time()
        date_time = datetime(self.date.data.year,
                             self.date.data.month,
                             self.date.data.day,
                             time.hour,
                             time.minute)
        if date_time < datetime.now():
            return True
        location = self.location.data
        staff = self.staff.data
        duration = self.duration.data
        date = self.date.data
        if not location:
            flash(_l('Incorrect data'))
            raise ValidationError(_l('Incorrect data'))
        if not staff:
            flash(_l('Incorrect data'))
            raise ValidationError(_l('Incorrect data'))
        if self.appointment:
            except_id = self.appointment.id
        else:
            except_id = None
        intervals = get_free_time_intervals(location, date, staff, duration,
                                            except_id)
        if not intervals:
            flash(_l('This time unavailable'))
            raise ValidationError(_l('This time unavailable'))
        time = datetime.strptime(field.data, '%H:%M').time()
        dt = datetime(date.year, date.month,
                      date.day, time.hour, time.minute)
        check = False
        for interval in intervals:
            time_from = interval[0]
            time_to = interval[1]
            if time_from <= dt <= time_to:
                check = True
        if not check:
            flash(_l('This time unavailable'))
            raise ValidationError(_l('This time unavailable'))


class ResultForm(FlaskForm):
    result = TextAreaField(_l('Result'), validators=[Length(max=255)])
    submit = SubmitField(_l('Submit'))


class ReceiptForm(FlaskForm):
    link = StringField(_l('Link to payment receipt'))
    submit = SubmitField(_l('Submit'))


class SearchForm(FlaskForm):
    pass


class ConfirmForm(FlaskForm):
    submit = SubmitField(_l('Confirm'))


class ItemForm(FlaskForm):
    name = StringField(_l('Title'), validators=[DataRequired(),
                                                validate_name_global])
    description = TextAreaField('Description', validators=[Length(max=255)])
    submit = SubmitField(_l('Submit'))


class ItemFlowForm(FlaskForm):
    location = SelectField(_l('Location'), choices=[], coerce=int)
    date = DateField(_l('Date'))
    item = SelectField(_l('Item'), choices=[], coerce=int)
    action = SelectField(_l('Operation'),
                         choices=[(1, _l('Plus')), (-1, _l('Minus'))],
                         coerce=int)
    quantity = FloatField(_l('Quantity'), default=0)
    submit = SubmitField(_l('Submit'))

    def __init__(self, source_location=None, source_item=None,
                 source_quantity=None, *args, **kwargs):
        super(ItemFlowForm, self).__init__(*args, **kwargs)
        self.source_location = source_location
        self.source_item = source_item
        self.source_quantity = source_quantity

    def validate_quantity(self, field):
        if self.action.data == 1:
            return True
        item = Item.query.get(self.item.data)
        count = item.get_balance_location(self.location.data)
        if (self.source_location == self.location.data and
                self.source_item == self.item.data):
            count -= self.source_quantity
        if field.data > count:
            msg = _l('Quantity exceeds available %(count)s', count=count)
            flash(msg)
            raise ValidationError(msg)


class ContactForm(FlaskForm):
    name = StringField(_l('Name'), validators=[DataRequired(),
                                               validate_name_global])
    email = StringField(_l('E-mail'), validators=[DataRequired(), Email()])
    text = TextAreaField(_l('Text'), validators=[DataRequired(),
                                                 Length(max=255)])
    submit = SubmitField(_l('Send'))


class NoticeForm(FlaskForm):
    client = SelectField(_l('Client'), choices=[], coerce=int)
    date = DateField(_l('Date'))
    description = TextAreaField(_l('Description'), validators=[DataRequired(),
                                                               Length(max=255)])
    processed = BooleanField(_l('Processed'))
    submit = SubmitField(_l('Submit'))


class HolidayForm(FlaskForm):
    staff = SelectField(_l('Staff'), choices=[], coerce=int)
    date = DateField(_l('Date'), validators=[DataRequired()], format='%Y-%m-%d')
    working_day = BooleanField(_l('Working day'))
    hour_from = TimeField(_l('From hour'), validators=[Optional()])
    hour_to = TimeField(_l('To hour'), validators=[Optional()])
    submit = SubmitField(_l('Submit'))


class ReportForm(FlaskForm):
    location = SelectField(_l('Location'), choices=[], coerce=int)
    staff = SelectField(_l('Worker'), choices=[], coerce=int)
    date_from = DateField(_l('Date from'), validators=[DataRequired()], format='%Y-%m-%d')
    date_to = DateField(_l('Date to'), validators=[DataRequired()], format='%Y-%m-%d')
    # export_excel = BooleanField(_l('Export to Excel'))
    submit = SubmitField(_l('Submit'))


class CashFlowForm(FlaskForm):
    location = SelectField(_l('Location'), choices=[], coerce=int)
    date = DateField(_l('Date'))
    description = StringField(_l('Description'), validators=[DataRequired(),
                                                             Length(max=120)])
    action = SelectField(_l('Operation'), choices=[(1, _l('Plus')), (-1, _l('Minus'))],
                         coerce=int)
    cost = FloatField(_l('Sum'), default=0)
    submit = SubmitField(_l('Submit'))

    def validate_location(self, field):
        if not self.location.data:
            flash(_l('Please select location'))
            raise ValidationError(_l('Please select location'))
