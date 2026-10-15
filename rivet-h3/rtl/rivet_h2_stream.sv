module rivet_h2_stream (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         clear,
    input  wire         load,
    input  wire         release_block,
    input  wire         capture,
    input  wire         drain,
    input  wire [511:0] load_buffer,
    input  wire [6:0]   load_used,
    input  wire [31:0]  beat_data,
    input  wire [2:0]   beat_bytes,
    input  wire         beat_last,
    output reg  [511:0] block_data,
    output reg  [6:0]   used_bytes,
    output reg          staged,
    output wire         byte_fire,
    output wire [7:0]   byte_data,
    output wire         beat_end,
    output wire         last_pending
);
    reg [31:0] stage_data;
    reg [2:0] remaining;
    reg stage_last;

    assign byte_fire = drain && staged && (used_bytes < 7'd64) &&
                       (remaining != 3'd0);
    assign byte_data = stage_data[31:24];
    assign beat_end = drain && staged && (used_bytes < 7'd64) &&
                      (remaining <= 3'd1);
    assign last_pending = stage_last;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            block_data <= 512'd0;
            used_bytes <= 7'd0;
            staged <= 1'b0;
            stage_data <= 32'd0;
            remaining <= 3'd0;
            stage_last <= 1'b0;
        end else if (clear) begin
            block_data <= 512'd0;
            used_bytes <= 7'd0;
            staged <= 1'b0;
            stage_data <= 32'd0;
            remaining <= 3'd0;
            stage_last <= 1'b0;
        end else if (load) begin
            block_data <= load_buffer;
            used_bytes <= load_used;
            staged <= 1'b0;
            stage_data <= 32'd0;
            remaining <= 3'd0;
            stage_last <= 1'b0;
        end else begin
            if (release_block) begin
                block_data <= 512'd0;
                used_bytes <= 7'd0;
            end else if (byte_fire) begin
                block_data[511 - used_bytes * 8 -: 8] <= byte_data;
                used_bytes <= used_bytes + 7'd1;
            end
            if (capture) begin
                stage_data <= beat_data;
                remaining <= beat_bytes;
                stage_last <= beat_last;
                staged <= 1'b1;
            end else if (drain && staged && (used_bytes < 7'd64)) begin
                if (remaining != 3'd0) begin
                    stage_data <= {stage_data[23:0], 8'd0};
                    remaining <= remaining - 3'd1;
                end
                if (remaining <= 3'd1) begin
                    staged <= 1'b0;
                    stage_last <= 1'b0;
                    stage_data <= 32'd0;
                end
            end
        end
    end
endmodule
