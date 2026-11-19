from __future__ import annotations

import asyncio
from decimal import Decimal

from app.services.adaptive import AssistanceLevel
from app.services.evaluation.schemas import EvaluationResult
from app.services.feedback import OllamaFeedbackGenerator


async def main() -> None:
    evaluation = EvaluationResult(
        status="WRONG_ANSWER",
        passed_tests=1,
        total_tests=2,
        score=Decimal("50.00"),
        execution_time_ms=None,
        compilation_error=None,
        runtime_error=None,
        test_case_results=[],
    )
    result = await OllamaFeedbackGenerator().generate_feedback(
        problem_description="Read two integers and print their sum.",
        source_code=(
            "import java.util.Scanner;\n"
            "class Main { public static void main(String[] args) { "
            "Scanner s = new Scanner(System.in); "
            "System.out.println(s.nextInt() - s.nextInt()); } }"
        ),
        evaluation_result=evaluation,
        assistance_level=AssistanceLevel.MODERATE,
    )

    print("Status:", result.generation_status)
    print("Model:", result.model_name)
    if result.feedback_text is not None:
        print(result.feedback_text)
    else:
        print("Error:", result.error_message)


if __name__ == "__main__":
    asyncio.run(main())
