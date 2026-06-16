"""QA / tarkkuusvarmistus: pistepilvi vs. malli -poikkeama + manuaalitarkastuksen flägit."""
from scan2bim.core.qa.deviation import write_qa_report, model_deviation, flag_low_confidence

__all__ = ["write_qa_report", "model_deviation", "flag_low_confidence"]
