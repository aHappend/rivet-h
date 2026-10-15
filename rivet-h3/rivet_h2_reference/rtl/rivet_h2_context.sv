module rivet_h2_context (
    input  wire         mode,
    input  wire         key_valid,
    input  wire [63:0]  count,
    input  wire [6:0]   used,
    input  wire [255:0] chain,
    input  wire [255:0] inner_seed,
    input  wire [255:0] outer_seed,
    input  wire [511:0] buffer_data,
    input  wire [1535:0] candidate,
    output wire [1535:0] encoded,
    output reg          candidate_valid
);
    localparam [255:0] IV = {
        32'h6a09e667, 32'hbb67ae85, 32'h3c6ef372, 32'ha54ff53a,
        32'h510e527f, 32'h9b05688c, 32'h1f83d9ab, 32'h5be0cd19
    };
    localparam [63:0] SHA_LIMIT = 64'h1fff_ffff_ffff_ffff;
    localparam [63:0] HMAC_LIMIT = 64'h1fff_ffff_ffff_ffbf;
    wire candidate_mode = candidate[40];
    wire candidate_key_valid = candidate[41];
    wire [63:0] candidate_count = candidate[111:48];
    wire [7:0] candidate_used = candidate[119:112];
    wire [255:0] candidate_chain = candidate[375:120];
    wire [255:0] candidate_inner = candidate[631:376];
    wire [255:0] candidate_outer = candidate[887:632];
    wire [511:0] candidate_buffer = candidate[1399:888];
    integer i;

    assign encoded = {
        136'd0, buffer_data, outer_seed, inner_seed, chain,
        1'b0, used, count, 6'd0, key_valid, mode, 8'd1, 32'h52485632
    };

    always @* begin
        candidate_valid = 1'b1;
        if ((candidate[31:0] != 32'h52485632) ||
            (candidate[39:32] != 8'd1) ||
            (candidate[47:42] != 6'd0) ||
            (candidate[1535:1400] != 136'd0))
            candidate_valid = 1'b0;
        if ((candidate_used > 8'd63) ||
            (candidate_used != {2'd0, candidate_count[5:0]}))
            candidate_valid = 1'b0;
        if (candidate_count > (candidate_mode ? HMAC_LIMIT : SHA_LIMIT))
            candidate_valid = 1'b0;
        if (candidate_mode && !candidate_key_valid)
            candidate_valid = 1'b0;
        if (!candidate_key_valid &&
            ((candidate_inner != 256'd0) || (candidate_outer != 256'd0)))
            candidate_valid = 1'b0;
        if ((candidate_count < 64'd64) &&
            (candidate_chain != (candidate_mode ? candidate_inner : IV)))
            candidate_valid = 1'b0;
        for (i = 0; i < 64; i = i + 1) begin
            if ((i >= candidate_used) &&
                (candidate_buffer[511 - i * 8 -: 8] != 8'd0))
                candidate_valid = 1'b0;
        end
    end
endmodule
