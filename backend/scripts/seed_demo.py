from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.orm import Problem, Student, TestCase


def seed_demo_data(db: Session) -> None:
    demo_student_names = (
        "Demo Student",
        "Demo Student 2",
        "Demo Student 3",
    )
    existing_students = {
        student.display_name: student
        for student in db.query(Student)
        .filter(Student.display_name.in_(demo_student_names))
        .all()
    }
    for display_name in demo_student_names:
        if display_name not in existing_students:
            student = Student(display_name=display_name)
            db.add(student)
            existing_students[display_name] = student
    db.flush()
    student = existing_students["Demo Student"]

    problem_specs = (
        {
            "title": "Demo: Sum Two Integers",
            "description": (
                "Read two integers from standard input and print their sum.\n\n"
                "Input format:\nA single line containing two integers separated by a space.\n\n"
                "Output format:\nPrint one integer: the sum of the two integers.\n\n"
                "Constraints:\nEach input integer is between -1000 and 1000.\n\n"
                "Example input:\n1 2\n\n"
                "Example output:\n3"
            ),
            "cases": [
                ("1 2\n", "3", False, 1),
                ("10 25\n", "35", False, 2),
                ("-4 9\n", "5", True, 3),
                ("0 0\n", "0", True, 4),
            ],
        },
        {
            "title": "Even or Odd",
            "description": (
                "Read one integer and determine whether it is even or odd.\n\n"
                "Input format:\nA single line containing one integer.\n\n"
                "Output format:\nPrint \"Even\" for an even integer and \"Odd\" for an odd integer.\n\n"
                "Constraints:\nThe input integer is between -100000 and 100000.\n\n"
                "Example input:\n14\n\n"
                "Example output:\nEven"
            ),
            "cases": [
                ("14\n", "Even", False, 1),
                ("7\n", "Odd", False, 2),
                ("0\n", "Even", True, 3),
                ("-9\n", "Odd", True, 4),
            ],
        },
        {
            "title": "Largest of Three Numbers",
            "description": (
                "Read three integers and print the largest value.\n\n"
                "Input format:\nA single line containing three integers separated by spaces.\n\n"
                "Output format:\nPrint the largest integer.\n\n"
                "Constraints:\nEach integer is between -100000 and 100000.\n\n"
                "Example input:\n12 34 27\n\n"
                "Example output:\n34"
            ),
            "cases": [
                ("12 34 27\n", "34", False, 1),
                ("5 5 5\n", "5", False, 2),
                ("-8 -2 -10\n", "-2", True, 3),
                ("20 20 7\n", "20", True, 4),
            ],
        },
        {
            "title": "Calculate Factorial",
            "description": (
                "Read a non-negative integer n and calculate n factorial.\n\n"
                "Input format:\nA single line containing one integer n.\n\n"
                "Output format:\nPrint n factorial as one integer.\n\n"
                "Constraints:\n0 <= n <= 12. The selected bound keeps results within the Java int range "
                "(12! = 479001600).\n\n"
                "Example input:\n5\n\n"
                "Example output:\n120"
            ),
            "cases": [
                ("0\n", "1", False, 1),
                ("1\n", "1", False, 2),
                ("5\n", "120", False, 3),
                ("12\n", "479001600", True, 4),
            ],
        },
        {
            "title": "Sum of Array Elements",
            "description": (
                "Read an array size and then read that many integers. Print the sum of all elements.\n\n"
                "Input format:\nThe first line contains n. The second line contains n integers separated "
                "by spaces.\n\n"
                "Output format:\nPrint one integer: the sum of the array elements.\n\n"
                "Constraints:\n1 <= n <= 100. Each array element is between -1000 and 1000.\n\n"
                "Example input:\n5\n1 2 3 4 5\n\n"
                "Example output:\n15"
            ),
            "cases": [
                ("1\n42\n", "42", False, 1),
                ("4\n10 20 30 40\n", "100", False, 2),
                ("3\n-5 -10 -15\n", "-30", True, 3),
                ("5\n8 -3 12 -7 10\n", "20", True, 4),
            ],
        },
        {
            "title": "Prime Number Checker",
            "description": (
                "Read one integer and determine whether it is prime.\n\n"
                "Input format:\nA single line containing one integer.\n\n"
                "Output format:\nPrint \"Prime\" for a prime integer and \"Not Prime\" otherwise.\n\n"
                "Constraints:\nThe input integer is between -100000 and 100000.\n\n"
                "Example input:\n29\n\n"
                "Example output:\nPrime"
            ),
            "cases": [
                ("2\n", "Prime", False, 1),
                ("29\n", "Prime", False, 2),
                ("12\n", "Not Prime", False, 3),
                ("0\n", "Not Prime", True, 4),
                ("1\n", "Not Prime", True, 5),
                ("-7\n", "Not Prime", True, 6),
            ],
        },
    )

    for spec in problem_specs:
        problem = db.query(Problem).filter(Problem.title == spec["title"]).first()
        if problem is None:
            problem = Problem(
                title=spec["title"],
                description=spec["description"],
                difficulty="EASY",
                starter_code=(
                    "import java.util.Scanner;\n"
                    "public class Main {\n"
                    "    public static void main(String[] args) {\n"
                    "        Scanner scanner = new Scanner(System.in);\n"
                    "        // TODO: implement the solution\n"
                    "    }\n"
                    "}"
                ),
            )
            db.add(problem)
            db.flush()
        elif (
            spec["title"] == "Demo: Sum Two Integers"
            and problem.description != spec["description"]
        ):
            problem.description = spec["description"]

        existing_cases = {
            (
                test_case.input_data,
                test_case.expected_output,
                test_case.is_hidden,
                test_case.sequence_order,
            )
            for test_case in db.query(TestCase)
            .filter(TestCase.problem_id == problem.id)
            .all()
        }
        for input_data, expected_output, is_hidden, sequence in spec["cases"]:
            case_key = (
                input_data,
                expected_output,
                is_hidden,
                sequence,
            )
            if case_key not in existing_cases:
                db.add(
                    TestCase(
                        problem_id=problem.id,
                        input_data=input_data,
                        expected_output=expected_output,
                        is_hidden=is_hidden,
                        sequence_order=sequence,
                    )
                )
                existing_cases.add(case_key)

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
