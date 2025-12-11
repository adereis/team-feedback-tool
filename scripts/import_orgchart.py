"""
Import orgchart CSV export into feedback database

Usage:
    python3 import_orgchart.py REAL-orgchart-export.csv
"""

import sys
import csv
from models import init_db, Person


def import_orgchart(csv_path, db_path='feedback.db'):
    """Import orgchart CSV into database"""
    session = init_db(db_path)

    # Clear existing persons (fresh import)
    session.query(Person).delete()

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        count = 0

        for row in reader:
            person = Person(
                user_id=row['User ID'],
                name=row['Name'],
                job_title=row['Job Title'],
                location=row['Location'],
                email=row['Email'],
                manager_uid=row['Manager UID'] if row['Manager UID'] else None
            )
            session.add(person)
            count += 1

    session.commit()
    print(f"✓ Imported {count} people from {csv_path}")

    # Show summary
    managers = session.query(Person).filter(Person.direct_reports.any()).all()
    print(f"✓ Found {len(managers)} managers")

    session.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 import_orgchart.py <orgchart.csv>")
        sys.exit(1)

    import_orgchart(sys.argv[1])
