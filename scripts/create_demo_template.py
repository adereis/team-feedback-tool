#!/usr/bin/env python3
"""
Create the demo template database for session-isolated demo mode.

This script generates a pre-populated SQLite database with fictitious data
that can be copied for each demo session. It includes:
- Person records (small team)
- Peer Feedback records
- Manager Feedback records
- Workday Feedback records (structured and generic)

Usage:
    python3 scripts/create_demo_template.py

Output:
    demo-templates/demo.db
"""

import os
import sys
import tempfile
import shutil

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import init_db
from create_sample_data import (
    get_small_team_data,
    write_orgchart_csv,
    generate_sample_feedback,
    generate_manager_feedback,
)
from import_orgchart import import_orgchart


def create_demo_template():
    """Create the demo template database with all sample data."""
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(script_dir, 'demo-templates')
    template_db = os.path.join(template_dir, 'demo.db')

    # Ensure template directory exists
    os.makedirs(template_dir, exist_ok=True)

    print("=" * 50)
    print("Creating Demo Template Database")
    print("=" * 50)

    # Build in a private, randomly named directory (never fixed names in the
    # shared temp dir), then move the finished database into place.
    with tempfile.TemporaryDirectory(prefix='demo-template-') as work_dir:
        temp_db = os.path.join(work_dir, 'demo.db')
        temp_csv = os.path.join(work_dir, 'orgchart.csv')

        # Generate people data
        people = get_small_team_data()
        print(f"\n1. Generated {len(people)} fictitious employees")

        write_orgchart_csv(temp_csv, people)

        # Import orgchart to temporary database
        print("\n2. Importing orgchart to database...")
        import_orgchart(temp_csv, temp_db)

        # Generate peer feedback
        print("\n3. Generating peer feedback...")
        feedback_list = generate_sample_feedback(people, temp_db)

        # Generate manager feedback
        print("\n4. Generating manager feedback...")
        generate_manager_feedback(people, temp_db)

        # Generate Workday feedback and import it directly to DB
        print("\n5. Generating Workday feedback...")
        generate_workday_feedback_to_db(people, feedback_list, temp_db)

        # Move to final location
        if os.path.exists(template_db):
            os.remove(template_db)
        shutil.move(temp_db, template_db)

    # Verify
    file_size = os.path.getsize(template_db)
    print("\n" + "=" * 50)
    print(f"Demo template created: {template_db}")
    print(f"Size: {file_size:,} bytes")
    print("=" * 50)

    return template_db


def generate_workday_feedback_to_db(people, feedback_list, db_path):
    """Generate Workday-style feedback directly into database.

    This creates WorkdayFeedback records similar to what would be imported
    from a Workday XLSX export.
    """
    import random
    import json
    from datetime import datetime, timedelta
    from models import init_db, WorkdayFeedback

    session = init_db(db_path)

    # Load tenets
    tenets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'samples', 'tenets-sample.json')
    with open(tenets_path, 'r') as f:
        import json as json_module
        tenets_data = json_module.load(f)
    tenets = {t['id']: t['name'] for t in tenets_data['tenets'] if t.get('active', True)}

    # Get managers
    managers = {p['user_id']: p for p in people if not p['manager_uid']}
    people_by_id = {p['user_id']: p for p in people}

    # Questions used in Workday
    questions = [
        "What strengths does the associate demonstrate?",
        "What should the associate focus on to continue to develop?",
        "Please provide feedback on the associate's performance."
    ]

    # Generic feedback templates
    generic_templates = [
        "{name} has been a great team player this quarter. Strong communication and reliable delivery.",
        "Good collaboration skills. {name} is always willing to help others.",
        "{name} demonstrates solid technical skills and ownership of their work.",
        "I've enjoyed working with {name}. They bring positive energy to the team.",
        "{name} is dependable and delivers quality work consistently.",
    ]

    base_date = datetime.now() - timedelta(days=30)
    count = 0

    # Create Workday feedback from the peer feedback list
    for fb in feedback_list:
        to_person = people_by_id.get(fb['to_user_id'])
        from_person = people_by_id.get(fb['from_user_id'])

        if not to_person or not from_person:
            continue

        manager = managers.get(to_person['manager_uid'])
        if not manager:
            continue

        # Random date within last 60 days
        feedback_date = base_date + timedelta(days=random.randint(-30, 30))

        # Decide if self-requested or manager-requested
        is_self_request = random.choice([True, True, False])
        asked_by = to_person['name'] if is_self_request else manager['name']
        request_type = "Requested by Self" if is_self_request else "Requested by Others"

        # 60% structured, 40% generic
        if random.random() < 0.6:
            # Structured feedback with [TENETS] marker
            strength_names = [tenets.get(s, s) for s in fb['strengths']]
            improvement_names = [tenets.get(i, i) for i in fb['improvements']]

            feedback_text = f"""Strengths:
{chr(10).join('- ' + name for name in strength_names)}

{fb['strengths_text']}

Areas for Improvement:
{chr(10).join('- ' + name for name in improvement_names)}

{fb['improvements_text']}

[TENETS]
Strengths: {', '.join(fb['strengths'])}
Improvements: {', '.join(fb['improvements'])}
[/TENETS]"""
            is_structured = 1
            strengths_json = json.dumps(fb['strengths'])
            improvements_json = json.dumps(fb['improvements'])
        else:
            # Generic feedback
            feedback_text = random.choice(generic_templates).format(name=to_person['name'])
            is_structured = 0
            strengths_json = None
            improvements_json = None

        wd_feedback = WorkdayFeedback(
            about=to_person['name'],
            from_name=from_person['name'],
            question=random.choice(questions),
            feedback=feedback_text,
            asked_by=asked_by,
            request_type=request_type,
            date=feedback_date,
            is_structured=is_structured,
            strengths=strengths_json,
            improvements=improvements_json
        )
        session.add(wd_feedback)
        count += 1

    session.commit()
    session.close()

    print(f"  Created {count} Workday feedback entries")


# Patch generate_sample_feedback to accept db_path parameter
if __name__ == '__main__':
    create_demo_template()
