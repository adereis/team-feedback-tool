"""
Tenet tallies behind the butterfly charts.

A team member's feedback comes from three sources:
- peer feedback given in this tool (Feedback)
- feedback imported from Workday (WorkdayFeedback); only structured entries,
  those with a [TENETS] marker, carry tenet selections
- the manager's own picks (ManagerFeedback), which count +1 like a peer's

Two views combine them differently:
- manager view (report page, team chart): all three sources
- employee view (PDF): peer feedback and the manager's picks. Workday feedback
  is left out on purpose, since some of it may not be visible to the employee.
"""

from collections import Counter
from dataclasses import dataclass
from typing import List, Optional

from models import Feedback, ManagerFeedback, Person, WorkdayFeedback, name_to_user_id


class Tally:
    """How often each tenet was picked as a strength and as an improvement."""

    def __init__(self):
        self.strengths = Counter()
        self.improvements = Counter()

    def add(self, strengths, improvements):
        self.strengths.update(strengths)
        self.improvements.update(improvements)

    def add_tally(self, other):
        self.strengths.update(other.strengths)
        self.improvements.update(other.improvements)

    def butterfly(self, tenets):
        """Chart rows for the given tenets, most net-positive first."""
        rows = [{
            'id': tenet['id'],
            'name': tenet['name'],
            'strength_count': self.strengths[tenet['id']],
            'improvement_count': self.improvements[tenet['id']],
        } for tenet in tenets]
        rows.sort(key=lambda row: row['strength_count'] - row['improvement_count'], reverse=True)
        return rows


@dataclass
class MemberFeedback:
    """Everything recorded about one team member, grouped by source."""

    peer: List[Feedback]               # given in this tool
    workday: List[WorkdayFeedback]     # imported, newest first
    manager: Optional[ManagerFeedback]  # this manager's picks and text

    @property
    def workday_structured(self):
        return [fb for fb in self.workday if fb.is_structured]

    @property
    def workday_generic(self):
        return [fb for fb in self.workday if not fb.is_structured]

    def manager_view(self):
        """Tally for the manager: peer, structured Workday and manager picks."""
        tally = self._peer_and_manager()
        for fb in self.workday_structured:
            tally.add(fb.get_strengths(), fb.get_improvements())
        return tally

    def employee_view(self):
        """Tally for the employee (PDF): peer feedback and manager picks only."""
        return self._peer_and_manager()

    def _peer_and_manager(self):
        tally = Tally()
        for fb in self.peer:
            tally.add(fb.get_strengths(), fb.get_improvements())
        if self.manager:
            tally.add(self.manager.get_selected_strengths(), self.manager.get_selected_improvements())
        return tally


def load_member_feedback(db, user_id, name, manager_uid):
    """Collect one team member's feedback from all sources.

    Args:
        db: SQLAlchemy session
        user_id: orgchart ID, or a derived 'wd_' ID for a Workday-only person
            (who cannot have in-tool peer feedback)
        name: display name, which is how Workday rows identify people
        manager_uid: the manager's ID (real or derived) whose picks to include
    """
    peer = []
    if user_id and not user_id.startswith('wd_'):
        peer = db.query(Feedback).filter_by(to_user_id=user_id).all()

    workday = db.query(WorkdayFeedback).filter(
        WorkdayFeedback.about == name
    ).order_by(WorkdayFeedback.date.desc()).all()

    manager = None
    if user_id and manager_uid:
        manager = db.query(ManagerFeedback).filter_by(
            manager_uid=manager_uid, team_member_uid=user_id
        ).first()

    return MemberFeedback(peer=peer, workday=workday, manager=manager)


def orgchart_team_tally(db, manager_uid):
    """Team chart for a manager chosen from the orgchart.

    The sum of the manager view of each direct report, so it always agrees
    with the report pages it summarizes.
    """
    tally = Tally()
    for member in db.query(Person).filter_by(manager_uid=manager_uid).all():
        feedback = load_member_feedback(db, member.user_id, member.name, manager_uid)
        tally.add_tally(feedback.manager_view())
    return tally


def workday_team_tally(db, manager_uid):
    """Team chart for a manager who signed in by name (Workday workflow).

    The team is every recipient in the Workday import, as on the dashboard,
    and the chart is the sum of each recipient's manager view, like the
    orgchart team chart. A recipient whose name is in the orgchart uses that
    person's ID, anyone else a derived one: the same IDs the report pages use.

    Args:
        manager_uid: the manager's derived ID (name_to_user_id of their name)
    """
    tally = Tally()
    for (name,) in db.query(WorkdayFeedback.about).distinct().all():
        person = db.query(Person).filter_by(name=name).first()
        user_id = person.user_id if person else name_to_user_id(name)
        tally.add_tally(load_member_feedback(db, user_id, name, manager_uid).manager_view())
    return tally
