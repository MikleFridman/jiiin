from sqlalchemy.exc import IntegrityError

import app
import hashlib
import os.path
import uuid

from flask import render_template, redirect, url_for, request, jsonify, send_file, session
from flask_babel import _, lazy_gettext as _l
from flask_login import login_user, logout_user, login_required
from werkzeug.urls import url_parse

from app.forms import *
from app.functions import *
from app.models import *


def set_filter(class_object):
    search_list = []
    for search_attr, search_name, search_object in class_object.search:
        search_list.append(search_attr)
        if issubclass(search_object, Entity):
            choices = search_object.get_items(True)
            setattr(SearchForm, search_attr, SelectField(_l(search_name),
                                                         choices=[*choices],
                                                         coerce=int))
        elif issubclass(search_object, type(datetime.now())) or issubclass(
                search_object, Period):
            setattr(SearchForm, search_attr, DateField(_l(search_name)))
        else:
            setattr(SearchForm, search_attr, StringField(_l(search_name)))
    rest_args = list(set(request.args.keys()).difference(set(search_list)))
    rest_args_dict = {}
    for ra in rest_args:
        setattr(SearchForm, ra, HiddenField(ra))
        rest_args_dict[ra] = request.args.get(ra, None)
    setattr(SearchForm, 'filter', HiddenField('filter'))
    return SearchForm(request.form, meta={'csrf': False}, **rest_args_dict)


def get_filter_parameters(form, class_object):
    filter_param = {}
    search_param = []
    rest_args_list = list(request.args.keys())
    check_filter = False
    for search_attr, search_name, search_object in class_object.search:
        if search_attr in rest_args_list:
            rest_args_list.remove(search_attr)
        request_arg = request.args.get(search_attr, None, type=str)
        if request_arg and not request_arg == '0':
            check_filter = True
            if issubclass(search_object, Entity):
                filter_param[search_attr] = request_arg
                form[search_attr].default = request_arg
                form.process()
            elif issubclass(search_object, type(datetime.now())):
                filter_param[search_attr] = request_arg
                form[search_attr].data = datetime.strptime(request_arg,
                                                           '%Y-%m-%d')
            elif issubclass(search_object, Period):
                search_param.append(getattr(class_object, search_attr).between(
                    datetime.strptime(request_arg, '%Y-%m-%d'),
                    datetime.strptime(request_arg, '%Y-%m-%d') + timedelta(days=1)))
                search_param.append(getattr(class_object, search_attr
                                            ).ilike(f'%{str(request_arg)}%'))
                form[search_attr].data = datetime.strptime(request_arg,
                                                           '%Y-%m-%d')
            else:
                search_param.append(getattr(class_object, search_attr
                                            ).ilike(f'%{str(request_arg)}%'))
                form[search_attr].data = request_arg
        if hasattr(SearchForm, search_attr):
            delattr(SearchForm, search_attr)
    for ra in rest_args_list:
        if hasattr(SearchForm, ra):
            delattr(SearchForm, ra)
    form.filter.data = check_filter
    if hasattr(SearchForm, 'filter'):
        delattr(SearchForm, 'filter')
    return filter_param, search_param


@app.route('/sendmail/', methods=['GET', 'POST'])
def sendmail():
    url_back = request.args.get('url_back', url_for('index', **request.args))
    form = ContactForm()
    form.text.render_kw = {'rows': 6}
    if form.validate_on_submit():
        sender = form.name.data, form.email.data
        subject = f'Feedback from site ({form.email.data})'
        text = form.text.data
        send_mail_from_site(sender, subject, text)
        return render_template('success_sendmail.html')
    return render_template('data_form.html',
                           title=_('Send mail'),
                           form=form,
                           url_back=url_back)


@app.route('/')
@app.route('/index/')
def index():
    if current_user.is_authenticated:
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
                    email=form.email.data)
        db.session.add(user)
        db.session.flush()
        user.set_password(form.password.data)
        db.session.commit()
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
        user = User.find_user(form.username.data)
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        if not user.company or not user.company.config:
            logout_user()
            error_message = 'Not found company configuration!'
            return render_template('error.html', message=error_message), 404
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        app.logger.info('%s успешный вход в систему', user.username)
        return redirect(next_page)
    return render_template('login.html', title='Sign In', form=form)


@app.route('/logout/')
def logout():
    username = current_user.username
    logout_user()
    app.logger.info('%s выход из системы', username)
    return redirect(url_for('login'))


# Company block start
@app.route('/companies/edit/', methods=['GET', 'POST'])
@login_required
def company_edit():
    url_back = url_for('index', **request.args)
    form = CompanyForm()
    company = current_user.company
    if form.validate_on_submit():
        company.name = form.name.data
        company.registration_number = form.registration_number.data
        company.info = form.info.data
        company.config.default_time_from = form.default_time_from.data
        company.config.default_time_to = form.default_time_to.data
        company.config.simple_mode = form.simple_mode.data
        db.session.commit()
        return redirect(url_for('index'))
    elif request.method == 'GET':
        form = CompanyForm(
            obj=company,
            data={'simple_mode': CompanyConfig.get_parameter('simple_mode'),
                  'default_time_from': CompanyConfig.get_parameter('default_time_from'),
                  'default_time_to': CompanyConfig.get_parameter('default_time_to')})
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
        if form.password.data.strip() != '':
            if not user.check_password(form.password_old.data):
                flash('Invalid password')
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
    return render_template('data_form.html',
                           title=_('User (edit)'),
                           form=form,
                           url_back=url_back)


# User block end


# Staff block start
# noinspection PyTypeChecker
@app.route('/staff/')
@login_required
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
def staff_create():
    url_back = url_for('staff_table', **request.args)
    if CompanyConfig.get_parameter('simple_mode'):
        form = StaffFormSimple()
    else:
        form = StaffForm()
        form.schedule.choices = Schedule.get_items(True)
    if form.validate_on_submit():
        staff = Staff(cid=current_user.cid,
                      name=form.name.data,
                      phone=form.phone.data,
                      birthday=form.birthday.data)
        db.session.add(staff)
        if form.schedule.data:
            db.session.flush()
            schedule = Schedule.get_object(form.schedule.data)
            staff.schedules.append(schedule)
        db.session.commit()
        return redirect(url_for('staff_table'))
    return render_template('data_form.html',
                           title=_('Staff (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/staff/edit/<id>/', methods=['GET', 'POST'])
@login_required
def staff_edit(id):
    url_back = url_for('staff_table', **request.args)
    staff = Staff.get_object(id)
    if CompanyConfig.get_parameter('simple_mode'):
        form = StaffFormSimple(staff.phone)
    else:
        form = StaffForm(staff.phone)
        form.schedule.choices = Schedule.get_items(True)
    if form.validate_on_submit():
        staff.name = form.name.data
        staff.phone = form.phone.data
        staff.birthday = form.birthday.data
        if form.schedule.data:
            schedule = Schedule.get_object(form.schedule.data)
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
                form.process()
            form.name.data = staff.name
            form.phone.data = staff.phone
            form.birthday.data = staff.birthday
    return render_template('data_form.html',
                           title=_('Staff (edit)'),
                           form=form,
                           url_back=url_back)


@app.route('/staff/delete/<id>/', methods=['GET', 'POST'])
@login_required
def staff_delete(id):
    staff = Staff.get_object(id)
    if (len(staff.calendar) > 0 or
            len(staff.appointments) > 0 or
            len(staff.tasks) > 0 or
            len(staff.tasks_progress) > 0):
        flash('Unable to delete an object')
    else:
        try:
            db.session.delete(staff)
            db.session.commit()
            flash('Delete staff {}'.format(id))
        except IntegrityError:
            flash('Deletion error')
    return redirect(url_for('staff_table'))


# Staff block end

# Schedule block start
# noinspection PyTypeChecker
@app.route('/schedules/')
@login_required
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
def schedule_create():
    url_back = url_for('schedules_table', **request.args)
    form = ScheduleForm()
    if form.validate_on_submit():
        schedule = Schedule(cid=current_user.cid,
                            name=form.name.data)
        db.session.add(schedule)
        db.session.commit()
        return redirect(url_back)
    return render_template('data_form.html',
                           title=_('Schedule (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/schedules/edit/<id>', methods=['GET', 'POST'])
@login_required
def schedule_edit(id):
    url_back = url_for('schedules_table', **request.args)
    schedule = Schedule.get_object(id)
    form = ScheduleForm()
    if form.validate_on_submit():
        schedule.name = form.name.data
        db.session.commit()
        return redirect(url_for('schedules_table'))
    elif request.method == 'GET':
        form = ScheduleForm(obj=schedule)
    return render_template('data_form.html',
                           title=_('Schedule (edit)'),
                           form=form,
                           url_back=url_back)


@app.route('/schedules/delete/<id>', methods=['GET', 'POST'])
@login_required
def schedule_delete(id):
    schedule = Schedule.get_object(id)
    db.session.delete(schedule)
    db.session.commit()
    flash('Delete schedule {}'.format(id))
    return redirect(url_for('schedules_table'))


@app.route('/schedules/<schedule_id>/schedule_days/')
@login_required
def schedule_days_table(schedule_id):
    page = request.args.get('page', 1, type=int)
    param = {'schedule_id': schedule_id}
    data = ScheduleDay.get_pagination(page, param)
    return render_template('schedule_days_table.html',
                           title=_('Schedule_days'),
                           items=data.items,
                           pagination=data,
                           schedule_id=schedule_id)


@app.route('/schedules/<schedule_id>/schedule_days/create', methods=['GET', 'POST'])
@login_required
def schedule_day_create(schedule_id):
    url_back = url_for('schedule_days_table', schedule_id=schedule_id,
                       **request.args)
    schedule = Schedule.get_object(schedule_id)
    form = ScheduleDayForm()
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
def schedule_day_edit(schedule_id, id):
    url_back = url_for('schedule_days_table', schedule_id=schedule_id,
                       **request.args)
    schedule = Schedule.get_object(schedule_id)
    param = {'schedule_id': schedule.id, 'id': id}
    schedule_day = ScheduleDay.find_object(param, True)
    form = ScheduleDayForm()
    if form.validate_on_submit():
        schedule_day.day_number = form.weekday.data
        schedule_day.hour_from = form.hour_from.data
        schedule_day.hour_to = form.hour_to.data
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form.weekday.default = schedule_day.day_number
        form.process()
        form.hour_from.data = schedule_day.hour_from
        form.hour_to.data = schedule_day.hour_to
    return render_template('data_form.html',
                           title=_('Schedule day (edit)'),
                           form=form,
                           url_back=url_back)


@app.route('/schedules/<schedule_id>/schedule_days/delete/<id>', methods=['GET', 'POST'])
@login_required
def schedule_day_delete(schedule_id, id):
    url_back = url_for('schedule_days_table', schedule_id=schedule_id,
                       **request.args)
    schedule = Schedule.get_object(schedule_id)
    param = {'schedule_id': schedule.id, 'id': id}
    schedule_day = ScheduleDay.find_object(param, True)
    db.session.delete(schedule_day)
    db.session.commit()
    flash('Delete schedule day {}'.format(id))
    return redirect(url_back)


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
    return render_template('client_table.html',
                           title=_('Clients'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/clients/create/', methods=['GET', 'POST'])
@login_required
def client_create():
    url_back = url_for('clients_table', **request.args)
    form = ClientForm()
    if form.validate_on_submit():
        client = Client(cid=current_user.cid,
                        name=form.name.data,
                        phone=form.phone.data,
                        birthday=form.birthday.data,
                        info=form.info.data)
        db.session.add(client)
        db.session.commit()
        return redirect(url_for('clients_table'))
    return render_template('data_form.html',
                           title=_('Client (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/clients/edit/<id>/', methods=['GET', 'POST'])
@login_required
def client_edit(id):
    url_back = url_for('clients_table', **request.args)
    form = ClientForm()
    client = Client.get_object(id)
    if form.validate_on_submit():
        client.name = form.name.data
        client.phone = form.phone.data
        client.birthday = form.birthday.data
        client.info = form.info.data
        db.session.commit()
        return redirect(url_for('clients_table'))
    elif request.method == 'GET':
        form = ClientForm(obj=client)
    return render_template('data_form.html',
                           title=_('Client (edit)'),
                           form=form,
                           url_back=url_back)


@app.route('/clients/delete/<id>/', methods=['GET', 'POST'])
@login_required
def client_delete(id):
    client = Client.get_object(id)
    if (len(client.files) > 0 or
            len(client.appointments) > 0):
        flash('Unable to delete an object')
    else:
        try:
            db.session.delete(client)
            db.session.commit()
            flash('Delete client {}'.format(id))
        except IntegrityError:
            flash('Deletion error')
    return redirect(url_for('clients_table'))


# noinspection PyTypeChecker
@app.route('/clients/<id>/files/', methods=['GET', 'POST'])
@login_required
def client_files_table(id):
    page = request.args.get('page', 1, type=int)
    form = set_filter(ClientFile)
    param = get_filter_parameters(form, ClientFile)
    param_filter = {**param[0], **{'client_id': id}}
    param_search = param[1]
    data = ClientFile.get_pagination(page, param_filter, param_search)
    return render_template('client_files_table.html',
                           id=id,
                           title=_('Files'),
                           items=data.items,
                           pagination=data,
                           form=form)


@app.route('/clients/<id>/upload_file/', methods=['GET', 'POST'])
@login_required
def client_file_upload(id):
    url_back = url_for('client_files_table', id=id, **request.args)
    client = Client.get_object(id)
    if not client:
        return redirect(url_back)
    form = ClientFileForm()
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No selected file')
            return redirect(url_for('client_file_upload', id=id))
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(url_for('client_file_upload', id=id))
        if not allowed_file_ext(file.filename):
            flash('Unauthorized file extension')
            return redirect(url_for('client_file_upload', id=id))
        directory = os.path.join(app.config['UPLOAD_FOLDER'],
                                 str(current_user.cid))
        path = os.path.join(directory, str(uuid.uuid4()))
        if not os.path.exists(directory):
            os.makedirs(directory)
        file.save(path)
        with open(path, 'rb') as f:
            hash_file = hashlib.sha1(f.read()).hexdigest()
        client_file = ClientFile(cid=current_user.cid,
                                 client_id=id,
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


@app.route('/clients/<client_id>/delete_file/<id>/')
@login_required
def client_file_delete(client_id, id):
    url_back = url_for('client_files_table', id=client_id, **request.args)
    try:
        file = ClientFile.get_object(id)
        os.remove(file.path)
        db.session.delete(file)
        db.session.commit()
    except RuntimeError:
        flash('Runtime error')
        return redirect(url_back)
    flash('Delete file {}'.format(id))
    return redirect(url_back)


# Client block end


# Tag block start
# noinspection PyTypeChecker
@app.route('/tags/')
@login_required
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


@app.route('/tags/delete/<id>/')
@login_required
def tag_delete(id):
    url_back = url_for('tags_table', **request.args)
    tag = Tag.get_object(id)
    db.session.delete(tag)
    db.session.commit()
    flash('Delete tag {}'.format(id))
    return redirect(url_back)


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
        url_submit = url_for('appointment_create')
    if url_back == url_for('appointments_table'):
        session.pop('services', None)
        session.pop('location', None)
        session.pop('staff', None)
        session.pop('client', None)
        session.pop('date', None)
        session.pop('time', None)
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
                           id=appointment_id,
                           form=form)


@app.route('/services/create/', methods=['GET', 'POST'])
@login_required
def service_create():
    url_back = url_for('services_table', **request.args)
    form = ServiceForm()
    location_list = Location.get_items(True)
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
        return redirect(url_for('services_table'))
    return render_template('data_form.html',
                           title=_('Service (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/services/edit/<id>/', methods=['GET', 'POST'])
@login_required
def service_edit(id):
    url_back = url_for('services_table', **request.args)
    form = ServiceForm()
    location_list = Location.get_items(True)
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


@app.route('/services/delete/<id>/', methods=['GET', 'POST'])
@login_required
def service_delete(id):
    service = Service.get_object(id)
    db.session.delete(service)
    db.session.commit()
    flash('Delete service {}'.format(id))
    return redirect(url_for('services_table'))
# Service block end


# Location block start
# noinspection PyTypeChecker
@app.route('/locations/')
@login_required
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
def location_create():
    url_back = url_for('locations_table', **request.args)
    form = LocationForm()
    form.schedule.choices = Schedule.get_items(True)
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
        return redirect(url_for('locations_table'))
    return render_template('data_form.html',
                           title=_('Location (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/locations/edit/<id>/', methods=['GET', 'POST'])
@login_required
def location_edit(id):
    url_back = url_for('locations_table', **request.args)
    form = LocationForm()
    form.schedule.choices = Schedule.get_items(True)
    location = Location.get_object(id)
    if form.validate_on_submit():
        location.name = form.name.data
        location.phone = form.phone.data
        location.address = form.address.data
        if form.schedule.data:
            schedule = Schedule.get_object(form.schedule.data)
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
    return render_template('data_form.html',
                           title=_('Location (edit)'),
                           form=form,
                           url_back=url_back)


@app.route('/locations/delete/<id>/', methods=['GET', 'POST'])
@login_required
def location_delete(id):
    location = Location.get_object(id)
    db.session.delete(location)
    db.session.commit()
    flash('Delete location {}'.format(id))
    return redirect(url_for('locations_table'))
# Location block end


# Appointment block start
# noinspection PyTypeChecker
@app.route('/appointments/')
@login_required
def appointments_table():
    page = request.args.get('page', 1, type=int)
    form = set_filter(Appointment)
    param = get_filter_parameters(form, Appointment)
    data = Appointment.get_pagination(page, *param)
    return render_template('timetable.html',
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
    selected_services_id = session.get('services')
    selected_location_id = session.get('location')
    selected_staff_id = session.get('staff')
    selected_client_id = session.get('client')
    selected_date = session.get('date')
    selected_time = session.get('time')
    form = AppointmentForm()
    form.location.choices = Location.get_items(True)
    form.staff.choices = Staff.get_items(True)
    form.client.choices = Client.get_items(True)
    form.duration.data = get_duration(selected_services_id)
    selected_services = []
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
                                  info=form.info.data)
        db.session.add(appointment)
        db.session.flush()
        for service in selected_services:
            appointment.add_service(service)
        session.pop('services', None)
        db.session.commit()
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
                           url_select_service=url_select_service)


@app.route('/appointments/edit/<id>/', methods=['GET', 'POST'])
@login_required
def appointment_edit(id):
    appointment = Appointment.get_object(id)
    param_url = {**request.args}
    param_url.pop('mod_services', None)
    url_back = url_for('appointments_table', **param_url)
    mod_services = request.args.get('mod_services', None)
    if not mod_services:
        session.pop('services', None)
        session['services'] = [str(s.id) for s in appointment.services]
    selected_services_id = session.get('services')
    url_select_service = url_for('services_table',
                                 choice_mode=1,
                                 appointment_id=id,
                                 url_back=request.path)
    selected_services = []
    for service_id in selected_services_id:
        service = Service.get_object(service_id)
        selected_services.append(service)
    selected_services.sort(key=lambda x: x.name)
    form = AppointmentForm(appointment)
    form.duration.data = get_duration(selected_services_id)
    form.location.choices = Location.get_items(True)
    form.staff.choices = Staff.get_items(True)
    form.client.choices = Client.get_items(True)
    current_time = appointment.date_time.time().strftime('%H:%M')
    form.time.choices = (current_time, current_time)
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
        appointment.info = form.info.data
        appointment.services.clear()
        for service in selected_services:
            appointment.add_service(service)
        session.pop('services', None)
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form.location.default = appointment.location_id
        form.staff.default = appointment.staff_id
        form.client.default = appointment.client_id
        form.time.default = current_time
        form.process()
        form.date.data = appointment.date_time.date()
        form.info.data = appointment.info
    form.services.data = ','.join(list(str(s) for s in selected_services_id))
    return render_template('appointment_form.html',
                           title=_('Appointment (edit)'),
                           form=form,
                           id=id,
                           items=selected_services,
                           url_select_service=url_select_service,
                           url_back=url_back)


@app.route('/appointments/delete/<id>/', methods=['GET', 'POST'])
@login_required
def appointment_delete(id):
    appointment = Appointment.get_object(id)
    db.session.delete(appointment)
    db.session.commit()
    flash('Delete appointment {}'.format(id))
    return redirect(url_for('appointments_table'))


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


@app.route('/items/delete/<id>')
@login_required
def item_delete(id):
    item = Item.get_object(id)
    db.session.delete(item)
    db.session.commit()
    flash('Delete item {}'.format(id))
    return redirect(url_for('items_table'))
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


@app.route('/items_flow/delete/<id>')
@login_required
def item_flow_delete(id):
    item_flow = ItemFlow.get_object(id)
    db.session.delete(item_flow)
    param = {'location_id': item_flow.location_id, 'item_id': item_flow.item_id}
    storage = Storage.find_object(param)
    storage.quantity -= item_flow.quantity
    db.session.commit()
    flash('Delete item flow {}'.format(id))
    return redirect(url_for('items_flow_table'))
# ItemFlow block end


# Notice block start
# noinspection PyTypeChecker
@app.route('/notices/')
@login_required
def notices_table():
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
    appointment_id = request.args.get('appointment_id', None)
    appointment = Appointment.get_object(appointment_id, False)
    form = NoticeForm()
    form.client.choices = Client.get_items(True)
    if form.validate_on_submit():
        notice = Notice(cid=current_user.cid,
                        client_id=form.client.data,
                        date=form.date.data,
                        description=form.description.data)
        db.session.add(notice)
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        if client_id:
            form.client.default = client_id
            form.process()
        if appointment:
            form.date.data = appointment.date_repeat
            previous_visit = appointment.date_time.date()
            form.description.data = f'*Previous visit {previous_visit}'
    return render_template('data_form.html',
                           title=_('Notice (create)'),
                           form=form,
                           url_back=url_back)


@app.route('/notices/edit/<id>/', methods=['GET', 'POST'])
@login_required
def notice_edit(id):
    url_back = request.args.get('url_back', url_for('notices_table',
                                                    **request.args))
    notice = Notice.get_object(id)
    form = NoticeForm()
    form.client.choices = Client.get_items(True)
    if form.validate_on_submit():
        notice.client_id = form.client.data
        notice.date = form.date.data
        notice.description = form.description.data
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form.client.default = notice.client_id
        form.process()
        form.date.data = notice.date
        form.description.data = notice.description
    return render_template('data_form.html',
                           title=_('Notice (edit)'),
                           form=form,
                           url_back=url_back)


@app.route('/notices/delete/<id>/')
@login_required
def notice_delete(id):
    url_back = url_for('notices_table', **request.args)
    notice = Notice.get_object(id)
    db.session.delete(notice)
    db.session.commit()
    flash('Delete notice {}'.format(id))
    return redirect(url_back)
# Notice block end


# CashFlow block start
# noinspection PyTypeChecker
@app.route('/cash_flow/')
@login_required
def cash_flow_table():
    page = request.args.get('page', 1, type=int)
    form = set_filter(CashFlow)
    param = get_filter_parameters(form, CashFlow)
    data = CashFlow.get_pagination(page, *param)
    return render_template('cash_flow_table.html',
                           title=_('Cash flow'),
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
    if form.validate_on_submit():
        cash_flow = CashFlow(cid=current_user.cid,
                             location_id=form.location.data,
                             date=form.date.data,
                             description=form.description.data,
                             cost=form.cost.data * form.action.data)
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
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        if appointment:
            location_id = appointment.location_id
            description = ' '.join((_('#Payment for services'),
                                    str(appointment.date_time)))
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
    form.location.choices = Location.get_items(True)
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
        param = {'location_id': form.location.data}
        cash = Cash.find_object(param)
        if cash:
            cash.cost += form.cost.data * form.action.data
        else:
            cash = Cash(cid=current_user.cid,
                        location_id=form.location.data,
                        cost=form.cost.data * form.action.data)
            db.session.add(cash)
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form.location.default = cash_flow.location_id
        form.process()
        form.date.data = cash_flow.date
        form.description.data = cash_flow.description
        form.cost.data = abs(cash_flow.cost)
        form.action.data = cash_flow.cost / abs(cash_flow.cost)
    return render_template('data_form.html',
                           title=_('Cash flow (edit)'),
                           form=form,
                           url_back=url_back)


@app.route('/cash_flow/delete/<id>')
@login_required
def cash_flow_delete(id):
    cash_flow = CashFlow.get_object(id)
    db.session.delete(cash_flow)
    param = {'location_id': cash_flow.location_id}
    cash = Cash.find_object(param, True)
    cash.cost -= cash_flow.cost
    db.session.commit()
    flash('Delete cash flow {}'.format(id))
    return redirect(url_for('cash_flow_table'))
# CashFlow block end


@app.route('/select_service/<service_id>/<selected>/')
@login_required
def select_service(service_id, selected):
    if int(selected) == 1:
        services_id = session.get('services', [])
        if str(service_id) not in services_id:
            services_id.append(service_id)
            session['services'] = services_id
    else:
        services_id = session.get('services', [])
        if str(service_id) in services_id:
            services_id.remove(str(service_id))
            session['services'] = services_id
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
    return jsonify('Ok')


@app.route('/select_date/<date>/')
@login_required
def select_date(date):
    session['date'] = date
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


@app.route('/get_intervals/<location_id>/<staff_id>/<date>')
@login_required
def get_intervals(location_id, staff_id, date):
    timeslots = []
    duration = get_duration(session['services'])
    intervals = get_free_time_intervals(int(location_id), datetime.strptime(
        date, '%Y-%m-%d').date(), int(staff_id), duration)
    delta_config = CompanyConfig.get_parameter('min_time_interval')
    for interval in intervals:
        start = interval[0] + timedelta(minutes=14)
        start = start - timedelta(minutes=start.minute % delta_config,
                                  seconds=start.second,
                                  microseconds=start.microsecond)
        delta = timedelta(minutes=delta_config)
        timeslots.append(start.strftime('%H:%M'))
        while start < interval[1]:
            start = start + delta
            timeslots.append(start.strftime('%H:%M'))
    return jsonify(timeslots)


# Tasks block start
@app.route('/task_statuses/')
@login_required
def task_statuses_table():
    page = request.args.get('page', 1, type=int)
    data = TaskStatus.get_pagination(page)
    return render_template('task_status_table.html',
                           title='Task statuses',
                           items=data.items,
                           pagination=data)


@app.route('/task_statuses/create/', methods=['GET', 'POST'])
@login_required
def task_status_create():
    url_back = url_for('staff_table', **request.args)
    form = TaskStatusForm()
    if form.validate_on_submit():
        task_status = TaskStatus(cid=current_user.cid,
                                 name=form.name.data,
                                 description=form.description.data,
                                 final=form.final.data)
        db.session.add(task_status)
        db.session.commit()
        return redirect(url_for('task_statuses_table'))
    return render_template('data_form.html',
                           title='Task status (create)',
                           form=form,
                           url_back=url_back)


@app.route('/task_statuses/edit/<id>/', methods=['GET', 'POST'])
@login_required
def task_status_edit(id):
    url_back = url_for('task_statuses_table', **request.args)
    task_status = TaskStatus.get_object(id)
    form = TaskStatusForm()
    if form.validate_on_submit():
        task_status.name = form.name.data
        task_status.description = form.description.data
        task_status.final = form.final.data
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form = TaskStatusForm(obj=task_status)
    return render_template('data_form.html',
                           title='Task status (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/task_statuses/delete/<id>/', methods=['GET', 'POST'])
@login_required
def task_status_delete(id):
    task_status = TaskStatus.get_object(id)
    if len(task_status.progress) > 0:
        flash('Unable to delete an object')
    else:
        try:
            db.session.delete(task_status)
            db.session.commit()
            flash('Delete task status {}'.format(id))
        except IntegrityError:
            flash('Deletion error')
    return redirect(url_for('task_statuses_table'))


@app.route('/tasks/')
@login_required
def tasks_table():
    page = request.args.get('page', 1, type=int)
    data = Task.get_pagination(page)
    return render_template('task_table.html',
                           title='Tasks',
                           items=data.items,
                           pagination=data)


@app.route('/tasks/create', methods=['GET', 'POST'])
@login_required
def task_create():
    url_back = url_for('tasks_table', **request.args)
    form = TaskForm()
    form.staff.choices = Staff.get_items(True)
    if form.validate_on_submit():
        task = Task(cid=current_user.cid,
                    name=form.name.data,
                    description=form.description.data,
                    staff_id=form.staff.data,
                    author_id=current_user.id,
                    deadline=form.deadline.data)
        db.session.add(task)
        db.session.flush()
        status = TaskStatus.query.get_or_404(1)
        task_progress = TaskProgress(cid=current_user.cid,
                                     task_id=task.id,
                                     staff_id=form.staff.data,
                                     status_id=status.id)
        db.session.add(task_progress)
        db.session.commit()
        return redirect(url_for('tasks_table'))
    return render_template('data_form.html',
                           title='Task (create)',
                           form=form,
                           url_back=url_back)


# Tasks block end
