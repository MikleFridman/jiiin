from flask import url_for, request, redirect
from flask_admin import AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from werkzeug.urls import url_parse

from app.functions import check_permission


class MyAdminView(AdminIndexView):
    def is_accessible(self):
        if not current_user.is_authenticated:
            return False
        return check_permission('Admin', 'read')

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login', next=url_parse(request.url).path))


class MyModelView(ModelView):
    def is_accessible(self):
        if not current_user.is_authenticated:
            return False
        return check_permission('Admin', 'read')

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login', next=url_parse(request.url).path))


class UserAdminView(MyModelView):
    column_exclude_list = ['password_hash', 'info']
    form_excluded_columns = ['password_hash', 'tasks', 'files']


class CompanyAdminView(MyModelView):
    column_exclude_list = ['info']
    form_excluded_columns = ['staff', 'clients', 'services', 'locations', 'appointments']
