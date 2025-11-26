#!/usr/bin/env python3
"""
Create sample demo data for the Team Feedback Tool.
This generates fictitious orgchart data and optionally sample feedback.

Usage:
    python3 create_sample_feedback_data.py              # Creates small team (12 employees, 1 manager)
    python3 create_sample_feedback_data.py --large      # Creates large org (50 employees, 5 managers)
    python3 create_sample_feedback_data.py --with-feedback  # Include sample feedback data

Output:
    - sample-feedback-orgchart.csv (or sample-feedback-orgchart-large.csv)
    - Optionally populates feedback.db with sample feedback
"""

import csv
import random
import sys
from feedback_models import init_db, Feedback
import json


def generate_user_id(name):
    """Generate user ID from name (first initial + last name, lowercase)"""
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1]).lower().replace("'", "").replace(".", "")
    return name.lower().replace(" ", "")[:8]


def generate_email(user_id):
    """Generate email from user ID"""
    return f"{user_id}@example.com"


def get_location():
    """Get random location"""
    locations = [
        'Remote US CA', 'Remote US TX', 'Remote US NY', 'Remote US MA',
        'RH - Raleigh', 'RH - Boston', 'RH - San Francisco',
        'Remote UK', 'Remote Ireland', 'Remote France', 'Remote Spain',
        'RH - Brno - Tech Park', 'RH - Pune - Tower 6'
    ]
    return random.choice(locations)


def get_small_team_data():
    """
    Small team: 12 employees under single manager (Della Gate).
    Perfect for testing with a manageable dataset.
    """
    manager = 'dgate'

    # Reuse names from bonus tool
    employees = [
        ('Paige Duty', 'Staff SRE'),
        ('Lee Latency', 'Senior Software Developer'),
        ('Mona Torr', 'Senior SRE'),
        ('Robin Rollback', 'Software Developer'),
        ('Kenny Canary', 'Software Developer'),
        ('Tracey Loggins', 'Senior SRE'),
        ('Sue Q. Ell', 'Senior Software Developer'),
        ('Jason Blob', 'Software Developer'),
        ('Al Ert', 'Staff SRE'),
        ('Addie Min', 'Senior Software Developer'),
        ('Tim Out', 'Software Developer'),
        ('Barbie Que', 'Senior SRE'),
    ]

    result = []
    for name, job in employees:
        user_id = generate_user_id(name)
        result.append({
            'name': name,
            'user_id': user_id,
            'job_title': job,
            'location': get_location(),
            'email': generate_email(user_id),
            'manager_uid': manager
        })

    # Add the manager
    result.append({
        'name': 'Della Gate',
        'user_id': 'dgate',
        'job_title': 'Engineering Manager',
        'location': 'RH - Raleigh',
        'email': 'dgate@example.com',
        'manager_uid': ''  # Top-level
    })

    return result


def get_large_org_data():
    """
    Large org: 50 employees across 5 managers.
    Tests multi-manager scenario.
    """
    # Manager names from bonus tool
    managers = {
        'dgate': 'Della Gate',
        'rmap': 'Rhoda Map',
        'keye': 'Kay P. Eye',
        'aenda': 'Agie Enda',
        'mstone': 'Mai Stone'
    }

    # Tech-themed employee names from bonus tool
    names = [
        'Paige Duty', 'Lee Latency', 'Mona Torr', 'Robin Rollback',
        'Kenny Canary', 'Tracey Loggins', 'Sue Q. Ell', 'Jason Blob',
        'Al Ert', 'Addie Min', 'Tim Out', 'Barbie Que',
        'Terry Byte', 'Nole Pointer', 'Marge Conflict', 'Bridget Branch',
        'Cody Ryder', 'Cy Ferr', 'Phil Wall', 'Lana Wan',
        'Artie Ficial', 'Ruth Cause', 'Matt Rick', 'Cassie Cache',
        'Sue Do', 'Pat Ch', 'Devin Null', 'Justin Time',
        'Annie O\'Maly', 'Sam Box', 'Val Idation', 'Bill Ding',
        'Ty Po', 'Mike Roservices', 'Lou Pe', 'Connie Tainer',
        'Noah Node', 'Sara Ver', 'Exa M. Elle', 'Dee Ploi',
        'Ray D. O\'Button', 'Cam Elcase', 'Hashim Map', 'Ben Chmark',
        'Grace Full', 'Shel Script', 'Sal T. Hash', 'Reba Boot',
        'Stan Dup', 'Kay Eight'
    ]

    jobs = [
        'Principal Software Developer', 'Staff Software Developer',
        'Senior Software Developer', 'Software Developer',
        'Principal SRE', 'Staff SRE', 'Senior SRE', 'SRE',
        'Engineering Manager'
    ]

    result = []
    name_idx = 0

    # Create employees for each manager (10 per manager)
    for manager_uid in managers.keys():
        for i in range(10):
            if name_idx >= len(names):
                break
            name = names[name_idx]
            user_id = generate_user_id(name)
            job = random.choice(jobs)

            result.append({
                'name': name,
                'user_id': user_id,
                'job_title': job,
                'location': get_location(),
                'email': generate_email(user_id),
                'manager_uid': manager_uid
            })
            name_idx += 1

    # Add managers
    for manager_uid, manager_name in managers.items():
        result.append({
            'name': manager_name,
            'user_id': manager_uid,
            'job_title': 'Engineering Manager',
            'location': get_location(),
            'email': generate_email(manager_uid),
            'manager_uid': ''  # Top-level
        })

    return result


def write_orgchart_csv(filename, people):
    """Write orgchart CSV file"""
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Name', 'User ID', 'Job Title', 'Location', 'Email', 'Manager UID'])

        for person in people:
            writer.writerow([
                person['name'],
                person['user_id'],
                person['job_title'],
                person['location'],
                person['email'],
                person['manager_uid']
            ])

    print(f"✓ Created {filename} with {len(people)} people")


def generate_sample_feedback(people):
    """Generate realistic sample feedback in database with ~80% coverage"""
    # Load tenets
    with open('tenets-sample.json', 'r') as f:
        tenets_data = json.load(f)
    tenets = [t for t in tenets_data['tenets'] if t.get('active', True)]
    tenet_ids = [t['id'] for t in tenets]

    session = init_db()

    # Clear existing feedback
    session.query(Feedback).delete()

    # Get employees (not managers)
    employees = [p for p in people if p['manager_uid']]
    managers_dict = {p['user_id']: p for p in people if not p['manager_uid']}

    feedback_count = 0

    # Varied feedback text templates
    strength_texts = [
        "{name} consistently demonstrates excellence in these areas and serves as a role model for the team.",
        "I've observed {name} excel in these tenets throughout our collaboration this quarter.",
        "{name} brings exceptional capability in these areas, making significant positive impact.",
        "These are standout strengths for {name}. They handle challenges in these areas with expertise and professionalism.",
        "Working with {name} has shown me their strong command of these principles. Keep up the great work!",
        "{name} sets the bar high in these tenets and helps elevate the entire team's performance.",
        "I appreciate how {name} embodies these values in their daily work. It makes a real difference.",
        "{name} has shown consistent growth and mastery in these areas over the time we've worked together.",
        "These tenets are clearly where {name} shines brightest. Their expertise is invaluable to our success.",
        "I've been impressed by {name}'s dedication to these principles and the results they achieve.",
        "{name} demonstrates deep understanding and application of these tenets in everything they do.",
        "The team benefits greatly from {name}'s strength in these areas. Excellent work overall.",
    ]

    improvement_texts = [
        "I see opportunities for {name} to develop further in these areas to increase their overall impact.",
        "These tenets could use more attention and focus from {name} going forward.",
        "With some dedicated effort in these areas, {name} could take their contributions to the next level.",
        "I'd encourage {name} to prioritize growth in these tenets as they continue their development.",
        "These are areas where I think {name} has room to grow and strengthen their skillset.",
        "Focusing on these principles would help {name} become even more effective in their role.",
        "I believe {name} would benefit from additional practice and experience with these tenets.",
        "These areas represent growth opportunities that could enhance {name}'s overall effectiveness.",
        "I'd like to see {name} invest more time and energy into developing these capabilities.",
        "While {name} has many strengths, these tenets could use some improvement and refinement.",
        "Working on these areas would round out {name}'s already solid skillset nicely.",
        "I think {name} could make meaningful progress by focusing attention on these tenets.",
    ]

    # Generate feedback: each employee gives feedback to ~80% of peers
    for employee in employees:
        # Find peers (same manager)
        peers = [p for p in employees
                if p['user_id'] != employee['user_id']
                and p['manager_uid'] == employee['manager_uid']]

        # Calculate 80% of peers (minimum 1, maximum all peers)
        num_feedback = max(1, int(len(peers) * 0.8))
        num_feedback = min(num_feedback, len(peers))

        # Randomly select which peers to give feedback to
        selected_peers = random.sample(peers, num_feedback) if len(peers) > 0 else []

        for peer in selected_peers:
            # Select 3 random strengths
            strengths = random.sample(tenet_ids, 3)

            # Select 2-3 random improvements
            num_improvements = random.choice([2, 3])
            # Make sure improvements don't overlap with strengths
            available_improvements = [tid for tid in tenet_ids if tid not in strengths]
            improvements = random.sample(available_improvements, num_improvements)

            # Generate sample text with name substitution
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
            feedback_count += 1

    session.commit()
    session.close()

    # Calculate coverage statistics per manager
    from collections import defaultdict
    team_sizes = defaultdict(int)
    for emp in employees:
        team_sizes[emp['manager_uid']] += 1

    # Total possible feedback = sum of (team_size * (team_size - 1)) for each team
    total_possible = sum(size * (size - 1) for size in team_sizes.values())
    coverage_percent = (feedback_count / total_possible * 100) if total_possible > 0 else 0

    print(f"✓ Generated {feedback_count} sample feedback entries in feedback.db")
    print(f"  Coverage: {coverage_percent:.1f}% of possible peer feedback within teams")
    print(f"  Teams: {len(team_sizes)} managers, avg team size: {sum(team_sizes.values()) / len(team_sizes):.1f}")


def main():
    large = '--large' in sys.argv
    with_feedback = '--with-feedback' in sys.argv

    # Generate people data
    if large:
        people = get_large_org_data()
        filename = 'sample-feedback-orgchart-large.csv'
    else:
        people = get_small_team_data()
        filename = 'sample-feedback-orgchart.csv'

    # Write CSV
    write_orgchart_csv(filename, people)

    # Generate feedback if requested
    if with_feedback:
        print("\nGenerating sample feedback data...")
        generate_sample_feedback(people)
        print("\nTo load the orgchart into the database, run:")
        print(f"  python3 import_orgchart.py {filename}")
    else:
        print("\nNext steps:")
        print(f"  1. Import orgchart: python3 import_orgchart.py {filename}")
        print(f"  2. Start app: python3 feedback_app.py")
        print(f"  3. Or re-run with --with-feedback to also generate sample feedback")


if __name__ == '__main__':
    if '--help' in sys.argv or '-h' in sys.argv:
        print(__doc__)
        sys.exit(0)

    main()
