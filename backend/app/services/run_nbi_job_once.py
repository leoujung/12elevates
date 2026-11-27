"""One-shot runner: execute the NBI business matching job for ONE member, print counts only.

Usage (inside the image, env provided by the caller, never printed):
  python -m app.services.run_nbi_job_once <member_id>
"""
import sys

from sqlalchemy.orm import sessionmaker

from app.core.db import make_engine
from app.services.nbi_matching_job import run_business_job


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_nbi_job_once <member_id>")
        return 2
    member_id = sys.argv[1]
    engine = make_engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        out = run_business_job(db, member_id)
        db.commit()
        print({k: v for k, v in out.items() if k != "job_id"})
        print("job_id_prefix", out["job_id"][:8])
        return 0
    except Exception as exc:  # no PII in message: only exception type
        db.rollback()
        print("job_failed", type(exc).__name__)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
