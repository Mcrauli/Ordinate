"""QA / tarkkuusvarmistus: pistepilvi vs. malli -poikkeama + manuaalitarkastuksen flägit."""
from ordinate.core.qa.deviation import (
    write_qa_report, model_deviation, flag_low_confidence, measure_wall_support, scan_coverage,
)

__all__ = ["write_qa_report", "model_deviation", "flag_low_confidence", "scan_coverage"]
