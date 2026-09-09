# CI performance measurements

This experiment compares the unchanged CI with three cumulative changes:

1. run the scheduler lifecycle probe on independent runners;
2. run the complete pytest suite with two workers;
3. run independent installed-wheel smoke commands concurrently.

The baseline is commit `9505800`. All three operating systems, numerical
goldens, GUI checks, scheduler repetitions, packaging checks, and installed
command checks remain in scope. Measurements will record complete workflow
elapsed time, individual step time, test outcomes, and implementation cost.

No numerical formulas, supported interfaces, or expected results are changed.
