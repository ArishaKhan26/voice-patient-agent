"""Creates the patients table (and any future tables) from the SQLAlchemy
models. Run once: source venv/bin/activate && python -m app.init_db
"""
from app.database import Base, engine
from app.models import Patient  # noqa: F401 - registers the model with Base

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("OK: tables created (or already existed)")
