module fifo (
    input logic clk, rst_n,
    input logic in_valid, output logic in_ready, input logic [7:0] in_data,
    output logic out_valid, input logic out_ready, output logic [7:0] out_data
);
    logic [7:0] mem [0:3];
    logic [1:0] rd, wr;
    logic [2:0] count;
    logic push, pop;
    assign out_valid = count != 0;
    assign in_ready = count < 4 || (out_valid && out_ready);
    assign out_data = mem[rd];
    assign push = in_valid && in_ready;
    assign pop = out_valid && out_ready;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rd <= 0;
            wr <= 0;
            count <= 0;
        end else begin
            if (push) begin
                mem[wr] <= in_data;
                wr <= wr + 2'd1;
            end
            if (pop) rd <= rd + 2'd1;
            case ({push, pop})
                2'b10: count <= count + 3'd1;
                2'b01: count <= count - 3'd1;
                default: count <= count;
            endcase
        end
    end
endmodule
