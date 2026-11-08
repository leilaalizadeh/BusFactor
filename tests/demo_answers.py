"""Strong SYNTHETIC answers for the demo D03 transfer scenarios.

Each scenario has its own rubric, so a strong answer for one scenario is not automatically a
strong answer for the other (that is the point of scenario-specific transfer).
"""
from busfactor.models import InterviewQuestion

FN_COSTLY = ("Because the classes are imbalanced, accuracy is misleading: always predicting no finding already gives "
             "88%. If false negatives cost 10 times more, I would focus on recall, for example report F2 next to F1.")
TWO_PERCENT = ("With only 2% positives, always predicting no finding already gives about 98% accuracy, so accuracy "
               "becomes even more misleading. F1 is built on precision and recall of the positive class, so it still "
               "shows whether the rare findings are found, but with so few positives the test F1 is noisy.")
GOOD = FN_COSTLY   # the first D03 scenario a learner receives


def strong_answer(question: InterviewQuestion) -> str:
    """The strong answer for the scenario this transfer question asks about."""
    return TWO_PERCENT if "2%" in question.prompt else FN_COSTLY
