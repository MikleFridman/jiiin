import app
import hashlib
import os.path
import uuid

from flask import render_template, flash, redirect, url_for, request, jsonify, send_file, session
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
    notices = get_notices()
    return render_template('index.html',
                           notices=notices,
                           appointments_count=appointments_count)


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
        cfg = get_company_config()
        if cfg is None:
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
    url_back = url_for('companies', **request.args)
    form = CompanyForm()
    company = current_user.company
    if form.validate_on_submit():
        company.name = form.name.data
        company.registration_number = form.registration_number.data
        company.info = form.info.data
        company.no_active = form.no_active.data
        db.session.commit()
        return redirect(url_for('companies'))
    elif request.method == 'GET':
        form = CompanyForm(obj=company)
    return render_template('data_form.html',
                           title='Company (edit)',
                           form=form,
                           url_back=url_back)


# Company block end


# User block start
@app.route('/users/edit/<id>/', methods=['GET', 'POST'])
@login_required
def user_edit(id):
    url_back = url_for('index', **request.args)
    user = current_user
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
def staff():
    page = request.args.get('page', 1, type=int)
    items = Staff.query.filter_by(
        cid=current_user.cid).paginate(page,
                                       app.config['ROWS_PER_PAGE'], False)
    return render_template('staff_table.html',
                           title='Staff',
                           items=items.items,
                           pagination=items)


@app.route('/staff/create/', methods=['GET', 'POST'])
@login_required
def staff_create():
    url_back = url_for('staff', **request.args)
    if get_tariff_limit('staff') == 0:
        return redirect(url_for('staff'))
    form = StaffForm()
    if form.validate_on_submit():
        staff = Staff(cid=current_user.cid,
                      name=form.name.data,
                      phone=form.phone.data,
                      no_active=form.no_active.data)
        db.session.add(staff)
        db.session.commit()
        return redirect(url_for('staff'))
    return render_template('data_form.html',
                           title='Staff (create)',
                           form=form,
                           url_back=url_back)


@app.route('/staff/edit/<id>/', methods=['GET', 'POST'])
@login_required
def staff_edit(id):
    url_back = url_for('staff', **request.args)
    staff = Staff.query.filter_by(cid=current_user.cid,
                                  id=id).first_or_404()
    form = StaffForm(staff.phone)
    if form.validate_on_submit():
        staff.name = form.name.data
        staff.phone = form.phone.data
        staff.no_active = form.no_active.data
        db.session.commit()
        return redirect(url_for('staff'))
    elif request.method == 'GET':
        form = StaffForm(obj=staff)
    return render_template('data_form.html',
                           title='Staff (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/staff/delete/<id>/', methods=['GET', 'POST'])
@login_required
def staff_delete(id):
    if not check_permission('Staff', 'delete'):
        flash('Insufficient access level')
        return redirect(url_for('staff'))
    service = Staff.query.filter_by(cid=current_user.cid,
                                    id=id).first_or_404()
    db.session.delete(service)
    db.session.commit()
    flash('Delete staff {}'.format(id))
    return redirect(url_for('staff'))


@app.route('/staff/<id>/schedule/')
@login_required
def staff_schedule(id):
    page = request.args.get('page', 1, type=int)
    items = StaffSchedule.query.filter_by(
        cid=current_user.id, staff_id=id).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('schedule_table.html',
                           id=id,
                           title='Schedule',
                           items=items.items,
                           pagination=items)


@app.route('/staff/<id>/schedule/create', methods=['GET', 'POST'])
@login_required
def staff_schedule_create(id):
    url_back = url_for('staff_schedule', id=id, **request.args)
    form = StaffScheduleForm()
    form.staff.choices = get_active_staff()
    form.staff.render_kw = {'disabled': 'True'}
    form.staff.validate_choice = False
    form.location.choices = get_active_locations()
    if form.validate_on_submit():
        days = [form.day_0.data,
                form.day_1.data,
                form.day_2.data,
                form.day_3.data,
                form.day_4.data,
                form.day_5.data,
                form.day_6.data]
        schedule = StaffSchedule(
            cid=current_user.cid,
            staff_id=id,
            location_id=form.location.data,
            date_from=form.date_from.data,
            date_to=form.date_to.data,
            time_from=form.time_from.data,
            time_to=form.time_to.data,
            weekdays=convert_weekdays_to_str(days),
            no_active=form.no_active.data
        )
        db.session.add(schedule)
        db.session.commit()
        return redirect(url_back)
    else:
        form.staff.default = id
        if request.method == 'POST':
            form.location.default = form.location.data
        form.process()
    return render_template('staff_schedule_form.html',
                           title='Schedule (create)',
                           form=form,
                           url_back=url_back)


@app.route('/staff/<staff_id>/schedule/edit/<id>', methods=['GET', 'POST'])
@login_required
def staff_schedule_edit(staff_id, id):
    url_back = url_for('staff_schedule', id=staff_id, **request.args)
    schedule = StaffSchedule.query.filter_by(cid=current_user.cid,
                                             id=id).first_or_404(id)
    form = StaffScheduleForm()
    form.staff.choices = get_active_staff()
    form.staff.validate_choice = False
    form.staff.render_kw = {'disabled': 'True'}
    form.location.choices = get_active_locations()
    if form.validate_on_submit():
        days = [form.day_0.data,
                form.day_1.data,
                form.day_2.data,
                form.day_3.data,
                form.day_4.data,
                form.day_5.data,
                form.day_6.data]
        schedule.location_id = form.location.data
        schedule.date_from = form.date_from.data
        schedule.date_to = form.date_to.data
        schedule.time_from = form.time_from.data
        schedule.time_to = form.time_to.data
        schedule.weekdays = convert_weekdays_to_str(days)
        schedule.no_active = form.no_active.data
        db.session.commit()
        return redirect(url_back)
    else:
        form.staff.default = schedule.staff_id
        form.location.default = schedule.location_id
        form.process()
        if request.method == 'GET':
            form.date_from.data = schedule.date_from
            form.date_to.data = schedule.date_to
            form.time_from.data = schedule.time_from
            form.time_to.data = schedule.time_to
            form.no_active.data = schedule.no_active
            weekdays = convert_str_to_weekdays(schedule.weekdays)
            form.day_0.data = weekdays[0]
            form.day_1.data = weekdays[1]
            form.day_2.data = weekdays[2]
            form.day_3.data = weekdays[3]
            form.day_4.data = weekdays[4]
            form.day_5.data = weekdays[5]
            form.day_6.data = weekdays[6]
    return render_template('staff_schedule_form.html',
                           title='Schedule (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/staff/<staff_id>/schedule/delete/<id>')
@login_required
def staff_schedule_delete(staff_id, id):
    url_back = url_for('staff_schedule', id=staff_id, **request.args)
    if not check_permission('StaffSchedule', 'delete'):
        flash('Insufficient access level')
        return redirect(url_back)
    schedule = StaffSchedule.query.filter_by(cid=current_user.cid,
                                             id=id).first_or_404()
    db.session.delete(schedule)
    db.session.commit()
    flash('Delete schedule {}'.format(id))
    return redirect(url_for('staff_schedule', id=staff_id))


# Staff block end


# Client block start
@app.route('/clients/')
@login_required
def clients():
    page = request.args.get('page', 1, type=int)
    items = Client.query.filter_by(
        cid=current_user.cid).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('client_table.html',
                           title='Clients',
                           items=items.items,
                           pagination=items)


@app.route('/clients/create/', methods=['GET', 'POST'])
@login_required
def client_create():
    url_back = url_for('clients', **request.args)
    form = ClientForm()
    if form.validate_on_submit():
        client = Client(cid=current_user.cid,
                        name=form.name.data,
                        phone=form.phone.data,
                        info=form.info.data,
                        no_active=form.no_active.data)
        db.session.add(client)
        db.session.commit()
        return redirect(url_for('clients'))
    return render_template('data_form.html',
                           title='Client (create)',
                           form=form,
                           url_back=url_back)


@app.route('/clients/edit/<id>/', methods=['GET', 'POST'])
@login_required
def client_edit(id):
    url_back = url_for('clients', **request.args)
    form = ClientForm()
    client = Client.query.filter_by(cid=current_user.cid,
                                    id=id).first_or_404()
    if form.validate_on_submit():
        client.name = form.name.data
        client.phone = form.phone.data
        client.info = form.info.data
        client.no_active = form.no_active.data
        db.session.commit()
        return redirect(url_for('clients'))
    elif request.method == 'GET':
        form = ClientForm(obj=client)
    return render_template('data_form.html',
                           title='Client (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/client/delete/<id>/', methods=['GET', 'POST'])
@login_required
def client_delete(id):
    if not check_permission('Client', 'delete'):
        flash('Insufficient access level')
        return redirect(url_for('clients'))
    service = Client.query.filter_by(cid=current_user.cid,
                                     id=id).first_or_404()
    db.session.delete(service)
    db.session.commit()
    flash('Delete client {}'.format(id))
    return redirect(url_for('clients'))


@app.route('/clients/<id>/files/', methods=['GET', 'POST'])
@login_required
def client_files(id):
    page = request.args.get('page', 1, type=int)
    items = ClientFile.query.filter_by(
        cid=current_user.id, client_id=id).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('client_files_table.html',
                           id=id,
                           title='Files',
                           items=items.items,
                           pagination=items)


@app.route('/clients/<id>/upload_file/', methods=['GET', 'POST'])
@login_required
def client_file_upload(id):
    url_back = url_for('client_files', id=id, **request.args)
    client = Client.query.filter_by(cid=current_user.cid,
                                    id=id).first_or_404()
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
    url_back = url_for('client_files', id=client_id, **request.args)
    file = ClientFile.query.filter_by(cid=current_user.cid,
                                      id=id).first()
    return send_file(file.path, as_attachment=True, download_name=file.name)


@app.route('/clients/<client_id>/delete_file/<id>/')
@login_required
def client_file_delete(client_id, id):
    url_back = url_for('client_files', id=client_id, **request.args)
    if not check_permission('ClientFile', 'delete'):
        flash('Insufficient access level')
        return redirect(url_back)
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


# Clients tag block start
@app.route('/clients_tags/')
@login_required
def clients_tags():
    page = request.args.get('page', 1, type=int)
    items = ClientTag.query.filter_by(
        cid=current_user.id).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('clients_tags_table.html',
                           id=id,
                           title='Clients tags',
                           items=items.items,
                           pagination=items)


@app.route('/clients_tags/create/', methods=['GET', 'POST'])
@login_required
def clients_tags_create():
    url_back = url_for('clients_tags', **request.args)
    form = ClientTagForm()
    if form.validate_on_submit():
        tag = ClientTag(cid=current_user.cid,
                        name=form.name.data)
        db.session.add(tag)
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'POST':
        return redirect(url_for('clients_tags_create'))
    else:
        return render_template('data_form.html',
                               title='Client tag (create)',
                               form=form,
                               url_back=url_back)


@app.route('/clients_tags/edit/<id>/', methods=['GET', 'POST'])
@login_required
def clients_tags_edit(id):
    url_back = url_for('clients_tags', **request.args)
    tag = ClientTag.query.filter_by(cid=current_user.cid,
                                    id=id).first_or_404()
    form = ClientTagForm()
    if form.validate_on_submit():
        tag.name = form.name.data
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form = ClientTagForm(obj=tag)
    return render_template('data_form.html',
                           title='Clients tag (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/clients_tags/delete/<id>/')
@login_required
def clients_tags_delete(id):
    url_back = url_for('clients_tags', **request.args)
    if not check_permission('ClientTag', 'delete'):
        flash('Insufficient access level')
        return redirect(url_back)
    tag = ClientTag.query.filter_by(cid=current_user.cid,
                                    id=id).first_or_404()
    db.session.delete(tag)
    db.session.commit()
    flash('Delete tag {}'.format(id))
    return redirect(url_back)
# Client tag block end


# Service block start
@app.route('/services/', methods=['GET', 'POST'])
@login_required
def services():
    page = request.args.get('page', 1, type=int)
    appointment_id = request.args.get('appointment_id', None, type=int)
    url_back = request.args.get('url_back', url_for('appointments'))
    if appointment_id:
        appointment = Appointment.query.filter_by(
            cid=current_user.cid, id=appointment_id).first_or_404()
        session['services'] = [str(s.id) for s in appointment.services]
    if 'edit' in url_back:
        url_submit = url_back + '?mod_services=1'
    else:
        url_submit = url_for('appointment_create')
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
    items = Service.query.filter(*param).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template(template,
                           title='Services',
                           items=items.items,
                           pagination=items,
                           url_back=url_back,
                           url_submit=url_submit)


@app.route('/services/create/', methods=['GET', 'POST'])
@login_required
def service_create():
    url_back = url_for('services', **request.args)
    form = ServiceForm()
    form.location.choices = get_active_locations(multi=True)
    if form.validate_on_submit():
        service = Service(cid=current_user.cid,
                          name=form.name.data,
                          duration=form.duration.data,
                          price=form.price.data,
                          no_active=form.no_active.data)
        db.session.add(service)
        db.session.flush()
        for location_id in form.location.data:
            location = Location.query.get_or_404(location_id)
            location.add_service(service)
        db.session.commit()
        return redirect(url_for('services'))
    return render_template('data_form.html',
                           title='Service (create)',
                           form=form,
                           url_back=url_back)


@app.route('/services/edit/<id>/', methods=['GET', 'POST'])
@login_required
def service_edit(id):
    url_back = url_for('services', **request.args)
    form = ServiceForm()
    form.location.choices = get_active_locations(multi=True)
    service = Service.query.filter_by(cid=current_user.cid,
                                      id=id).first_or_404()
    if form.validate_on_submit():
        service.name = form.name.data
        service.duration = form.duration.data
        service.price = form.price.data
        service.no_active = form.no_active.data
        service.locations.clear()
        for location_id in form.location.data:
            location = Location.query.get_or_404(location_id)
            location.add_service(service)
        db.session.commit()
        return redirect(url_for('services'))
    elif request.method == 'GET':
        form.location.default = [s.id for s in service.locations]
        form.process()
        form.name.data = service.name
        form.duration.data = service.duration
        form.price.data = service.price
        form.no_active.data = service.no_active
    return render_template('data_form.html',
                           title='Service (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/service/delete/<id>/', methods=['GET', 'POST'])
@login_required
def service_delete(id):
    if not check_permission('Service', 'delete'):
        flash('Insufficient access level')
        return redirect(url_for('services'))
    service = Service.query.filter_by(cid=current_user.cid,
                                      id=id).first_or_404()
    db.session.delete(service)
    db.session.commit()
    flash('Delete service {}'.format(id))
    return redirect(url_for('services'))
# Service block end


# Location block start
@app.route('/locations/')
@login_required
def locations():
    page = request.args.get('page', 1, type=int)
    items = Location.query.filter_by(
        cid=current_user.cid).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('location_table.html',
                           title='Locations',
                           items=items.items,
                           pagination=items)


@app.route('/locations/create/', methods=['GET', 'POST'])
@login_required
def location_create():
    url_back = url_for('locations', **request.args)
    if get_tariff_limit('location') == 0:
        return redirect(url_for('locations'))
    form = LocationForm()
    if form.validate_on_submit():
        location = Location(cid=current_user.cid,
                            name=form.name.data,
                            phone=form.phone.data,
                            address=form.address.data,
                            open=form.open.data,
                            close=form.close.data,
                            no_active=form.no_active.data)
        db.session.add(location)
        db.session.commit()
        return redirect(url_for('locations'))
    return render_template('data_form.html',
                           title='Location (create)',
                           form=form,
                           url_back=url_back)


@app.route('/locations/edit/<id>/', methods=['GET', 'POST'])
@login_required
def location_edit(id):
    url_back = url_for('locations', **request.args)
    form = LocationForm()
    location = Location.query.filter_by(cid=current_user.cid,
                                        id=id).first_or_404()
    if form.validate_on_submit():
        location.name = form.name.data
        location.address = form.address.data
        location.open = form.open.data
        location.close = form.close.data
        location.no_active = form.no_active.data
        db.session.commit()
        return redirect(url_for('locations'))
    elif request.method == 'GET':
        form = LocationForm(obj=location)
    return render_template('data_form.html',
                           title='Location (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/locations/delete/<id>/', methods=['GET', 'POST'])
@login_required
def location_delete(id):
    if not check_permission('Location', 'delete'):
        flash('Insufficient access level')
        return redirect(url_for('locations'))
    location = Location.query.filter_by(cid=current_user.cid,
                                        id=id).first_or_404()
    db.session.delete(location)
    db.session.commit()
    flash('Delete location {}'.format(id))
    return redirect(url_for('locations'))
# Location block end


# Appointment block start
@app.route('/appointments/')
@login_required
def appointments():
    form = SearchForm()
    form.location_id.choices = get_active_locations()
    form.location_id.render_kw = {'onchange': 'this.form.submit()'}
    form.staff_id.choices = get_active_staff()
    form.staff_id.render_kw = {'onchange': 'this.form.submit()'}
    form.client_id.choices = get_active_clients()
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
    items = Appointment.query.filter_by(**param).order_by(
        Appointment.date_time.desc(), Appointment.location_id).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('timetable.html',
                           title='Appointments',
                           items=items.items,
                           pagination=items,
                           form=form)


@app.route('/appointments/create/', methods=['GET', 'POST'])
@login_required
def appointment_create():
    url_back = url_for('appointments', **request.args)
    form = AppointmentForm()
    form.location.choices = get_active_locations()
    form.staff.choices = get_active_staff()
    form.client.choices = get_active_clients()
    selected_services_id = session.get('services', [])
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
        # services = form.service.data
        for service in selected_services:
            appointment.add_service(service)
        session.pop('services')
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'POST':
        form.location.default = form.location.data
        form.staff.default = form.staff.data
        form.client.default = form.client.data
        # services = form.service.data
        # if form.location.data is not None and form.location.data != 0:
        #     form.service.choices = get_active_services(
        #         location_id=form.location.data,
        #         multi=True)
        # form.service.default = services
        # form.process()
    else:
        if request.args.get('client', None):
            form.client.default = request.args.get('client')
            form.process()
    return render_template('appointment_form.html',
                           title='Appointment (create)',
                           form=form,
                           items=selected_services,
                           url_back=url_back)

#
# @app.route('/select_service/<service_id>/')
# @login_required
# def select_service(service_id):
#     url_back = request.args.get('url_back')
#     mod_services = request.args.get('mod_services')
#     services_id = session.get('services', [])
#     if str(service_id) not in services_id:
#         services_id.append(service_id)
#         session['services'] = services_id
#     return redirect(url_for('services',
#                             choice_mode=1,
#                             url_back=url_back,
#                             mod_services=mod_services))
#
#
# @app.route('/unselect_service/<service_id>/')
# @login_required
# def unselect_service(service_id):
#     url_back = request.args.get('url_back')
#     mod_services = request.args.get('mod_services')
#     services_id = session.get('services', [])
#     if str(service_id) in services_id:
#         services_id.remove(str(service_id))
#         session['services'] = services_id
#     return redirect(url_for('services',
#                             choice_mode=1,
#                             url_back=url_back,
#                             mod_services=mod_services))


# @app.route('/cancel_services/')
# @login_required
# def cancel_services():
#     url_back = request.args.get('url_back', url_for('appointment_create'))
#     if 'services' in session:
#         session.pop('services')
#     return redirect(url_for('services', choice_mode=1, url_back=url_back))


@app.route('/services/<location_id>/')
@login_required
def services_location(location_id):
    if location_id == 0 or location_id is None:
        return jsonify({'services': []})
    items = get_active_services(location_id=location_id, queryset=True)
    services = []
    for item in items:
        service = {'id': item.id, 'name': '{} ({} min)'.format(
            item.name, item.duration)}
        services.append(service)
    return jsonify({'services': services})


@app.route('/locations/<service_id>/')
@login_required
def locations_service(service_id):
    service = Service.query.get(service_id)
    items = list(filter(lambda x:
                        not x.no_active and
                        x.cid == current_user.cid, service.locations))
    locations = [{'id': 0, 'name': '-Select-'}]
    for item in items:
        location = {'id': item.id, 'name': item.name}
        locations.append(location)
    return jsonify({'locations': locations})


@app.route('/appointments/edit/<id>/', methods=['GET', 'POST'])
@login_required
def appointment_edit(id):
    appointment = Appointment.query.filter_by(cid=current_user.cid,
                                              id=id).first_or_404()
    param_url = {**request.args}
    param_url.pop('mod_services', None)
    url_back = url_for('appointments', **param_url)
    mod_services = request.args.get('mod_services', None) and 'services' in session
    if mod_services:
        selected_services_id = session.get('services')
        url_select_service = url_for('services',
                                     choice_mode=1,
                                     url_back=request.path)
    else:
        selected_services_id = [s.id for s in appointment.services]
        url_select_service = url_for('services',
                                     choice_mode=1,
                                     appointment_id=id,
                                     url_back=request.path)
    selected_services = []
    for service_id in selected_services_id:
        service = Service.query.get_or_404(service_id)
        selected_services.append(service)
    form = AppointmentForm(appointment)
    form.duration.data = get_duration(selected_services_id)
    form.location.choices = get_active_locations()
    form.staff.choices = get_active_staff()
    form.client.choices = get_active_clients()
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
        # services = form.service.data
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
        # services = form.service.data
        # if form.location.data is not None and form.location.data != 0:
        #     form.service.choices = get_active_services(
        #         location_id=form.location.data,
        #         multi=True)
        #     form.service.default = services
        # else:
        #     form.service.choices = get_active_services(
        #         location_id=appointment.location_id,
        #         multi=True)
        #     form.service.default = [s.id for s in appointment.services]
        form.process()
    else:
        form.location.default = appointment.location_id
        form.staff.default = appointment.staff_id
        form.client.default = appointment.client_id
        # form.service.choices = get_active_services(
        #     location_id=appointment.location_id,
        #     multi=True)
        # form.service.default = [s.id for s in appointment.services]
        form.process()
        form.date.data = appointment.date_time.date()
        form.time.data = appointment.date_time.time()
        form.info.data = appointment.info
        form.cancel.data = appointment.cancel
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
    if not check_permission('Appointment', 'delete'):
        flash('Insufficient access level')
        return redirect(url_for('appointments'))
    appointment = Appointment.query.filter_by(cid=current_user.cid,
                                              id=id).first_or_404()
    db.session.delete(appointment)
    db.session.commit()
    flash('Delete appointment {}'.format(id))
    return redirect(url_for('appointments'))


@app.route('/appointments/<appointment_id>/result/', methods=['GET', 'POST'])
@login_required
def appointment_result(appointment_id):
    url_back = request.args.get('url_back', url_for('appointments', **request.args))
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
def items():
    page = request.args.get('page', 1, type=int)
    items = Item.query.filter_by(cid=current_user.cid).paginate(
        page, app.config['ROWS_PER_PAGE'], False)
    return render_template('item_table.html',
                           title='Items',
                           items=items.items,
                           pagination=items)


@app.route('/items/create', methods=['GET', 'POST'])
@login_required
def item_create():
    url_back = url_for('items', **request.args)
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
    url_back = url_for('items', **request.args)
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
    if not check_permission('Item', 'delete'):
        flash('Insufficient access level')
        return redirect(url_for('items'))
    item = Item.query.filter_by(cid=current_user.cid,
                                id=id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash('Delete item {}'.format(id))
    return redirect(url_for('items'))


# Item block end


# ItemFlow block start
@app.route('/items_flow/')
@login_required
def items_flow():
    page = request.args.get('page', 1, type=int)
    param = {'cid': current_user.cid}
    select_item = request.args.get('item_id', 0, type=int)
    if select_item > 0:
        param['item_id'] = select_item
    items = ItemFlow.query.filter_by(**param).paginate(
        page, app.config['ROWS_PER_PAGE'], False)

    return render_template('item_flow_table.html',
                           title='Items flow',
                           items=items.items,
                           pagination=items)


@app.route('/items_flow/create', methods=['GET', 'POST'])
@login_required
def item_flow_create():
    url_back = url_for('items_flow', **request.args)
    item_id = request.args.get('item_id')
    form = ItemFlowForm()
    form.location.choices = get_active_locations()
    form.item.choices = get_active_items()
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
    url_back = url_for('items_flow', **request.args)
    item_flow = ItemFlow.query.filter_by(cid=current_user.cid,
                                         id=id).first_or_404()
    form = ItemFlowForm(item_flow.location_id,
                        item_flow.item_id,
                        item_flow.quantity)
    form.location.choices = get_active_locations()
    form.item.choices = get_active_items()
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
    if not check_permission('ItemFlow', 'delete'):
        flash('Insufficient access level')
        return redirect(url_for('items_flow'))
    item_flow = ItemFlow.query.filter_by(cid=current_user.cid,
                                         id=id).first_or_404()
    db.session.delete(item_flow)
    storage = Storage.query.filter_by(cid=current_user.cid,
                                      location_id=item_flow.location_id,
                                      item_id=item_flow.item_id).first()
    storage.quantity -= item_flow.quantity
    db.session.commit()
    flash('Delete item flow {}'.format(id))
    return redirect(url_for('items_flow'))


# ItemFlow block end


# Notice block start
@app.route('/notices/')
@login_required
def notices():
    page = request.args.get('page', 1, type=int)
    client_id = request.args.get('client_id', None)
    param = {'cid': current_user.cid}
    if client_id:
        param['client_id'] = client_id
    items = Notice.query.filter_by(**param).paginate(
        page, app.config['ROWS_PER_PAGE'], False)

    return render_template('notice_table.html',
                           title='Notices',
                           items=items.items,
                           pagination=items)


@app.route('/notice/create/', methods=['GET', 'POST'])
@login_required
def notice_create():
    url_back = request.args.get('url_back', url_for('notices', **request.args))
    client_id = request.args.get('client_id', None)
    form = NoticeForm()
    form.client.choices = get_active_clients()
    if form.validate_on_submit():
        notice = Notice(cid=current_user.cid,
                        client_id=form.client.data,
                        date=form.date.data,
                        description=form.description.data,
                        no_active=form.no_active.data)
        db.session.add(notice)
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'POST':
        form.client.default = form.client.data
    else:
        if client_id:
            form.client.default = client_id
            form.process()
    return render_template('data_form.html',
                           title='Notice (create)',
                           form=form,
                           url_back=url_back)


@app.route('/notice/edit/<id>/', methods=['GET', 'POST'])
@login_required
def notice_edit(id):
    url_back = request.args.get('url_back', url_for('notices',
                                                    **request.args))
    notice = Notice.query.filter_by(cid=current_user.cid,
                                    id=id).first_or_404()
    form = NoticeForm()
    form.client.choices = get_active_clients()
    if form.validate_on_submit():
        notice.client_id = form.client.data
        notice.date = form.date.data
        notice.description = form.description.data
        notice.no_active = form.no_active.data
        db.session.commit()
        return redirect(url_back)
    elif request.method == 'GET':
        form.client.default = notice.client_id
        form.process()
        form.date.data = notice.date
        form.description.data = notice.description
        form.no_active.data = notice.no_active
    return render_template('data_form.html',
                           title='Notice (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/notice/delete/<id>/')
@login_required
def notice_delete(id):
    url_back = url_for('notices', **request.args)
    if not check_permission('Notice', 'delete'):
        flash('Insufficient access level')
        return redirect(url_back)
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
def cash_flow():
    page = request.args.get('page', 1, type=int)
    param = {'cid': current_user.cid}
    items = CashFlow.query.filter_by(**param).paginate(
        page, app.config['ROWS_PER_PAGE'], False)

    return render_template('cash_flow_table.html',
                           title='Cash flow',
                           items=items.items,
                           pagination=items)


@app.route('/cash_flow/create', methods=['GET', 'POST'])
@login_required
def cash_flow_create():
    url_back = request.args.get('url_back', url_for('cash_flow',
                                                    **request.args))
    appointment_id = request.args.get('appointment_id')
    appointment = Appointment.query.filter_by(cid=current_user.cid,
                                              id=appointment_id).first_or_404()
    if appointment.payment_id:
        return redirect(url_for('cash_flow_edit', id=appointment.payment_id,
                                **request.args))
    form = CashFlowForm()
    form.location.choices = get_active_locations()
    if form.validate_on_submit():
        cash_flow = CashFlow(cid=current_user.cid,
                             location_id=form.location.data,
                             date=form.date.data,
                             description=form.description.data,
                             sum=form.sum.data * form.action.data)
        db.session.add(cash_flow)
        cash = Cash.query.filter_by(cid=current_user.cid,
                                    location_id=form.location.data
                                    ).first()
        if cash:
            cash.sum += form.sum.data * form.action.data
        else:
            cash = Cash(cid=current_user.cid,
                        location_id=form.location.data,
                        sum=form.sum.data * form.action.data)
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
            sum = appointment.sum()
            form.location.default = location_id
            form.process()
            form.date.data = date
            form.sum.data = sum
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
    url_back = request.args.get('url_back', url_for('cash_flow',
                                                    **request.args))
    cash_flow = CashFlow.query.filter_by(cid=current_user.cid,
                                         id=id).first_or_404()
    form = CashFlowForm()
    form.location.choices = get_active_locations()
    if form.validate_on_submit():
        current_location = cash_flow.location_id
        current_sum = cash_flow.sum
        cash_flow.location_id = form.location.data
        cash_flow.description = form.description.data
        cash_flow.date = form.date.data
        cash_flow.sum = form.sum.data * form.action.data
        current_cash = Cash.query.filter_by(cid=current_user.cid,
                                            location_id=current_location
                                            ).first()
        current_cash.sum -= current_sum
        cash = Cash.query.filter_by(cid=current_user.cid,
                                    location_id=form.location.data
                                    ).first()
        if cash:
            cash.sum += form.sum.data * form.action.data
        else:
            cash = Cash(cid=current_user.cid,
                        location_id=form.location.data,
                        sum=form.sum.data * form.action.data)
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
        form.sum.data = abs(cash_flow.sum)
        form.action.data = cash_flow.sum / abs(cash_flow.sum)
    return render_template('data_form.html',
                           title='Cash flow (edit)',
                           form=form,
                           url_back=url_back)


@app.route('/cash_flow/delete/<id>')
@login_required
def cash_flow_delete(id):
    if not check_permission('CashFlow', 'delete'):
        flash('Insufficient access level')
        return redirect(url_for('cash_flow'))
    cash_flow = CashFlow.query.filter_by(cid=current_user.cid,
                                         id=id).first_or_404()
    db.session.delete(cash_flow)
    cash = Cash.query.filter_by(cid=current_user.cid,
                                location_id=cash_flow.location_id
                                ).first()
    cash.sum -= cash_flow.sum
    db.session.commit()
    flash('Delete cash flow {}'.format(id))
    return redirect(url_for('cash_flow'))
# CashFlow block end


@app.route('/select_service/<service_id>/<selected>/')
@login_required
def select_checkbox(service_id, selected):
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
