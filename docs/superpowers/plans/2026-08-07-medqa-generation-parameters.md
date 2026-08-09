# MedQA Generation Parameters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MedQA generation parameters configurable so reasoning models can receive enough output budget while preserving the existing evals interfaces.

**Architecture:** Add `temperature` and `max_tokens` constructor parameters to `MedQAEval`, with defaults suitable for reasoning models. Expose those defaults through the medical MedQA Registry entry; existing CLI `--extra_eval_params` remains the override path. Keep response parsing, Recorder ownership, and evals core unchanged.

**Tech Stack:** Python, pytest, YAML Registry, OpenAI-compatible CompletionFn.

## Global Constraints

- Do not modify `evals/` core logic.
- Do not change the MedQA dataset or add dependencies.
- Do not call a real model from tests.
- Preserve sampling ownership in the Adapter and match ownership in `MedQAEval`.

### Task 1: Define configurable MedQA request behavior with tests

**Files:**
- Modify: `tests/medical_evals/test_medqa_eval.py`
- Modify: `medical_evals/evals/medqa.py`
- Modify: `evals/registry/evals/medical_medqa.yaml`
- Modify: `tests/integration/test_medqa_pipeline.py`

**Interfaces:**
- `MedQAEval(..., temperature: float = 0.1, max_tokens: int = 2048)` stores the values and passes them to `completion_fn` for every sample.
- Registry defaults use `temperature: 0.1` and `max_tokens: 2048`.
- CLI `--extra_eval_params temperature=...,max_tokens=...` overrides Registry values through the existing evals runner.

- [x] **Step 1: Write the failing test**

Add a test completion function that records kwargs, construct `MedQAEval` with `temperature=0.2, max_tokens=512`, run one sample, and assert those exact values were passed. Add Registry assertions for the two defaults.

- [x] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
OPENAI_API_KEY=dummy python -m pytest -q tests/medical_evals/test_medqa_eval.py tests/integration/test_medqa_pipeline.py
```

Expected failure: `MedQAEval` does not accept or forward the new parameters and the Registry args do not contain them.

- [x] **Step 3: Implement the minimal behavior**

Add the two keyword parameters to `MedQAEval.__init__`, call `super().__init__`, save them, and replace the hard-coded completion call with:

```python
result = self.completion_fn(
    prompt=prompt,
    temperature=self.temperature,
    max_tokens=self.max_tokens,
)
```

Add the two defaults to `medical_medqa.yaml`.

- [x] **Step 4: Run focused tests and verify they pass**

Run the focused pytest command above; expected result is all passing.

### Task 2: Verify reasoning-style parsing and full regression

**Files:**
- Modify: `tests/medical_evals/test_choice_parser.py`
- Modify: `tests/adapters/test_openai_compatible.py` only if a response-shape regression is exposed.

**Interfaces:**
- `parse_choice("<think>... </think>\nC")` returns `"C"`.
- Adapter continues to return normal `message.content` and records one sampling event.

- [x] **Step 1: Add the reasoning-output regression test**

Add a parser case containing a reasoning block followed by a final option letter; keep the expected result `C`.

- [x] **Step 2: Run parser tests and verify the behavior**

Run:

```bash
OPENAI_API_KEY=dummy python -m pytest -q tests/medical_evals/test_choice_parser.py
```

- [x] **Step 3: Run the complete test suite**

Run:

```bash
OPENAI_API_KEY=dummy python -m pytest -q tests tests/unit/evals
```

Expected result: all existing tests pass.

### Task 3: Smoke-test command handoff

**Files:**
- Modify: `README.md` only if the documented command still shows the old fixed-parameter behavior.

- [x] **Step 1: Verify the CLI override syntax**

Use `--extra_eval_params temperature=0.2,max_tokens=512` with the existing `--no-sync` source-mode command and confirm the run starts without changing the Registry file.

- [x] **Step 2: Report the real-model rerun command**

The rerun should use a valid MiniMax key and the configured environment; do not execute a real API call as part of automated tests.
