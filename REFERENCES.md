# References

Working bibliography for the Portland Traffic ABM. These are the references
Christof sent (Jun 15, 2026), annotated with the role each one plays in the
project. Keep this current as you read. A clean, complete bibliography is part of
doing the work credibly, and it makes the final chapter's reference list one step
away.

Tip: also track these in a reference manager (Christof recommended Zotero or
Mendeley) so citations and the bibliography stay in sync as you write.

## The baseline and its lineage

[1] Rao, M., et al. (2017). Assessing the potential of land use modification to
mitigate ambient NO2 and its consequences for respiratory health. International
Journal of Environmental Research and Public Health, 14(7), 750.
- Role: THE baseline. Rao's land-use-fed random forest is what the agent-fed
  random forest is compared against. Read first. Also the natural choice for the
  Jun 23 key-paper presentation.

[4] Hoek, G., et al. (2008). A review of land-use regression models to assess
spatial variation of outdoor air pollution. Atmospheric Environment, 42(33),
7561-7578.
- Role: background on land-use regression (LUR), the family of statistical methods
  Rao belongs to. Read for "how it is done today" (Heilmeier question 2).

[2] Michanowicz, D. R., et al. (2016). A hybrid land use regression/line-source
dispersion model for predicting intra-urban NO2. Transportation Research Part D:
Transport and Environment.
- Role: a hybrid that adds a road/line-source term to LUR. Useful for choosing
  which predictors to feed the forest, and a midpoint between pure statistics and
  the source-based modeling the ABM pushes further.

## Methods rigor

[3] Roberts, D. R., Bahn, V., Ciuti, S., et al. (2017). Cross-validation
strategies for data with temporal, spatial, hierarchical, or phylogenetic
structure. Ecography, 40(8), 913-929. doi:10.1111/ecog.02881
- Role: how to validate fairly on spatial data. Naive cross-validation lets nearby
  points leak between train and test sets and inflates accuracy. Spatial
  cross-validation prevents fooling yourself. This is what keeps the
  model-to-model comparison honest, so it matters directly for the NO2 path in
  weeks 6 to 7.

## The noise comparison (week 8)

[5] Bozigar, M., Mowrer, C., Larkin, A., Hystad, P., et al. (2025). Systematic
measurement and machine learning-based profile characterization of community
noise in a medium-large city in the United States. Journal of Exposure Science
and Environmental Epidemiology. doi:10.1038/s41370-025-00794-y
- Role: the noise analog of the Rao baseline. Real Class 1 sound measurements
  across Portland feed a machine-learning noise surface (DNL, Lden, L10). The
  ABM's mechanistic noise surface is compared against this statistical one, the
  same model-to-model setup Rao gives for NO2. Part one of two; the citywide 10 m
  gridded surface is in a forthcoming second paper (Multnomah County is building
  an interactive map from it). Read at the week-8 noise layer. Found Jun 23.

## Why model-to-model (the sparse-monitoring justification)

[6] Oregon Department of Environmental Quality (2023). 2023 Oregon Annual Ambient
Criteria Pollutant Air Monitoring Network Plan. Submitted to EPA Region 10, July 1, 2023.
- Role: primary-source evidence for the model-to-model framing. Documents that the entire
  Portland-Vancouver-Hillsboro metro (2.5M people) runs only two regulatory NO2 monitors:
  a community / NCore site at SE Lafayette (AQS 41-051-0080, 45.4966, -122.6029) and one
  freeway near-road site (AQS 41-067-0005, I-5 at MP 290.14, AADT 153,822, 27 m from the
  road), with the planned second near-road site deferred as low priority because the
  existing one reads "well below the NAAQS." Neither monitor is on Powell. This is the
  citable proof that Portland lacks the dense NO2 sensor data a surface would need to be
  validated against, so the comparison is model-to-model, not measurement validation. The
  nearest monitor (SE Lafayette) is at most a single-point magnitude sanity check, never
  the spine. Found Jun 26. Note: this is a network PLAN (locations and siting rules), not
  measured concentrations; pull the latter from EPA AQS by site ID if needed. See
  DATASETS.md section 6.

## Methods the project uses (citations to add as they are pulled in)

- HBEFA emission factors (per-vehicle NO2).
- CNOSSOS-EU (mechanistic road noise).
- FHWA Traffic Noise Model (noise reference baseline).
