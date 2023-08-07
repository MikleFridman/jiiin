from datetime import datetime, timedelta

from flask import g, jsonify, request, session, url_for
from flask_login import current_user

from app import app, db, csrf
from app.errors import error_response
from app.functions import get_free_time_intervals, time_in_intervals, get_duration
from app.models import Location, Staff, Service, Appointment
from app.auth import basic_auth, token_auth


@app.route('/api/get_token/')
@basic_auth.login_required
def api_get_token():
    token = g.current_user.get_token()
    db.session.commit()
    return jsonify({'token': token})


@app.route('/api/get_locations/')
@token_auth.login_required
def api_get_locations():
    locations = {}
    for location in Location.get_items():
        data = location.get_dict()
        locations[location.name] = data
    return jsonify(locations)


@app.route('/api/get_staff/')
@token_auth.login_required
def api_get_staff():
    staff = {}
    for worker in Staff.get_items():
        data = worker.get_dict()
        staff[worker.name] = data
    return jsonify(staff)


@app.route('/api/get_services/')
@token_auth.login_required
def api_get_services():
    services = {}
    for service in Service.get_items():
        data = service.get_dict()
        services[service.name] = data
    return jsonify(services)


@csrf.exempt
@app.route('/api/get_free_time_intervals/', methods=['POST'])
@token_auth.login_required
def api_get_free_time_intervals():
    data = request.get_json() or None
    if 'location_id' not in data:
        return error_response(400, message='Data must include location_id')
    if 'staff_id' not in data:
        return error_response(400, message='Data must include staff_id')
    if 'date' not in data:
        return error_response(400, message='Data must include date')
    if 'duration' not in data:
        return error_response(400, message='Data must include duration')
    intervals = get_free_time_intervals(data['location_id'],
                                        datetime.strptime(data['date'], '%Y-%m-%d'),
                                        data['staff_id'],
                                        timedelta(minutes=int(data['duration'])))
    return jsonify(intervals)


@csrf.exempt
@app.route('/api/create_appointment/', methods=['POST'])
@token_auth.login_required
def api_create_appointment():
    data = request.get_json() or None
    if 'location_id' not in data:
        return error_response(400, message='Data must include location_id')
    if 'staff_id' not in data:
        return error_response(400, message='Data must include staff_id')
    if 'client_id' not in data:
        return error_response(400, message='Data must include client_id')
    if 'date_time' not in data:
        return error_response(400, message='Data must include date_time')
    if 'services_id' not in data:
        return error_response(400, message='Data must include services')
    dt = datetime.strptime(data['date_time'], '%Y-%m-%d %H:%M')
    services = data['services_id'].split(';')
    intervals = get_free_time_intervals(data['location_id'],
                                        dt.date(),
                                        data['staff_id'],
                                        get_duration(services))
    if not intervals or not time_in_intervals(dt, intervals):
        return error_response(400, message='No free time')
    appointment = Appointment(cid=current_user.cid,
                              location_id=int(data['location_id']),
                              date_time=dt,
                              client_id=int(data['client_id']),
                              staff_id=int(data['staff_id']))
    db.session.add(appointment)
    db.session.flush()
    for service_id in services:
        service = Service.get_object(int(service_id))
        appointment.add_service(service)
    db.session.commit()
    response = jsonify(appointment.get_dict())
    response.status_code = 201
    response.location = url_for('api_get_appointment', id=appointment.id)
    return response


@app.route('/api/get_appointment/<id>')
@token_auth.login_required
def api_get_appointment(id):
    appointment = Appointment.get_object(id)
    return jsonify(appointment.get_dict())
