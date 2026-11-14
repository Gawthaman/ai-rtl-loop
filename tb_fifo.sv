module tb_fifo;
    logic clk = 0, rst_n = 0, in_valid = 0, out_ready = 0;
    logic in_ready, out_valid;
    logic [7:0] in_data = 0, out_data;
    fifo dut (.*);
    fifo_checks checks (.*, .count(dut.count));
    byte unsigned expected[$];
    bit repro, pending = 0;
    byte unsigned pending_data, discarded;
    int cycle = 0, seed = 1, rng, unused, pushes = 0, pops = 0, stalls = 0;
    bit [6:0] coverage = 0;
    string wave;
    always #5 clk = !clk;

    // Drive at falling edges; sample transfers at rising edges before NBA updates.
    // A pending source item stays valid and stable until accepted or reset.
    task automatic step(input bit reset_n, offer, ready, input byte unsigned data,
                        input bit reset_pulse = 0);
        int n;
        bit push, pop;
        @(negedge clk);
        rst_n = reset_n;
        in_valid = reset_n && (offer || pending);
        in_data = reset_n && pending ? pending_data : data;
        out_ready = ready;
        // A reset pulse with no rising edge must not flush a synchronous FIFO.
        if (reset_pulse) begin
            rst_n = 0;
            #1;
            rst_n = 1;
        end
        @(posedge clk);
        n = expected.size();
        push = in_valid && in_ready;
        pop = out_valid && out_ready;
        $display("TRACE cycle=%0d reset=%0b iv=%0b ir=%0b id=%0d ov=%0b or=%0b od=%0d expected_n=%0d coverage=%0d", cycle, rst_n, in_valid, in_ready, in_data, out_valid, out_ready, out_data, n, coverage);
        if (!rst_n) begin
            if (n > 0) coverage[6] = 1;
            expected.delete();
            pending = 0;
            stalls = 0;
            pushes = 0;
            pops = 0;
        end else begin
            if (!repro) begin
                if (out_valid != (n > 0))
                    $fatal(1, "out_valid expected=%0b observed=%0b cycle=%0d", n > 0, out_valid, cycle);
                if (in_ready != ((n < 4) || ((n > 0) && ready)))
                    $fatal(1, "in_ready expected=%0b observed=%0b cycle=%0d: space or output transfer requires readiness", (n < 4) || ((n > 0) && ready), in_ready, cycle);
            end
            if (pop) begin
                if (n == 0) $fatal(1, "unexpected output cycle=%0d", cycle);
                if (out_data != expected[0])
                    $fatal(1, "data expected=%0d observed=%0d cycle=%0d", expected[0], out_data, cycle);
                discarded = expected.pop_front();
                pops++;
            end
            if (push) begin
                expected.push_back(in_data);
                pushes++;
            end
            if (n == 0 && push) coverage[0] = 1;
            if (expected.size() == 4) coverage[1] = 1;
            if (n == 4 && push && pop) coverage[2] = 1;
            if (n > 0 && n < 4 && push && pop) coverage[3] = 1;
            if ((push && pushes % 4 == 0) || (pop && pops % 4 == 0)) coverage[4] = 1;
            stalls = out_valid && !ready ? stalls + 1 : 0;
            if (stalls >= 2) coverage[5] = 1;
            pending = in_valid && !in_ready;
            pending_data = in_data;
        end
        #1;
        cycle++;
    endtask

    task automatic drain;
        // Finish any stalled source item before withdrawing valid.
        for (int budget = 0; pending && budget < 8; budget++)
            step(1, 1, 1, pending_data);
        if (pending) $fatal(1, "pending source did not complete cycle=%0d", cycle - 1);
        repeat (8) step(1, 0, 1, 0);
        if (expected.size() != 0 || out_valid) $fatal(1, "bounded drain incomplete cycle=%0d", cycle - 1);
    endtask

    initial begin
        unused = $value$plusargs("seed=%d", seed);
        rng = seed;
        unused = $urandom(rng);
        repro = $test$plusargs("repro");
        if (!$value$plusargs("wave=%s", wave)) wave = "wave.vcd";
        $dumpfile(wave);
        $dumpvars(0, tb_fifo);
        step(0, 0, 0, 0);
        step(1, 0, 1, 0);
        step(1, 1, 0, 8'h11);
        step(1, 0, 1, 0);
        drain();
        // Partial simultaneous transfers reproduce the seeded occupancy fault.
        step(1, 1, 0, 1);
        step(1, 1, 0, 2);
        for (int i = 0; i < 12; i++) step(1, 1, 1, 8'(i + 3));
        drain();
        if (!repro) begin
            for (int i = 0; i < 4; i++) step(1, 1, 0, 8'(i));
            repeat (3) step(1, 0, 0, 0);
            // Full replacement plus sustained one-transfer-per-cycle traffic.
            for (int i = 0; i < 16; i++) step(1, 1, 1, 8'(i + 20));
            drain();
            step(1, 1, 0, 42);
            step(1, 0, 0, 0, 1);
            step(0, 0, 0, 0);
            step(1, 0, 1, 0);
            repeat (200) begin
                step(1, 1'($urandom_range(0, 1)), 1'($urandom_range(0, 1)), 8'($urandom));
            end
            drain();
        end
        $display("RESULT pass=1 coverage=%0d seed=%0d cycles=%0d", coverage, seed, cycle);
        $finish;
    end
endmodule
