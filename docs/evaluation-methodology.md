# Evaluation methodology

The reviewer separates two different validation questions:

1. **Regression stability:** do known repository shapes keep their intended
   deterministic outputs after a code change?
2. **External validity:** do independent human labels agree with the reviewer's
   repository type, rubric fit and individual findings on repositories that did
   not guide the rules?

The frozen benchmark suite answers the first question. It does not answer the
second. The `portfolio-evaluate` command provides the measurement plumbing for
the second without claiming that the project author is an independent labeler.

## Observation schema

Each JSON case records a repository name plus an `expected` human label and an
`observed` reviewer result. Kind values are `Software project`, `Monorepo`,
`Educational or content repository`, or `Unknown repository type`. Fit values
are `High`, `Medium`, or `Low`.

```json
{
  "name": "example/project",
  "expected": {"kind": "Software project", "fit": "High"},
  "observed": {"kind": "Software project", "fit": "High"}
}
```

Run the supplied baseline:

```bash
portfolio-evaluate evaluation/high-star-fairness.json
```

The baseline transcribes the curated fairness observations already documented
by the author. Its perfect agreement is a regression record, **not an independent
accuracy estimate**.

## Independent evaluation protocol

1. Freeze a ruleset before selecting evaluation repositories.
2. Sample repositories across languages, popularity levels and intended uses.
3. Ask at least two reviewers who did not write the rules to label repository
   type and rubric fit from a written guide, without seeing the app's result.
4. Resolve human disagreements or report inter-rater agreement.
5. Review every repository at one recorded commit and save the observed labels.
6. Run `portfolio-evaluate` and report accuracy and the complete confusion
   tables, including failures.
7. Keep the evaluation set separate from fixtures used to change the rules.

Future versions should extend the schema to finding-level precision and recall.
No accuracy claim should be published until independent labels are available.
