import datetime

import phonenumbers
from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, BooleanField,
                     SubmitField, TextAreaField, TelField, IntegerField,
                     FloatField, SelectField, DateField, TimeField,
                     SelectMultipleField)
from wtforms.validators import (DataRequired, Email, EqualTo,
                                ValidationError, Length)

from app.functions import *


# global validators
def validate_phone(form, field):
    try:
        p = phonenumbers.parse(field.data)
        if not phonenumbers.is_valid_number(p):
            raise ValueError()
    except (phonenumbers.phonenumberutil.NumberParseException, ValueError):
        raise ValidationError('Invalid phone number')


# forms
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember me')
    submit = SubmitField('Submit')


class UserForm(FlaskForm):
    cid = SelectField('Company', choices=[], validate_choice=False, coerce=int)
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    role = SelectField('Role', choices=[(1, 'User'), (99, 'Admin')], validate_choice=False, coerce=int)
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
    no_active = BooleanField('No active')
    submit = SubmitField('Submit')


class StaffForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    phone = TelField('Phone', validators=[DataRequired(), validate_phone])
    no_active = BooleanField('No active')
    submit = SubmitField('Submit')


class StaffScheduleForm(FlaskForm):
    staff = SelectField('Staff', choices=[], coerce=int)
    location = SelectField('Location', choices=[], coerce=int)
    date_from = DateField('Date from', validators=[DataRequired()])
    date_to = DateField('Date to', validators=[DataRequired()])
    time_from = TimeField('Date from', validators=[DataRequired()])
    time_to = TimeField('Date to', validators=[DataRequired()])
    no_active = BooleanField('No active')

    def validate_location(self, field):
        if field.data is None or field.data == 0:
            raise ValidationError('Please, select location')

    def validate_date_from(self, field):
        if self.date_to.data <= self.date_from.data:
            raise ValidationError("Invalid dates")

    def validate_date_to(self, field):
        if self.date_to.data <= self.date_from.data:
            raise ValidationError("Invalid dates")

    def validate_time_from(self, field):
        if self.time_to.data <= self.time_from.data:
            raise ValidationError("Invalid time")

    def validate_time_to(self, field):
        if self.time_to.data <= self.time_from.data:
            raise ValidationError("Invalid time")


class ClientForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    phone = TelField('Phone', validators=[DataRequired(), validate_phone])
    info = TextAreaField('Info', validators=[Length(max=200)])
    no_active = BooleanField('No active')
    submit = SubmitField('Submit')


class ServiceForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    duration = IntegerField('Duration', default=0)
    price = FloatField("Price", default=0)
    location = SelectMultipleField('Locations', choices=[],
                                   validate_choice=False, coerce=int)
    no_active = BooleanField('No active')
    submit = SubmitField('Submit')


class LocationForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    phone = TelField('Phone', validators=[DataRequired()])
    address = StringField('Address', validators=[DataRequired()])
    open = TimeField('Open', validators=[DataRequired()])
    close = TimeField('Close', validators=[DataRequired()])
    # timezone = SelectField('Timezone', choices=[], validate_choice=False, coerce=int)
    no_active = BooleanField('No active')
    submit = SubmitField('Submit')

    def validate_open(self, field):
        if self.close.data <= self.open.data:
            raise ValidationError("Invalid open-close hours")

    def validate_close(self, field):
        if self.close.data <= self.open.data:
            raise ValidationError("Invalid open-close hours")


class AppointmentForm(FlaskForm):
    location = SelectField('Location', choices=[], coerce=int)
    date = DateField('Date', validators=[DataRequired()], format='%Y-%m-%d')
    time = TimeField('Time', validators=[DataRequired()], format='%H:%M')
    client = SelectField('Client', choices=[], coerce=int)
    staff = SelectField('Staff', choices=[], coerce=int)
    service = SelectMultipleField('Services', choices=[],
                                  validate_choice=False, coerce=int)
    info = TextAreaField('Info', validators=[Length(max=200)])
    cancel = BooleanField('Cancel')
    submit = SubmitField('Submit')

    def __init__(self, appointment=None, *args, **kwargs):
        super(AppointmentForm, self).__init__(*args, **kwargs)
        self.appointment = appointment

    def validate_location(self, field):
        if field.data is None or field.data == 0:
            raise ValidationError('Please, select location')

    def validate_client(self, field):
        if field.data is None or field.data == 0:
            raise ValidationError('Please, select client')

    def validate_staff(self, field):
        if field.data is None or field.data == 0:
            raise ValidationError('Please, select staff')

    def validate_time(self, time):
        location = self.location.data
        staff = self.staff.data
        services = self.service.data
        duration = get_duration(services)
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
                                            True, except_id)
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


class SearchForm(FlaskForm):
    location = SelectField('Location', choices=[], coerce=int)
    staff = SelectField('Staff', choices=[], coerce=int)
    client = SelectField('Client', choices=[], coerce=int)


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

    def __init__(self, source_location, source_item, source_quantity,
                 *args, **kwargs):
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
