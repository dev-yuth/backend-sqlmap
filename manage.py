# manage.py
from app import create_app
from app.extensions import db
from flask_migrate import Migrate

app = create_app()
migrate = Migrate(app, db)
print("manage.py imported - creating app and migrate")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
