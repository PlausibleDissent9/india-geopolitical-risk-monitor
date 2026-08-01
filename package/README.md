# igrm

Python client for the [India Geopolitical Risk Monitor](https://plausibledissent9.github.io/india-geopolitical-risk-monitor/) open datasets: a daily, category-decomposed press-salience index for India (2017-present) with events, chokepoint, gauge, and comparator layers.

The instrument measures press salience (attention), never risk. Every function returns pandas objects fetched from the published payloads; every number is traceable to raw inputs via the [codebook](https://plausibledissent9.github.io/india-geopolitical-risk-monitor/codebook.html).

```python
import igrm

df = igrm.history()        # daily channel + composite percentiles
ev = igrm.events()         # daily India event counts (GDELT Events v1)
sg = igrm.stress_gauge()   # the pre-registered fused gauge
cp = igrm.chokepoints()    # corridor salience vs PortWatch transits
cm = igrm.comparators()    # four-country comparator percentiles
```

Data license: CC BY 4.0. Cite as:

> Krishna, Ishan (2026). India Geopolitical Risk Monitor. https://plausibledissent9.github.io/india-geopolitical-risk-monitor/
