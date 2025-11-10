# main Flask entrypoint
from app import create_app_with_db

(app, db) = create_app_with_db()

# run interactively if needed
if __name__ == "__main__":
    app.run()
