module rivet_h1_pad (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         clear,
    input  wire         append,
    input  wire [31:0]  beat_data,
    input  wire [2:0]   beat_bytes,
    input  wire         prepare,
    input  wire         final_block,
    input  wire         prepare_second,
    input  wire         release_block,
    input  wire [63:0]  bit_length,
    output reg  [511:0] block_data,
    output reg  [6:0]   used_bytes,
    output reg          needs_second
);
    reg second_marker;
    integer lane;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            block_data <= 512'd0;
            used_bytes <= 7'd0;
            needs_second <= 1'b0;
            second_marker <= 1'b0;
        end else if (clear || release_block) begin
            block_data <= 512'd0;
            used_bytes <= 7'd0;
            needs_second <= 1'b0;
            second_marker <= 1'b0;
        end else if (prepare_second) begin
            block_data <= {8'h00, 440'd0, bit_length} |
                          (second_marker ? {8'h80, 504'd0} : 512'd0);
            used_bytes <= 7'd0;
            needs_second <= 1'b0;
            second_marker <= 1'b0;
        end else if (prepare) begin
            needs_second <= 1'b0;
            second_marker <= 1'b0;
            if (final_block) begin
                if (used_bytes == 7'd64) begin
                    needs_second <= 1'b1;
                    second_marker <= 1'b1;
                end else begin
                    block_data[511 - used_bytes * 8 -: 8] <= 8'h80;
                    if (used_bytes <= 7'd55)
                        block_data[63:0] <= bit_length;
                    else
                        needs_second <= 1'b1;
                end
            end
        end else if (append) begin
            for (lane = 0; lane < 4; lane = lane + 1) begin
                if (lane < beat_bytes)
                    block_data[511 - (used_bytes + lane) * 8 -: 8] <=
                        beat_data[31 - lane * 8 -: 8];
            end
            used_bytes <= used_bytes + {4'd0, beat_bytes};
        end
    end
endmodule
