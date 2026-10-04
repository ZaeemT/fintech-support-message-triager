from typesafe_sdk import ChoiceAnswer, NoulAnswer, ScoreAnswer, SystemOneResponse


class TriageResult(SystemOneResponse):
    """Typed Jev response: the SDK copies each named answer into its field.

    A missing answer or wrong answer type raises TypeSafeAPIResponseValidationError.
    """

    category: ChoiceAnswer
    urgency: ScoreAnswer
    fraud_related: NoulAnswer
    needs_human: NoulAnswer
