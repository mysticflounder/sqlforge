# Future Ideas

## Performance floor in specs
Compare built code against reference implementation performance. Built code must be at least as fast as the reference. Challenges: timing variance across machines, need margins/multiple runs/statistical comparison. Possible approach: pytest-benchmark with relative thresholds rather than absolute timings.
