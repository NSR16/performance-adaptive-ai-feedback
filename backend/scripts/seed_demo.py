from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.orm import Problem, Student, TestCase


def seed_demo_data(db: Session) -> None:
    student = db.query(Student).filter(Student.display_name == "Demo Student").first()
    if student is None:
        student = Student(display_name="Demo Student")
        db.add(student)
        db.flush()

    problem = db.query(Problem).filter(
        Problem.title == "Demo: Sum Two Integers"
    ).first()
    if problem is None:
        problem = Problem(
            title="Demo: Sum Two Integers",
            description=(
                "Read two integers from standard input and print their sum."
            ),
            difficulty="EASY",
            starter_code=(
                "import java.util.Scanner;\n"
                "public class Main {\n"
                "    public static void main(String[] args) {\n"
                "        Scanner scanner = new Scanner(System.in);\n"
                "        // TODO: read and print the sum\n"
                "    }\n"
                "}"
            ),
        )
        db.add(problem)
        db.flush()

    public_cases = [
        ("1 2\n", "3", 1),
        ("10 25\n", "35", 2),
    ]
    hidden_cases = [
        ("-4 9\n", "5", 3),
        ("0 0\n", "0", 4),
    ]
    existing_sequences = {
        test_case.sequence_order
        for test_case in db.query(TestCase)
        .filter(TestCase.problem_id == problem.id)
        .all()
    }
    for input_data, expected_output, sequence in public_cases:
        if sequence not in existing_sequences:
            db.add(
                TestCase(
                    problem_id=problem.id,
                    input_data=input_data,
                    expected_output=expected_output,
                    is_hidden=False,
                    sequence_order=sequence,
                )
            )
    for input_data, expected_output, sequence in hidden_cases:
        if sequence not in existing_sequences:
            db.add(
                TestCase(
                    problem_id=problem.id,
                    input_data=input_data,
                    expected_output=expected_output,
                    is_hidden=True,
                    sequence_order=sequence,
                )
            )

    db.commit()
    print(
        f"Demo seed ready: student_id={student.id}, problem_id={problem.id}"
    )


def main() -> None:
    if SessionLocal is None:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it before running the seed."
        )
    with SessionLocal() as db:
        seed_demo_data(db)


if __name__ == "__main__":
    main()
