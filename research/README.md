# Research

How the algorithm in `core/` was arrived at, including the branches that were tried and
dropped. Each file is one stage. They run on their own, print the working out, and draw
the charts.

Why keep them: the final version in `core/brain.py` looks tidy, but it looks tidy
because several approaches were cut. These files are where those approaches are
recorded.

## Running

The files are split into cells with `# %%`. Run them cell by cell in VS Code (Python
and Jupyter extensions) or run the whole file.

```
data.py            read and clean the raw data
affinity.py        measure which items travel together
algorithm.py       pick the reserve aisle, the heaviest stage
weights.py         balance the two objectives, find the 0.6/0.4 split
replenishment.py   look at refill patterns, a branch that was dropped
```

Needs `numpy`, `matplotlib` and `gensim`. Point `SLOTWISE_DATA` at your CSV directory;
column and file names come from the `COL_*` and `F_*` variables in `_common.py`.

## What each stage asked

| File | Question | Method | Answer |
|---|---|---|---|
| `data.py` | What is in the data, and is it clean? | Scan every CSV, measure how full each column is, drop dead columns and deleted rows | Many columns are entirely empty; the warehouse has three zone types |
| `affinity.py` | Which items travel together? | Count co-occurring pairs, compare against Word2Vec | Word2Vec's top 5 companions overlap 71% with the top 20 from counting, so it adds nothing |
| `algorithm.py` | Where should reserve stock go? | Four versions: same aisle number, then mean, then median, then per item | Median hits the true optimum in all 26 aisles; mean is worse, 209,932 against 195,455 |
| `weights.py` | Where does 0.6/0.4 come from? | Sweep w from 0 to 1, re-slot 1,603 items at each step, add refill cost to pick cost | w = 0.4 costs 427,274; the cheapest is w = 0.45 at 427,187. Flat bottom from 0.05 to 0.45 |
| `replenishment.py` | Is refill worth handling separately? | Map reserve against pick aisles, measure overlap in refill dates between pairs | Of 20,000 pairs sampled from 79,800, only 2 reach a Jaccard of 0.5. Dropped this branch |

## Where the measurements favour their own conclusion

Writing these down, because without them the numbers above look firmer than they are.

- `affinity.py` uses raw counting as the reference it compares against, so counting
  **cannot lose**. The honest reading is "no need for a heavier model", not "Word2Vec
  is weak".
- The median hitting the optimum in `algorithm.py` follows from the L1 median theorem.
  It was predictable from theory. The measurement confirms it rather than discovers it.
- The two costs in `weights.py` are in different units, one per refill trip and one per
  pick order. Adding them is shaky. The real evidence is the exchange rate sweep:
  price a refill trip anywhere from 0.5x to 3x and the best w still sits between 0.30
  and 0.60.
- `algorithm.py` prints the trip count for each branch because the aisle branch
  (107,210 trips) and the item branch (88,196) have different denominators and cannot
  be compared directly.

## A branch kept even though it was wrong

`algorithm.py` still contains the step where the mean was tried and measured worse.
Deleting it would make the file shorter and remove the reason the median was chosen.
