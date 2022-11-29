from app import app
from app.models import *


@app.shell_context_processor
def make_shell_context():
    return {'db': db,
            'User': User,
            'Role': Role,
            'Company': Company,
            'CompanyConfig': CompanyConfig,
            'Tariff': Tariff,
            'Service': Service,
            'Location': Location,
            'Appointment': Appointment,
            'Item': Item,
            'Storage': Storage,
            'ItemFlow': ItemFlow,
            }


if __name__ == '__main__':
    app.run()
