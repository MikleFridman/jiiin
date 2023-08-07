import os

from dotenv import load_dotenv
from flask import Flask
from flask_admin.menu import MenuLink
from flask_babel import Babel, lazy_gettext as _l
from flask_login import LoginManager
from flask_mail import Mail
from flask_admin import Admin

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
csrf = CSRFProtect(app)
login = LoginManager(app)
login.login_message = _l('Please log in to access this page')
login.login_view = 'login'
mail = Mail(app)
babel = Babel(app)

from app import views, models, errors, api
from app.models import *
from app.admin import *
from .bot import send_bot_message
admin = Admin(app, name="Jiiin", index_view=MyAdminView())
admin.add_view(CompanyAdminView(Company, db.session))
admin.add_view(MyModelView(CompanyConfig, db.session))
admin.add_view(MyModelView(Tariff, db.session))
admin.add_view(UserAdminView(User, db.session))
admin.add_view(MyModelView(Role, db.session))
admin.add_view(MyModelView(Permission, db.session))
with app.test_request_context():
    admin.add_link(MenuLink(name=_l('Go to site'), url=url_for('index')))


@babel.localeselector
def get_locale():
    if current_user.is_authenticated and current_user.language:
        return current_user.language
    return request.accept_languages.best_match(app.config['LANGUAGES'].keys())
