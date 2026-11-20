# ILINet history used in Paper B

`flusight_target_multivals.csv` is the observed-truth file of the FluSight Network
(https://github.com/FluSightNetwork/cdc-flusight-ensemble, `scores/target-multivals.csv`),
derived from CDC ILINet weighted influenza-like illness (wILI) for the US and the 10 HHS
regions, seasons 2010/2011 to 2018/2019 (MMWR weeks 40 to 20), together with the CDC
season onset week and peak week of each season.

`experiments/paper_b/ilinet_data.py` rebuilds the weekly wILI series from the "1 wk ahead"
truth rows (the value on a row for week w is the wILI of week w + 1).
