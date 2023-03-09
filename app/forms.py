import phonenumbers
from flask import flash
from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, BooleanField,
                     SubmitField, TextAreaField, TelField, IntegerField,
                     FloatField, SelectField, DateField, TimeField,
                     SelectMultipleField, FileField, HiddenField)
from wtforms.validators import (DataRequired, Email, EqualTo,
                                ValidationError, Length, Optional)

from .models import Schedule, Item
from app.functions import *


# global validators
def validate_phone(form, field):
    try:
        p = phonenumbers.parse(field.data)
        if not phonenumbers.is_valid_number(p):
            raise ValueError()
    except (phonenumbers.phonenumberutil.NumberParseException, ValueError):
        raise ValidationError('Invalid phone number')


class RegisterForm(FlaskForm):
    company = StringField(_l('Company'), validators=[DataRequired()])
    username = StringField(_l('Username'), validators=[DataRequired()])
    email = StringField(_l('E-mail'), validators=[DataRequired(), Email()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    password2 = PasswordField(_l('Repeat password'), validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField(_l('Submit'))

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email')


class LoginForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    remember_me = BooleanField(_l('Remember me'))
    submit = SubmitField(_l('Submit'))


class UserForm(RegisterForm):
    company = None


class UserFormEdit(UserForm):
    language = SelectField(_l('Language'), choices=get_languages(), coerce=str,
                           validators=[Optional()])
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
            user = User.query.filter_by(username=username.data).first()
            if user is not None:
                raise ValidationError(_l('Please use a different username'))

    def validate_email(self, email):
        if email.data != self.original_email:
            user = User.query.filter_by(email=email.data).first()
            if user is not None:
                raise ValidationError(_l('Please use a different email'))


class CompanyForm(FlaskForm):
    name = StringField(_l('Company name'), validators=[DataRequired()])
    registration_number = StringField(_l('Registration number'))
    info = TextAreaField(_l('Info'), validators=[Length(max=200)])
    default_time_from = TimeField(_l('Open from (default)'))
    default_time_to = TimeField(_l('Open until (default)'))
    simple_mode = BooleanField(_l('Not use staff schedules'))
    submit = SubmitField(_l('Submit'))


class StaffForm(FlaskForm):
    name = StringField(_l('Name'), validators=[DataRequired()])
    phone = TelField(_l('Phone'), validators=[DataRequired(), validate_phone])
    birthday = DateField(_l('Birthday'), validators=[Optional()])
    schedule = SelectField(_l('Schedule'), choices=[], coerce=int,
                           validate_choice=False)
    submit = SubmitField(_l('Submit'))

    def __init__(self, source_phone=None, *args, **kwargs):
        super(StaffForm, self).__init__(*args, **kwargs)
        self.source_phone = source_phone

    def validate_phone(self, field):
        if field.data != self.source_phone:
            staff = Staff.query.filter_by(phone=field.data).first()
            if staff is not None:
                raise ValidationError(_l('Please use a different phone'))


class StaffFormSimple(StaffForm):
    schedule = None


class ScheduleForm(FlaskForm):
    name = StringField(_l('Title'), validators=[DataRequired()])
    submit = SubmitField(_l('Submit'))


class ScheduleDayForm(FlaskForm):
    weekday = SelectField(_l('Weekday'),
                          choices=[(i, d) for i, d in enumerate(Schedule.week)],
                          coerce=int)
    hour_from = TimeField(_l('From hour'))
    hour_to = TimeField(_l('To hour'))
    submit = SubmitField(_l('Submit'))


class ClientForm(FlaskForm):
    name = StringField(_l('Name'), validators=[DataRequired()])
    phone = TelField(_l('Phone'), validators=[DataRequired(), validate_phone])
    birthday = DateField(_l('Birthday'), validators=[Optional()])
    info = TextAreaField(_l('Info'), validators=[Length(max=200)])
    submit = SubmitField(_l('Submit'))


class ClientFileForm(FlaskForm):
    file = FileField('')
    submit = SubmitField(_l('Submit'))


class TagForm(FlaskForm):
    name = StringField(_l('Title'), validators=[DataRequired()])
    submit = SubmitField(_l('Submit'))


class ServiceForm(FlaskForm):
    name = StringField(_l('Name'), validators=[DataRequired()])
    duration = IntegerField(_l('Duration'), default=0)
    price = FloatField(_l('Price'), default=0)
    repeat = IntegerField(_l('Repeat'), default=0)
    location = SelectMultipleField(_l('Locations'), choices=[],
                                   validate_choice=False, coerce=int)
    submit = SubmitField(_l('Submit'))


class LocationForm(FlaskForm):
    name = StringField(_l('Title'), validators=[DataRequired()])
    phone = TelField(_l('Phone'), validators=[DataRequired(), validate_phone])
    address = StringField(_l('Address'), validators=[DataRequired()])
    schedule = SelectField(_l('Schedule'), choices=[], coerce=int,
                           validate_choice=False)
    submit = SubmitField(_l('Submit'))


class AppointmentForm(FlaskForm):
    location = SelectField(_l('Location'), choices=[], coerce=int)
    date = DateField(_l('Date'), validators=[], format='%Y-%m-%d')
    time = TimeField(_l('Time'), validators=[], format='%H:%M')
    client = SelectField(_l('Client'), choices=[], coerce=int)
    staff = SelectField(_l('Worker'), choices=[], coerce=int)
    service = SelectMultipleField(_l('Services'), choices=[],
                                  validate_choice=False, coerce=int)
    duration = HiddenField(_l('Duration'), default=0)
    services = HiddenField(_l('Services'), default='')
    info = TextAreaField(_l('Info'), validators=[Length(max=200)])
    submit = SubmitField(_l('Submit'))

    def __init__(self, appointment=None, *args, **kwargs):
        super(AppointmentForm, self).__init__(*args, **kwargs)
        self.appointment = appointment

    def validate_location(self, field):
        if not self.location.data:
            raise ValidationError(_l('Please select location'))

    def validate_services(self, field):
        if len(field.data) == 0:
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
            raise ValidationError(_l('Please select client'))

    def validate_staff(self, field):
        if not self.staff.data:
            raise ValidationError(_l('Please select staff'))

    def validate_date(self, field):
        if not self.date.data:
            raise ValidationError(_l('Please select date'))

    def validate_time(self, time):
        if not time.data:
            raise ValidationError(_l('Please select time'))
        location = self.location.data
        staff = self.staff.data
        duration = self.duration.data
        date = self.date.data
        if not location:
            raise ValidationError(_l('Incorrect data'))
        if not staff:
            raise ValidationError(_l('Incorrect data'))
        if self.appointment:
            except_id = self.appointment.id
        else:
            except_id = None
        intervals = get_free_time_intervals(location, date, staff, duration,
                                            except_id)
        if not intervals:
            raise ValidationError(_l('This time unavailable'))
        dt = datetime(date.year, date.month,
                      date.day, time.data.hour, time.data.minute)
        check = False
        for interval in intervals:
            time_from = interval[0]
            time_to = interval[1]
            if time_from <= dt <= time_to:
                check = True
        if not check:
            raise ValidationError(_l('This time unavailable'))


class ResultForm(FlaskForm):
    result = TextAreaField(_l('Result'), validators=[Length(max=255)])
    submit = SubmitField(_l('Submit'))


class SearchForm(FlaskForm):
    pass
    # location_id = SelectField(_l('Location'), choices=[], coerce=int)
    # staff_id = SelectField(_l('Worker'), choices=[], coerce=int)
    # client_id = SelectField(_l('Client'), choices=[], coerce=int)


class ItemForm(FlaskForm):
    name = StringField(_l('Title'), validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Length(max=255)])
    submit = SubmitField(_l('Submit'))


class ItemFlowForm(FlaskForm):
    location = SelectField(_l('Location'), choices=[], coerce=int)
    date = DateField(_l('Date'))
    item = SelectField(_l('Item'), choices=[], coerce=int)
    action = SelectField(_l('Operation'), choices=[(1, 'Plus'), (-1, 'Minus')],
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
            raise ValidationError(_l('Quantity exceeds available %(count)s',
                                     count=count))


class ContactForm(FlaskForm):
    name = StringField(_l('Name'), validators=[DataRequired()])
    email = StringField(_l('E-mail'), validators=[DataRequired(), Email()])
    text = TextAreaField(_l('Text'), validators=[DataRequired(), Length(max=255)])
    submit = SubmitField(_l('Submit'))


class NoticeForm(FlaskForm):
    client = SelectField(_l('Client'), choices=[], coerce=int)
    date = DateField(_l('Date'))
    description = TextAreaField(_l('Description'), validators=[DataRequired(),
                                                               Length(max=255)])
    submit = SubmitField(_l('Submit'))


class CashFlowForm(FlaskForm):
    location = SelectField(_l('Location'), choices=[], coerce=int)
    date = DateField(_l('Date'))
    description = StringField(_l('Description'), validators=[DataRequired(),
                                                             Length(max=120)])
    action = SelectField(_l('Operation'), choices=[(1, 'Plus'), (-1, 'Minus')],
                         coerce=int)
    cost = FloatField(_l('Sum'), default=0)
    submit = SubmitField(_l('Submit'))

    def validate_location(self, field):
        if not self.location.data:
            raise ValidationError(_l('Please select location'))


class TaskForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    deadline = DateField('Date')
    staff = SelectField('Worker', choices=[], coerce=int)
    description = TextAreaField('Description', validators=[Length(max=255)])
    submit = SubmitField('Submit')


class TaskStatusForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Length(max=255)])
    final = BooleanField('Final')
    submit = SubmitField('Submit')
