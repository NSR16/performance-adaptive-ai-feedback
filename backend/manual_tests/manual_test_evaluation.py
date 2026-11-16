
from app.services.evaluation import EvaluationEngine, TestCaseInput

java_source = """
public class Main {
    public static void main(String[] args) {
        System.out.println(999);
    }
}
"""

test_cases = [
    TestCaseInput(1, "1 2\n", "3", False, 1),
    TestCaseInput(2, "10 25\n", "35", False, 2),
    TestCaseInput(3, "-4 9\n", "5", False, 3),
]

result = EvaluationEngine().evaluate(
    source_code=java_source,
    test_cases=test_cases,
)

print("\n--- Evaluation Result ---")
print("Status:", result.status)
print("Passed:", result.passed_tests)
print("Total:", result.total_tests)
print("Score:", result.score)

print("\n--- Individual Test Results ---")

for case in result.test_case_results:
    print(
        f"Test {case.test_case_id}: "
        f"status={case.status}, "
        f"actual_output={case.actual_output!r}, "
        f"execution_time_ms={case.execution_time_ms}, "
        f"error_message={case.error_message!r}"
    )
