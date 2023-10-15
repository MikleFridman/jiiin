import ast
import datetime
import json
import zipfile
from base64 import b64encode
from functools import wraps
from io import BytesIO
from urllib.request import urlopen
from xml.dom import minidom
from datetime import time

import pandas as pd
import qrcode
from dateutil.relativedelta import relativedelta
from pandas import ExcelWriter
from sqlalchemy.orm import RelationshipProperty

import app
import hashlib
import os.path

from flask import render_template, redirect, url_for, request, jsonify, send_file, g
from flask_babel import _, lazy_gettext as _l, get_locale
from flask_login import login_user, logout_user, login_required
from werkzeug.urls import url_parse

from .bot import send_bot_message
from app.forms import *
from app.functions import *
from app.models import *


doc_version = minidom.parse('version.xml')
VERSION = doc_version.getElementsByTagName('version')[0].firstChild.data
VERSION_DATE = doc_version.getElementsByTagName('date')[0].firstChild.data


@app.before_request
def before_request():
    g.locale = str(get_locale())


@app.context_processor
def ip_country():
    if not session.get('country', None):
        if request.remote_addr == '127.0.0.1':
            url = 'http://ipinfo.io/json'
        else:
            url = 'http://ipinfo.io/' + str(request.remote_addr) + '/json'
        geo_data = json.load(urlopen(url))
        country_code_ip = geo_data.get('country', None)
        if country_code_ip and country_code_ip.upper() == 'IL':
            country_code = 'IL'
            country = 'Israel'
            currency_code = 'ILS'
            currency = '\u20AA'
        else:
            country_code = ''
            country = 'Other'
            currency_code = 'USD'
            currency = '\u0024'
        country = {'country_code': country_code,
                   'country': country,
                   'currency_code': currency_code,
                   'currency': currency}
        session['country'] = country
    return session['country']


@app.context_processor
def inject_today_date():
    return {'today_date': datetime.now().date()}


@app.context_processor
def inject_week_date():
    return {'week_date': datetime.now().date() + timedelta(days=7)}


@app.context_processor
def inject_version():
    return {'version': VERSION, 'version_date': VERSION_DATE}


@app.context_processor
def inject_tariff():
    if current_user.is_authenticated:
        if not session.get('current_tariff', None):
            current_tariff = {'tariff': Company.get_current_tariff().name,
                              'tariff_id': Company.get_current_tariff().id}
            session['current_tariff'] = current_tariff
        return session['current_tariff']
    return {'tariff': Tariff.get_tariff_default().name,
            'tariff_id': Tariff.get_tariff_default().id}


@app.context_processor
def get_theme():
    return {'theme': session.get('theme', 'dark')}


@app.context_processor
def check_notices():
    if current_user.is_authenticated:
        if not session.get('notices_count', None):
            param = dict(date=datetime.now().date(), processed=False)
            session['notices_count'] = len(Notice.get_items(data_filter=param))
        return {'notices_count': session['notices_count']}
    return []


def admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if not current_user.staff:
            return f(*args, **kwargs)
        else:
            flash(_l('Access denied'))
            url_back = request.args.get('url_back', url_for('index'))
            return redirect(url_back)
    return wrap


def global_admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if current_user.check_permission('AdminView', 'read'):
            return f(*args, **kwargs)
        else:
            flash(_l('Access denied'))
            url_back = request.args.get('url_back', url_for('index'))
            return redirect(url_back)
    return wrap


def confirm(desc):
    def outer(f):
        @wraps(f)
        def wrap(*args, **kwargs):
            form = ConfirmForm()
            url_back = request.args.get('url_back', url_for('index'))
            if form.validate_on_submit():
                return f(*args, **kwargs)
            return render_template('base.html',
                                   form=form,
                                   desc=desc,
                                   modal=True,
                                   url_back=url_back)
        return wrap
    return outer


def check_limit(class_object):
    def outer(f):
        @wraps(f)
        def wrap(*args, **kwargs):
            tariff = Company.get_current_tariff()
            if not tariff.check_tariff_limit(class_object):
                flash(_('Exceeded the limit on your tariff'))
                return redirect(url_for(class_object.table_link))
            return f(*args, **kwargs)
        return wrap
    return outer


@app.route('/delete/<class_name>/<object_id>/', methods=['GET', 'POST'])
@login_required
@admin_required
@confirm(_l('Delete the selected object?'))
def delete(class_name, object_id):
    class_object = Entity.get_class(class_name)
    del_object = class_object.get_object(object_id)
    url_back = request.args.get('url_back', url_for('index'))
    del_object.delete_object()
    if class_object == Notice:
        session.pop('notices_count', None)
    return redirect(url_back)


def set_filter(class_object):
    search_list = []
    for search_attr, search_name, search_object in class_object.search:
        search_list.append(search_attr)
        if issubclass(search_object, Entity) or issubclass(search_object, Week):
            choices = search_object.get_items(True)
            setattr(SearchForm, search_attr, SelectField(_l(search_name),
                                                         choices=[*choices],
                                                         coerce=int))
        elif issubclass(search_object, bool) or issubclass(search_object,
                                                           type(None)):
            choices = [('', _l('-Select-')),
                       ('False', _l('False')),
                       ('True', _l('True'))]
            setattr(SearchForm, search_attr, SelectField(_l(search_name),
                                                         choices=[*choices],
                                                         coerce=str))
        elif issubclass(search_object, type(datetime.now())):
            setattr(SearchForm, search_attr,
                    DateField(_l(search_name),
                              validators=[validate_date_global]))
        elif issubclass(search_object, Period):
            search_attr_from = search_attr + '_from'
            search_attr_to = search_attr + '_to'
            setattr(SearchForm, search_attr_from,
                    DateField(_l('Date from'),
                              validators=[validate_date_global]))
            setattr(SearchForm, search_attr_to,
                    DateField(_l('Date to'),
                              validators=[validate_date_global]))
            search_list.remove(search_attr)
            search_list.append(search_attr_from)
            search_list.append(search_attr_to)
        else:
            setattr(SearchForm, search_attr, StringField(_l(search_name)))
    rest_args = list(set(request.args.keys()).difference(set(search_list)))
    rest_args_dict = {}
    ignore_list = ['page']
    for ra in rest_args:
        if ra not in ignore_list:
            setattr(SearchForm, ra, HiddenField(ra))
            rest_args_dict[ra] = request.args.get(ra, None)
    setattr(SearchForm, 'filter', HiddenField('filter'))
    return SearchForm(request.form, meta={'csrf': False}, **rest_args_dict)


def get_filter_parameters(form, class_object):
    filter_param = {}
    search_param = []
    check_filter = False
    for search_attr, search_name, search_object in class_object.search:
        request_arg = request.args.get(search_attr, None, type=str)
        if request_arg and not request_arg == '0':
            check_filter = True
            if issubclass(search_object, Entity) or issubclass(search_object, Week):
                if (getattr(class_object, search_attr) and
                        type(getattr(class_object, search_attr).property) == RelationshipProperty):
                    search_param.append(getattr(class_object, search_attr).any(id=request_arg))
                else:
                    filter_param[search_attr] = request_arg
                form[search_attr].default = request_arg
                form.process()
            elif issubclass(search_object, bool):
                request_value = ast.literal_eval(request_arg)
                if request_value:
                    search_param.append(getattr(class_object, search_attr).is_(True))
                else:
                    search_param.append(getattr(class_object, search_attr).is_not(True))
                form[search_attr].default = request_arg
                form.process()
            elif issubclass(search_object, type(None)):
                request_value = ast.literal_eval(request_arg)
                if request_value:
                    search_param.append(getattr(class_object, search_attr).is_not(None))
                else:
                    search_param.append(getattr(class_object, search_attr).is_(None))
                form[search_attr].default = request_arg
                form.process()
            elif issubclass(search_object, type(datetime.now())):
                try:
                    filter_param[search_attr] = request_arg
                    form[search_attr].data = datetime.strptime(request_arg,
                                                               '%Y-%m-%d')
                except ValueError:
                    check_filter = False
                    flash(_l('Invalid date'))
            else:
                search_param.append(getattr(class_object, search_attr
                                            ).ilike(f'%{str(request_arg)}%'))
                form[search_attr].data = request_arg
        if issubclass(search_object, Period):
            search_attr_from = search_attr + '_from'
            search_attr_to = search_attr + '_to'
            request_arg_from = request.args.get(search_attr_from, None, type=str)
            request_arg_to = request.args.get(search_attr_to, None, type=str)
            if request_arg_from and not request_arg_from == '0':
                try:
                    search_param.append(func.date(
                        getattr(class_object, search_attr)) >=
                                        datetime.strptime(request_arg_from, '%Y-%m-%d').date())
                    form[search_attr_from].data = datetime.strptime(
                        request_arg_from, '%Y-%m-%d')
                    check_filter = True
                except ValueError:
                    flash(_l('Invalid date'))
            if request_arg_to and not request_arg_to == '0':
                try:
                    search_param.append(func.date(
                        getattr(class_object, search_attr)) <
                                        (datetime.strptime(request_arg_to, '%Y-%m-%d') +
                                         timedelta(days=1)).date())
                    form[search_attr_to].data = datetime.strptime(
                        request_arg_to, '%Y-%m-%d').date()
                    check_filter = True
                except ValueError:
                    flash(_l('Invalid date'))
            delattr(SearchForm, search_attr_from)
            delattr(SearchForm, search_attr_to)
        if hasattr(SearchForm, search_attr):
            delattr(SearchForm, search_attr)
    for ra in list(request.args.keys()):
        if hasattr(SearchForm, ra):
            delattr(SearchForm, ra)
    form.filter.data = check_filter
    if hasattr(SearchForm, 'filter'):
        delattr(SearchForm, 'filter')
    choice_mode = request.args.get('choice_mode', None)
    if choice_mode:
        form.choice_mode.data = choice_mode
    if hasattr(SearchForm, 'choice_mode'):
        delattr(SearchForm, 'choice_mode')
    return filter_param, search_param


@app.route('/sendmail/', methods=['GET', 'POST'])
def sendmail():
    url_back = request.args.get('url_back', url_for('index', **request.args))
    if current_user.is_authenticated:
        form = ContactUserForm()
    else:
        form = ContactForm()
    form.text.render_kw = {'rows': 6}
    if form.validate_on_submit():
        sender = app.config['MAIL_DEFAULT_SENDER']
        subject = f'Feedback from site ({form.name.data}, {form.email.data})'
        text = form.text.data
        send_mail_from_site(sender, subject, text)
        flash(_('Message success send'))
        return redirect(url_back)
    return render_template('data_form.html',
                           title=_('Send mail'),
                           form=form,
                           url_back=url_back)


@app.route('/')
@app.route('/index/')
def index():
    if current_user.is_authenticated:
        start_page = current_user.start_page
        if start_page:
            return redirect(url_for(start_page))
        else:
            return redirect(url_for('appointments_table'))
    return render_template('index.html')


@app.route('/register/', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    url_back = url_for('index')
    form = RegisterForm()
    if form.validate_on_submit():
        company = Company(name=form.company.data)
        db.session.add(company)
        db.session.flush()
        cfg = CompanyConfig(cid=company.id)
        db.session.add(cfg)
        user = User(cid=company.id,
                    username=form.username.data,
                    email=form.email.data,
                    promo_code=form.promo_code.data)
        db.session.add(user)
        db.session.flush()
        user.set_password(form.password.data)
        db.session.commit()
        if not app.debug and app.config['SEND_BOT_MESSAGE']:
            msg = 'Registered new account: ' + form.username.data
            if form.promo_code.data:
                msg += ' promo code: ' + form.promo_code.data
            send_bot_message(app.config['ADMIN_CHAT_ID'], msg)
        flash(_('Registration successfully'), 'info')
        send_mail(subject=_('Registration') + ' Jiiin',
                  sender=app.config['MAIL_DEFAULT_SENDER'],
                  recipients=[form.email.data],
                  text_body=render_template('welcome.txt'))
        return redirect(url_for('login'))
    return render_template('data_form.html',
                           form=form,
                           url_back=url_back)


@app.route('/login/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.find_object({'username': form.username.data},
                                overall=True)
        if not user:
            user = User.find_object({'email': form.username.data},
                                    overall=True)
        if user is None or not user.check_password(form.password.data):
            flash(_('Invalid username or password'))
            return redirect(url_for('login'))
        login_user(user, remember=True)
        user.update_login_timestamp()
        if not user.company or not user.company.config:
            logout_user()
            error_message = _('Not found company configuration!')
            return render_template('error.html', message=error_message), 404
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        app.logger.info('%s успешный вход в систему', user.username)
        if current_user.company.config.show_quick_start:
            next_page = url_for('quick_start')
        return redirect(next_page)
    return render_template('login.html',
                           title=_('Sign in'),
                           form=form)


@app.route('/logout/')
def logout():
    if current_user.is_authenticated:
        username = current_user.username
        logout_user()
        app.logger.info('%s выход из системы', username)
    return redirect(url_for('login'))


@app.route('/delete_account/', methods=['GET', 'POST'])
@login_required
@admin_required
@confirm(_l('Confirm deletion account and all data'))
def delete_account():
    db.session.delete(current_user.company)
    username = current_user.username
    db.session.commit()
    flash(_('Account successfully deleted'))
    if not app.debug:
        send_bot_message(app.config['ADMIN_CHAT_ID'],
                         'Deleted account: ' + username)
    # send_mail_from_site(sender, subject, text)
    logout()
    return redirect(url_for('index'))


@app.route('/delete_page/', methods=['GET', 'POST'])
@login_required
def delete_page():
    url_back = url_for('company_edit')
    form = DeleteAccountForm()
    if form.validate_on_submit():
        if form.confirm_delete.data:
            return redirect(url_for('delete_account'))
    return render_template('data_form.html',
                           title='Delete account',
                           form=form,
                           url_back=url_back)


# Company block start
@app.route('/companies/edit/', methods=['GET', 'POST'])
@login_required
@admin_required
def company_edit():
    url_back = url_for('index', **request.args)
    form = CompanyForm()
    company = current_user.company
    if form.validate_on_submit():
        company.name = form.name.data
        company.registration_number = form.registration_number.data
        # company.info = form.info.data
        company.config.default_time_from = form.default_time_from.data
        company.config.default_time_to = form.default_time_to.data
        company.config.simple_mode = form.simple_mode.data
        company.config.show_quick_start = form.show_quick_start.data
        company.config.min_time_interval = form.min_time_interval.data
        db.session.commit()
        session.pop('current_tariff', None)
        if not company.config.simple_mode and not Staff.check_schedules():
            flash(_('It is necessary to select employee schedules'), 'info')
            return redirect(url_for('staff_table'))
        return redirect(url_for('index'))
    elif request.method == 'GET':
        form.min_time_interval.default = CompanyConfig.get_parameter('min_time_interval')
        form.process()
        form.name.data = company.name
        form.registration_number.data = company.registration_number
        # form.info.data = company.info
        form.default_time_from.data = company.config.default_time_from
        form.default_time_to.data = company.config.default_time_to
        form.simple_mode.data = CompanyConfig.get_parameter('simple_mode')
        form.show_quick_start.data = CompanyConfig.get_parameter('show_quick_start')
        form.default_time_from.data = CompanyConfig.get_parameter('default_time_from')
        form.default_time_to.data = CompanyConfig.get_parameter('default_time_to')
        form.delete_account.data = url_for('delete_page')
    return render_template('data_form.html',
                           title=_('Company (edit)'),
                           form=form,
                           url_back=url_back)


# Company block end


# User block start
@app.route('/users/edit/<id>', methods=['GET', 'POST'])
@login_required
def user_edit(id):
    url_back = url_for('index', **request.args)
    user = User.get_object(id)
    form = UserFormEdit(user.username, user.email)
    if form.validate_on_submit():
        user.username = form.username.data
        user.email = form.email.data
        if form.language.data:
            user.language = form.language.data
        else:
            user.language = None
        if form.start_page.data:
            user.start_page = form.start_page.data
        else:
            user.start_page = None
        if form.password.data.strip() != '':
            if not user.check_password(form.password_old.data):
                flash(_('Invalid username or password'))
                return render_template('data_form.html',
                                       title=_('User (edit)'),
                                       form=form)
            user.set_password(form.password.data)
        db.session.commit()
        return redirect(url_for('index'))
    elif request.method == 'GET':
        form.username.data = user.username
        form.email.data = user.email
        form.language.data = user.language
        form.start_page.data = user.start_page
    return render_template('data_form.html',
                           title=_('User (edit)'),
                           form=form,
                           url_back=url_back)


@app.route('/reset_password_request/', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    url_back = url_for('login')
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.find_object({'email': form.email.data}, overall=True)
        if user:
            temp_password = User.get_random_password()
            user.set_password(temp_password)
            db.session.commit()
            send_mail(subject=_('Reset password') + ' Jiiin',
                      sender=app.config['MAIL_DEFAULT_SENDER'],
                      recipients=[user.email],
                      text_body=render_template('reset_password.txt',
                                                password=temp_password))
            flash(_('Temporary password has been sent to your e-mail'))
            return redirect(url_for('login'))
        else:
            flash(_('User with the specified e-mail is not registered'))
            return redirect(url_for('reset_password_request'))
    return render_template('data_form.html',
                           title=_('Reset password'),
                           form=form,
                           url_back=url_back)
# User block end


# Staff block start
# noinspection PyTypeChecker
@app.route('/staff/')
@login_required
@admin_required
def staff_table():
    page = request.args.get('page', 1, type=int)
    form = set_filter(Staff)
    param = get_filter_parameters(form, Staff)
    data = Staff.get_pagination(page, *param)
    return render_template('staff_table.html',
                           title=_('Staff'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/staff/create/', methods=['GET', 'POST'])
@login_required
@admin_required
@check_limit(Staff)
def staff_create():
    url_back = request.args.get('next', url_for('staff_table', **request.args))
    next_page = request.args.get('next')
    if not next_page or url_parse(next_page).netloc != '':
        next_page = url_for('staff_table')
    if CompanyConfig.get_parameter('simple_mode'):
        form = StaffFormSimple()
    else:
        form = StaffForm()
        form.schedule.choices = Schedule.get_items(True)
    if request.method == 'POST':
        form.phone.data = phone_number_plus(form.phone.data)
    if form.validate_on_submit():
        staff = Staff(cid=current_user.cid,
                      name=form.name.data,
                      phone=form.phone.data,
                      birthday=form.birthday.data)
        db.session.add(staff)
        if not CompanyConfig.get_parameter('simple_mode'):
            if form.schedule.data:
                db.session.flush()
                schedule = Schedule.get_object(form.schedule.data)
                staff.schedules.append(schedule)
        db.session.commit()
        return redirect(next_page)
    form.user_link.data = None
    return render_template('data_form.html',
                           title=_('Staff (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/staff/edit/<id>/', methods=['GET', 'POST'])
@login_required
@admin_required
def staff_edit(id):
    url_back = url_for('staff_table', **request.args)
    staff = Staff.get_object(id)
    if CompanyConfig.get_parameter('simple_mode'):
        form = StaffFormSimple(staff.phone)
    else:
        form = StaffForm(staff.phone)
        form.schedule.choices = Schedule.get_items(True)
    if request.method == 'POST':
        form.phone.data = phone_number_plus(form.phone.data)
    if form.validate_on_submit():
        staff.name = form.name.data
        staff.phone = form.phone.data
        staff.birthday = form.birthday.data
        if not CompanyConfig.get_parameter('simple_mode'):
            if form.schedule.data:
                schedule = Schedule.get_object(form.schedule.data)
                staff.schedules.clear()
                staff.schedules.append(schedule)
            else:
                staff.schedules.clear()
        db.session.commit()
        return redirect(url_for('staff_table'))
    elif request.method == 'GET':
        if CompanyConfig.get_parameter('simple_mode'):
            form = StaffFormSimple(obj=staff)
        else:
            if staff.main_schedule:
                form.schedule.default = staff.main_schedule.id
            form.process(obj=staff)
        form.user_link.data = url_for('staff_user', id=staff.id)
    return render_template('data_form.html',
                           title=_('Staff (edit)'),
                           form=form,
                           url_back=url_back)


@app.route('/staff/edit/<id>/user', methods=['GET', 'POST'])
@login_required
@admin_required
def staff_user(id):
    url_back = url_for('staff_edit', id=id, **request.args)
    if not id:
        flash(_('Save the data first'))
        return redirect(url_back)
    staff = Staff.get_object(id)
    if staff.user:
        form = StaffUserEditForm(staff.user.username, staff.user.email)
    else:
        form = UserForm()
    if form.validate_on_submit():
        if staff.user:
            staff.user.username = form.username.data
            staff.user.email = form.email.data
            if form.password.data:
                staff.user.set_password(form.password.data)
            staff.user.no_active = form.no_active.data
            db.session.commit()
            flash(_('User successfully changed'), 'info')
        else:
            user = User(cid=current_user.cid,
                        username=form.username.data,
                        email=form.email.data)
            db.session.add(user)
            user.set_password(form.password.data)
            db.session.flush()
            staff.user_id = user.id
            db.session.commit()
            flash(_('User successfully create'), 'info')
        return redirect(url_back)
    elif request.method == 'GET':
        if staff.user:
            form.process(obj=staff.user)
    return render_template('data_form.html',
                           title=_('User (edit)'),
                           form=form,
                           url_back=url_back)


# noinspection PyTypeChecker
@app.route('/holidays/')
@login_required
@admin_required
def holidays_table():
    page = request.args.get('page', 1, type=int)
    form = set_filter(Holiday)
    param = get_filter_parameters(form, Holiday)
    data = Holiday.get_pagination(page, *param)
    return render_template('holiday_table.html',
                           title=_('Holidays'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/holidays/create/', methods=['GET', 'POST'])
@login_required
@admin_required
def holiday_create():
    url_back = request.args.get('url_back', url_for('holidays_table',
                                                    **request.args))
    form = HolidayForm()
    form.staff.choices = Staff.get_items(True)
    if form.validate_on_submit():
        holiday = Holiday(cid=current_user.cid,
                          staff_id=form.staff.data,
                          date=form.date.data,
                          working_day=form.working_day.data,
                          hour_from=form.hour_from.data,
                          hour_to=form.hour_to.data)
        db.session.add(holiday)
        db.session.commit()
        return redirect(url_back)
    return render_template('data_form.html',
                           title=_('Holiday (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/holidays/edit/<id>/', methods=['GET', 'POST'])
@login_required
@admin_required
def holiday_edit(id):
    url_back = request.args.get('url_back', url_for('holidays_table',
                                                    **request.args))
    holiday = Holiday.get_object(id)
    form = HolidayForm()
    form.staff.choices = Staff.get_items(True)
    if form.validate_on_submit():
        holiday.staff_id = form.staff.data
        holiday.date = form.date.data
        holiday.working_day = form.working_day.data
        holiday.hour_from = form.hour_from.data
        holiday.hour_to = form.hour_to.data
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form.staff.default = holiday.staff_id
        form.process()
        form.date.data = holiday.date
        form.working_day.data = holiday.working_day
        form.hour_from.data = holiday.hour_from
        form.hour_to.data = holiday.hour_to
    return render_template('data_form.html',
                           title=_('Holiday (edit)'),
                           form=form,
                           url_back=url_back)
# Staff block end


# Schedule block start
# noinspection PyTypeChecker
@app.route('/schedules/')
@login_required
@admin_required
def schedules_table():
    page = request.args.get('page', 1, type=int)
    form = set_filter(Schedule)
    # noinspection PyTypeChecker
    param = get_filter_parameters(form, Schedule)
    data = Schedule.get_pagination(page, *param)
    return render_template('schedule_table.html',
                           title=_('Schedules'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/schedules/create', methods=['GET', 'POST'])
@login_required
@admin_required
def schedule_create():
    url_back = request.args.get('next',
                                url_for('schedules_table', **request.args))
    form = ScheduleForm()
    if form.validate_on_submit():
        schedule = Schedule(cid=current_user.cid,
                            name=form.name.data)
        db.session.add(schedule)
        db.session.commit()
        return redirect(url_for('schedule_edit', id=schedule.id, **request.args))
    return render_template('schedule_form.html',
                           title=_('Schedule (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/schedules/edit/<id>', methods=['GET', 'POST'])
@login_required
@admin_required
def schedule_edit(id):
    next_page = request.args.get('next')
    if not next_page or url_parse(next_page).netloc != '':
        next_page = url_for('schedules_table', **request.args)
    url_back = next_page
    schedule = Schedule.get_object(id)
    param_filter = {'schedule_id': schedule.id}
    days = ScheduleDay.get_items(data_filter=param_filter)
    form = ScheduleForm()
    if form.validate_on_submit():
        schedule.name = form.name.data
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form = ScheduleForm(obj=schedule)
    return render_template('schedule_form.html',
                           title=_('Schedule (edit)'),
                           form=form,
                           schedule=schedule,
                           days=days,
                           url_back=url_back)


@app.route('/schedules/reset/<id>', methods=['GET', 'POST'])
@login_required
@admin_required
@confirm(_l('Reset schedule to default?'))
def schedule_reset(id):
    schedule = Schedule.get_object(id)
    schedule.complete_weekday()
    db.session.commit()
    return redirect(url_for('schedule_edit', id=id))


# noinspection PyTypeChecker
@app.route('/schedules/<schedule_id>/schedule_days/')
@login_required
@admin_required
def schedule_days_table(schedule_id):
    page = request.args.get('page', 1, type=int)
    form = set_filter(ScheduleDay)
    param = get_filter_parameters(form, ScheduleDay)
    param_filter = {**param[0], **{'schedule_id': schedule_id}}
    param_search = param[1]
    data = ScheduleDay.get_pagination(page, param_filter, param_search)
    return render_template('schedule_days_table.html',
                           title=_('Schedule_days'),
                           items=data.items,
                           pagination=data,
                           schedule_id=schedule_id,
                           form=form)


@app.route('/schedules/<schedule_id>/schedule_days/create', methods=['GET', 'POST'])
@login_required
@admin_required
def schedule_day_create(schedule_id):
    url_back = url_for('schedule_days_table', schedule_id=schedule_id,
                       **request.args)
    schedule = Schedule.get_object(schedule_id)
    form = ScheduleDayForm(schedule=schedule)
    if form.validate_on_submit():
        schedule_day = ScheduleDay(cid=current_user.cid,
                                   schedule_id=schedule.id,
                                   day_number=form.weekday.data,
                                   hour_from=form.hour_from.data,
                                   hour_to=form.hour_to.data)
        db.session.add(schedule_day)
        db.session.commit()
        return redirect(url_back)
    return render_template('data_form.html',
                           title=_('Schedule day (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/schedules/<schedule_id>/schedule_days/edit/<id>', methods=['GET', 'POST'])
@login_required
@admin_required
def schedule_day_edit(schedule_id, id):
    url_back = request.args.get('url_back', url_for('schedule_days_table',
                                                    schedule_id=schedule_id,
                                                    **request.args))
    schedule = Schedule.get_object(schedule_id)
    param = {'schedule_id': schedule.id, 'id': id}
    schedule_day = ScheduleDay.find_object(param, True)
    form = ScheduleDayForm(schedule=schedule, schedule_day=schedule_day)
    if form.validate_on_submit():
        schedule_day.day_number = form.weekday.data
        schedule_day.hour_from = form.hour_from.data
        schedule_day.hour_to = form.hour_to.data
        schedule_day.holiday = form.holiday.data
        if form.holiday.data:
            schedule_day.hour_from = schedule_day.hour_to = time()
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form.weekday.default = schedule_day.day_number
        form.process()
        form.hour_from.data = schedule_day.hour_from
        form.hour_to.data = schedule_day.hour_to
        form.holiday.data = schedule_day.holiday
    return render_template('data_form.html',
                           title=_('Schedule day (edit)'),
                           form=form,
                           url_back=url_back)
# Schedule block end


# Client block start
# noinspection PyTypeChecker
@app.route('/clients/')
@login_required
def clients_table():
    page = request.args.get('page', 1, type=int)
    form = set_filter(Client)
    param = get_filter_parameters(form, Client)
    data = Client.get_pagination(page, *param)
    url_back = request.args.get('url_back')
    choice_mode = request.args.get('choice_mode', None, type=int)
    if choice_mode:
        template = 'client_table_choice.html'
    else:
        template = 'client_table.html'
    return render_template(template,
                           title=_('Clients'),
                           items=data.items,
                           pagination=data,
                           url_back=url_back,
                           form=form)


@app.route('/clients/create/', methods=['GET', 'POST'])
@login_required
def client_create():
    url_back = request.args.get('url_back',
                                url_for('clients_table', **request.args))
    form = ClientForm()
    if request.method == 'POST':
        form.phone.data = phone_number_plus(form.phone.data)
    if form.validate_on_submit():
        client = Client(cid=current_user.cid,
                        name=form.name.data,
                        phone=form.phone.data,
                        birthday=form.birthday.data,
                        info=form.info.data)
        db.session.add(client)
        db.session.commit()
        if request.args.get('choice_mode', 0, type=int):
            session['client'] = client.id
            return redirect(url_back)
        else:
            return redirect(url_for('clients_table'))
    return render_template('data_form.html',
                           title=_('Client (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/clients/edit/<id>/', methods=['GET', 'POST'])
@login_required
def client_edit(id):
    url_back = url_for('clients_table', **request.args)
    client = Client.get_object(id)
    form = ClientForm(client.phone)
    if request.method == 'POST':
        form.phone.data = phone_number_plus(form.phone.data)
    if form.validate_on_submit():
        client.name = form.name.data
        client.phone = form.phone.data
        client.birthday = form.birthday.data
        client.info = form.info.data
        db.session.commit()
        return redirect(url_for('clients_table'))
    elif request.method == 'GET':
        form = ClientForm(obj=client)
        form.tag_link.data = url_for('client_tags', client_id=client.id)
        # form.files_link.data = url_for('client_files_table', client_id=client.id)
    return render_template('data_form.html',
                           title=_('Client (edit)'),
                           form=form,
                           url_back=url_back)


# noinspection PyTypeChecker
@app.route('/clients/<client_id>/files/', methods=['GET', 'POST'])
@login_required
def client_files_table(client_id):
    page = request.args.get('page', 1, type=int)
    form = set_filter(ClientFile)
    param = get_filter_parameters(form, ClientFile)
    param_filter = {**param[0], **{'client_id': client_id}}
    param_search = param[1]
    data = ClientFile.get_pagination(page, param_filter, param_search)
    return render_template('client_files_table.html',
                           client_id=client_id,
                           title=_('Files'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/clients/<client_id>/upload_file/', methods=['GET', 'POST'])
@login_required
def client_file_upload(client_id):
    url_back = url_for('client_files_table', client_id=client_id, **request.args)
    client = Client.get_object(client_id)
    if not client:
        return redirect(url_back)
    form = ClientFileForm()
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No selected file')
            return redirect(url_for('client_file_upload', client_id=client_id))
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(url_for('client_file_upload', client_id=client_id))
        if not allowed_file_ext(file.filename):
            flash('Unauthorized file extension')
            return redirect(url_for('client_file_upload', client_id=client_id))
        directory = os.path.join(app.config['UPLOAD_FOLDER'],
                                 str(current_user.cid))
        if not os.path.exists(directory):
            os.mkdir(directory)
        path = os.path.join(directory, str(uuid.uuid4()))
        if not os.path.exists(directory):
            os.makedirs(directory)
        file.save(path)
        with open(path, 'rb') as f:
            hash_file = hashlib.sha1(f.read()).hexdigest()
        client_file = ClientFile(cid=current_user.cid,
                                 client_id=client_id,
                                 name=file.filename,
                                 path=path,
                                 hash=hash_file)
        db.session.add(client_file)
        db.session.commit()
        return redirect(url_back)
    return render_template('upload_form.html',
                           title=_('File upload'),
                           form=form,
                           url_back=url_back)


@app.route('/clients/<client_id>/download_file/<id>/')
@login_required
def client_file_download(client_id, id):
    param = {'id': id, 'client_id': client_id}
    file = ClientFile.find_object(param, True)
    return send_file(file.path, as_attachment=True, download_name=file.name)


@app.route('/clients/<client_id>/tags/', methods=['GET', 'POST'])
@login_required
def client_tags(client_id):
    url_back = url_for('client_edit', id=client_id, **request.args)
    form = ClientTagForm()
    tag_list = Tag.get_items(True)
    if len(tag_list) > 0 and type(tag_list[0]) == tuple and tag_list[0][0] == 0:
        tag_list.pop(0)
    form.tags.choices = tag_list
    client = Client.get_object(client_id)
    if form.validate_on_submit():
        client.tags.clear()
        for tag_id in form.tags.data:
            tag = Tag.get_object(tag_id)
            client.add_tag(tag)
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form.tags.default = [x.id for x in client.tags]
        form.process()
    return render_template('data_form.html',
                           title=_('Tags'),
                           form=form,
                           url_back=url_back)
# Client block end


# Tag block start
# noinspection PyTypeChecker
@app.route('/tags/')
@login_required
@admin_required
def tags_table():
    page = request.args.get('page', 1, type=int)
    form = set_filter(Tag)
    param = get_filter_parameters(form, Tag)
    data = Tag.get_pagination(page, *param)
    return render_template('tags_table.html',
                           id=id,
                           title=_('Tags'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/tags/create/', methods=['GET', 'POST'])
@login_required
@admin_required
def tag_create():
    url_back = url_for('tags_table', **request.args)
    form = TagForm()
    if form.validate_on_submit():
        tag = Tag(cid=current_user.cid,
                  name=form.name.data)
        db.session.add(tag)
        db.session.commit()
        return redirect(url_back)
    return render_template('data_form.html',
                           title=_('Tag (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/tags/edit/<id>/', methods=['GET', 'POST'])
@login_required
@admin_required
def tag_edit(id):
    url_back = url_for('tags_table', **request.args)
    tag = Tag.get_object(id)
    form = TagForm()
    if form.validate_on_submit():
        tag.name = form.name.data
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form = TagForm(obj=tag)
    return render_template('data_form.html',
                           title=_('Tag (edit)'),
                           form=form,
                           url_back=url_back)
# Tag block end


# Service block start
# noinspection PyTypeChecker
@app.route('/services/', methods=['GET', 'POST'])
@login_required
def services_table():
    page = request.args.get('page', 1, type=int)
    appointment_id = request.args.get('appointment_id', None, type=int)
    url_back = request.args.get('url_back', url_for('appointments_table'))
    if 'edit' in url_back:
        url_submit = url_for('appointment_edit', id=appointment_id,
                             mod_services=1)
    else:
        url_submit = url_for('appointment_create', **request.args)
    choice_mode = request.args.get('choice_mode', None, type=int)
    if choice_mode:
        template = 'service_table_choice.html'
        url_back = url_for('appointments_table')
    else:
        template = 'service_table.html'
    form = set_filter(Service)
    param = get_filter_parameters(form, Service)
    data = Service.get_pagination(page, *param)
    return render_template(template,
                           title=_('Services'),
                           items=data.items,
                           pagination=data,
                           url_back=url_back,
                           url_submit=url_submit,
                           appointment_id=appointment_id,
                           form=form)


@app.route('/services/create/', methods=['GET', 'POST'])
@login_required
@admin_required
def service_create():
    url_back = request.args.get('next',
                                url_for('services_table', **request.args))
    next_page = request.args.get('next')
    if not next_page or url_parse(next_page).netloc != '':
        next_page = url_for('services_table')
    form = ServiceForm()
    location_list = Location.get_items(True)
    if (len(location_list) > 0 and type(location_list[0]) == tuple and
            location_list[0][0] == 0):
        location_list.pop(0)
    form.location.choices = location_list
    if form.validate_on_submit():
        service = Service(cid=current_user.cid,
                          name=form.name.data,
                          duration=form.duration.data,
                          price=form.price.data,
                          repeat=form.repeat.data)
        db.session.add(service)
        db.session.flush()
        for location_id in form.location.data:
            location = Location.get_object(location_id)
            location.add_service(service)
        db.session.commit()
        return redirect(next_page)
    elif request.method == 'GET':
        form.duration.data = CompanyConfig.get_parameter('min_time_interval')
        form.location.data = list([lc.id for lc in current_user.company.locations])
    return render_template('data_form.html',
                           title=_('Service (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/services/edit/<id>/', methods=['GET', 'POST'])
@login_required
@admin_required
def service_edit(id):
    url_back = url_for('services_table', **request.args)
    form = ServiceForm()
    location_list = Location.get_items(True)
    if (len(location_list) > 0 and type(location_list[0]) == tuple and
            location_list[0][0] == 0):
        location_list.pop(0)
    form.location.choices = location_list
    service = Service.get_object(id)
    if form.validate_on_submit():
        service.name = form.name.data
        service.duration = form.duration.data
        service.price = form.price.data
        service.repeat = form.repeat.data
        service.locations.clear()
        for location_id in form.location.data:
            location = Location.get_object(location_id)
            location.add_service(service)
        db.session.commit()
        return redirect(url_for('services_table'))
    elif request.method == 'GET':
        form.location.default = [s.id for s in service.locations]
        form.process()
        form.name.data = service.name
        form.duration.data = service.duration
        form.price.data = service.price
        form.repeat.data = service.repeat
    return render_template('data_form.html',
                           title=_('Service (edit)'),
                           form=form,
                           url_back=url_back)
# Service block end


# Location block start
# noinspection PyTypeChecker
@app.route('/locations/')
@login_required
@admin_required
def locations_table():
    page = request.args.get('page', 1, type=int)
    form = set_filter(Location)
    param = get_filter_parameters(form, Location)
    data = Location.get_pagination(page, *param)
    return render_template('location_table.html',
                           title=_('Locations'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/locations/create/', methods=['GET', 'POST'])
@login_required
@admin_required
@check_limit(Location)
def location_create():
    url_back = request.args.get('next',
                                url_for('locations_table', **request.args))
    next_page = request.args.get('next')
    if not next_page or url_parse(next_page).netloc != '':
        next_page = url_for('locations_table')
    form = LocationFormCreate()
    form.schedule.choices = Schedule.get_items(True)
    if request.method == 'POST':
        form.phone.data = phone_number_plus(form.phone.data)
    if form.validate_on_submit():
        location = Location(cid=current_user.cid,
                            name=form.name.data,
                            phone=form.phone.data,
                            address=form.address.data)
        db.session.add(location)
        if form.schedule.data:
            db.session.flush()
            schedule = Schedule.get_object(form.schedule.data)
            location.schedules.append(schedule)
        db.session.commit()
        return redirect(next_page)
    return render_template('data_form.html',
                           title=_('Location (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/locations/edit/<id>/', methods=['GET', 'POST'])
@login_required
@admin_required
def location_edit(id):
    url_back = url_for('locations_table', **request.args)
    location = Location.get_object(id)
    form = LocationForm(location.phone)
    form.schedule.choices = Schedule.get_items(True)
    if request.method == 'POST':
        form.phone.data = phone_number_plus(form.phone.data)
    if form.validate_on_submit():
        location.name = form.name.data
        location.phone = form.phone.data
        location.address = form.address.data
        if form.schedule.data:
            schedule = Schedule.get_object(form.schedule.data)
            location.schedules.clear()
            location.schedules.append(schedule)
        else:
            location.schedules.clear()
        db.session.commit()
        return redirect(url_for('locations_table'))
    elif request.method == 'GET':
        if location.main_schedule:
            form.schedule.default = location.main_schedule.id
            form.process()
        form.name.data = location.name
        form.address.data = location.address
        form.phone.data = location.phone
        url_back_confirm = url_for('location_edit', id=id)
        form.add_services.data = url_for('location_add_all_services',
                                         id=id,
                                         url_back=url_back_confirm)
        form.delete_services.data = url_for('location_delete_all_services',
                                            id=id,
                                            url_back=url_back_confirm)
    return render_template('data_form.html',
                           title=_('Location (edit)'),
                           form=form,
                           url_back=url_back)


@app.route('/locations/add_all_services/<id>/', methods=['GET', 'POST'])
@login_required
@admin_required
@confirm(_l('Add all services?'))
def location_add_all_services(id):
    url_back = url_for('location_edit', id=id)
    location = Location.get_object(id)
    services = Service.get_items()
    for service in services:
        location.services.append(service)
    db.session.commit()
    return redirect(url_back)


@app.route('/locations/delete_all_services/<id>/', methods=['GET', 'POST'])
@login_required
@admin_required
@confirm(_l('Delete all services?'))
def location_delete_all_services(id):
    url_back = url_for('location_edit', id=id)
    location = Location.get_object(id)
    location.services.clear()
    db.session.commit()
    db.session.commit()
    return redirect(url_back)
# Location block end


# Appointment block start
# noinspection PyTypeChecker
@app.route('/appointments/assistant/', methods=['GET', 'POST'])
@login_required
def appointment_assistant():
    if not current_user.company.check_start_config():
        return redirect(url_for('quick_start'))
    offset = request.args.get('offset', 0, type=int)
    form = set_filter(Assistant)
    param = get_filter_parameters(form, Assistant)[0]
    clear_session()
    first_day = (datetime(datetime.now().year, datetime.now().month, 1).date() +
                 relativedelta(months=offset))
    calendar = get_calendar(days=42, data_filter=param, day_start=first_day)
    n_holidays = NationalHoliday.get_month_holidays(first_day.year, first_day.month)

    return render_template('assistant.html',
                           calendar=calendar,
                           holidays=n_holidays,
                           month=first_day,
                           form=form)


# noinspection PyTypeChecker
@app.route('/appointments/')
@login_required
def appointments_table():
    clear_session()
    page = request.args.get('page', 1, type=int)
    form = set_filter(Appointment)
    param = get_filter_parameters(form, Appointment)
    data = Appointment.get_pagination(page, *param)
    return render_template('timetable_card.html',
                           title=_('Timetable'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/appointments/create/', methods=['GET', 'POST'])
@login_required
def appointment_create():
    url_back = url_for('appointments_table', **request.args)
    url_select_service = url_for('services_table',
                                 choice_mode=1,
                                 url_back=request.path)
    url_select_client = url_for('clients_table',
                                choice_mode=1,
                                url_back=request.path)
    selected_services_id = session.get('services')
    selected_location_id = session.get('location')
    selected_staff_id = session.get('staff')
    selected_client_id = session.get('client')
    if request.args.get('date'):
        session['date'] = request.args.get('date')
    selected_date = session.get('date')
    selected_time = session.get('time')
    form = AppointmentForm()
    if selected_time:
        form.time.choices = (selected_time, selected_time)
    form.location.choices = Location.get_items(True)
    form.staff.choices = Staff.get_items(True)
    form.client.choices = Client.get_items(True)
    selected_services = []
    if selected_services_id:
        form.duration.data = get_duration(selected_services_id)
        for service_id in selected_services_id:
            service = Service.get_object(service_id)
            selected_services.append(service)
        form.services.data = ','.join(list(str(s) for s in selected_services_id))
    if form.validate_on_submit():
        time = datetime.strptime(form.time.data, '%H:%M').time()
        appointment = Appointment(cid=current_user.cid,
                                  location_id=form.location.data,
                                  date_time=datetime(form.date.data.year,
                                                     form.date.data.month,
                                                     form.date.data.day,
                                                     time.hour,
                                                     time.minute),
                                  client_id=form.client.data,
                                  staff_id=form.staff.data,
                                  no_check_duration=form.no_check_duration.data,
                                  allow_booking_this_time=form.allow_booking_this_time.data,
                                  info=form.info.data)
        db.session.add(appointment)
        db.session.flush()
        for service in selected_services:
            appointment.add_service(service)
        db.session.commit()
        clear_session()
        return redirect(url_for('appointments_table'))
    elif request.method == 'GET':
        if selected_location_id:
            form.location.default = selected_location_id
        if selected_staff_id:
            form.staff.default = selected_staff_id
        if selected_client_id:
            form.client.default = selected_client_id
        if selected_time:
            form.time.default = selected_time
        form.process()
        if selected_date:
            form.date.data = datetime.strptime(selected_date, '%Y-%m-%d')
    return render_template('appointment_form.html',
                           title=_('Appointment (create)'),
                           form=form,
                           items=selected_services,
                           url_back=url_back,
                           url_select_service=url_select_service,
                           url_select_client=url_select_client)


@app.route('/appointments/edit/<id>/', methods=['GET', 'POST'])
@login_required
def appointment_edit(id):
    appointment = Appointment.get_object(id)
    param_url = {**request.args}
    param_url.pop('mod_services', None)
    url_back = request.args.get('url_back', url_for('appointments_table', **param_url))
    mod_services = request.args.get('mod_services', None)
    if not mod_services:
        session.pop('services', None)
        session['services'] = [str(s.id) for s in appointment.services]
    selected_services_id = session.get('services')
    url_select_service = url_for('services_table',
                                 choice_mode=1,
                                 appointment_id=id,
                                 url_back=request.path)
    url_select_client = url_for('clients_table',
                                choice_mode=1,
                                url_back=request.path)
    selected_services = []
    for service_id in selected_services_id:
        service = Service.get_object(service_id)
        selected_services.append(service)
    selected_services.sort(key=lambda x: x.name)
    selected_location_id = session.get('location')
    selected_staff_id = session.get('staff')
    selected_client_id = session.get('client')
    selected_date = session.get('date')
    selected_time = session.get('time')
    form = AppointmentForm(appointment)
    form.duration.data = get_duration(selected_services_id)
    form.location.choices = Location.get_items(True)
    form.staff.choices = Staff.get_items(True)
    form.client.choices = Client.get_items(True)
    current_time = appointment.date_time.time().strftime('%H:%M')
    form.services.data = ','.join(list(str(s) for s in selected_services_id))
    if form.validate_on_submit():
        time = datetime.strptime(form.time.data, '%H:%M').time()
        appointment.location_id = form.location.data
        appointment.date_time = datetime(form.date.data.year,
                                         form.date.data.month,
                                         form.date.data.day,
                                         time.hour,
                                         time.minute)
        appointment.client_id = form.client.data
        appointment.staff_id = form.staff.data
        appointment.no_check_duration = form.no_check_duration.data
        appointment.allow_booking_this_time = form.allow_booking_this_time.data
        appointment.info = form.info.data
        appointment.services.clear()
        for service in selected_services:
            appointment.add_service(service)
        db.session.commit()
        clear_session()
        return redirect(url_back)
    elif request.method == 'GET':
        if selected_location_id:
            form.location.default = selected_location_id
        else:
            form.location.default = appointment.location_id
        if selected_staff_id:
            form.staff.default = selected_staff_id
        else:
            form.staff.default = appointment.staff_id
        if selected_client_id:
            form.client.default = selected_client_id
        else:
            form.client.default = appointment.client_id
        if selected_time:
            form.time.choices = (selected_time, selected_time)
            form.time.default = selected_time
        else:
            form.time.choices = (current_time, current_time)
            form.time.default = current_time
        form.process()
        if selected_date:
            form.date.data = datetime.strptime(selected_date, '%Y-%m-%d')
        else:
            form.date.data = appointment.date_time.date()
        form.no_check_duration.data = appointment.no_check_duration
        form.allow_booking_this_time.data = appointment.allow_booking_this_time
        form.info.data = appointment.info
    return render_template('appointment_form.html',
                           title=_('Appointment (edit)'),
                           form=form,
                           appointment_id=id,
                           payment_id=appointment.payment_id,
                           items=selected_services,
                           url_select_service=url_select_service,
                           url_select_client=url_select_client,
                           url_back=url_back)


@app.route('/appointments/<appointment_id>/result/', methods=['GET', 'POST'])
@login_required
def appointment_result(appointment_id):
    url_back = request.args.get('url_back', url_for('appointments_table', **request.args))
    appointment = Appointment.get_object(appointment_id)
    form = ResultForm()
    if form.validate_on_submit():
        appointment.result = form.result.data
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form.result.data = appointment.result
    return render_template('data_form.html',
                           title=_('Result'),
                           form=form,
                           url_back=url_back)


@app.route('/appointments/<appointment_id>/receipt/', methods=['GET', 'POST'])
@login_required
def appointment_receipt(appointment_id):
    url_back = request.args.get('url_back', url_for('appointments_table',
                                                    **request.args))
    appointment = Appointment.get_object(appointment_id)
    payment = CashFlow.get_object(appointment.payment_id, False)
    link = str(request.host + url_for('payment_receipt', link=payment.link))
    qr_data = qrcode.make(link)
    buffer = BytesIO()
    qr_data.save(buffer)
    buffer.seek(0)
    qr_code = b64encode(buffer.read()).decode()
    if not payment:
        return redirect(url_back)
    form = ReceiptForm()
    if form.validate_on_submit():
        return redirect(url_back)
    elif request.method == 'GET':
        form.link.data = url_for('payment_receipt', link=payment.link)
    return render_template('receipt_form.html',
                           title=_('Payment receipt'),
                           form=form,
                           qr_code=qr_code,
                           url_back=url_back)
# Appointment block end


# Item block start
# noinspection PyTypeChecker
@app.route('/items/')
@login_required
def items_table():
    page = request.args.get('page', 1, type=int)
    form = set_filter(Item)
    param = get_filter_parameters(form, Item)
    data = Item.get_pagination(page, *param)
    return render_template('item_table.html',
                           title=_('Items'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/items/create', methods=['GET', 'POST'])
@login_required
def item_create():
    url_back = url_for('items_table', **request.args)
    form = ItemForm()
    if form.validate_on_submit():
        item = Item(cid=current_user.cid,
                    name=form.name.data,
                    description=form.description.data)
        db.session.add(item)
        db.session.commit()
        return redirect(url_back)
    return render_template('data_form.html',
                           title=_('Item (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/items/edit/<id>', methods=['GET', 'POST'])
@login_required
def item_edit(id):
    url_back = url_for('items_table', **request.args)
    item = Item.get_object(id)
    form = ItemForm()
    if form.validate_on_submit():
        item.name = form.name.data
        item.description = form.description.data
        db.session.commit()
        return redirect(url_back)
    else:
        form = ItemForm(obj=item)
    return render_template('data_form.html',
                           title=_('Item (edit)'),
                           form=form,
                           url_back=url_back)
# Item block end


# ItemFlow block start
# noinspection PyTypeChecker
@app.route('/items_flow/')
@login_required
def items_flow_table():
    page = request.args.get('page', 1, type=int)
    form = set_filter(ItemFlow)
    param = get_filter_parameters(form, ItemFlow)
    data = ItemFlow.get_pagination(page, *param)
    return render_template('item_flow_table.html',
                           title=_('Items flow'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/items_flow/create', methods=['GET', 'POST'])
@login_required
def item_flow_create():
    url_back = url_for('items_flow_table', **request.args)
    item_id = request.args.get('item_id')
    form = ItemFlowForm()
    form.location.choices = Location.get_items(True)
    form.item.choices = Item.get_items(True)
    if form.validate_on_submit():
        item_flow = ItemFlow(cid=current_user.cid,
                             location_id=form.location.data,
                             date=form.date.data,
                             item_id=form.item.data,
                             quantity=form.quantity.data * form.action.data)
        db.session.add(item_flow)
        param = {'location_id': form.location.data, 'item_id': form.item.data}
        storage = Storage.find_object(param)
        if storage:
            storage.quantity += form.quantity.data * form.action.data
        else:
            storage = Storage(cid=current_user.cid,
                              location_id=form.location.data,
                              item_id=form.item.data,
                              quantity=form.quantity.data * form.action.data)
            db.session.add(storage)
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form.item.default = item_id
        form.process()
        form.date.data = datetime.now().date()
    return render_template('data_form.html',
                           title=_('Item flow (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/items_flow/edit/<id>', methods=['GET', 'POST'])
@login_required
def item_flow_edit(id):
    url_back = url_for('items_flow_table', **request.args)
    item_flow = ItemFlow.get_object(id)
    form = ItemFlowForm(item_flow.location_id,
                        item_flow.item_id,
                        item_flow.quantity)
    form.location.choices = Location.get_items(True)
    form.item.choices = Item.get_items(True)
    if form.validate_on_submit():
        current_location = item_flow.location_id
        current_item = item_flow.item_id
        current_quantity = item_flow.quantity
        item_flow.location_id = form.location.data
        item_flow.date = form.date.data
        item_flow.item_id = form.item.data
        item_flow.quantity = form.quantity.data * form.action.data
        param = {'location_id': current_location, 'item_id': current_item}
        current_storage = Storage.find_object(param, True)
        current_storage.quantity -= current_quantity
        param = {'location_id': form.location.data, 'item_id': form.item.data}
        storage = Storage.find_object(param)
        if storage:
            storage.quantity += form.quantity.data * form.action.data
        else:
            storage = Storage(cid=current_user.cid,
                              location_id=form.location.data,
                              item_id=form.item.data,
                              quantity=form.quantity.data * form.action.data)
            db.session.add(storage)
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form.location.default = item_flow.location_id
        form.item.default = item_flow.item_id
        form.process()
        form.date.data = item_flow.date
        form.quantity.data = abs(item_flow.quantity)
        form.action.data = item_flow.quantity / abs(item_flow.quantity)
    return render_template('data_form.html',
                           title=_('Item flow (edit)'),
                           form=form,
                           url_back=url_back)
# ItemFlow block end


# Notice block start
# noinspection PyTypeChecker
@app.route('/notices/')
@login_required
def notices_table():
    clear_session()
    page = request.args.get('page', 1, type=int)
    form = set_filter(Notice)
    param = get_filter_parameters(form, Notice)
    data = Notice.get_pagination(page, *param)
    return render_template('notice_table.html',
                           title=_('Notices'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/notices/create/', methods=['GET', 'POST'])
@login_required
def notice_create():
    url_back = request.args.get('url_back', url_for('notices_table', **request.args))
    client_id = request.args.get('client_id', None)
    selected_client_id = session.get('client')
    appointment_id = request.args.get('appointment_id', None)
    appointment = Appointment.get_object(appointment_id, False)
    form = NoticeForm()
    form.processed.render_kw = {'disabled': ''}
    form.client.choices = Client.get_items(True)
    url_select_client = url_for('clients_table',
                                choice_mode=1,
                                url_back=request.path)
    if form.validate_on_submit():
        notice = Notice(cid=current_user.cid,
                        client_id=form.client.data,
                        date=form.date.data,
                        description=form.description.data)
        db.session.add(notice)
        db.session.commit()
        session.pop('notices_count', None)
        return redirect(url_back)
    elif request.method == 'GET':
        if client_id:
            form.client.default = client_id
            form.process()
        if selected_client_id:
            form.client.default = selected_client_id
            form.process()
        if appointment:
            if appointment.date_repeat:
                form.date.data = max(appointment.date_repeat,
                                     datetime.now().date())
            previous_visit = appointment.date_time.date().strftime('%d.%m.%Y')
            form.description.data = _('*Previous visit') + ' ' + previous_visit
        form.date.data = datetime.now().date()
    return render_template('notice_form.html',
                           title=_('Notice (create)'),
                           form=form,
                           url_back=url_back,
                           url_select_client=url_select_client)


@app.route('/notices/edit/<id>/', methods=['GET', 'POST'])
@login_required
def notice_edit(id):
    url_back = request.args.get('url_back', url_for('notices_table',
                                                    **request.args))
    notice = Notice.get_object(id)
    form = NoticeForm()
    form.client.choices = Client.get_items(True)
    selected_client_id = session.get('client')
    url_select_client = url_for('clients_table',
                                choice_mode=1,
                                url_back=request.path)
    if form.validate_on_submit():
        notice.client_id = form.client.data
        notice.date = form.date.data
        notice.description = form.description.data
        notice.processed = form.processed.data
        db.session.commit()
        session.pop('notices_count', None)
        return redirect(url_back)
    elif request.method == 'GET':
        form.client.default = notice.client_id
        if selected_client_id:
            form.client.default = selected_client_id
        form.process()
        form.date.data = notice.date
        form.description.data = notice.description
        form.processed.data = notice.processed
    return render_template('notice_form.html',
                           title=_('Notice (edit)'),
                           form=form,
                           url_back=url_back,
                           url_select_client=url_select_client,
                           client=notice.client)
# Notice block end


# CashFlow block start
# noinspection PyTypeChecker
@app.route('/cash_table/')
@login_required
@admin_required
def cash_table():
    page = request.args.get('page', 1, type=int)
    form = set_filter(Cash)
    param = get_filter_parameters(form, Cash)
    data = Cash.get_pagination(page, *param)
    return render_template('cash_table.html',
                           title=_('Cash desk'),
                           items=data.items,
                           pagination=data,
                           form=form)


# noinspection PyTypeChecker
@app.route('/cash_flow/')
@login_required
@admin_required
def cash_flow_table():
    page = request.args.get('page', 1, type=int)
    form = set_filter(CashFlow)
    param = get_filter_parameters(form, CashFlow)
    data = CashFlow.get_pagination(page, *param)
    return render_template('cash_flow_table.html',
                           title=_('Cash desk'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/cash_flow/create', methods=['GET', 'POST'])
@login_required
def cash_flow_create():
    url_back = request.args.get('url_back', url_for('cash_flow_table',
                                                    **request.args))
    appointment_id = request.args.get('appointment_id')
    appointment = Appointment.get_object(appointment_id, False)
    if appointment and appointment.payment_id:
        return redirect(url_for('cash_flow_edit', id=appointment.payment_id,
                                **request.args))
    form = CashFlowForm()
    form.location.choices = Location.get_items(True)
    form.payment_method.choices = PaymentMethod.get_items(True)
    form.cost.render_kw = {'type': 'number'}
    if form.validate_on_submit():
        cash_flow = CashFlow(cid=current_user.cid,
                             location_id=form.location.data,
                             date=form.date.data,
                             description=form.description.data,
                             cost=form.cost.data * form.action.data,
                             payment_method_id=form.payment_method.data)
        db.session.add(cash_flow)
        param = {'location_id': form.location.data}
        cash = Cash.find_object(param)
        if cash:
            cash.cost += form.cost.data * form.action.data
        else:
            cash = Cash(cid=current_user.cid,
                        location_id=form.location.data,
                        cost=form.cost.data * form.action.data)
            db.session.add(cash)
        if appointment:
            appointment.payment_id = cash_flow.id
        if cash.cost < 0:
            db.session.rollback()
            flash(_('Amount exceeds the balance in the cash box'))
        else:
            db.session.commit()
            return redirect(url_back)
    elif request.method == 'GET':
        if appointment:
            location_id = appointment.location_id
            description = ' '.join((_('#Payment for services'),
                                    appointment.date_time.strftime('%d.%m.%Y %H:%M')))
            date = appointment.date_time.date()
            cost = appointment.cost
            form.location.default = location_id
            form.process()
            form.date.data = date
            form.cost.data = cost
            form.description.data = description
        else:
            form.date.data = datetime.now().date()
    return render_template('data_form.html',
                           title=_('Cash flow (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/cash_flow/edit/<id>', methods=['GET', 'POST'])
@login_required
def cash_flow_edit(id):
    url_back = request.args.get('url_back', url_for('cash_flow_table',
                                                    **request.args))
    cash_flow = CashFlow.get_object(id)
    form = CashFlowForm()
    form.cost.render_kw = {'type': 'number'}
    form.location.choices = Location.get_items(True)
    form.payment_method.choices = PaymentMethod.get_items(True)
    info_msg = ''
    if form.validate_on_submit():
        current_location = cash_flow.location_id
        current_cost = cash_flow.cost
        cash_flow.location_id = form.location.data
        cash_flow.description = form.description.data
        cash_flow.date = form.date.data
        cash_flow.cost = form.cost.data * form.action.data
        param = {'location_id': current_location}
        current_cash = Cash.find_object(param, True)
        current_cash.cost -= current_cost
        cash_flow.payment_method_id = form.payment_method.data
        param = {'location_id': form.location.data}
        cash = Cash.find_object(param)
        if cash:
            cash.cost += form.cost.data * form.action.data
        else:
            cash = Cash(cid=current_user.cid,
                        location_id=form.location.data,
                        cost=form.cost.data * form.action.data)
            db.session.add(cash)
        if cash.cost < 0:
            db.session.rollback()
            flash(_('Amount exceeds the balance in the cash box'))
        else:
            db.session.commit()
            return redirect(url_back)
    elif request.method == 'GET':
        form.location.default = cash_flow.location_id
        form.payment_method.default = cash_flow.payment_method_id
        form.process()
        form.date.data = cash_flow.date
        form.description.data = cash_flow.description
        form.cost.data = abs(cash_flow.cost)
        if cash_flow.cost >= 0:
            form.action.data = 1
        else:
            form.action.data = -1
        if cash_flow.appointment:
            appointment_id = request.args.get('appointment_id', 1, type=int)
            if not appointment_id == cash_flow.appointment[0].id:
                form.submit.render_kw = {'disabled': ''}
                info_msg = _('Payment can be changed only through the appointment form')
                form.appointment_link.data = url_for('appointment_edit',
                                                     id=cash_flow.appointment[0].id,
                                                     url_back=request.path)
                form.appointment_link.label.text = (
                        _('Link to appointment') + ': ' +
                        cash_flow.appointment[0].date_time.strftime('%d.%m.%Y %H:%M'))
    return render_template('data_form.html',
                           title=_('Cash flow (edit)'),
                           form=form,
                           url_back=url_back,
                           info_msg=info_msg)


@app.route('/payment_receipt/')
def payment_receipt():
    link = request.args.get('link')
    payment = services = None
    if link:
        payment = CashFlow.find_object({'link': link}, overall=True)
    if payment:
        services = payment.appointment[0].services
    return render_template('receipt.html',
                           payment=payment,
                           services=services)

# CashFlow block end


# Report block start
@app.route('/report_statistics_view/', methods=['GET', 'POST'])
@login_required
@admin_required
def report_statistics_view():
    form = ReportForm()
    form.location.choices = Location.get_items(True)
    form.staff.choices = Staff.get_items(True)
    data = []
    if form.validate_on_submit():
        filter_param = {}
        if form.location.data:
            filter_param['location_id'] = form.location.data
        if form.staff.data:
            filter_param['staff_id'] = form.staff.data
        date_time_from = datetime(form.date_from.data.year,
                                  form.date_from.data.month,
                                  form.date_from.data.day,
                                  0, 0, 0)
        date_time_to = datetime(form.date_to.data.year,
                                form.date_to.data.month,
                                form.date_to.data.day,
                                23, 59, 59)
        search_param = [Appointment.date_time.between(date_time_from,
                                                      date_time_to)]
        data = Appointment.get_report_statistics(data_filter=filter_param,
                                                 data_search=search_param,
                                                 sort_mode='asc')
    elif request.method == 'GET':
        form.date_from.data = datetime.now().replace(day=1)
        form.date_to.data = datetime.now().date()
    return render_template('report_statistics_table.html',
                           title=_('Reports'),
                           form=form,
                           items=data)


@app.route('/dashboard_view/')
@login_required
@admin_required
def dashboard_view():
    users_count = len(User.query.all())
    services_count = len(Service.query.all())
    clients_count = len(Client.query.all())
    users_items = User.query.with_entities(
        func.date(User.timestamp_create),
        func.count(User.id)).group_by(func.date(User.timestamp_create)).all()
    users = {}
    u_count = 0
    for u in users_items:
        u_count += u[1]
        users[u[0]] = u_count
    return render_template('dashboard.html',
                           title='Dashboard',
                           users_count=users_count,
                           services_count=services_count,
                           clients_count=clients_count,
                           users=users)

# Report block end


@app.route('/select_service/<service_id>/<selected>/')
@login_required
def select_service(service_id, selected):
    services_id = session.get('services', [])
    if int(selected) == 1:
        if str(service_id) not in services_id:
            services_id.append(service_id)
    else:
        if str(service_id) in services_id:
            services_id.remove(str(service_id))
    session['services'] = services_id
    url_back = request.args.get('url_back')
    if url_back:
        return redirect(url_back)
    return jsonify(services_id)


@app.route('/select_location/<location_id>/')
@login_required
def select_location(location_id):
    session['location'] = location_id
    return jsonify('Ok')


@app.route('/select_staff/<staff_id>/')
@login_required
def select_staff(staff_id):
    session['staff'] = staff_id
    return jsonify('Ok')


@app.route('/select_client/<client_id>/')
@login_required
def select_client(client_id):
    session['client'] = client_id
    url_back = request.args.get('url_back')
    if url_back:
        return redirect(url_back)
    return jsonify('Ok')


@app.route('/select_date/<date>/')
@login_required
def select_date(date):
    session['date'] = date
    url_back = request.args.get('url_back')
    if url_back:
        return redirect(url_back)
    return jsonify('Ok')


@app.route('/select_time/<time>/')
@login_required
def select_time(time):
    session['time'] = time
    return jsonify('Ok')


@app.route('/get_services/')
@login_required
def get_services():
    return jsonify(session['services'])


@app.route('/get_intervals/<location_id>/<staff_id>/<date_string>/<appointment_id>/<no_check>/')
@login_required
def get_intervals(location_id, staff_id, date_string, appointment_id, no_check):
    timeslots = []
    try:
        date = datetime.strptime(date_string, '%Y-%m-%d')
    except ValueError:
        return jsonify(timeslots)
    current_time = None
    min_time_interval = timedelta(
        minutes=CompanyConfig.get_parameter('min_time_interval'))
    if no_check == 'true':
        duration = min_time_interval
    else:
        duration = get_duration(session.get('services', None))
    if int(appointment_id):
        intervals = get_free_time_intervals(
            int(location_id), date.date(),
            int(staff_id), duration, appointment_id)
        appointment = Appointment.get_object(appointment_id)
        current_time = appointment.date_time.time().strftime('%H:%M')
    else:
        intervals = get_free_time_intervals(
            int(location_id), date.date(),
            int(staff_id), duration)
    delta_config = CompanyConfig.get_parameter('min_time_interval')
    for interval in intervals:
        start = interval[0] + timedelta(minutes=4)
        start = start - timedelta(minutes=start.minute % delta_config,
                                  seconds=start.second,
                                  microseconds=start.microsecond)
        delta = timedelta(minutes=delta_config)
        timeslots.append(start.strftime('%H:%M'))
        while start < interval[1]:
            start = start + delta
            timeslots.append(start.strftime('%H:%M'))
    if current_time and current_time not in timeslots:
        timeslots.append(current_time)
    timeslots.sort()
    return jsonify(timeslots)


@app.route('/export/', methods=['GET', 'POST'])
@login_required
@admin_required
@confirm(_l('Export data to Excel?'))
def export():
    class_list = [Client, Staff, Appointment, Notice, CashFlow]
    directory = os.path.join(app.config['UPLOAD_FOLDER'],
                             str(current_user.cid), 'temp')
    if not os.path.exists(directory):
        os.makedirs(directory)
    zip_path = os.path.join(directory, 'export.zip')
    if os.path.exists(zip_path):
        os.remove(zip_path)
    for class_object in class_list:
        file_name = class_object.__name__ + '.xlsx'
        path = os.path.join(directory, file_name)
        items = class_object.get_items()
        ignore_list = {'id', 'no_active', 'timestamp_create',
                       'timestamp_update', 'cid', 'cancel', 'payment_id',
                       'no_check_duration', 'allow_booking_this_time', 'link',
                       'payment_method_id'}
        column_list = [get_attr_inspect(col.name, class_object) for col in
                       inspect(class_object).columns
                       if col.name not in ignore_list]
        df = pd.DataFrame([[getattr(item, get_attr_inspect(col.name,
                                                           class_object))
                            for col in inspect(class_object).columns
                            if col.name not in ignore_list] for item in items],
                          columns=column_list)
        file = ExcelWriter(path)
        df.to_excel(file, 'Sheet1', index=True, header=True)
        file.save()
        with zipfile.ZipFile(zip_path, mode='a') as archive:
            archive.write(file, arcname=file_name)
            os.remove(path)
    return render_template('export_link.html')


@app.route('/export_download/', methods=['GET', 'POST'])
@login_required
@admin_required
def export_download():
    directory = os.path.join(app.config['UPLOAD_FOLDER'],
                             str(current_user.cid), 'temp')
    zip_path = os.path.join(directory, 'export.zip')
    if os.path.exists(zip_path):
        return send_file(zip_path, as_attachment=True)
    flash(_('File not found'))
    return render_template('export_link.html')


@app.route('/quick_start/')
@login_required
def quick_start():
    check_list = [{'object': Schedule, 'title': _('Schedules'),
                   'create_link': 'schedule_create',
                   'description':
                       _('Necessary to create at least one schedule')},
                  {'object': Location, 'title': _('Locations'),
                   'create_link': 'location_create',
                   'description':
                       _('Necessary to create at least one location')},
                  {'object': Service, 'title': _('Services'),
                   'create_link': 'service_create',
                   'description':
                       _('Necessary to create at least one service')},
                  {'object': Staff, 'title': _('Staff'),
                   'create_link': 'staff_create',
                   'description':
                       _('Necessary to create at least one worker')}]
    progress = 0
    for cl in check_list:
        check = bool(cl['object'].get_items(False))
        cl['flag'] = check
        if check:
            progress += 1 / len(check_list) * 100
    if progress == 100:
        current_user.company.config.show_quick_start = False
        db.session.commit()
    return render_template('quick_start.html',
                           title=_('Quick start'),
                           check_list=check_list,
                           progress=progress)


@app.route('/change_theme/')
@login_required
def change_theme():
    current_theme = session.get('theme', 'dark')
    if current_theme == 'dark':
        session['theme'] = 'light'
    else:
        session['theme'] = 'dark'
    url_back = request.args.get('url_back')
    if url_back:
        return redirect(url_back)
    return redirect(url_for('index'))


@app.route('/price/')
@login_required
@admin_required
def price():
    items = Tariff.get_items(overall=True)
    return render_template('price.html',
                           title=_('Tariffs'),
                           plans=items)


@app.route('/select_tariff/<tariff_id>', methods=['GET', 'POST'])
@login_required
@admin_required
@confirm(_l('Change the tariff plan?'))
def select_tariff(tariff_id):
    tariff = Tariff.get_object(tariff_id, overall=True)
    if tariff.check_downgrade():
        cfg = current_user.company.config
        if cfg:
            cfg.tariff_id = tariff_id
            db.session.commit()
            session.pop('current_tariff', None)
            flash(_('Tariff plan successfully changed'), 'info')
    return redirect(url_for('price'))


# Admin views
@app.route('/inactive_accounts/', methods=['GET', 'POST'])
@login_required
@global_admin_required
def inactive_accounts():
    flag_send_mail = request.args.get('send_mail', 0, type=int)
    active_users = User.query.filter(User.timestamp_login.isnot(None))
    active_companies = []
    for user in active_users:
        if user.company not in active_companies:
            active_companies.append(user.company)
    inactive_users = User.query.filter(User.timestamp_login.is_(None))
    inactive_companies = []
    for user in inactive_users:
        if user.company not in inactive_companies and user.company not in active_companies:
            inactive_companies.append(user.company)
    if flag_send_mail == 1:
        with mail.connect() as conn:
            for company in inactive_companies:
                subject = _('Inactive account') + ' Jiiin'
                sender = app.config['MAIL_DEFAULT_SENDER']
                recipients = [company.admin_email]
                msg = Message(subject=subject,
                              sender=sender,
                              recipients=recipients)
                msg.body = render_template('inactive_account.txt',
                                           company=company.name)
                conn.send(msg)
    return render_template('delete_accounts.html',
                           items=inactive_companies)


@app.route('/delete_account_admin/<company_id>/', methods=['GET', 'POST'])
@login_required
@global_admin_required
@confirm(_l('Confirm deletion account'))
def delete_account_admin(company_id):
    url_back = request.args.get('url_back',
                                url_for('delete_inactive_accounts'))
    company = Company.get_object(id=company_id, overall=True)
    # db.session.delete(company)
    # db.session.commit()
    flash(_('Account successfully deleted'))
    return redirect(url_back)


@app.route('/get_hebrew_calendar/', methods=['GET', 'POST'])
@login_required
@global_admin_required
@confirm(_l('Complete calendar of national holidays?'))
def get_hebrew_calendar():
    year = request.args.get('year', None, type=str)
    month = request.args.get('month', None, type=str)
    url = 'https://www.hebcal.com/hebcal?v=1&cfg=json&maj=on&mod=on&min=off&i=on'
    if year:
        url += '&year=' + year
    else:
        url += '&year=now'
    if month:
        url += '&month=' + month
    json_data = json.load(urlopen(url))
    count = 0
    for item in json_data['items']:
        date = datetime.strptime(item['date'], '%Y-%m-%d').date()
        name = item['title']
        description = item['memo']
        data_filter = {'date': date, 'name': name}
        holidays = NationalHoliday.get_items(data_filter=data_filter,
                                             overall=True)
        if not holidays:
            n_holiday = NationalHoliday(date=date,
                                        name=name,
                                        description=description)
            db.session.add(n_holiday)
            db.session.flush()
            count += 1
    if count:
        db.session.commit()
    return redirect(url_for('index'))
