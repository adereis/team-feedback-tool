"""
Import orgchart CSV export into feedback database

Usage:
    python3 scripts/import_orgchart.py REAL-orgchart-export.csv
"""

import sys
import os
import csv

# Add parent directory to path for imports when running as standalone script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Import orgchart CSV export into feedback database.',
        epilog='''
Example:
  python3 scripts/import_orgchart.py samples/sample-orgchart.csv

The CSV file should have columns: User ID, Name, Job Title, Location, Email, Manager UID
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'csv_file',
        help='Path to the orgchart CSV file to import'
    )
    parser.add_argument(
        '--db',
        default='feedback.db',
        help='Path to database file (default: feedback.db)'
    )

    args = parser.parse_args()
    import_orgchart(args.csv_file, args.db)


if __name__ == '__main__':
    main()
