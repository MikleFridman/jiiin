import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config():
    SECRET_KEY = os.environ.get('SECRET_KEY') or '69d5708f91ffe3d0e6bfeb7be62858c0a1b83aa1'
    SQLALCHEMY_DATABASE_URI = (os.environ.get('DATABASE_URL') or
                               'sqlite:///' + os.path.join(basedir, 'app.db'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BOOTSTRAP_SERVE_LOCAL = True
    BOOTSTRAP_BOOTSWATCH_THEME = 'spacelab'
    ROWS_PER_PAGE = 10
    LANGUAGES = ['en', 'ru', 'he']

    MAIL_SERVER = 'smtp.googlemail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'mikle.fridman@gmail.com'
    MAIL_DEFAULT_SENDER = 'mikle.fridman@gmail.com'
    MAIL_PASSWORD = 'xclvwfrftcbcruvi'
    ADMINS = ['mikle.fridman@gmail.com']
    UPLOAD_FOLDER = (os.environ.get('UPLOAD_FOLDER') or
                     os.path.join(basedir, 'upload'))
    UPLOAD_EXTENSIONS = ['.jpg',
                         '.jpeg',
                         '.png',
                         '.xls',
                         '.xlsx',
                         '.doc',
                         '.docx',
                         '.pdf']
    MAX_CONTENT_LENGTH = 1024 * 1024
