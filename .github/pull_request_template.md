## Summary

<!-- What does this PR do? One paragraph. -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (existing behaviour changes)
- [ ] Refactor (no behaviour change)
- [ ] Documentation / tests only

## Changes

<!-- List the files changed and why. -->

-
-

## Testing

<!-- How was this tested? Which test files cover this change? -->

- [ ] `pytest tests/ --fast` — all unit tests pass
- [ ] `pytest tests/` — full suite including integration tests passes
- [ ] New tests added for new code paths
- [ ] Coverage gate still passes (`pytest --cov`)

## Checklist

- [ ] `make lint` passes (ruff)
- [ ] `make format-check` passes (black)
- [ ] Docstrings updated for changed functions
- [ ] No hardcoded paths, credentials, or secrets introduced
- [ ] `docker build -f docker/Dockerfile .` succeeds locally (if Dockerfile changed)

## Related issues

Closes #
