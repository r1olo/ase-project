# main Flask entrypoint
from app import create_app

app = create_app()

# run interactively if needed
if __name__ == "__main__":
    app.run()
