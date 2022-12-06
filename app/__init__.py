import os

from dotenv import load_dotenv
from flask import Flask, redirect, url_for, request
from flask_admin.contrib.sqla import ModelView
from flask_babel import Babel
from flask_login import LoginManager
from flask_mail import Mail
from flask_moment import Moment
from flask_admin import Admin, AdminIndexView
from werkzeug.urls import url_parse

from config import Config
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_bootstrap import Bootstrap

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

app = Flask(__name__, static_folder='static', static_url_path='')
app.config.from_object(Config)
naming_convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}
db = SQLAlchemy(app=app, metadata=MetaData(naming_convention=naming_convention))
migrate = Migrate(app, db, render_as_batch=True)
bootstrap = Bootstrap(app)
csrf = CSRFProtect()
csrf.init_app(app)
login = LoginManager(app)
login.login_view = 'login'
moment = Moment(app)
babel = Babel(app)
mail = Mail(app)

from app import views, models, errors
from app.models import *
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
    column_exclude_list = ['password_hash']
    form_excluded_columns = ['password_hash']


admin = Admin(app, name="Workshop", index_view=MyAdminView())
admin.add_view(MyModelView(Company, db.session))
admin.add_view(MyModelView(CompanyConfig, db.session))
admin.add_view(MyModelView(Tariff, db.session))
admin.add_view(UserAdminView(User, db.session))
admin.add_view(MyModelView(Role, db.session))
admin.add_view(MyModelView(Permission, db.session))
