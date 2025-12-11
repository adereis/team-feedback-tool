"""
Import feedback from Workday XLSX export.

Parses the "Feedback on My Team" export from Workday and imports
feedback entries into the database. Distinguishes between:
1. Structured feedback (tool-assisted with [TENETS] marker)
2. Generic feedback (free-text from other WD workflows)
"""

import openpyxl
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from feedback_models import init_db, WorkdayFeedback


class ImportResult:
    """Result of an XLSX import operation."""

    def __init__(self):
        self.imported = 0
        self.skipped_duplicates = 0
        self.skipped_empty = 0
        self.structured_count = 0
        self.generic_count = 0
        self.warnings = []
        self.errors = []

    @property
    def success(self):
        return len(self.errors) == 0

    def to_dict(self):
        return {
            'success': self.success,
            'imported': self.imported,
            'skipped_duplicates': self.skipped_duplicates,
            'skipped_empty': self.skipped_empty,
            'structured_count': self.structured_count,
            'generic_count': self.generic_count,
            'warnings': self.warnings,
            'errors': self.errors
        }


def validate_row(row, row_num):
    """Validate a single row from the XLSX.

    Args:
        row: Tuple of cell values (columns A-J)
        row_num: Row number for error messages

    Returns:
        Tuple of (is_valid, error_message or None)
    """
    # Row structure: (about_photo, about, feedback_also, from_photo, from_name,
    #                 question, feedback, asked_by, type, date)
    if len(row) < 10:
        return False, f"Row {row_num}: Incomplete row (expected 10 columns)"

    about = row[1]
    from_name = row[4]
    asked_by = row[7]
    request_type = row[8]

    # Skip empty rows (section headers or pending requests)
    if not from_name:
        return False, None  # Not an error, just skip

    # Validate type consistency
    if about and asked_by and request_type:
        if about == asked_by and request_type != "Requested by Self":
            return False, (f"Row {row_num}: Data inconsistency - About '{about}' matches "
                          f"Asked By but Type is '{request_type}' (expected 'Requested by Self')")
        if about != asked_by and request_type != "Requested by Others":
            return False, (f"Row {row_num}: Data inconsistency - About '{about}' differs from "
                          f"Asked By '{asked_by}' but Type is '{request_type}' "
                          f"(expected 'Requested by Others')")

    return True, None


def import_workday_xlsx(file_path, db_path='feedback.db'):
    """Import feedback from a Workday XLSX export.

    Args:
        file_path: Path to the XLSX file
        db_path: Path to the SQLite database

    Returns:
        ImportResult with import statistics and any warnings/errors
    """
    result = ImportResult()

    try:
        wb = openpyxl.load_workbook(file_path)
    except Exception as e:
        result.errors.append(f"Failed to open XLSX file: {e}")
        return result

    # Find the feedback sheet
    sheet_name = None
    for name in wb.sheetnames:
        if 'feedback' in name.lower():
            sheet_name = name
            break

    if not sheet_name:
        # Use first sheet if no feedback sheet found
        sheet_name = wb.sheetnames[0]
        result.warnings.append(f"No 'Feedback' sheet found, using '{sheet_name}'")

    ws = wb[sheet_name]
    session = init_db(db_path)

    # Track if we see any data in "Feedback Also Given To" column
    feedback_also_given_to_used = False

    # Process rows (skip header rows 1-2)
    for row_num, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
        # Check for "Feedback Also Given To" usage
        if row[2]:  # Column C
            feedback_also_given_to_used = True

        # Validate row
        is_valid, error = validate_row(row, row_num)

        if error:
            result.errors.append(error)
            continue

        if not is_valid:
            # Empty row, skip silently but count
            result.skipped_empty += 1
            continue

        # Extract values
        about = row[1]
        from_name = row[4]
        question = row[5]
        feedback_text = row[6]
        asked_by = row[7]
        request_type = row[8]
        date = row[9]

        # Handle date conversion
        if isinstance(date, datetime):
            feedback_date = date
        elif isinstance(date, str):
            try:
                feedback_date = datetime.fromisoformat(date)
            except ValueError:
                feedback_date = None
        else:
            feedback_date = None

        # Create feedback entry
        wd_feedback = WorkdayFeedback(
            about=about,
            from_name=from_name,
            question=question,
            feedback=feedback_text,
            asked_by=asked_by,
            request_type=request_type,
            date=feedback_date
        )

        # Parse for structured feedback
        wd_feedback.parse_structured_feedback()

        # Try to add to database
        try:
            session.add(wd_feedback)
            session.flush()  # Check for constraint violations
            result.imported += 1

            if wd_feedback.is_structured:
                result.structured_count += 1
            else:
                result.generic_count += 1

        except IntegrityError:
            session.rollback()
            result.skipped_duplicates += 1

    # Commit all changes
    session.commit()
    session.close()

    # Add warnings
    if result.skipped_empty > 0:
        result.warnings.append(
            f"Skipped {result.skipped_empty} empty/incomplete rows "
            "(possibly pending feedback requests)"
        )

    if feedback_also_given_to_used:
        result.warnings.append(
            "Some entries have 'Feedback Also Given To' values - "
            "this column is not currently supported"
        )

    return result


def get_available_date_ranges(db_path='feedback.db'):
    """Get date ranges that have feedback available.

    Returns:
        List of (year, month, count) tuples sorted by date descending
    """
    session = init_db(db_path)

    # Query distinct year-month combinations with counts
    from sqlalchemy import func, extract

    results = session.query(
        extract('year', WorkdayFeedback.date).label('year'),
        extract('month', WorkdayFeedback.date).label('month'),
        func.count(WorkdayFeedback.id).label('count')
    ).filter(
        WorkdayFeedback.date.isnot(None)
    ).group_by(
        extract('year', WorkdayFeedback.date),
        extract('month', WorkdayFeedback.date)
    ).order_by(
        extract('year', WorkdayFeedback.date).desc(),
        extract('month', WorkdayFeedback.date).desc()
    ).all()

    session.close()

    return [(int(r.year), int(r.month), r.count) for r in results]


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python import_workday.py <xlsx_file> [db_path]")
        sys.exit(1)

    xlsx_path = sys.argv[1]
    db_path = sys.argv[2] if len(sys.argv) > 2 else 'feedback.db'

    print(f"Importing from {xlsx_path}...")
    result = import_workday_xlsx(xlsx_path, db_path)

    print(f"\nImport complete:")
    print(f"  Imported: {result.imported}")
    print(f"  - Structured (with tenets): {result.structured_count}")
    print(f"  - Generic (free-text): {result.generic_count}")
    print(f"  Skipped (duplicates): {result.skipped_duplicates}")
    print(f"  Skipped (empty rows): {result.skipped_empty}")

    if result.warnings:
        print(f"\nWarnings:")
        for w in result.warnings:
            print(f"  - {w}")

    if result.errors:
        print(f"\nErrors:")
        for e in result.errors:
            print(f"  - {e}")
        sys.exit(1)
