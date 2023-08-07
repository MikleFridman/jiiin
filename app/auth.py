from flask import g
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth
from flask_login import login_user

from app.models import User
from app.errors import error_response

basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth()


@basic_auth.verify_password
def verify_password(login, password):
    user = User.query.filter_by(username=login).first()
    if not user:
        return False
    g.current_user = user
    return user.check_password(password)


@basic_auth.error_handler
def basic_auth_error():
    return error_response(401)


@token_auth.verify_token
def verify_token(token):
    g.current_user = User.check_token(token) if token else None
    if g.current_user:
        login_user(g.current_user)
    return g.current_user is not None


@token_auth.error_handler
def token_auth_error():
    return error_response(401)
