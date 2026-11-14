// Sample before NBA updates; previous transfers predict this edge's state.
module fifo_checks (
    input logic clk, rst_n, in_valid, in_ready, out_valid, out_ready,
    input logic [7:0] out_data, input logic [2:0] count, input int cycle
);
    bit past_valid = 0;
    logic prev_reset, prev_stall;
    logic [7:0] prev_data;
    int expected_count;
    always @(posedge clk) begin
        if (past_valid) begin
            if (!prev_reset) assert (count == 0)
                else $fatal(1, "reset occupancy expected=0 observed=%0d cycle=%0d", count, cycle);
            else if (rst_n) begin
                assert (int'(count) == expected_count)
                    else $fatal(1, "occupancy delta expected=%0d observed=%0d cycle=%0d", expected_count, count, cycle);
                if (prev_stall)
                    assert (out_valid && out_data == prev_data)
                        else $fatal(1, "stalled output changed cycle=%0d", cycle);
            end
        end
        if (rst_n) assert (count <= 4) else $fatal(1, "occupancy bounds cycle=%0d", cycle);
        expected_count = int'(count) + int'(in_valid && in_ready) - int'(out_valid && out_ready);
        prev_reset = rst_n;
        prev_stall = out_valid && !out_ready;
        prev_data = out_data;
        past_valid = 1;
    end
endmodule
