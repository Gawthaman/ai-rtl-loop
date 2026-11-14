# Four-entry streaming FIFO

Eight-bit data, depth four, one clock, register storage. Reset is synchronous,
active low: a rising edge with rst_n=0 flushes all queued data. Checks apply
outside reset. No empty bypass. Transfers occur at rising edges when valid and
ready are both high. Every accepted input returns once, in order, unless reset.

For independent reference occupancy N before an edge:

- out_valid = N > 0
- output_transfer = (N > 0) && out_ready
- in_ready = (N < 4) || output_transfer
- next occupancy = N + input_transfer - output_transfer

A full FIFO must accept replacement input while transferring output. A stalled
output keeps valid and data stable until transfer or reset. Sources hold valid
and data while waiting; consumers may change readiness freely. A final drain
finishes pending source work, withdraws input, holds out_ready=1, and requires
empty within eight cycles.

Acceptance requires compilation, assertions, original reproduction, directed
scenarios and random seeds 1, 7, 42, bounded drains, and all seven named coverage
bins in every full suite. Coverage is scenario evidence, not correctness.

Drive at falling edges; sample transfers at rising edges before NBA updates,
then update the independent queue (pop before push).
Assertions sample pre-NBA state at rising edges and compare it to prior transfers.
A short reset pulse between rising edges must preserve queued data; a reset
sampled low at a rising edge must flush it.
Pointer wrap coverage counts every fourth observed accepted transfer, independent
of the DUT pointers, with transfer counts restarted on reset. Ordered data checks
detect incorrect wrap behavior. Trace coverage records completed preceding cycles;
the completion marker includes the final cycle.

Repair proposals may change fifo.sv only. Checkers are hashed; each candidate
gets a fresh build/report directory. Failures, timeouts and missing completion
markers reject. Stop after three repair proposals or a failed patch command.
The focused assertions observe the three-bit internal count, which repairs must
preserve. Qualification requires each of the five fixed mutants to compile and
fail an executable check; tool failures do not qualify as fault detection.
Qualification is separate from functional coverage. No formal proof or model
convergence is claimed.
