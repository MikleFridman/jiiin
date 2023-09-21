from flask import url_for, request, redirect
from flask_admin import AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from werkzeug.urls import url_parse

from app import app


class MyAdminView(AdminIndexView):

    def is_accessible(self):
        if not current_user.is_authenticated:
            return False
        if not app.config.get('ALLOW_ADMIN_VIEW', False):
            return False
        return current_user.check_permission('AdminView', 'read')

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login', next=url_parse(request.url).path))


class MyModelView(ModelView):
    def is_accessible(self):
        if not current_user.is_authenticated:
            return False
        if not app.config.get('ALLOW_ADMIN_VIEW', False):
            return False
        return current_user.check_permission('AdminView', 'read')

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login', next=url_parse(request.url).path))


class UserAdminView(MyModelView):
    column_exclude_list = ['password_hash', 'info']
    form_excluded_columns = ['password_hash', 'tasks', 'files']


class TariffAdminView(MyModelView):
    form_excluded_columns = ['companies']


class CompanyAdminView(MyModelView):
    column_exclude_list = ['info']
    form_excluded_columns = ['staff',
                             'clients',
                             'services',
                             'locations',
                             'notices',
                             'cash',
                             'cash_flow',
                             'holidays',
                             'client_files',
                             'tags',
                             'appointments']
