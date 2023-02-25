from sqlalchemy.exc import IntegrityError

import app
import hashlib
import os.path
import uuid

from flask import render_template, redirect, url_for, request, jsonify, send_file, session
from flask_login import login_user, logout_user, login_required
from werkzeug.urls import url_parse

from app.forms import *
from app.functions import *
from app.models import *


@app.route('/sendmail/', methods=['GET', 'POST'])
@login_required
def sendmail():
    url_back = request.args.get('url_back', url_for('index', **request.args))
    form = ContactForm()
    if form.validate_on_submit():
        sender = form.name.data, form.email.data
        subject = f'Feedback from site ({form.email.data})'
        text = form.text.data
        send_mail_from_site(sender, subject, text)
        return render_template('success_sendmail.html')
    return render_template('data_form.html',
                           title='Send mail',
                           form=form,
                           url_back=url_back)


@app.route('/')
@app.route('/index/')
@login_required
def index():
    param = {'cid': current_user.cid}
    appointments_count = db.session.query(
        Location, func.count(Appointment.location_id)).join(
        Location, Appointment.location_id == Location.id).group_by(
        Appointment.location_id).filter(
        func.date(Appointment.date_time) == datetime.utcnow().date()
    ).filter_by(**param).all()
    notice_list = Notice.get_notices()
    return render_template('index.html',
                           notices=notice_list,
                           appointments_count=appointments_count)


@app.route('/register/', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
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
                           form=form)


@app.route('/login/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
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
        db.session.commit()
        return redirect(url_for('index'))
    elif request.method == 'GET':
        form = CompanyForm(obj=company)
    return render_template('data_form.html',
                           title='Company (edit)',
                           form=form,
                           url_back=url_back)


# Company block end


# User block start
@app.route('/users/edit/<id>', methods=['GET', 'POST'])
@login_required
def user_edit(id):
    url_back = url_for('index', **request.args)
    user = User.query.get_or_404(id)
    form = UserFormEdit(user.username, user.email)
    if form.validate_on_submit():
        user.username = form.username.data
        user.email = form.email.data
        if form.password.data.strip() != '':
            if not user.check_password(form.password_old.data):
                flash('Invalid password')
                return render_template('data_form.html',
                                       title='User (edit)',
                                       form=form)
            user.set_password(form.password.data)
        db.session.commit()
        return redirect(url_for('index'))
    elif request.method == 'GET':
        form.username.data = user.username
        form.email.data = user.email
    return render_template('data_form.html',
                           title='User (edit)',
                           form=form,
                           url_back=url_back)


# User block end


# Staff block start
@app.route('/staff/')
@login_required
def staff_table():
    page = request.args.get('page', 1, type=int)
    data = Staff.query.filter_by(
        cid=current_user.cid).order_by(
        Staff.name.asc()).paginate(page, app.config['ROWS_PER_PAGE'], False)
    return render_template('staff_table.html',
                           title='Staff',
                           items=data.items,
                           pagination=data)


@app.route('/staff/create/', methods=['GET', 'POST'])
@login_required
def staff_create():
    url_back = url_for('staff_table', **request.args)
    form = StaffForm()
    if form.validate_on_submit():
        staff = Staff(cid=current_user.cid,
                      name=form.name.data,
                      phone=form.phone.data,
                      birthday=form.birthday.data)
        db.session.add(staff)
        db.session.commit()
        return redirect(url_for('staff_table'))
    return render_template('data_form.html',
                           title='Staff (create)',
                           form=form,
                           url_back=url_back)


@app.route('/staff/edit/<id>/', methods=['GET', 'POST'])
@login_required
def staff_edit(id):
    url_back = url_for('staff_table', **request.args)
    staff = Staff.query.filter_by(cid=current_user.cid,
                                  id=id).first_or_404()
    form = StaffForm(staff.phone)
    if form.validate_on_submit():
        staff.name = form.name.data
        staff.phone = form.phone.data
        staff.birthday = form.birthday.data
        db.session.commit()
        return redirect(url_for('staff_table'))
    elif request.method == 'GET':
        form = StaffForm(obj=staff)
    return render_template('data_form.html',
                           title='Staff (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/staff/delete/<id>/', methods=['GET', 'POST'])
@login_required
def staff_delete(id):
    staff = Staff.query.filter_by(cid=current_user.cid,
                                  id=id).first_or_404()
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
@app.route('/schedules/')
@login_required
def schedules_table():
    page = request.args.get('page', 1, type=int)
    param = {'cid': current_user.cid, 'no_active': False}
    data = Schedule.query.filter_by(
        **param).order_by(Schedule.name.asc()).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('schedule_table.html',
                           items=data.items,
                           pagination=data)


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
                           title='Schedule (create)',
                           form=form,
                           url_back=url_back)


@app.route('/schedules/edit/<id>', methods=['GET', 'POST'])
@login_required
def schedule_edit(id):
    url_back = url_for('schedules_table', **request.args)
    param = {'cid': current_user.cid, 'id': id}
    schedule = Schedule.query.filter_by(**param).first_or_404()
    form = ScheduleForm()
    if form.validate_on_submit():
        schedule.name = form.name.data
        db.session.commit()
        return redirect(url_for('schedules_table'))
    elif request.method == 'GET':
        form = ScheduleForm(obj=schedule)
    return render_template('data_form.html',
                           title='Schedule (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/schedules/delete/<id>', methods=['GET', 'POST'])
@login_required
def schedule_delete(id):
    param = {'cid': current_user.cid, 'id': id}
    schedule = Schedule.query.filter_by(**param).first_or_404()
    db.session.delete(schedule)
    db.session.commit()
    flash('Delete schedule {}'.format(id))
    return redirect(url_for('schedules_table'))


@app.route('/schedules/<schedule_id>/schedule_days/')
@login_required
def schedule_days_table(schedule_id):
    page = request.args.get('page', 1, type=int)
    param = {'cid': current_user.cid, 'schedule_id': schedule_id,
             'no_active': False}
    data = ScheduleDay.query.filter_by(
        **param).order_by(ScheduleDay.day_number.asc()).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('schedule_days_table.html',
                           items=data.items,
                           pagination=data,
                           schedule_id=schedule_id)


@app.route('/schedules/<schedule_id>/schedule_days/create', methods=['GET', 'POST'])
@login_required
def schedule_day_create(schedule_id):
    url_back = url_for('schedule_days_table', schedule_id=schedule_id,
                       **request.args)
    param = {'cid': current_user.cid, 'id': schedule_id}
    schedule = Schedule.query.filter_by(**param).first_or_404()
    form = ScheduleDayForm()
    if form.validate_on_submit():
        day = Schedule.week[form.weekday.data]
        schedule_day = ScheduleDay(cid=current_user.cid,
                                   schedule_id=schedule.id,
                                   name=day,
                                   day_number=form.weekday.data,
                                   hour_from=form.hour_from.data,
                                   hour_to=form.hour_to.data)
        db.session.add(schedule_day)
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'POST':
        form.weekday.default = form.weekday.data
    return render_template('data_form.html',
                           title='Schedule day (create)',
                           form=form,
                           url_back=url_back)


@app.route('/schedules/<schedule_id>/schedule_days/edit/<id>', methods=['GET', 'POST'])
@login_required
def schedule_day_edit(schedule_id, id):
    url_back = url_for('schedule_days_table', schedule_id=schedule_id,
                       **request.args)
    param = {'cid': current_user.cid, 'id': schedule_id}
    schedule = Schedule.query.filter_by(**param).first_or_404()
    param = {'cid': current_user.cid, 'schedule_id': schedule.id, 'id': id}
    schedule_day = ScheduleDay.query.filter_by(**param).first_or_404()
    form = ScheduleDayForm()
    if form.validate_on_submit():
        day = Schedule.week[form.weekday.data]
        schedule_day.name = day
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
                           title='Schedule day (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/schedules/<schedule_id>/schedule_days/delete/<id>', methods=['GET', 'POST'])
@login_required
def schedule_day_delete(schedule_id, id):
    url_back = url_for('schedule_days_table', schedule_id=schedule_id,
                       **request.args)
    param = {'cid': current_user.cid, 'id': schedule_id}
    schedule = Schedule.query.filter_by(**param).first_or_404()
    param = {'cid': current_user.cid, 'schedule_id': schedule.id, 'id': id}
    schedule_day = ScheduleDay.query.filter_by(**param).first_or_404()
    db.session.delete(schedule_day)
    db.session.commit()
    flash('Delete schedule day {}'.format(id))
    return redirect(url_back)


# Schedule block end


# Client block start
@app.route('/clients/')
@login_required
def clients_table():
    page = request.args.get('page', 1, type=int)
    data = Client.query.filter_by(
        cid=current_user.cid).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('client_table.html',
                           title='Clients',
                           items=data.items,
                           pagination=data)


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
                           title='Client (create)',
                           form=form,
                           url_back=url_back)


@app.route('/clients/edit/<id>/', methods=['GET', 'POST'])
@login_required
def client_edit(id):
    url_back = url_for('clients_table', **request.args)
    form = ClientForm()
    client = Client.query.filter_by(cid=current_user.cid,
                                    id=id).first_or_404()
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
                           title='Client (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/clients/delete/<id>/', methods=['GET', 'POST'])
@login_required
def client_delete(id):
    client = Client.query.filter_by(cid=current_user.cid,
                                    id=id).first_or_404()
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


@app.route('/clients/<id>/files/', methods=['GET', 'POST'])
@login_required
def client_files_table(id):
    page = request.args.get('page', 1, type=int)
    data = ClientFile.query.filter_by(
        cid=current_user.id, client_id=id).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('client_files_table.html',
                           id=id,
                           title='Files',
                           items=data.items,
                           pagination=data)


@app.route('/clients/<id>/upload_file/', methods=['GET', 'POST'])
@login_required
def client_file_upload(id):
    url_back = url_for('client_files_table', id=id, **request.args)
    client = Client.query.filter_by(cid=current_user.cid,
                                    id=id).first_or_404()
    if not client:
        return redirect(url_back)
    form = ClientFileForm()
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No selected file')
            return redirect(url_for('upload_client_file', id=id))
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(url_for('upload_client_file', id=id))
        if not allowed_file_ext(file.filename):
            flash('Unauthorized file extension')
            return redirect(url_for('upload_client_file', id=id))
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
                           title='File upload',
                           form=form,
                           url_back=url_back)


@app.route('/clients/<client_id>/download_file/<id>/')
@login_required
def client_file_download(client_id, id):
    file = ClientFile.query.filter_by(cid=current_user.cid,
                                      id=id, client_id=client_id).first()
    return send_file(file.path, as_attachment=True, download_name=file.name)


@app.route('/clients/<client_id>/delete_file/<id>/')
@login_required
def client_file_delete(client_id, id):
    url_back = url_for('client_files_table', id=client_id, **request.args)
    try:
        file = ClientFile.query.filter_by(cid=current_user.cid,
                                          id=id).first()
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
@app.route('/tags/')
@login_required
def tags_table():
    page = request.args.get('page', 1, type=int)
    data = Tag.query.filter_by(
        cid=current_user.id).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('tags_table.html',
                           id=id,
                           title='Tags',
                           items=data.items,
                           pagination=data)


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
    elif request.method == 'POST':
        return redirect(url_for('tag_create'))
    else:
        return render_template('data_form.html',
                               title='Tag (create)',
                               form=form,
                               url_back=url_back)


@app.route('/tags/edit/<id>/', methods=['GET', 'POST'])
@login_required
def tag_edit(id):
    url_back = url_for('tags_table', **request.args)
    tag = Tag.query.filter_by(cid=current_user.cid,
                              id=id).first_or_404()
    form = TagForm()
    if form.validate_on_submit():
        tag.name = form.name.data
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form = TagForm(obj=tag)
    return render_template('data_form.html',
                           title='Tag (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/tags/delete/<id>/')
@login_required
def tag_delete(id):
    url_back = url_for('tags_table', **request.args)
    tag = Tag.query.filter_by(cid=current_user.cid,
                              id=id).first_or_404()
    db.session.delete(tag)
    db.session.commit()
    flash('Delete tag {}'.format(id))
    return redirect(url_back)


# Tag block end


# Service block start
@app.route('/services/', methods=['GET', 'POST'])
@login_required
def services_table():
    page = request.args.get('page', 1, type=int)
    appointment_id = request.args.get('appointment_id', None, type=int)
    client_id = request.args.get('client_id', None, type=int)
    url_back = request.args.get('url_back', url_for('appointments_table'))
    if appointment_id:
        appointment = Appointment.query.filter_by(
            cid=current_user.cid, id=appointment_id).first_or_404()
        session['services'] = [str(s.id) for s in appointment.services]
    if 'edit' in url_back:
        url_submit = url_back + '?mod_services=1'
    else:
        url_submit = url_for('appointment_create', client_id=client_id)
    if url_back == url_for('appointments_table'):
        session.pop('services', None)
    location_id = request.args.get('location_id', None, type=int)
    active = request.args.get('active', None, type=int)
    choice_mode = request.args.get('choice_mode', None, type=int)
    param = [Service.cid == current_user.cid]
    if location_id:
        location = Location.query.filter_by(cid=current_user.cid,
                                            id=location_id).first_or_404()
        param.append(Service.id.in_([s.id for s in location.services]))
    if choice_mode:
        template = 'service_table_choice.html'
        active = 1
    else:
        template = 'service_table.html'
    if active:
        param.append(Service.no_active != True)
    data = Service.query.filter(*param).order_by(Service.name).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template(template,
                           title='Services',
                           items=data.items,
                           pagination=data,
                           url_back=url_back,
                           url_submit=url_submit,
                           id=appointment_id)


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
            location = Location.query.get_or_404(location_id)
            location.add_service(service)
        db.session.commit()
        return redirect(url_for('services_table'))
    return render_template('data_form.html',
                           title='Service (create)',
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
    service = Service.query.filter_by(cid=current_user.cid,
                                      id=id).first_or_404()
    if form.validate_on_submit():
        service.name = form.name.data
        service.duration = form.duration.data
        service.price = form.price.data
        service.repeat = form.repeat.data
        service.locations.clear()
        for location_id in form.location.data:
            location = Location.query.get_or_404(location_id)
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
                           title='Service (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/services/delete/<id>/', methods=['GET', 'POST'])
@login_required
def service_delete(id):
    service = Service.query.filter_by(cid=current_user.cid,
                                      id=id).first_or_404()
    db.session.delete(service)
    db.session.commit()
    flash('Delete service {}'.format(id))
    return redirect(url_for('services_table'))
# Service block end


# Location block start
@app.route('/locations/')
@login_required
def locations_table():
    page = request.args.get('page', 1, type=int)
    data = Location.query.filter_by(
        cid=current_user.cid).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('location_table.html',
                           title='Locations',
                           items=data.items,
                           pagination=data)


@app.route('/locations/create/', methods=['GET', 'POST'])
@login_required
def location_create():
    url_back = url_for('locations_table', **request.args)
    form = LocationForm()
    if form.validate_on_submit():
        location = Location(cid=current_user.cid,
                            name=form.name.data,
                            phone=form.phone.data,
                            address=form.address.data)
        db.session.add(location)
        db.session.commit()
        return redirect(url_for('locations_table'))
    return render_template('data_form.html',
                           title='Location (create)',
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
        db.session.commit()
        return redirect(url_for('locations_table'))
    elif request.method == 'GET':
        if location.main_schedule:
            form.schedule.default = location.main_schedule.id
            form.process()
        form.name.data = location.name
        form.address.data = location.address
        form.phone.data = location.phone
    else:
        form.schedule.default = form.schedule.data
        form.process()
    return render_template('data_form.html',
                           title='Location (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/locations/delete/<id>/', methods=['GET', 'POST'])
@login_required
def location_delete(id):
    location = Location.query.filter_by(cid=current_user.cid,
                                        id=id).first_or_404()
    db.session.delete(location)
    db.session.commit()
    flash('Delete location {}'.format(id))
    return redirect(url_for('locations_table'))
# Location block end


# Appointment block start
@app.route('/appointments/')
@login_required
def appointments_table():
    form = SearchForm()
    form.location_id.choices = Location.get_items(True)
    form.location_id.render_kw = {'onchange': 'this.form.submit()'}
    form.staff_id.choices = Staff.get_items(True)
    form.staff_id.render_kw = {'onchange': 'this.form.submit()'}
    form.client_id.choices = Client.get_items(True)
    form.client_id.render_kw = {'onchange': 'this.form.submit()'}
    page = request.args.get('page', 1, type=int)
    param = {'cid': current_user.cid}
    location_id = request.args.get('location_id', None, type=int)
    staff_id = request.args.get('staff_id', None, type=int)
    client_id = request.args.get('client_id', None, type=int)
    if location_id:
        form.location_id.default = location_id
        form.process()
        param['location_id'] = location_id
    if staff_id:
        form.staff_id.default = staff_id
        form.process()
        param['staff_id'] = staff_id
    if client_id:
        form.client_id.default = client_id
        form.process()
        param['client_id'] = client_id
    data = Appointment.query.filter_by(**param).order_by(
        Appointment.date_time.desc(), Appointment.location_id).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('timetable.html',
                           title='Appointments',
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
    form = AppointmentForm()
    form.location.choices = Location.get_items(True)
    form.staff.choices = Staff.get_items(True)
    form.client.choices = Client.get_items(True)
    form.duration.data = get_duration(selected_services_id)
    selected_services = []
    for service_id in selected_services_id:
        service = Service.query.get_or_404(service_id)
        selected_services.append(service)
    if form.validate_on_submit():
        date = form.date.data
        appointment = Appointment(cid=current_user.cid,
                                  location_id=form.location.data,
                                  date_time=datetime(date.year,
                                                     date.month,
                                                     date.day,
                                                     form.time.data.hour,
                                                     form.time.data.minute),
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
    elif request.method == 'POST':
        form.location.default = form.location.data
        form.staff.default = form.staff.data
        form.client.default = form.client.data
    else:
        if request.args.get('client_id', None):
            form.client.default = request.args.get('client_id')
            form.process()
    form.services.data = ','.join(list(str(s) for s in selected_services_id))
    return render_template('appointment_form.html',
                           title='Appointment (create)',
                           form=form,
                           items=selected_services,
                           url_back=url_back,
                           url_select_service=url_select_service)


@app.route('/appointments/edit/<id>/', methods=['GET', 'POST'])
@login_required
def appointment_edit(id):
    appointment = Appointment.query.filter_by(cid=current_user.cid,
                                              id=id).first_or_404()
    param_url = {**request.args}
    param_url.pop('mod_services', None)
    url_back = url_for('appointments_table', **param_url)
    mod_services = request.args.get('mod_services', None) and 'services' in session
    if mod_services:
        selected_services_id = session.get('services')
        url_select_service = url_for('services_table',
                                     choice_mode=1,
                                     url_back=request.path)
    else:
        selected_services_id = [s.id for s in appointment.services]
        url_select_service = url_for('services_table',
                                     choice_mode=1,
                                     appointment_id=id,
                                     url_back=request.path)
    selected_services = []
    for service_id in selected_services_id:
        service = Service.query.get_or_404(service_id)
        selected_services.append(service)
    form = AppointmentForm(appointment)
    form.duration.data = get_duration(selected_services_id)
    form.location.choices = Location.get_items(True)
    form.staff.choices = Staff.get_items(True)
    form.client.choices = Client.get_items(True)
    if form.validate_on_submit():
        appointment.location_id = form.location.data
        appointment.date_time = datetime(form.date.data.year,
                                         form.date.data.month,
                                         form.date.data.day,
                                         form.time.data.hour,
                                         form.time.data.minute)
        appointment.client_id = form.client.data
        appointment.staff_id = form.staff.data
        appointment.info = form.info.data
        appointment.cancel = form.cancel.data
        appointment.services.clear()
        for service in selected_services:
            appointment.add_service(service)
        session.pop('services', None)
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'POST':
        form.location.default = form.location.data
        form.staff.default = form.staff.data
        form.client.default = form.client.data
        form.process()
    else:
        form.location.default = appointment.location_id
        form.staff.default = appointment.staff_id
        form.client.default = appointment.client_id
        form.process()
        form.date.data = appointment.date_time.date()
        form.time.data = appointment.date_time.time()
        form.info.data = appointment.info
        form.cancel.data = appointment.cancel
    form.services.data = ','.join(list(str(s) for s in selected_services_id))
    return render_template('appointment_form.html',
                           title='Appointment (edit)',
                           form=form,
                           id=id,
                           items=selected_services,
                           url_select_service=url_select_service,
                           url_back=url_back)


@app.route('/appointments/delete/<id>/', methods=['GET', 'POST'])
@login_required
def appointment_delete(id):
    appointment = Appointment.query.filter_by(cid=current_user.cid,
                                              id=id).first_or_404()
    db.session.delete(appointment)
    db.session.commit()
    flash('Delete appointment {}'.format(id))
    return redirect(url_for('appointments_table'))


@app.route('/appointments/<appointment_id>/result/', methods=['GET', 'POST'])
@login_required
def appointment_result(appointment_id):
    url_back = request.args.get('url_back', url_for('appointments_table', **request.args))
    param = {'cid': current_user.cid,
             'id': appointment_id}
    appointment = Appointment.query.filter_by(**param).first_or_404()
    form = ResultForm()
    if form.validate_on_submit():
        appointment.result = form.result.data
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form.result.data = appointment.result
    return render_template('data_form.html',
                           title='Result',
                           form=form,
                           url_back=url_back)
# Appointment block end


# Item block start
@app.route('/items/')
@login_required
def items_table():
    page = request.args.get('page', 1, type=int)
    data = Item.query.filter_by(cid=current_user.cid).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('item_table.html',
                           title='Items',
                           items=data.items,
                           pagination=data)


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
                           title='Item (create)',
                           form=form,
                           url_back=url_back)


@app.route('/items/edit/<id>', methods=['GET', 'POST'])
@login_required
def item_edit(id):
    url_back = url_for('items_table', **request.args)
    item = Item.query.filter_by(cid=current_user.cid,
                                id=id).first_or_404()
    form = ItemForm()
    if form.validate_on_submit():
        item.name = form.name.data
        item.description = form.description.data
        db.session.commit()
        return redirect(url_back)
    else:
        form = ItemForm(obj=item)
    return render_template('data_form.html',
                           title='Item (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/items/delete/<id>')
@login_required
def item_delete(id):
    item = Item.query.filter_by(cid=current_user.cid,
                                id=id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash('Delete item {}'.format(id))
    return redirect(url_for('items_table'))
# Item block end


# ItemFlow block start
@app.route('/items_flow/')
@login_required
def items_flow_table():
    page = request.args.get('page', 1, type=int)
    param = {'cid': current_user.cid}
    select_item = request.args.get('item_id', 0, type=int)
    if select_item > 0:
        param['item_id'] = select_item
    data = ItemFlow.query.filter_by(**param).paginate(
        page, app.config['ROWS_PER_PAGE'], False)

    return render_template('item_flow_table.html',
                           title='Items flow',
                           items=data.items,
                           pagination=data)


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
        storage = Storage.query.filter_by(cid=current_user.cid,
                                          location_id=form.location.data,
                                          item_id=form.item.data).first()
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
    elif request.method == 'POST':
        form.location.default = form.location.data
        form.item.default = form.item.data
        form.action.default = form.action.data
        form.process()
    else:
        form.item.default = item_id
        form.process()
        form.date.data = datetime.now().date()
    return render_template('data_form.html',
                           title='Item flow (create)',
                           form=form,
                           url_back=url_back)


@app.route('/items_flow/edit/<id>', methods=['GET', 'POST'])
@login_required
def item_flow_edit(id):
    url_back = url_for('items_flow_table', **request.args)
    item_flow = ItemFlow.query.filter_by(cid=current_user.cid,
                                         id=id).first_or_404()
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
        current_storage = Storage.query.filter_by(cid=current_user.cid,
                                                  location_id=current_location,
                                                  item_id=current_item).first()
        current_storage.quantity -= current_quantity
        storage = Storage.query.filter_by(cid=current_user.cid,
                                          location_id=form.location.data,
                                          item_id=form.item.data).first()
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
    elif request.method == 'POST':
        form.location.default = form.location.data
        form.item.default = form.item.data
        form.action.default = form.action.data
        form.process()
    else:
        form.location.default = item_flow.location_id
        form.item.default = item_flow.item_id
        form.process()
        form.date.data = item_flow.date
        form.quantity.data = abs(item_flow.quantity)
        form.action.data = item_flow.quantity / abs(item_flow.quantity)
    return render_template('data_form.html',
                           title='Item flow (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/items_flow/delete/<id>')
@login_required
def item_flow_delete(id):
    item_flow = ItemFlow.query.filter_by(cid=current_user.cid,
                                         id=id).first_or_404()
    db.session.delete(item_flow)
    storage = Storage.query.filter_by(cid=current_user.cid,
                                      location_id=item_flow.location_id,
                                      item_id=item_flow.item_id).first()
    storage.quantity -= item_flow.quantity
    db.session.commit()
    flash('Delete item flow {}'.format(id))
    return redirect(url_for('items_flow_table'))
# ItemFlow block end


# Notice block start
@app.route('/notices/')
@login_required
def notices_table():
    page = request.args.get('page', 1, type=int)
    client_id = request.args.get('client_id', None)
    param = {'cid': current_user.cid}
    if client_id:
        param['client_id'] = client_id
    data = Notice.query.filter_by(**param).paginate(
        page, app.config['ROWS_PER_PAGE'], False)

    return render_template('notice_table.html',
                           title='Notices',
                           items=data.items,
                           pagination=data)


@app.route('/notices/create/', methods=['GET', 'POST'])
@login_required
def notice_create():
    url_back = request.args.get('url_back', url_for('notices_table', **request.args))
    client_id = request.args.get('client_id', None)
    appointment_id = request.args.get('appointment_id', None)
    appointment = Appointment.query.get_or_404(appointment_id)
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
    elif request.method == 'POST':
        form.client.default = form.client.data
    else:
        if client_id:
            form.client.default = client_id
            form.process()
        if appointment:
            form.date.data = appointment.date_repeat
            previous_visit = appointment.date_time.date()
            form.description.data = f'*Previous visit {previous_visit}'
    return render_template('data_form.html',
                           title='Notice (create)',
                           form=form,
                           url_back=url_back)


@app.route('/notices/edit/<id>/', methods=['GET', 'POST'])
@login_required
def notice_edit(id):
    url_back = request.args.get('url_back', url_for('notices_table',
                                                    **request.args))
    notice = Notice.query.filter_by(cid=current_user.cid,
                                    id=id).first_or_404()
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
                           title='Notice (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/notices/delete/<id>/')
@login_required
def notice_delete(id):
    url_back = url_for('notices_table', **request.args)
    notice = Notice.query.filter_by(cid=current_user.cid,
                                    id=id).first_or_404()
    db.session.delete(notice)
    db.session.commit()
    flash('Delete notice {}'.format(id))
    return redirect(url_back)
# Notice block end


# CashFlow block start
@app.route('/cash_flow/')
@login_required
def cash_flow_table():
    page = request.args.get('page', 1, type=int)
    param = {'cid': current_user.cid}
    data = CashFlow.query.filter_by(**param).paginate(
        page, app.config['ROWS_PER_PAGE'], False)

    return render_template('cash_flow_table.html',
                           title='Cash flow',
                           items=data.items,
                           pagination=data)


@app.route('/cash_flow/create', methods=['GET', 'POST'])
@login_required
def cash_flow_create():
    url_back = request.args.get('url_back', url_for('cash_flow_table',
                                                    **request.args))
    appointment_id = request.args.get('appointment_id')
    appointment = Appointment.query.filter_by(cid=current_user.cid,
                                              id=appointment_id).first()
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
        cash = Cash.query.filter_by(cid=current_user.cid,
                                    location_id=form.location.data
                                    ).first()
        if cash:
            cash.cost += form.cost.data * form.action.data
        else:
            cash = Cash(cid=current_user.cid,
                        location_id=form.location.data,
                        cost=form.cost.data * form.action.data)
            db.session.add(cash)
        appointment.payment_id = cash_flow.id
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'POST':
        form.location.default = form.location.data
        form.action.default = form.action.data
        form.process()
    else:
        if appointment:
            location_id = appointment.location_id
            description = ' '.join(('#Appointment',
                                    str(appointment.id),
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
                           title='Cash flow (create)',
                           form=form,
                           url_back=url_back)


@app.route('/cash_flow/edit/<id>', methods=['GET', 'POST'])
@login_required
def cash_flow_edit(id):
    url_back = request.args.get('url_back', url_for('cash_flow_table',
                                                    **request.args))
    cash_flow = CashFlow.query.filter_by(cid=current_user.cid,
                                         id=id).first_or_404()
    form = CashFlowForm()
    form.location.choices = Location.get_items(True)
    if form.validate_on_submit():
        current_location = cash_flow.location_id
        current_cost = cash_flow.cost
        cash_flow.location_id = form.location.data
        cash_flow.description = form.description.data
        cash_flow.date = form.date.data
        cash_flow.cost = form.cost.data * form.action.data
        current_cash = Cash.query.filter_by(cid=current_user.cid,
                                            location_id=current_location
                                            ).first()
        current_cash.cost -= current_cost
        cash = Cash.query.filter_by(cid=current_user.cid,
                                    location_id=form.location.data
                                    ).first()
        if cash:
            cash.cost += form.cost.data * form.action.data
        else:
            cash = Cash(cid=current_user.cid,
                        location_id=form.location.data,
                        cost=form.cost.data * form.action.data)
            db.session.add(cash)
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'POST':
        form.location.default = form.location.data
        form.action.default = form.action.data
        form.process()
    else:
        form.location.default = cash_flow.location_id
        form.process()
        form.date.data = cash_flow.date
        form.description.data = cash_flow.description
        form.cost.data = abs(cash_flow.cost)
        form.action.data = cash_flow.cost / abs(cash_flow.cost)
    return render_template('data_form.html',
                           title='Cash flow (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/cash_flow/delete/<id>')
@login_required
def cash_flow_delete(id):
    cash_flow = CashFlow.query.filter_by(cid=current_user.cid,
                                         id=id).first_or_404()
    db.session.delete(cash_flow)
    cash = Cash.query.filter_by(cid=current_user.cid,
                                location_id=cash_flow.location_id
                                ).first()
    cash.cost -= cash_flow.cost
    db.session.commit()
    flash('Delete cash flow {}'.format(id))
    return redirect(url_for('cash_flow_table'))
# CashFlow block end


# Tasks block start
@app.route('/task_statuses/')
@login_required
def task_statuses_table():
    page = request.args.get('page', 1, type=int)
    data = TaskStatus.query.filter_by(
        cid=current_user.cid).paginate(page,
                                       app.config['ROWS_PER_PAGE'], False)
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
    task_status = TaskStatus.query.filter_by(cid=current_user.cid,
                                             id=id).first_or_404()
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
    task_status = TaskStatus.query.filter_by(cid=current_user.cid,
                                             id=id).first_or_404()
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
    param = {'cid': current_user.cid}
    data = Task.query.filter_by(**param).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
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
    elif request.method == 'POST':
        form.staff.default = form.staff.data
    return render_template('data_form.html',
                           title='Task (create)',
                           form=form,
                           url_back=url_back)


@app.route('/tasks/edit/<id>', methods=['GET', 'POST'])
@login_required
def task_edit(id):
    pass


@app.route('/tasks/delete/<id>')
@login_required
def task_delete(id):
    pass
# Tasks block end


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
    return jsonify(len(services_id))
