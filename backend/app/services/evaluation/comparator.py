def normalize_output(output: str) -> str:
    """Normalize line endings and trim outer whitespace, preserving interior whitespace."""
    return output.replace("\r\n", "\n").replace("\r", "\n").strip()


def outputs_match(actual: str, expected: str) -> bool:
    return normalize_output(actual) == normalize_output(expected)
