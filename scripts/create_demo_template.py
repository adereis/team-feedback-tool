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

from models import init_db, Base
from create_sample_data import (
    get_small_team_data,
    write_orgchart_csv,
    generate_sample_feedback,
    generate_manager_feedback,
    generate_workday_xlsx
)
from import_orgchart import import_orgchart


def create_demo_template():
    """Create the demo template database with all sample data."""
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(script_dir, 'demo-templates')
    template_db = os.path.join(template_dir, 'demo.db')

    # Ensure template directory exists
    os.makedirs(template_dir, exist_ok=True)

    # Use a temporary database path during generation
    temp_db = os.path.join(tempfile.gettempdir(), 'demo_template_temp.db')

    # Remove existing temp db if any
    if os.path.exists(temp_db):
        os.remove(temp_db)

    print("=" * 50)
    print("Creating Demo Template Database")
    print("=" * 50)

    # Generate people data
    people = get_small_team_data()
    print(f"\n1. Generated {len(people)} fictitious employees")

    # Create temporary orgchart CSV
    temp_csv = os.path.join(tempfile.gettempdir(), 'demo_orgchart.csv')
    write_orgchart_csv(temp_csv, people)

    # Import orgchart to temporary database
    print("\n2. Importing orgchart to database...")
    import_orgchart(temp_csv, temp_db)

    # Clean up temp CSV
    os.remove(temp_csv)

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
def generate_sample_feedback(people, db_path='feedback.db'):
    """Modified version that accepts db_path parameter."""
    import random
    import json
    from collections import defaultdict
    from models import init_db, Feedback

    tenets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'samples', 'tenets-sample.json')
    with open(tenets_path, 'r') as f:
        tenets_data = json.load(f)
    tenets = [t for t in tenets_data['tenets'] if t.get('active', True)]
    tenet_ids = [t['id'] for t in tenets]

    session = init_db(db_path)

    # Clear existing feedback
    session.query(Feedback).delete()

    # Get employees (not managers)
    employees = [p for p in people if p['manager_uid']]

    feedback_list = []

    # Feedback text templates
    strength_texts = [
        "{name} consistently demonstrates excellence in these areas.",
        "I've observed {name} excel in these tenets throughout our collaboration.",
        "{name} brings exceptional capability in these areas.",
        "These are standout strengths for {name}.",
        "Working with {name} has shown me their strong command of these principles.",
    ]

    improvement_texts = [
        "I see opportunities for {name} to develop further in these areas.",
        "These tenets could use more attention from {name}.",
        "With dedicated effort in these areas, {name} could excel further.",
        "I'd encourage {name} to prioritize growth in these tenets.",
        "These are areas where {name} has room to grow.",
    ]

    # Generate feedback: each employee gives feedback to ~80% of peers
    for employee in employees:
        peers = [p for p in employees
                 if p['user_id'] != employee['user_id']
                 and p['manager_uid'] == employee['manager_uid']]

        num_feedback = max(1, int(len(peers) * 0.8))
        num_feedback = min(num_feedback, len(peers))

        selected_peers = random.sample(peers, num_feedback) if peers else []

        for peer in selected_peers:
            strengths = random.sample(tenet_ids, 3)
            num_improvements = random.choice([2, 3])
            available = [tid for tid in tenet_ids if tid not in strengths]
            improvements = random.sample(available, num_improvements)

            strength_text = random.choice(strength_texts).format(name=peer['name'])
            improvement_text = random.choice(improvement_texts).format(name=peer['name'])

            feedback = Feedback(
                from_user_id=employee['user_id'],
                to_user_id=peer['user_id'],
                strengths_text=strength_text,
                improvements_text=improvement_text
            )
            feedback.set_strengths(strengths)
            feedback.set_improvements(improvements)

            session.add(feedback)

            feedback_list.append({
                'from_user_id': employee['user_id'],
                'to_user_id': peer['user_id'],
                'to_manager_uid': peer['manager_uid'],
                'strengths': strengths,
                'improvements': improvements,
                'strengths_text': strength_text,
                'improvements_text': improvement_text
            })

    session.commit()
    session.close()

    print(f"  Created {len(feedback_list)} peer feedback entries")
    return feedback_list


def generate_manager_feedback(people, db_path='feedback.db'):
    """Modified version that accepts db_path parameter."""
    import random
    from collections import defaultdict
    from models import init_db, Feedback, ManagerFeedback

    session = init_db(db_path)
    session.query(ManagerFeedback).delete()

    managers = [p for p in people if not p['manager_uid']]
    employees = [p for p in people if p['manager_uid']]

    manager_texts = [
        "Based on peer feedback, {name} shows strong performance in the highlighted areas.",
        "{name} has received consistent positive feedback from peers.",
        "Peer feedback confirms {name}'s strengths align with team expectations.",
    ]

    count = 0
    for manager in managers:
        team = [e for e in employees if e['manager_uid'] == manager['user_id']]

        for member in team:
            feedbacks = session.query(Feedback).filter_by(to_user_id=member['user_id']).all()

            if not feedbacks:
                continue

            strength_counts = defaultdict(int)
            improvement_counts = defaultdict(int)

            for fb in feedbacks:
                for s in fb.get_strengths():
                    strength_counts[s] += 1
                for i in fb.get_improvements():
                    improvement_counts[i] += 1

            top_strengths = sorted(strength_counts.keys(),
                                   key=lambda x: strength_counts[x],
                                   reverse=True)[:random.choice([2, 3])]
            top_improvements = sorted(improvement_counts.keys(),
                                      key=lambda x: improvement_counts[x],
                                      reverse=True)[:random.choice([1, 2])]

            feedback_text = random.choice(manager_texts).format(name=member['name'])

            mgr_feedback = ManagerFeedback(
                manager_uid=manager['user_id'],
                team_member_uid=member['user_id'],
                feedback_text=feedback_text
            )
            mgr_feedback.set_selected_strengths(top_strengths)
            mgr_feedback.set_selected_improvements(top_improvements)

            session.add(mgr_feedback)
            count += 1

    session.commit()
    session.close()

    print(f"  Created {count} manager feedback entries")


if __name__ == '__main__':
    create_demo_template()
