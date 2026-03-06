"""
DOA estimation package (SRP-PHAT + GCC-PHAT) for a 4-mic square array.

Public entrypoints:
- doa.cli.main() for CLI usage
- doa.pipeline.run_one() for programmatic usage
"""

from .pipeline import run_one  # noqa: F401