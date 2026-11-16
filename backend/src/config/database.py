from sqlalchemy import create_engine,text,inspect
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .settings import DATABASE_URL
engine=create_engine(DATABASE_URL,pool_pre_ping=True)
SessionLocal=sessionmaker(bind=engine,expire_on_commit=False)
class Base(DeclarativeBase): pass
def session():
    with SessionLocal() as db: yield db
def ensure_run_type_column():
    """create_all不改已存在的表；为既有库幂等补association_runs.run_type列。

    历史研究默认layerwise_exact（原全层检验），不追补区间扫描结果。
    """
    inspector=inspect(engine)
    if 'association_runs' not in inspector.get_table_names():
        return
    if 'run_type' not in {col['name'] for col in inspector.get_columns('association_runs')}:
        with engine.begin() as db:
            db.execute(text(
                "ALTER TABLE association_runs "
                "ADD COLUMN run_type VARCHAR(32) NOT NULL DEFAULT 'layerwise_exact'"
            ))
