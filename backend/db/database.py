
from sqlmodel import SQLModel, create_engine, Session

# Database setup
sqlite_file_name = "inkflow.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})


def create_db_and_tables():
    """Create database tables."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Get DB session."""
    with Session(engine) as session:
        yield session
