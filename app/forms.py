import datetime

import phonenumbers
from flask import flash
from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, BooleanField,
                     SubmitField, TextAreaField, TelField, IntegerField,
                     FloatField, SelectField, DateField, TimeField,
                     SelectMultipleField, FileField, HiddenField)
from wtforms.validators import (DataRequired, Email, EqualTo,
                                ValidationError, Length, Optional)

from .models import Schedule
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
    company = StringField('Company', validators=[DataRequired()])
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField('Repeat password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Submit')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email')


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember me')
    submit = SubmitField('Submit')


class UserForm(RegisterForm):
    company = None


class UserFormEdit(UserForm):
    password_old = PasswordField('Password')
    password = PasswordField('Password new')
    password2 = PasswordField('Repeat password new', validators=[EqualTo('password')])

    def __init__(self, original_username, original_email, *args, **kwargs):
        super(UserFormEdit, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=username.data).first()
            if user is not None:
                raise ValidationError('Please use a different username')

    def validate_email(self, email):
        if email.data != self.original_email:
            user = User.query.filter_by(email=email.data).first()
            if user is not None:
                raise ValidationError('Please use a different email')


class EditProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    submit = SubmitField('Submit')


class CompanyForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    registration_number = StringField('Registration number')
    info = TextAreaField('Info', validators=[Length(max=200)])
    submit = SubmitField('Submit')


class StaffForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    phone = TelField('Phone', validators=[DataRequired(), validate_phone])
    birthday = DateField('Birthday', validators=[Optional()])
    schedule = SelectField('Schedule', choices=[], coerce=int,
                           validate_choice=False)
    submit = SubmitField('Submit')

    def __init__(self, source_phone=None, *args, **kwargs):
        super(StaffForm, self).__init__(*args, **kwargs)
        self.source_phone = source_phone

    def validate_phone(self, field):
        if field.data != self.source_phone:
            staff = Staff.query.filter_by(phone=field.data).first()
            if staff is not None:
                raise ValidationError('Please use a different phone')


class ScheduleForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    submit = SubmitField('Submit')


class ScheduleDayForm(FlaskForm):
    weekday = SelectField('Weekday',
                          choices=[(i, d) for i, d in enumerate(Schedule.week)],
                          coerce=int)
    hour_from = TimeField('From hour')
    hour_to = TimeField('To hour')
    submit = SubmitField('Submit')


class ClientForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    phone = TelField('Phone', validators=[DataRequired(), validate_phone])
    birthday = DateField('Birthday', validators=[Optional()])
    info = TextAreaField('Info', validators=[Length(max=200)])
    submit = SubmitField('Submit')


class ClientFileForm(FlaskForm):
    file = FileField('')
    submit = SubmitField('Submit')


class TagForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    submit = SubmitField('Submit')


class ServiceForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    duration = IntegerField('Duration', default=0)
    price = FloatField("Price", default=0)
    repeat = IntegerField('Repeat', default=0)
    location = SelectMultipleField('Locations', choices=[],
                                   validate_choice=False, coerce=int)
    submit = SubmitField('Submit')


class LocationForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    phone = TelField('Phone', validators=[DataRequired()])
    address = StringField('Address', validators=[DataRequired()])
    schedule = SelectField('Schedule', choices=[], coerce=int,
                           validate_choice=False)
    submit = SubmitField('Submit')


class AppointmentForm(FlaskForm):
    location = SelectField('Location', choices=[], coerce=int)
    date = DateField('Date', validators=[], format='%Y-%m-%d')
    time = TimeField('Time', validators=[], format='%H:%M')
    client = SelectField('Client', choices=[], coerce=int)
    staff = SelectField('Staff', choices=[], coerce=int)
    service = SelectMultipleField('Services', choices=[],
                                  validate_choice=False, coerce=int)
    duration = HiddenField('Duration', default=0)
    services = HiddenField('Services', default='')
    info = TextAreaField('Info', validators=[Length(max=200)])
    cancel = BooleanField('Cancel')
    submit = SubmitField('Submit')

    def __init__(self, appointment=None, *args, **kwargs):
        super(AppointmentForm, self).__init__(*args, **kwargs)
        self.appointment = appointment

    def validate_location(self, field):
        if self.location.data is None or self.location.data == 0:
            raise ValidationError('Please, select location')

    def validate_services(self, field):
        if len(field.data) == 0:
            raise ValidationError('Please, select services')
        else:
            if self.location.data is None or self.location.data == 0:
                raise ValidationError('Please, select location')
            location = Location.query.get_or_404(self.location.data)
            services_id = [x.id for x in location.services]
            for s in field.data.split(','):
                if int(s) not in services_id:
                    message = f'Service id {s} unavailable in select location'
                    flash(message)
                    raise ValidationError(message)

    def validate_client(self, field):
        if self.client.data is None or self.client.data == 0:
            raise ValidationError('Please, select client')

    def validate_staff(self, field):
        if self.staff.data is None or self.staff.data == 0:
            raise ValidationError('Please, select staff')

    def validate_date(self, field):
        if not self.date.data:
            raise ValidationError('Please, select date')

    def validate_time(self, time):
        location = self.location.data
        staff = self.staff.data
        duration = self.duration.data
        date = self.date.data
        if location == 0 or location is None:
            raise ValidationError('Incorrect data')
        if staff == 0 or staff is None:
            raise ValidationError('Incorrect data')
        if self.appointment:
            except_id = self.appointment.id
        else:
            except_id = None
        intervals = get_free_time_intervals(location, date, staff, duration,
                                            except_id)
        if not intervals:
            raise ValidationError('Sorry, this time unavailable')
        dt = datetime(date.year, date.month,
                      date.day, time.data.hour, time.data.minute)
        check = False
        for interval in intervals:
            time_from = interval[0]
            time_to = interval[1]
            if time_from <= dt <= time_to:
                check = True
        if not check:
            raise ValidationError('Sorry, this time unavailable')


class ResultForm(FlaskForm):
    result = TextAreaField('Result', validators=[Length(max=255)])
    submit = SubmitField('Submit')


class SearchForm(FlaskForm):
    location_id = SelectField('Location', choices=[], coerce=int)
    staff_id = SelectField('Staff', choices=[], coerce=int)
    client_id = SelectField('Client', choices=[], coerce=int)


class ItemForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Length(max=255)])
    submit = SubmitField('Submit')


class ItemFlowForm(FlaskForm):
    location = SelectField('Location', choices=[], coerce=int)
    date = DateField('Date')
    item = SelectField('Item', choices=[], coerce=int)
    action = SelectField('Action', choices=[(1, 'Plus'), (-1, 'Minus')],
                         coerce=int)
    quantity = FloatField('Quantity', default=0)
    submit = SubmitField('Submit')

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
            raise ValidationError(f'Quantity exceeds available ({count})')


class ContactForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    text = TextAreaField('Text', validators=[DataRequired(), Length(max=255)])
    submit = SubmitField('Submit')


class NoticeForm(FlaskForm):
    client = SelectField('Client', choices=[], coerce=int)
    date = DateField('Date')
    description = TextAreaField('Description', validators=[DataRequired(), Length(max=255)])
    submit = SubmitField('Submit')


class CashFlowForm(FlaskForm):
    location = SelectField('Location', choices=[], coerce=int)
    date = DateField('Date')
    description = StringField('Description', validators=[DataRequired(), Length(max=120)])
    action = SelectField('Action', choices=[(1, 'Plus'), (-1, 'Minus')],
                         coerce=int)
    cost = FloatField('Sum', default=0)
    submit = SubmitField('Submit')


class TaskForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    deadline = DateField('Date')
    staff = SelectField('Staff', choices=[], coerce=int)
    description = TextAreaField('Description', validators=[Length(max=255)])
    submit = SubmitField('Submit')


class TaskStatusForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Length(max=255)])
    final = BooleanField('Final')
    submit = SubmitField('Submit')
