# Minimal RTL repair gate

Requires Python 3, Verilator 5.054 and a C++20 toolchain on macOS or Linux.

```sh
python3 run.py                 # correct FIFO
python3 run.py --demo          # baseline plus five hand-written fault fixtures
python3 run.py fixtures/count_bug.sv
python3 -m unittest -v         # acceptance gate and failure handling
```

`reports/attempt-*/` preserves candidate RTL, diff, tool version, checker hashes,
compile/run logs, sampled traces, VCDs and structured verdicts. `qualification.json`
links the six qualification results. A mutant must compile and fail a behavioral
check to qualify; a tool failure is inconclusive. Each full-suite seed must hit all required
bins. The bad repair intentionally passes the weaker reproduction while failing
input readiness in the full suite.

To connect a model, supply a local command that reads a JSON prompt from stdin
and writes only complete FIFO RTL to stdout:

```sh
python3 run.py fixtures/count_bug.sv --repair-command 'your-model-adapter'
```

The runner verifies the initial candidate and up to three repairs, saving each
prompt, response and command status, including failures. The adapter handles
model authentication and API access. Only use trusted
adapters: external commands are not sandboxed. Accepted RTL remains in the report
folder for review; the runner does not overwrite the baseline.

The testbench covers reset/empty, single item, fill, drain, partial/full
simultaneous transfers, wraps, stalls, queued reset, sustained traffic and seeded
random traffic. Immediate clocked assertions check occupancy bounds/deltas,
synchronous reset (including a pulse between clock edges) and stalled output.
The source holds pending input until acceptance or reset. The queue and interface equations do not
read the DUT counter. Optional formal verification, UVM and a UI are omitted.

Validated locally with Verilator 5.054: baseline accepted, all seven coverage bins
hit for each pinned seed, and all five manual mutants rejected. The bad repair
passes reproduction and fails the readiness contract. The external patch command
interface was smoke-tested with a manual adapter; no live model call was made.
