module rivet_h1_length (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        clear,
    input  wire        accept,
    input  wire [2:0]  beat_bytes,
    output reg  [63:0] byte_count,
    output wire [63:0] next_byte_count,
    output wire        overflow
);
    wire [64:0] proposed_count = {1'b0, byte_count} +
                                {{62{1'b0}}, beat_bytes};
    assign next_byte_count = proposed_count[63:0];
    assign overflow = proposed_count > 65'h01fff_ffff_ffff_ffff;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            byte_count <= 64'd0;
        else if (clear)
            byte_count <= 64'd0;
        else if (accept && !overflow)
            byte_count <= next_byte_count;
    end
endmodule
